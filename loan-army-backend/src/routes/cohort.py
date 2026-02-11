"""Cohort API endpoints.

Handles:
- Admin cohort seeding and management
- Public cohort browsing and analytics
"""
from flask import Blueprint, request, jsonify, copy_current_request_context
from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney
from src.routes.api import require_api_key
from src.services.cohort_service import CohortService
from src.utils.background_jobs import create_background_job, update_job, get_job
from datetime import datetime, timezone
import threading
import logging

cohort_bp = Blueprint('cohort', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Admin Endpoints
# =============================================================================

@cohort_bp.route('/admin/cohorts/seed', methods=['POST'])
@require_api_key
def admin_seed_cohort():
    """Seed a single cohort.

    Body: {team_api_id, league_api_id, season}
    """
    data = request.get_json() or {}

    team_api_id = data.get('team_api_id')
    league_api_id = data.get('league_api_id')
    season = data.get('season')

    if not all([team_api_id, league_api_id, season]):
        return jsonify({'error': 'team_api_id, league_api_id, and season are required'}), 400

    try:
        # Clear stale cache that may contain empty API responses
        from src.models.api_cache import APICache
        for page in range(1, 11):
            APICache.invalidate_cached('players', {
                'team': int(team_api_id), 'league': int(league_api_id),
                'season': int(season), 'page': page,
            })

        service = CohortService()
        cohort = service.discover_cohort(int(team_api_id), int(league_api_id), int(season))
        return jsonify(cohort.to_dict(include_members=True)), 201
    except Exception as e:
        logger.exception('admin_seed_cohort failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/seed-big6', methods=['POST'])
@require_api_key
def admin_seed_big6():
    """Start Big 6 bulk seeding as a background job.

    Body (all optional): {seasons: [], team_ids: [], league_ids: []}
    """
    from src.services.big6_seeding_service import run_big6_seed

    data = request.get_json() or {}
    seasons = data.get('seasons')
    team_ids = data.get('team_ids')
    league_ids = data.get('league_ids')

    job_id = create_background_job('seed_big6')

    @copy_current_request_context
    def run_in_background():
        try:
            result = run_big6_seed(job_id, seasons=seasons, team_ids=team_ids, league_ids=league_ids)
            update_job(job_id, status='completed', results=result,
                       completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.exception(f'Big 6 seed job {job_id} failed')
            db.session.rollback()
            update_job(job_id, status='failed', error=str(e),
                       completed_at=datetime.now(timezone.utc).isoformat())

    thread = threading.Thread(target=run_in_background)
    thread.start()

    return jsonify({
        'message': 'Big 6 seeding started in background',
        'job_id': job_id,
        'status': 'running',
        'check_status_url': f'/api/admin/jobs/{job_id}'
    }), 202


@cohort_bp.route('/admin/cohorts/<int:cohort_id>/sync-journeys', methods=['POST'])
@require_api_key
def admin_sync_cohort_journeys(cohort_id):
    """Trigger journey sync for all members in a cohort."""
    try:
        service = CohortService()
        cohort = service.sync_cohort_journeys(cohort_id)
        return jsonify(cohort.to_dict(include_members=True))
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.exception('admin_sync_cohort_journeys failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/<int:cohort_id>/refresh-stats', methods=['POST'])
@require_api_key
def admin_refresh_cohort_stats(cohort_id):
    """Recalculate denormalized analytics for a cohort."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    try:
        service = CohortService()
        service.refresh_cohort_stats(cohort_id)
        return jsonify(cohort.to_dict())
    except Exception as e:
        logger.exception('admin_refresh_cohort_stats failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/seed-status', methods=['GET'])
@require_api_key
def admin_cohort_seed_status():
    """List all cohorts with sync status."""
    cohorts = AcademyCohort.query.order_by(
        AcademyCohort.season.desc(),
        AcademyCohort.team_name
    ).all()
    return jsonify({
        'cohorts': [c.to_dict() for c in cohorts],
        'total': len(cohorts),
    })


@cohort_bp.route('/admin/cohorts/<int:cohort_id>', methods=['DELETE'])
@require_api_key
def admin_delete_cohort(cohort_id):
    """Delete a cohort and all its members."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    db.session.delete(cohort)
    db.session.commit()
    return '', 204


@cohort_bp.route('/admin/cohorts/re-derive-statuses', methods=['POST'])
@require_api_key
def admin_re_derive_statuses():
    """Re-derive current_status for all synced cohort members.

    Fixes data produced by the bug where _derive_status was called
    without parent club context. Iterates all members with
    journey_synced=True, re-runs status derivation with the correct
    parent club from their cohort, then refreshes aggregate stats.

    Body (optional): {cohort_ids: [1, 2, 3]}
    """
    data = request.get_json() or {}
    target_cohort_ids = data.get('cohort_ids')

    service = CohortService()
    current_year = datetime.now().year

    query = CohortMember.query.filter(CohortMember.journey_synced == True)
    if target_cohort_ids:
        query = query.filter(CohortMember.cohort_id.in_(target_cohort_ids))

    members = query.all()
    updated = 0
    errors = []

    for member in members:
        try:
            if not member.journey_id:
                continue

            journey = db.session.get(PlayerJourney, member.journey_id)
            if not journey:
                continue

            cohort = db.session.get(AcademyCohort, member.cohort_id)
            if not cohort:
                continue

            new_status = CohortService._derive_status(
                journey, current_year,
                parent_api_id=cohort.team_api_id,
                parent_club_name=cohort.team_name or '',
            )

            if member.current_status != new_status:
                member.current_status = new_status
                updated += 1

        except Exception as e:
            errors.append(f"Player {member.player_api_id}: {e}")

    db.session.commit()

    # Refresh stats for affected cohorts
    affected_cohort_ids = target_cohort_ids or list(set(m.cohort_id for m in members))
    for cid in affected_cohort_ids:
        service.refresh_cohort_stats(cid)

    return jsonify({
        'members_checked': len(members),
        'statuses_updated': updated,
        'cohorts_refreshed': len(affected_cohort_ids),
        'errors': errors[:20],
    })


# =============================================================================
# Public Endpoints
# =============================================================================

@cohort_bp.route('/cohorts', methods=['GET'])
def list_cohorts():
    """List cohorts with optional filters.

    Query params: team_api_id, season, league_api_id
    """
    query = AcademyCohort.query

    team_api_id = request.args.get('team_api_id', type=int)
    if team_api_id:
        query = query.filter_by(team_api_id=team_api_id)

    season = request.args.get('season', type=int)
    if season:
        query = query.filter_by(season=season)

    league_api_id = request.args.get('league_api_id', type=int)
    if league_api_id:
        query = query.filter_by(league_api_id=league_api_id)

    cohorts = query.order_by(AcademyCohort.season.desc(), AcademyCohort.team_name).all()

    return jsonify({
        'cohorts': [c.to_dict() for c in cohorts],
        'total': len(cohorts),
    })


@cohort_bp.route('/cohorts/<int:cohort_id>', methods=['GET'])
def get_cohort(cohort_id):
    """Get a single cohort, optionally with members."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    include_members = request.args.get('include_members', 'false').lower() == 'true'
    return jsonify(cohort.to_dict(include_members=include_members))


@cohort_bp.route('/cohorts/teams', methods=['GET'])
def cohort_teams():
    """Get distinct teams that have cohort data."""
    from src.models.league import TeamProfile

    results = db.session.query(
        AcademyCohort.team_api_id,
        db.func.max(AcademyCohort.team_name).label('team_name'),
    ).filter(
        AcademyCohort.total_players > 0,
    ).group_by(AcademyCohort.team_api_id).order_by(
        db.func.max(AcademyCohort.team_name)
    ).all()

    # Resolve correct parent club logos from TeamProfile
    team_ids = [r.team_api_id for r in results]
    profiles = {p.team_id: p.logo_url for p in
                TeamProfile.query.filter(TeamProfile.team_id.in_(team_ids)).all()}

    teams = [{
        'team_api_id': r.team_api_id,
        'team_name': r.team_name,
        'team_logo': profiles.get(r.team_api_id),
    } for r in results]

    return jsonify({'teams': teams})


@cohort_bp.route('/cohorts/analytics', methods=['GET'])
def cohort_analytics():
    """Cross-club comparison analytics."""
    from src.models.league import TeamProfile

    cohorts = AcademyCohort.query.filter(
        AcademyCohort.sync_status.in_(('complete', 'partial', 'seeded')),
        AcademyCohort.total_players > 0,
    ).all()

    # Build logo lookup from TeamProfile
    team_ids = list(set(c.team_api_id for c in cohorts))
    profiles = {p.team_id: p.logo_url for p in
                TeamProfile.query.filter(TeamProfile.team_id.in_(team_ids)).all()}

    # Group by team
    team_data = {}
    for c in cohorts:
        tid = c.team_api_id
        if tid not in team_data:
            team_data[tid] = {
                'team_api_id': tid,
                'team_name': c.team_name,
                'team_logo': profiles.get(tid),
                'total_players': 0,
                'players_first_team': 0,
                'players_on_loan': 0,
                'players_still_academy': 0,
                'players_released': 0,
                'cohort_count': 0,
                'seasons': [],
            }

        td = team_data[tid]
        td['total_players'] += c.total_players
        td['players_first_team'] += c.players_first_team
        td['players_on_loan'] += c.players_on_loan
        td['players_still_academy'] += c.players_still_academy
        td['players_released'] += c.players_released
        td['cohort_count'] += 1
        if c.season not in td['seasons']:
            td['seasons'].append(c.season)

    # Calculate conversion rates
    analytics = []
    for td in team_data.values():
        total = td['total_players']
        td['conversion_rate'] = round(td['players_first_team'] / total * 100, 1) if total > 0 else 0
        td['seasons'] = sorted(td['seasons'])
        analytics.append(td)

    analytics.sort(key=lambda x: x['conversion_rate'], reverse=True)

    return jsonify({'analytics': analytics})


# =============================================================================
# Full Academy Rebuild
# =============================================================================

@cohort_bp.route('/admin/academy/full-rebuild', methods=['POST'])
@require_api_key
def admin_full_rebuild():
    """Run the full academy rebuild pipeline as a background job.

    Stages:
      1. Clean slate (delete tracked players, journeys, cohorts, loans, locations)
      2. Seed academy leagues
      3. Cohort discovery + journey sync (Big 6 seeding)
      4. Create TrackedPlayer records for each team
      5. Link orphaned journeys
      6. Refresh statuses
      7. Seed club locations

    Body (all optional):
      team_ids: list of API team IDs (default: Big 6)
      seasons: list of season years (default: 2020-2024)
      skip_clean: bool (default: false)
      skip_cohorts: bool (default: false)
    """
    from src.models.league import Team, LoanedPlayer, AcademyLeague
    from src.models.tracked_player import TrackedPlayer
    from src.models.journey import PlayerJourney, PlayerJourneyEntry, ClubLocation
    from src.services.big6_seeding_service import run_big6_seed, BIG_6, SEASONS
    from src.services.youth_competition_resolver import build_academy_league_seed_rows
    from src.utils.academy_classifier import derive_player_status
    from src.api_football_client import APIFootballClient
    from src.services.journey_sync import JourneySyncService, seed_club_locations
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    data = request.get_json() or {}
    team_ids = data.get('team_ids') or list(BIG_6.keys())
    seasons = data.get('seasons') or SEASONS
    skip_clean = data.get('skip_clean', False)
    skip_cohorts = data.get('skip_cohorts', False)

    job_id = create_background_job('full_rebuild')

    @copy_current_request_context
    def run_in_background():
        stage = 'starting'
        try:
            total_stages = 7
            results = {
                'stages_completed': [],
                'teams': {},
                'errors': [],
            }

            # ── Stage 1: Clean slate ──
            if not skip_clean:
                stage = 'clean'
                update_job(job_id, progress=0, total=total_stages, current_player='Stage 1: Cleaning data...')
                deleted = {}
                for name, model in [
                    ('tracked_players', TrackedPlayer),
                    ('journey_entries', PlayerJourneyEntry),
                    ('cohort_members', CohortMember),
                    ('journeys', PlayerJourney),
                    ('cohorts', AcademyCohort),
                    ('loaned_players', LoanedPlayer),
                    ('club_locations', ClubLocation),
                ]:
                    count = model.query.count()
                    if count > 0:
                        model.query.delete()
                        db.session.commit()
                    deleted[name] = count
                # Also clear cached API responses so discovery gets fresh data
                from src.models.api_cache import APICache
                deleted['players_cache'] = APICache.invalidate_cached('players')
                results['deleted'] = deleted
                results['stages_completed'].append('clean')
            else:
                results['stages_completed'].append('clean (skipped)')

            # ── Stage 2: Seed academy leagues ──
            stage = 'seed_leagues'
            update_job(job_id, progress=1, total=total_stages, current_player='Stage 2: Seeding academy leagues...')
            api_client_for_leagues = APIFootballClient()
            youth_league_rows = build_academy_league_seed_rows(
                api_client=api_client_for_leagues,
                season=max(seasons),
            )
            leagues_created = 0
            leagues_updated = 0
            for ld in youth_league_rows:
                existing = AcademyLeague.query.filter_by(api_league_id=ld['api_league_id']).first()
                if not existing:
                    league = AcademyLeague(
                        api_league_id=ld['api_league_id'],
                        name=ld['name'],
                        country=ld['country'],
                        level=ld['level'],
                        season=ld.get('season'),
                        is_active=True,
                        sync_enabled=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.session.add(league)
                    leagues_created += 1
                else:
                    changed = False
                    if existing.name != ld['name']:
                        existing.name = ld['name']
                        changed = True
                    if existing.country != ld['country']:
                        existing.country = ld['country']
                        changed = True
                    if existing.level != ld['level']:
                        existing.level = ld['level']
                        changed = True
                    if ld.get('season') and existing.season != ld.get('season'):
                        existing.season = ld.get('season')
                        changed = True
                    if not existing.is_active:
                        existing.is_active = True
                        changed = True
                    if not existing.sync_enabled:
                        existing.sync_enabled = True
                        changed = True
                    if changed:
                        existing.updated_at = datetime.now(timezone.utc)
                        leagues_updated += 1
            if leagues_created or leagues_updated:
                db.session.commit()
            results['leagues_created'] = leagues_created
            results['leagues_updated'] = leagues_updated
            results['stages_completed'].append('seed_leagues')

            # ── Stage 3: Cohort discovery + journey sync ──
            if not skip_cohorts:
                stage = 'cohorts'
                update_job(job_id, progress=2, total=total_stages, current_player='Stage 3: Discovering cohorts + syncing journeys...')
                seed_result = run_big6_seed(job_id, seasons=seasons, team_ids=team_ids)
                results['cohorts_created'] = seed_result.get('cohorts_created', 0)
                results['players_synced'] = seed_result.get('players_synced', 0)
                results['stages_completed'].append('cohorts')
            else:
                results['stages_completed'].append('cohorts (skipped)')

            # ── Stage 4: Create TrackedPlayers ──
            stage = 'tracked_players'
            update_job(job_id, progress=4, total=total_stages, current_player='Stage 4: Creating TrackedPlayer records...')
            api_client = APIFootballClient()
            journey_svc = JourneySyncService(api_client)
            current_season = max(seasons)
            total_created = 0
            total_skipped = 0

            for api_team_id in team_ids:
                team_name = BIG_6.get(api_team_id, str(api_team_id))
                update_job(job_id, current_player=f'Stage 4: Seeding {team_name}...')

                team = Team.query.filter_by(team_id=api_team_id).order_by(Team.season.desc()).first()
                if not team:
                    results['errors'].append(f'{team_name}: no Team row found')
                    continue

                parent_api_id = team.team_id

                # Source 1: academy_club_ids
                known_journeys = PlayerJourney.query.filter(
                    PlayerJourney.academy_club_ids.contains(cast([parent_api_id], PG_JSONB))
                ).all()
                candidate_ids = {j.player_api_id: j for j in known_journeys}

                # Source 2: API squad (multiple seasons)
                squad_data = []
                seasons_to_fetch = range(current_season - 3, current_season + 1)
                for fetch_season in seasons_to_fetch:
                    try:
                        season_squad = api_client.get_team_players(parent_api_id, season=fetch_season)
                        for entry in season_squad:
                            player_info = (entry or {}).get('player') or {}
                            pid = player_info.get('id')
                            if pid:
                                pass  # just collecting data
                        squad_data.extend(season_squad)
                    except Exception as e:
                        logger.warning('Squad fetch failed for %s season %d: %s', team_name, fetch_season, e)

                # Sync journeys for squad players
                for entry in squad_data:
                    player_info = (entry or {}).get('player') or {}
                    pid = player_info.get('id')
                    if not pid:
                        continue
                    pid = int(pid)
                    if pid in candidate_ids:
                        continue
                    age = player_info.get('age')
                    if age and int(age) > 23:
                        continue
                    existing_journey = PlayerJourney.query.filter_by(player_api_id=pid).first()
                    if existing_journey:
                        if parent_api_id in (existing_journey.academy_club_ids or []):
                            candidate_ids[pid] = existing_journey
                        continue
                    try:
                        journey = journey_svc.sync_player(pid)
                        if journey and parent_api_id in (journey.academy_club_ids or []):
                            candidate_ids[pid] = journey
                    except Exception:
                        pass

                # Source 3: CohortMember records
                cohort_ids = [c.id for c in AcademyCohort.query.filter_by(team_api_id=parent_api_id).all()]
                if cohort_ids:
                    cohort_members = CohortMember.query.filter(CohortMember.cohort_id.in_(cohort_ids)).all()
                    for cm in cohort_members:
                        if cm.player_api_id and cm.player_api_id not in candidate_ids:
                            journey = PlayerJourney.query.filter_by(player_api_id=cm.player_api_id).first()
                            candidate_ids[cm.player_api_id] = journey

                # Build squad lookup
                squad_by_id = {}
                for entry in squad_data:
                    pi = (entry or {}).get('player') or {}
                    if pi.get('id'):
                        squad_by_id[int(pi['id'])] = entry

                # Create TrackedPlayer rows
                created = 0
                skipped = 0
                for pid, journey in candidate_ids.items():
                    try:
                        existing = TrackedPlayer.query.filter_by(player_api_id=pid, team_id=team.id).first()
                        if existing:
                            skipped += 1
                            continue

                        squad_entry = squad_by_id.get(pid) or {}
                        pi = squad_entry.get('player') or {}

                        player_name = (journey.player_name if journey else None) or pi.get('name') or f'Player {pid}'
                        photo_url = (journey.player_photo if journey else None) or pi.get('photo')
                        nationality = (journey.nationality if journey else None) or pi.get('nationality')
                        birth_date = (journey.birth_date if journey else None) or (pi.get('birth') or {}).get('date')
                        position = pi.get('position') or ''
                        age = pi.get('age')

                        status, loan_club_api_id, loan_club_name = derive_player_status(
                            current_club_api_id=journey.current_club_api_id if journey else None,
                            current_club_name=journey.current_club_name if journey else None,
                            current_level=journey.current_level if journey else None,
                            parent_api_id=parent_api_id,
                            parent_club_name=team.name,
                        )

                        current_level = journey.current_level if journey and journey.current_level else None

                        tp = TrackedPlayer(
                            player_api_id=pid,
                            player_name=player_name,
                            photo_url=photo_url,
                            position=position,
                            nationality=nationality,
                            birth_date=birth_date,
                            age=int(age) if age else None,
                            team_id=team.id,
                            status=status,
                            current_level=current_level,
                            loan_club_api_id=loan_club_api_id,
                            loan_club_name=loan_club_name,
                            data_source='api-football',
                            data_depth='full_stats',
                            journey_id=journey.id if journey else None,
                        )
                        db.session.add(tp)
                        created += 1
                    except Exception as entry_err:
                        results['errors'].append(f'{team_name} player {pid}: {entry_err}')

                db.session.commit()
                results['teams'][team_name] = {'created': created, 'skipped': skipped, 'candidates': len(candidate_ids)}
                total_created += created
                total_skipped += skipped

            results['total_created'] = total_created
            results['total_skipped'] = total_skipped
            results['stages_completed'].append('tracked_players')

            # ── Stage 5: Link orphaned journeys ──
            stage = 'link_journeys'
            update_job(job_id, progress=5, total=total_stages, current_player='Stage 5: Linking orphaned journeys...')
            unlinked = TrackedPlayer.query.filter(
                TrackedPlayer.is_active == True,
                TrackedPlayer.journey_id.is_(None),
            ).all()
            linked = 0
            for tp in unlinked:
                journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
                if journey:
                    tp.journey_id = journey.id
                    linked += 1
            if linked:
                db.session.commit()
            results['journeys_linked'] = linked
            results['stages_completed'].append('link_journeys')

            # ── Stage 6: Refresh statuses ──
            stage = 'refresh_statuses'
            update_job(job_id, progress=6, total=total_stages, current_player='Stage 6: Refreshing statuses...')
            tracked = TrackedPlayer.query.filter(TrackedPlayer.is_active == True).all()
            updated = 0
            status_counts = {}
            for tp in tracked:
                if not tp.team:
                    continue
                journey = tp.journey
                status, loan_api_id, loan_name = derive_player_status(
                    current_club_api_id=journey.current_club_api_id if journey else None,
                    current_club_name=journey.current_club_name if journey else None,
                    current_level=journey.current_level if journey else None,
                    parent_api_id=tp.team.team_id,
                    parent_club_name=tp.team.name,
                )
                if tp.status != status or tp.loan_club_api_id != loan_api_id:
                    tp.status = status
                    tp.loan_club_api_id = loan_api_id
                    tp.loan_club_name = loan_name
                    updated += 1
                status_counts[status] = status_counts.get(status, 0) + 1
            if updated:
                db.session.commit()
            results['statuses_updated'] = updated
            results['status_breakdown'] = status_counts
            results['stages_completed'].append('refresh_statuses')

            # ── Stage 7: Seed club locations ──
            stage = 'locations'
            update_job(job_id, progress=7, total=total_stages, current_player='Stage 7: Seeding club locations...')
            locations_added = seed_club_locations()
            results['locations_added'] = locations_added
            results['stages_completed'].append('locations')

            update_job(job_id, status='completed', results=results,
                       completed_at=datetime.now(timezone.utc).isoformat())

        except Exception as e:
            logger.exception(f'Full rebuild job {job_id} failed at stage: {stage}')
            db.session.rollback()
            update_job(job_id, status='failed', error=f'Failed at {stage}: {e}',
                       completed_at=datetime.now(timezone.utc).isoformat())

    thread = threading.Thread(target=run_in_background)
    thread.start()

    return jsonify({
        'message': 'Full academy rebuild started in background',
        'job_id': job_id,
        'status': 'running',
        'check_status_url': f'/api/admin/jobs/{job_id}',
        'config': {
            'team_ids': team_ids,
            'seasons': seasons,
            'skip_clean': skip_clean,
            'skip_cohorts': skip_cohorts,
        }
    }), 202

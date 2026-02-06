"""Cohort API endpoints.

Handles:
- Admin cohort seeding and management
- Public cohort browsing and analytics
"""
from flask import Blueprint, request, jsonify, copy_current_request_context
from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
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
    results = db.session.query(
        AcademyCohort.team_api_id,
        AcademyCohort.team_name,
        AcademyCohort.team_logo
    ).distinct().order_by(AcademyCohort.team_name).all()

    teams = [
        {'team_api_id': r.team_api_id, 'team_name': r.team_name, 'team_logo': r.team_logo}
        for r in results
    ]
    return jsonify({'teams': teams})


@cohort_bp.route('/cohorts/analytics', methods=['GET'])
def cohort_analytics():
    """Cross-club comparison analytics."""
    cohorts = AcademyCohort.query.filter(
        AcademyCohort.sync_status == 'complete'
    ).all()

    # Group by team
    team_data = {}
    for c in cohorts:
        tid = c.team_api_id
        if tid not in team_data:
            team_data[tid] = {
                'team_api_id': tid,
                'team_name': c.team_name,
                'team_logo': c.team_logo,
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

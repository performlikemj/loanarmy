"""
Big 6 Seeding Service

Orchestrates bulk cohort discovery and journey sync for the
Premier League Big 6 clubs across multiple youth leagues and seasons.
"""

import logging
import time
from datetime import datetime, timezone
from collections import deque

from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
from src.services.cohort_service import CohortService
from src.services.journey_sync import JourneySyncService
from src.services.youth_competition_resolver import (
    get_default_youth_league_map,
    resolve_team_name,
    resolve_youth_leagues,
    resolve_youth_team_for_parent,
)
from src.utils.background_jobs import update_job

logger = logging.getLogger(__name__)

BIG_6 = {
    33: 'Manchester United',
    42: 'Arsenal',
    49: 'Chelsea',
    50: 'Manchester City',
    40: 'Liverpool',
    47: 'Tottenham',
}

YOUTH_LEAGUES = get_default_youth_league_map()

SEASONS = [2020, 2021, 2022, 2023, 2024]


class RateLimiter:
    """Simple rate limiter tracking per-minute and per-day API usage."""

    def __init__(self, per_minute_cap=280, per_day_cap=7000):
        self.per_minute_cap = per_minute_cap
        self.per_day_cap = per_day_cap
        self.minute_calls = deque()
        self.day_calls = 0

    def wait_if_needed(self):
        """Block if rate limits would be exceeded."""
        now = time.time()

        # Clean old minute entries
        while self.minute_calls and self.minute_calls[0] < now - 60:
            self.minute_calls.popleft()

        # Check per-minute cap
        if len(self.minute_calls) >= self.per_minute_cap:
            sleep_until = self.minute_calls[0] + 60
            sleep_time = sleep_until - now
            if sleep_time > 0:
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s (minute cap)")
                time.sleep(sleep_time)

        # Check per-day cap
        if self.day_calls >= self.per_day_cap:
            logger.warning("Daily API call limit reached, stopping")
            raise RuntimeError("Daily API call limit reached")

        self.minute_calls.append(time.time())
        self.day_calls += 1


def run_big6_seed(job_id, seasons=None, team_ids=None, league_ids=None):
    """
    Run the full Big 6 cohort seeding pipeline.

    Phase 1: Discover cohorts for each (team, league, season) combo
    Phase 2: Sync journeys for all unique players
    Phase 3: Refresh cohort aggregates

    Args:
        job_id: Background job ID for progress tracking
        seasons: List of season years (default: SEASONS)
        team_ids: List of team API IDs (default: BIG_6 keys)
        league_ids: List of league API IDs (default: YOUTH_LEAGUES keys)
    """
    seasons = seasons or SEASONS
    team_ids = team_ids or list(BIG_6.keys())
    provided_league_ids = league_ids
    league_ids = league_ids or list(YOUTH_LEAGUES.keys())

    cohort_service = CohortService()
    journey_service = JourneySyncService()
    api_client = cohort_service.api

    # Resolve youth competitions dynamically (with static fallback).
    resolved_leagues = resolve_youth_leagues(
        api_client=api_client,
        explicit_league_ids=provided_league_ids,
    )
    if not resolved_leagues:
        resolved_leagues = [
            {'league_id': lid, 'name': YOUTH_LEAGUES.get(lid, str(lid))}
            for lid in league_ids
        ]

    # Calculate total combos (team x resolved league x season)
    combos = [(t, lg, s) for t in team_ids for lg in resolved_leagues for s in seasons]
    total_combos = len(combos)

    update_job(job_id, total=total_combos, progress=0)
    logger.info(
        "Big 6 seed: %d combos across %d resolved youth leagues",
        total_combos,
        len(resolved_leagues),
    )

    parent_names = {
        team_id: resolve_team_name(api_client, team_id, fallback_name=BIG_6.get(team_id))
        for team_id in team_ids
    }
    teams_cache = {}
    skipped_no_youth_team = 0
    skipped_empty_cohorts = 0

    # ── Phase 1: Discovery ──
    cohort_ids = []
    for idx, (team_id, league_meta, season) in enumerate(combos):
        league_id = int(league_meta.get('league_id'))
        league_name = league_meta.get('name') or YOUTH_LEAGUES.get(league_id, str(league_id))
        team_name = parent_names.get(team_id, str(team_id))

        try:
            update_job(
                job_id,
                progress=idx,
                current_player=f"Discovering {team_name} {league_name} {season}",
            )

            # Resolve the youth-team API ID for this parent team in this league/season.
            query_team_id, query_team_name = resolve_youth_team_for_parent(
                api_client=api_client,
                league_id=league_id,
                season=season,
                parent_team_name=team_name,
                teams_cache=teams_cache,
            )
            if not query_team_id:
                skipped_no_youth_team += 1
                logger.info(
                    "Skipping combo: no youth team found for parent='%s' league=%s season=%s",
                    team_name,
                    league_name,
                    season,
                )
                continue

            # Skip if already complete
            existing = AcademyCohort.query.filter_by(
                team_api_id=team_id,
                league_api_id=league_id,
                season=season
            ).first()

            if existing and existing.sync_status != 'failed':
                member_count = CohortMember.query.filter_by(cohort_id=existing.id).count()
                if member_count > 0:
                    cohort_ids.append(existing.id)
                    continue
                # Empty cohort — fall through to re-discover

            # Clear stale cache entries that may contain empty API responses.
            try:
                from src.models.api_cache import APICache
                for page in range(1, 11):
                    APICache.invalidate_cached('players', {
                        'team': int(query_team_id),
                        'league': int(league_id),
                        'season': int(season),
                        'page': page,
                    })
            except Exception as cache_err:
                logger.warning("Cache clearing failed for combo %s/%s/%s: %s", team_name, league_name, season, cache_err)

            cohort = cohort_service.discover_cohort(
                team_id, league_id, season,
                fallback_team_name=team_name,
                fallback_league_name=league_name,
                query_team_api_id=int(query_team_id),
            )

            if cohort.total_players > 0:
                cohort_ids.append(cohort.id)
            else:
                skipped_empty_cohorts += 1
                logger.info(
                    "Skipping empty cohort id=%s (%s/%s/%s, query_team=%s %s)",
                    cohort.id,
                    team_name,
                    league_name,
                    season,
                    query_team_id,
                    query_team_name,
                )

        except Exception as e:
            logger.error(f"Failed to discover cohort {team_name}/{league_name}/{season}: {e}")
            continue

    if not cohort_ids:
        logger.warning("Big 6 seed produced no populated cohorts")
        return {
            'cohorts_created': 0,
            'players_synced': 0,
            'combos_attempted': total_combos,
            'combos_skipped_no_youth_team': skipped_no_youth_team,
            'combos_skipped_empty_cohort': skipped_empty_cohorts,
            'resolved_leagues': [l.get('league_id') for l in resolved_leagues],
        }

    # ── Phase 2: Journey sync ──
    # Pre-load cohort parent context for status derivation
    cohort_context = {}
    for cid in cohort_ids:
        c = db.session.get(AcademyCohort, cid)
        if c:
            cohort_context[cid] = (c.team_api_id, c.team_name or '')

    # Collect all unique player IDs across cohorts
    all_members = CohortMember.query.filter(
        CohortMember.cohort_id.in_(cohort_ids),
        CohortMember.journey_synced == False
    ).all()

    # Dedupe by player_api_id
    seen_players = set()
    unique_members = []
    for m in all_members:
        if m.player_api_id not in seen_players:
            seen_players.add(m.player_api_id)
            unique_members.append(m)

    total_players = len(unique_members)
    logger.info(f"Big 6 seed: {total_players} unique players to sync journeys")

    update_job(job_id, total=total_combos + total_players,
               progress=total_combos,
               current_player="Starting journey sync")

    current_year = datetime.now().year
    rate_limiter = RateLimiter()  # 280 req/min, 7000 req/day
    quota_exhausted = False
    synced_count = 0

    for idx, member in enumerate(unique_members):
        if quota_exhausted:
            break

        try:
            rate_limiter.wait_if_needed()

            update_job(job_id, progress=total_combos + idx,
                       current_player=f"Journey: {member.player_name}")

            journey = journey_service.sync_player(member.player_api_id)

            if journey and not journey.sync_error:
                # Update ALL members with this player_api_id
                all_player_members = CohortMember.query.filter_by(
                    player_api_id=member.player_api_id
                ).all()

                for pm in all_player_members:
                    pm.journey_id = journey.id
                    pm.current_club_api_id = journey.current_club_api_id
                    pm.current_club_name = journey.current_club_name
                    pm.current_level = journey.current_level
                    pm.first_team_debut_season = journey.first_team_debut_season
                    pm.total_first_team_apps = journey.total_first_team_apps
                    pm.total_clubs = journey.total_clubs
                    parent_api_id, parent_club_name = cohort_context.get(pm.cohort_id, (0, ''))
                    pm.current_status = CohortService._derive_status(
                        journey, current_year,
                        parent_api_id=parent_api_id,
                        parent_club_name=parent_club_name,
                    )
                    pm.journey_synced = True
                    pm.journey_sync_error = None

                db.session.commit()
                synced_count += 1
            elif journey and journey.sync_error:
                # Journey exists but had a sync error — don't mark as synced
                all_player_members = CohortMember.query.filter_by(
                    player_api_id=member.player_api_id
                ).all()
                for pm in all_player_members:
                    pm.journey_id = journey.id
                    pm.journey_synced = False
                    pm.journey_sync_error = journey.sync_error
                db.session.commit()
            else:
                all_player_members = CohortMember.query.filter_by(
                    player_api_id=member.player_api_id
                ).all()
                for pm in all_player_members:
                    pm.journey_synced = False
                    pm.journey_sync_error = "Journey sync returned no data"
                db.session.commit()

        except RuntimeError as e:
            err_msg = str(e).lower()
            if 'daily api call limit' in err_msg or 'daily quota' in err_msg:
                logger.warning(
                    "Daily API limit reached at player %d/%d (%d synced so far), saving progress",
                    idx + 1, total_players, synced_count,
                )
                quota_exhausted = True
                break
            logger.warning(f"Failed journey sync for player {member.player_api_id}: {e}")
            member.journey_sync_error = str(e)
            member.journey_synced = False
            db.session.commit()
        except Exception as e:
            logger.warning(f"Failed journey sync for player {member.player_api_id}: {e}")
            member.journey_sync_error = str(e)
            member.journey_synced = False
            db.session.commit()

        if (idx + 1) % 50 == 0:
            logger.info(
                "Journey sync progress: %d/%d (%.0f%%), %d synced",
                idx + 1, total_players, (idx + 1) / total_players * 100, synced_count,
            )

    if quota_exhausted:
        remaining = total_players - (idx + 1)
        logger.warning(
            "Journey sync stopped early: %d/%d completed, %d remaining (re-run to continue)",
            synced_count, total_players, remaining,
        )
    else:
        logger.info("Journey sync complete: %d/%d synced", synced_count, total_players)

    # ── Phase 3: Refresh stats ──
    update_job(job_id, current_player="Refreshing cohort stats")
    for cohort_id in cohort_ids:
        try:
            cohort_service.refresh_cohort_stats(cohort_id)
        except Exception as e:
            logger.warning(f"Failed to refresh stats for cohort {cohort_id}: {e}")

    # Mark cohorts by actual sync coverage.
    now = datetime.now(timezone.utc)
    for cohort_id in cohort_ids:
        try:
            c = db.session.get(AcademyCohort, cohort_id)
            if not c:
                continue
            total_members = CohortMember.query.filter_by(cohort_id=cohort_id).count()
            synced_members = CohortMember.query.filter_by(
                cohort_id=cohort_id,
                journey_synced=True,
            ).count()

            if total_members == 0:
                c.sync_status = 'no_data'
            elif synced_members == total_members:
                c.sync_status = 'complete'
                c.journeys_synced_at = now
            elif synced_members == 0:
                c.sync_status = 'failed'
            else:
                c.sync_status = 'partial'
                c.journeys_synced_at = now
        except Exception as e:
            logger.warning(f"Failed to mark cohort {cohort_id} complete: {e}")
    db.session.commit()

    logger.info(
        "Big 6 seed complete: %d cohorts, %d/%d players synced%s",
        len(cohort_ids), synced_count, total_players,
        " (quota exhausted)" if quota_exhausted else "",
    )
    return {
        'cohorts_created': len(cohort_ids),
        'players_synced': synced_count,
        'players_total': total_players,
        'quota_exhausted': quota_exhausted,
        'combos_attempted': total_combos,
        'combos_skipped_no_youth_team': skipped_no_youth_team,
        'combos_skipped_empty_cohort': skipped_empty_cohorts,
        'resolved_leagues': [l.get('league_id') for l in resolved_leagues],
    }

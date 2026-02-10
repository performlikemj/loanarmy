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
from src.models.journey import PlayerJourney, YOUTH_LEVELS
from src.services.cohort_service import CohortService
from src.services.journey_sync import JourneySyncService
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

YOUTH_LEAGUES = {
    703: 'U18 PL',
    706: 'PL2 Div 1',
    707: 'PL2 Div 2',
    708: 'PDL',
    718: 'FA Youth Cup',
    775: 'UEFA Youth League',
}

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
    league_ids = league_ids or list(YOUTH_LEAGUES.keys())

    cohort_service = CohortService()
    journey_service = JourneySyncService()

    # Calculate total combos
    combos = [(t, l, s) for t in team_ids for l in league_ids for s in seasons]
    total_combos = len(combos)

    update_job(job_id, total=total_combos, progress=0)
    logger.info(f"Big 6 seed: {total_combos} cohort combos to discover")

    # Clear stale cache entries that may contain empty API responses,
    # so discovery fetches fresh data from the live API.
    try:
        from src.models.api_cache import APICache
        for t in team_ids:
            for l in league_ids:
                for s in seasons:
                    for page in range(1, 11):
                        APICache.invalidate_cached('players', {
                            'team': t, 'league': l, 'season': s, 'page': page,
                        })
        logger.info("Cleared stale players cache for %d combos", len(combos))
    except Exception as e:
        logger.warning("Cache clearing failed (non-fatal): %s", e)

    # ── Phase 1: Discovery ──
    cohort_ids = []
    for idx, (team_id, league_id, season) in enumerate(combos):
        team_name = BIG_6.get(team_id, str(team_id))
        league_name = YOUTH_LEAGUES.get(league_id, str(league_id))

        try:
            # Skip if already complete
            existing = AcademyCohort.query.filter_by(
                team_api_id=team_id,
                league_api_id=league_id,
                season=season
            ).first()

            if existing and existing.sync_status in ('complete', 'seeded'):
                member_count = CohortMember.query.filter_by(cohort_id=existing.id).count()
                if member_count > 0:
                    cohort_ids.append(existing.id)
                    continue
                # Empty cohort — fall through to re-discover

            update_job(job_id, progress=idx,
                       current_player=f"Discovering {team_name} {league_name} {season}")

            cohort = cohort_service.discover_cohort(
                team_id, league_id, season,
                fallback_team_name=team_name,
                fallback_league_name=league_name
            )
            cohort_ids.append(cohort.id)

        except Exception as e:
            logger.error(f"Failed to discover cohort {team_name}/{league_name}/{season}: {e}")
            continue

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

    for idx, member in enumerate(unique_members):
        try:
            update_job(job_id, progress=total_combos + idx,
                       current_player=f"Journey: {member.player_name}")

            journey = journey_service.sync_player(member.player_api_id)

            if journey:
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

        except Exception as e:
            logger.warning(f"Failed journey sync for player {member.player_api_id}: {e}")
            member.journey_sync_error = str(e)
            db.session.commit()

    # ── Phase 3: Refresh stats ──
    update_job(job_id, current_player="Refreshing cohort stats")
    for cohort_id in cohort_ids:
        try:
            cohort_service.refresh_cohort_stats(cohort_id)
        except Exception as e:
            logger.warning(f"Failed to refresh stats for cohort {cohort_id}: {e}")

    # Mark cohorts with members as 'complete' so the analytics
    # endpoint (which filters on sync_status='complete') picks them up.
    now = datetime.now(timezone.utc)
    for cohort_id in cohort_ids:
        try:
            c = db.session.get(AcademyCohort, cohort_id)
            if c and c.total_players > 0 and c.sync_status != 'complete':
                c.sync_status = 'complete'
                c.journeys_synced_at = now
        except Exception as e:
            logger.warning(f"Failed to mark cohort {cohort_id} complete: {e}")
    db.session.commit()

    logger.info(f"Big 6 seed complete: {len(cohort_ids)} cohorts, {total_players} players")
    return {
        'cohorts_created': len(cohort_ids),
        'players_synced': total_players,
    }

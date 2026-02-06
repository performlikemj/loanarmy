"""
Cohort Service

Discovers academy cohorts from API-Football, syncs player journeys,
and calculates "where are they now" analytics.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney, PlayerJourneyEntry, YOUTH_LEVELS
from src.api_football_client import APIFootballClient
from src.services.journey_sync import JourneySyncService

logger = logging.getLogger(__name__)


class CohortService:
    """Service for discovering and managing academy cohorts"""

    def __init__(self, api_client: Optional[APIFootballClient] = None):
        self.api = api_client or APIFootballClient()

    def discover_cohort(self, team_api_id: int, league_api_id: int, season: int) -> AcademyCohort:
        """
        Discover players in a youth league/season for a team.

        Idempotent: returns existing cohort if already seeded.
        Creates AcademyCohort + CohortMember records with cohort stats.

        Args:
            team_api_id: API-Football team ID
            league_api_id: API-Football league ID
            season: Season year

        Returns:
            AcademyCohort record
        """
        logger.info(f"Discovering cohort: team={team_api_id} league={league_api_id} season={season}")

        # Check for existing cohort (idempotent)
        existing = AcademyCohort.query.filter_by(
            team_api_id=team_api_id,
            league_api_id=league_api_id,
            season=season
        ).first()

        if existing and existing.sync_status != 'failed':
            logger.info(f"Cohort already exists (id={existing.id}, status={existing.sync_status})")
            return existing

        try:
            # Create or reset cohort
            if existing:
                cohort = existing
                cohort.sync_status = 'seeding'
                cohort.sync_error = None
            else:
                cohort = AcademyCohort(
                    team_api_id=team_api_id,
                    league_api_id=league_api_id,
                    season=season,
                    sync_status='seeding'
                )
                db.session.add(cohort)
                db.session.flush()

            # Fetch players from API-Football (paginated)
            page = 1
            total_pages = 1
            players_added = 0

            while page <= total_pages:
                response = self.api._make_request('players', {
                    'team': team_api_id,
                    'league': league_api_id,
                    'season': season,
                    'page': page
                })

                paging = response.get('paging', {})
                total_pages = paging.get('total', 1)

                # Set team/league info from first response
                if page == 1:
                    results = response.get('response', [])
                    if results:
                        first_player = results[0]
                        stats = first_player.get('statistics', [{}])
                        if stats:
                            stat = stats[0]
                            team_info = stat.get('team', {})
                            league_info = stat.get('league', {})
                            cohort.team_name = team_info.get('name')
                            cohort.team_logo = team_info.get('logo')
                            cohort.league_name = league_info.get('name')

                for player_data in response.get('response', []):
                    player = player_data.get('player', {})
                    stats_list = player_data.get('statistics', [])

                    player_api_id = player.get('id')
                    if not player_api_id:
                        continue

                    # Check for existing member (for re-seeding failed cohorts)
                    existing_member = CohortMember.query.filter_by(
                        cohort_id=cohort.id,
                        player_api_id=player_api_id
                    ).first()
                    if existing_member:
                        continue

                    # Extract stats from first statistics entry
                    appearances = 0
                    goals = 0
                    assists = 0
                    minutes = 0
                    position = None
                    if stats_list:
                        stat = stats_list[0]
                        games = stat.get('games', {})
                        goals_data = stat.get('goals', {})
                        appearances = games.get('appearences') or games.get('appearances') or 0
                        goals = goals_data.get('total') or 0
                        assists = goals_data.get('assists') or 0
                        minutes = games.get('minutes') or 0
                        position = games.get('position')

                    member = CohortMember(
                        cohort_id=cohort.id,
                        player_api_id=player_api_id,
                        player_name=player.get('name'),
                        player_photo=player.get('photo'),
                        nationality=player.get('nationality'),
                        birth_date=player.get('birth', {}).get('date'),
                        position=position,
                        appearances_in_cohort=appearances,
                        goals_in_cohort=goals,
                        assists_in_cohort=assists,
                        minutes_in_cohort=minutes,
                    )
                    db.session.add(member)
                    players_added += 1

                page += 1

            cohort.total_players = players_added
            cohort.seeded_at = datetime.now(timezone.utc)
            cohort.sync_status = 'complete'
            db.session.commit()

            logger.info(f"Discovered cohort id={cohort.id}: {players_added} players")
            return cohort

        except Exception as e:
            logger.error(f"Failed to discover cohort: {e}")
            db.session.rollback()

            try:
                cohort = AcademyCohort.query.filter_by(
                    team_api_id=team_api_id,
                    league_api_id=league_api_id,
                    season=season
                ).first()
                if cohort:
                    cohort.sync_status = 'failed'
                    cohort.sync_error = str(e)
                    db.session.commit()
            except Exception:
                pass

            raise

    def sync_cohort_journeys(self, cohort_id: int) -> AcademyCohort:
        """
        Sync journeys for all members in a cohort.

        Reuses JourneySyncService for each member, then updates
        the "where are they now" snapshot fields.

        Args:
            cohort_id: ID of the cohort to sync

        Returns:
            Updated AcademyCohort record
        """
        cohort = db.session.get(AcademyCohort, cohort_id)
        if not cohort:
            raise ValueError(f"Cohort {cohort_id} not found")

        logger.info(f"Syncing journeys for cohort {cohort_id} ({cohort.team_name} {cohort.season})")

        cohort.sync_status = 'syncing_journeys'
        db.session.commit()

        journey_service = JourneySyncService(self.api)
        members = CohortMember.query.filter_by(
            cohort_id=cohort_id,
            journey_synced=False
        ).all()

        current_year = datetime.now().year

        for member in members:
            try:
                journey = journey_service.sync_player(member.player_api_id)

                if journey:
                    member.journey_id = journey.id
                    member.current_club_api_id = journey.current_club_api_id
                    member.current_club_name = journey.current_club_name
                    member.current_level = journey.current_level
                    member.first_team_debut_season = journey.first_team_debut_season
                    member.total_first_team_apps = journey.total_first_team_apps
                    member.total_clubs = journey.total_clubs

                    # Count loan spells
                    loan_entries = PlayerJourneyEntry.query.filter_by(
                        journey_id=journey.id,
                        entry_type='loan'
                    ).count()
                    member.total_loan_spells = loan_entries

                    # Derive current status
                    member.current_status = self._derive_status(journey, current_year)

                member.journey_synced = True
                member.journey_sync_error = None
                db.session.commit()

            except Exception as e:
                logger.warning(f"Failed to sync journey for player {member.player_api_id}: {e}")
                member.journey_sync_error = str(e)
                db.session.commit()

        # Refresh aggregates
        self.refresh_cohort_stats(cohort_id)

        cohort.sync_status = 'complete'
        cohort.journeys_synced_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(f"Journey sync complete for cohort {cohort_id}")
        return cohort

    def refresh_cohort_stats(self, cohort_id: int) -> None:
        """Recalculate denormalized analytics for a cohort."""
        cohort = db.session.get(AcademyCohort, cohort_id)
        if not cohort:
            return

        members = CohortMember.query.filter_by(cohort_id=cohort_id).all()

        cohort.total_players = len(members)
        cohort.players_first_team = sum(1 for m in members if m.current_status == 'first_team')
        cohort.players_on_loan = sum(1 for m in members if m.current_status == 'on_loan')
        cohort.players_still_academy = sum(1 for m in members if m.current_status == 'academy')
        cohort.players_released = sum(1 for m in members if m.current_status == 'released')

        db.session.commit()
        logger.info(f"Refreshed stats for cohort {cohort_id}: {cohort.total_players} players")

    @staticmethod
    def _derive_status(journey: PlayerJourney, current_year: int) -> str:
        """Derive current_status from a player's journey data."""
        if not journey:
            return 'unknown'

        level = journey.current_level
        if level == 'First Team':
            return 'first_team'
        if level in YOUTH_LEVELS:
            return 'academy'

        # Check if player has recent entries
        latest_entry = PlayerJourneyEntry.query.filter_by(
            journey_id=journey.id
        ).order_by(PlayerJourneyEntry.season.desc()).first()

        if latest_entry and latest_entry.season < current_year - 2:
            return 'released'

        return 'on_loan'

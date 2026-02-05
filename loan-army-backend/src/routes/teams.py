"""Teams blueprint for team and league endpoints.

This blueprint handles:
- League listings
- Gameweek information
- Team listings and details
- Team loan information
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import NotFound

from src.auth import _safe_error_payload
from src.models.league import (
    db,
    League,
    Team,
    LoanedPlayer,
    Player,
    SupplementalLoan,
    _dedupe_loans,
)

logger = logging.getLogger(__name__)

teams_bp = Blueprint('teams', __name__)


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client
    return api_client


# Expose api_client as a module-level attribute for patching in tests
class _LazyApiClient:
    def __getattr__(self, name):
        return getattr(_get_api_client(), name)

api_client = _LazyApiClient()


# ---------------------------------------------------------------------------
# League endpoints
# ---------------------------------------------------------------------------

@teams_bp.route('/leagues', methods=['GET'])
def get_leagues():
    """Get all European leagues."""
    try:
        leagues = League.query.filter_by(is_european_top_league=True).all()
        return jsonify([league.to_dict() for league in leagues])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# Gameweek endpoints
# ---------------------------------------------------------------------------

@teams_bp.route('/gameweeks', methods=['GET'])
def get_gameweeks():
    """Get available gameweeks for the season."""
    try:
        season = request.args.get('season', type=int)
        from src.utils.gameweeks import get_season_gameweeks
        weeks = get_season_gameweeks(season_start_year=season)
        return jsonify(weeks)
    except Exception as e:
        logger.error(f"Error getting gameweeks: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# Team endpoints
# ---------------------------------------------------------------------------

@teams_bp.route('/teams', methods=['GET'])
def get_teams():
    """Get all teams with optional filtering.

    Query params:
    - season: Filter by season year
    - european_only: Filter to European top leagues only
    - has_loans: Filter to teams with active loans
    - search: Filter by name search
    """
    try:
        logger.info("GET /teams endpoint called")
        logger.info(f"Request args: {dict(request.args)}")

        # Check database connection and teams table
        total_teams = Team.query.count()
        logger.info(f"Total teams in database: {total_teams}")

        # Start with base query for active teams
        query = Team.query.filter_by(is_active=True)

        # Handle season filter
        season = request.args.get('season', type=int)
        if season:
            logger.info(f"Filtering for season: {season}")
            query = query.filter_by(season=season)

        # Handle european_only filter
        european_only = request.args.get('european_only', '').lower() == 'true'
        if european_only:
            logger.info("Filtering for European teams only")
            european_leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1']
            query = query.join(League).filter(League.name.in_(european_leagues))

        # Handle has_loans filter
        has_loans = request.args.get('has_loans', '').lower() == 'true'
        if has_loans:
            logger.info("Filtering for teams with active loans")
            query = query.join(LoanedPlayer, Team.id == LoanedPlayer.primary_team_id)\
                        .filter(LoanedPlayer.is_active == True)\
                        .distinct()

        # Handle search filter (for global search)
        search = request.args.get('search', '').strip()
        if search:
            logger.info(f"Searching teams for: {search}")
            query = query.filter(Team.name.ilike(f'%{search}%'))

        teams = query.all()
        active_teams_count = len(teams)
        logger.info(f"Filtered teams found: {active_teams_count}")

        # Deduplicate teams by team_id, keeping the latest season
        deduped_teams = {}
        for team in teams:
            existing = deduped_teams.get(team.team_id)
            if not existing or team.season > existing.season:
                deduped_teams[team.team_id] = team

        teams = list(deduped_teams.values())
        # Sort by name for consistent display
        teams.sort(key=lambda x: x.name)

        if active_teams_count == 0 and european_only:
            # Lazy sync logic for European teams when none found
            try:
                _lazy_sync_european_teams(season)
                # Re-run the filtered query
                query = Team.query.filter_by(is_active=True)
                if season:
                    query = query.filter_by(season=season)
                if european_only:
                    european_leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1']
                    query = query.join(League).filter(League.name.in_(european_leagues))
                teams = query.all()
            except Exception as sync_ex:
                logger.error(f"Lazy sync failed: {sync_ex}")

        team_dicts = [team.to_dict() for team in teams]
        logger.info(f"Returning {len(team_dicts)} team records")

        return jsonify(team_dicts)
    except Exception as e:
        logger.error(f"Error in get_teams: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _lazy_sync_european_teams(season: int | None):
    """Lazily sync European teams if none exist in database."""
    real_client = _get_api_client()
    season = season or real_client.current_season_start_year
    logger.info(f"Attempting lazy sync for European top leagues for season {season}")

    # Sync leagues (top-5)
    leagues_data = real_client.get_european_leagues(season)
    for league_data in leagues_data:
        league_info = league_data.get('league', {})
        country_info = league_data.get('country', {})
        seasons = league_data.get('seasons', [])
        current_season = next((s for s in seasons if s.get('current')), seasons[0] if seasons else {})
        existing = League.query.filter_by(league_id=league_info.get('id')).first()
        if existing:
            existing.name = league_info.get('name')
            existing.country = country_info.get('name')
            existing.season = current_season.get('year', real_client.current_season_start_year)
            existing.logo = league_info.get('logo')
            existing.is_european_top_league = True
        else:
            db.session.add(League(
                league_id=league_info.get('id'),
                name=league_info.get('name'),
                country=country_info.get('name'),
                season=current_season.get('year', real_client.current_season_start_year),
                is_european_top_league=True,
                logo=league_info.get('logo')
            ))

    # Sync teams for those leagues
    all_teams = real_client.get_all_european_teams(season)
    for team_data in all_teams:
        team_info = team_data.get('team', {})
        league_info = team_data.get('league_info', {})
        league = League.query.filter_by(league_id=league_info.get('id')).first()
        if not league:
            continue
        existing_team = Team.query.filter_by(team_id=team_info.get('id'), season=season).first()
        if existing_team:
            existing_team.name = team_info.get('name')
            existing_team.country = team_info.get('country')
            existing_team.founded = team_info.get('founded')
            existing_team.logo = team_info.get('logo')
            existing_team.league_id = league.id
            existing_team.is_active = True
        else:
            db.session.add(Team(
                team_id=team_info.get('id'),
                name=team_info.get('name'),
                country=team_info.get('country'),
                founded=team_info.get('founded'),
                logo=team_info.get('logo'),
                league_id=league.id,
                season=season,
                is_active=True
            ))
    db.session.commit()
    logger.info("Lazy sync complete")


@teams_bp.route('/teams/<int:team_id>', methods=['GET'])
def get_team(team_id):
    """Get specific team with loan details."""
    try:
        team = Team.query.get_or_404(team_id)
        team_dict = team.to_dict()

        # Add detailed loan information with duplicates removed
        active_loans = team.unique_active_loans()
        team_dict['active_loans'] = [loan.to_dict() for loan in active_loans]

        return jsonify(team_dict)
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@teams_bp.route('/teams/<int:team_id>/loans', methods=['GET'])
def get_team_loans(team_id):
    """Get loans for a specific team.

    Query params:
    - direction: 'loaned_from' (default) to show players loaned OUT from this team,
                 'loaned_to' to show players loaned TO this team
    - active_only: filter to only active loans (default: true)
    - dedupe: deduplicate loans by player_id (default: true)
    - season: filter by season year
    - include_supplemental: include supplemental loans (default: false)
    - include_season_context: enrich with season stats (default: false)
    """
    try:
        team = Team.query.get_or_404(team_id)
        active_only = request.args.get('active_only', 'true').lower() in ('1', 'true', 'yes', 'on', 'y')
        dedupe = request.args.get('dedupe', 'true').lower() in ('1', 'true', 'yes', 'on', 'y')
        season_val = request.args.get('season', type=int)
        direction = request.args.get('direction', 'loaned_from').lower()

        # Filter by direction: loaned_from = parent club, loaned_to = loan destination
        if direction == 'loaned_to':
            query = LoanedPlayer.query.filter_by(loan_team_id=team.id)
        else:
            query = LoanedPlayer.query.filter_by(primary_team_id=team.id)

        if active_only:
            query = query.filter(LoanedPlayer.is_active.is_(True))

        if season_val:
            slug = f"{season_val}-{str(season_val + 1)[-2:]}"
            query = query.filter(LoanedPlayer.window_key.like(f"{slug}%"))

        loans = query.order_by(LoanedPlayer.updated_at.desc()).all()
        if dedupe:
            loans = _dedupe_loans(loans)

        result = []
        for loan in loans:
            loan_dict = loan.to_dict()

            # Add player photo and position from Player table
            if loan_dict.get('player_id'):
                loan_dict['player_photo'] = _get_player_photo(loan_dict['player_id'])
                loan_dict['position'] = _get_player_position(loan_dict['player_id'])
            else:
                loan_dict['player_photo'] = None
                loan_dict['position'] = None

            # Add loan team logo if loan_team_api_id is available
            if loan_dict.get('loan_team_api_id'):
                loan_dict['loan_team_logo'] = _get_team_logo(loan_dict['loan_team_api_id'])
            else:
                loan_dict['loan_team_logo'] = None

            # Optionally enrich with season context stats
            include_season_context = request.args.get('include_season_context', 'false').lower() in ('1', 'true', 'yes', 'on', 'y')
            if include_season_context and loan_dict.get('player_id') and loan_dict.get('loan_team_api_id'):
                _enrich_with_season_context(loan, loan_dict, season_val)

            result.append(loan_dict)

        # Include supplemental loans if requested
        include_supp = request.args.get('include_supplemental', 'false').lower() in ('1', 'true', 'yes', 'on')
        if include_supp:
            result.extend(_get_supplemental_loans(team.id, season_val))

        return jsonify(result)
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _get_player_photo(player_id: int) -> str | None:
    """Get player photo URL."""
    try:
        from src.agents.weekly_agent import _player_photo_for
        return _player_photo_for(player_id)
    except Exception:
        return None


def _get_player_position(player_id: int) -> str | None:
    """Get player position from Player table."""
    try:
        player = Player.query.filter_by(player_id=player_id).first()
        return player.position if player else None
    except Exception:
        return None


def _get_team_logo(team_api_id: int) -> str | None:
    """Get team logo URL."""
    try:
        from src.agents.weekly_agent import _team_logo_for_team
        return _team_logo_for_team(team_api_id)
    except Exception:
        return None


def _enrich_with_season_context(loan: LoanedPlayer, loan_dict: dict, season_val: int | None):
    """Enrich loan dict with season context stats."""
    try:
        from src.api_football_client import APIFootballClient
        from src.models.weekly import FixturePlayerStats

        real_client = APIFootballClient()

        # Determine season from window_key or use current season
        season_year = season_val
        if not season_year and loan.window_key:
            try:
                season_str = loan.window_key.split('-')[0]
                season_year = int(season_str)
            except (ValueError, IndexError):
                now = datetime.now(timezone.utc)
                season_year = now.year if now.month >= 8 else now.year - 1

        if not season_year:
            now = datetime.now(timezone.utc)
            season_year = now.year if now.month >= 8 else now.year - 1

        # Verify player ID
        player_id_to_use = loan_dict['player_id']
        verified_id, method = real_client.verify_player_id_via_fixtures(
            candidate_player_id=loan_dict['player_id'],
            player_name=loan.player_name,
            loan_team_id=loan_dict['loan_team_api_id'],
            season=season_year,
            max_fixtures=3
        )

        if verified_id != loan_dict['player_id']:
            logger.warning(
                f"Browse Teams ID correction for '{loan.player_name}': "
                f"{loan_dict['player_id']} -> {verified_id}"
            )
            player_id_to_use = verified_id
            # Update the database record
            loan.player_id = verified_id
            loan.reviewer_notes = (loan.reviewer_notes or '') + f' | ID auto-corrected in browse: {loan_dict["player_id"]} -> {verified_id}'
            loan.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            # Delete ghost stats
            FixturePlayerStats.query.filter(
                FixturePlayerStats.player_api_id == loan_dict['player_id'],
                FixturePlayerStats.team_api_id == loan_dict['loan_team_api_id'],
                FixturePlayerStats.minutes == 0
            ).delete()
            db.session.commit()
            loan_dict['player_id'] = verified_id

        # Get season context with verified ID
        season_context = real_client.get_player_season_context(
            player_id=player_id_to_use,
            loan_team_id=loan_dict['loan_team_api_id'],
            season=season_year,
            up_to_date=datetime.now(timezone.utc).date(),
            db_session=db.session
        )

        # Use cumulative season stats if available
        season_stats = season_context.get('season_stats', {})
        if season_stats:
            _merge_season_stats(loan_dict, season_stats)
    except Exception as e:
        logger.debug(f"Failed to enrich loan {loan.id} with season context: {e}")


def _merge_season_stats(loan_dict: dict, season_stats: dict):
    """Merge season stats into loan dict."""
    if season_stats.get('games_played', 0) > 0:
        loan_dict['appearances'] = season_stats.get('games_played', loan_dict.get('appearances', 0))
    if season_stats.get('goals', 0) > (loan_dict.get('goals') or 0):
        loan_dict['goals'] = season_stats.get('goals', loan_dict.get('goals', 0))
    if season_stats.get('assists', 0) > (loan_dict.get('assists') or 0):
        loan_dict['assists'] = season_stats.get('assists', loan_dict.get('assists', 0))
    if season_stats.get('minutes', 0) > (loan_dict.get('minutes_played') or 0):
        loan_dict['minutes_played'] = season_stats.get('minutes', loan_dict.get('minutes_played', 0))

    # Position-specific stats
    for key in ['tackles_total', 'interceptions', 'duels_won', 'duels_total', 'passes_key', 'saves', 'goals_conceded', 'clean_sheets']:
        if season_stats.get(key) is not None:
            mapped_key = {
                'tackles_total': 'tackles',
                'passes_key': 'key_passes',
            }.get(key, key)
            loan_dict[mapped_key] = season_stats.get(key)


def _get_supplemental_loans(team_id: int, season_val: int | None) -> list[dict]:
    """Get supplemental loans for a team."""
    result = []
    supp_query = SupplementalLoan.query.filter_by(parent_team_id=team_id)
    if season_val:
        supp_query = supp_query.filter_by(season_year=season_val)

    for s in supp_query.all():
        try:
            item = {
                'player_name': s.player_name,
                'primary_team_name': s.parent_team_name,
                'primary_team_api_id': getattr(s.parent_team, 'team_id', None),
                'loan_team_id': s.loan_team_id,
                'loan_team_name': s.loan_team_name,
                'loan_team_api_id': getattr(s.loan_team, 'team_id', None),
                'window_key': f"{s.season_year}-{str(s.season_year + 1)[-2:]}" if s.season_year else None,
                'is_active': True,
                'appearances': None,
                'goals': None,
                'assists': None,
                'minutes_played': None,
                'yellows': None,
                'reds': None,
                'data_source': s.data_source or 'supplemental',
                'can_fetch_stats': False,
                'created_at': s.created_at.isoformat() if s.created_at else None,
                'updated_at': s.updated_at.isoformat() if s.updated_at else None,
                'season_year': s.season_year,
                'id': f"supp-{s.id}",
                'player_id': s.api_player_id,
                'player_photo': _get_player_photo(s.api_player_id) if s.api_player_id else None,
                'loan_team_logo': _get_team_logo(getattr(s.loan_team, 'team_id', None)) if s.loan_team else None,
            }
            result.append(item)
        except Exception:
            continue
    return result


@teams_bp.route('/teams/<int:team_id>/loans/season/<int:season>', methods=['GET'])
def get_team_loans_by_season(team_id: int, season: int):
    """Get loans for a specific team in a specific season (by window_key prefix)."""
    try:
        team = Team.query.get_or_404(team_id)
        slug = f"{season}-{str(season + 1)[-2:]}"
        active_only = request.args.get('active_only', 'false').lower() in ('true', '1', 'yes', 'y')

        q = (
            LoanedPlayer.query
            .filter(LoanedPlayer.primary_team_id == team.id)
            .filter(LoanedPlayer.window_key.like(f"{slug}%"))
        )
        if active_only:
            q = q.filter(LoanedPlayer.is_active.is_(True))

        loans = q.order_by(LoanedPlayer.updated_at.desc()).all()
        return jsonify([loan.to_dict() for loan in loans])
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@teams_bp.route('/teams/season/<int:season>', methods=['GET'])
def get_teams_for_season(season):
    """Get all teams for a specific season with their names."""
    try:
        real_client = _get_api_client()
        team_mapping = real_client.get_teams_for_season(season)
        return jsonify({
            'season': season,
            'teams': team_mapping,
            'count': len(team_mapping)
        })
    except Exception as e:
        logger.error(f"Error fetching teams for season {season}: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@teams_bp.route('/teams/<int:team_id>/api-info', methods=['GET'])
def get_team_api_info(team_id):
    """Get team information from API-Football by ID."""
    try:
        real_client = _get_api_client()
        season = request.args.get('season', real_client.current_season_start_year)
        team_data = real_client.get_team_by_id(team_id)

        if not team_data:
            return jsonify({'error': f'Team {team_id} not found'}), 404

        return jsonify({
            'team_id': team_id,
            'season': season,
            'data': team_data
        })
    except Exception as e:
        logger.error(f"Error fetching team {team_id} from API: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

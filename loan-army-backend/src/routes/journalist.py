from flask import Blueprint, request, jsonify, g
from src.models.league import (
    db, UserAccount, JournalistSubscription, NewsletterCommentary, Newsletter, 
    JournalistTeamAssignment, JournalistLoanTeamAssignment, WriterCoverageRequest,
    Team, LoanedPlayer, Player, ManualPlayerSubmission
)
from src.routes.api import require_user_auth, _safe_error_payload, require_api_key, _ensure_user_account
from src.utils.team_utils import normalize_team_name, get_all_team_name_variations
from datetime import datetime, timezone
from sqlalchemy import func, or_
import re
import logging

journalist_bp = Blueprint('journalist', __name__)
logger = logging.getLogger(__name__)


def can_writer_cover_team(user_id: int, team_id: int) -> bool:
    """Check if writer is assigned to a parent club team.
    
    Used for intro/summary commentaries that are team-wide.
    """
    return JournalistTeamAssignment.query.filter_by(
        user_id=user_id, 
        team_id=team_id
    ).first() is not None


def can_writer_cover_player(user_id: int, player_id: int, team_id: int = None) -> bool:
    """Check if writer can cover a specific player.
    
    A writer can cover a player if:
    1. Writer is assigned to the player's parent club (via JournalistTeamAssignment), OR
    2. Writer is assigned to the player's loan team (via JournalistLoanTeamAssignment)
    
    Args:
        user_id: The writer's user ID
        player_id: The player's API ID (from LoanedPlayer.player_id)
        team_id: Optional parent club team_id to also check (for backwards compatibility)
    
    Returns:
        True if writer can cover this player
    """
    # Find the player's loan record
    loan = LoanedPlayer.query.filter_by(player_id=player_id).order_by(
        LoanedPlayer.updated_at.desc()
    ).first()
    
    if not loan:
        # Player not found - fall back to team check if provided
        if team_id:
            return can_writer_cover_team(user_id, team_id)
        return False
    
    # Check 1: Is writer assigned to the player's parent club?
    if loan.primary_team_id:
        parent_assignment = JournalistTeamAssignment.query.filter_by(
            user_id=user_id,
            team_id=loan.primary_team_id
        ).first()
        if parent_assignment:
            return True
    
    # Also check if assigned to the team_id passed (handles cross-season team IDs)
    if team_id and team_id != loan.primary_team_id:
        team_assignment = JournalistTeamAssignment.query.filter_by(
            user_id=user_id,
            team_id=team_id
        ).first()
        if team_assignment:
            return True
    
    # Check 2: Is writer assigned to the player's loan team?
    # Check by loan_team_id if available
    if loan.loan_team_id:
        loan_team_assignment = JournalistLoanTeamAssignment.query.filter_by(
            user_id=user_id,
            loan_team_id=loan.loan_team_id
        ).first()
        if loan_team_assignment:
            return True
    
    # Also check by loan team name (using normalization)
    if loan.loan_team_name:
        # Get all variations of the player's loan team name
        variations = get_all_team_name_variations(loan.loan_team_name)
        
        # Check if writer is assigned to ANY of these variations
        loan_name_assignment = JournalistLoanTeamAssignment.query.filter(
            JournalistLoanTeamAssignment.user_id == user_id,
            JournalistLoanTeamAssignment.loan_team_name.in_(variations)
        ).first()
        
        if loan_name_assignment:
            return True
    
    return False


def get_writer_available_players(user_id: int) -> list:
    """Get all players a writer can cover based on their assignments.
    
    Returns LoanedPlayer records that the writer can write about.
    """
    # Get all parent club assignments
    parent_assignments = JournalistTeamAssignment.query.filter_by(user_id=user_id).all()
    parent_team_ids = [a.team_id for a in parent_assignments]
    
    # Get all loan team assignments
    loan_assignments = JournalistLoanTeamAssignment.query.filter_by(user_id=user_id).all()
    loan_team_ids = [a.loan_team_id for a in loan_assignments if a.loan_team_id]
    
    # Expand assigned names to include all aliases
    assigned_names = [a.loan_team_name for a in loan_assignments]
    expanded_names = set()
    for name in assigned_names:
        variations = get_all_team_name_variations(name)
        expanded_names.update(variations)
    loan_team_names = list(expanded_names)
    
    # Build query for players
    conditions = []
    
    # Players from assigned parent clubs
    if parent_team_ids:
        conditions.append(LoanedPlayer.primary_team_id.in_(parent_team_ids))
    
    # Players loaned to assigned loan teams (by ID)
    if loan_team_ids:
        conditions.append(LoanedPlayer.loan_team_id.in_(loan_team_ids))
    
    # Players loaned to assigned loan teams (by name, for custom teams)
    if loan_team_names:
        conditions.append(LoanedPlayer.loan_team_name.in_(loan_team_names))
    
    if not conditions:
        return []
    
    players = LoanedPlayer.query.filter(
        LoanedPlayer.is_active == True,
        or_(*conditions)
    ).order_by(
        LoanedPlayer.player_name.asc()
    ).all()
    
    return players

@journalist_bp.route('/journalists', methods=['GET'])
def list_journalists():
    """List all users marked as journalists."""
    try:
        journalists = UserAccount.query.filter_by(is_journalist=True).all()
        result = []
        for user in journalists:
            data = user.to_dict()
            # Include assigned teams
            assigned_teams = []
            for assignment in user.assigned_teams:
                if assignment.team:
                    assigned_teams.append({
                        'id': assignment.team.id,
                        'team_id': assignment.team.team_id,
                        'name': assignment.team.name,
                        'logo': assignment.team.logo
                    })
            data['assigned_teams'] = assigned_teams
            result.append(data)
        return jsonify(result)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch journalists')), 500

@journalist_bp.route('/journalists/invite', methods=['POST'])
@require_api_key
def invite_journalist():
    """(Admin) Create or update a user to be a journalist."""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        user = _ensure_user_account(email)
        user.is_journalist = True
        user.bio = data.get('bio', user.bio)
        user.profile_image_url = data.get('profile_image_url', user.profile_image_url)
        user.can_author_commentary = True
        
        db.session.commit()
        return jsonify({'message': 'Journalist invited/updated', 'user': user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to invite journalist')), 500

@journalist_bp.route('/journalists/<int:journalist_id>/assign-teams', methods=['POST'])
@require_api_key
def assign_teams(journalist_id):
    """(Admin) Assign teams to a journalist."""
    try:
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
            
        data = request.get_json() or {}
        team_ids = data.get('team_ids', [])
        
        # Clear existing assignments
        JournalistTeamAssignment.query.filter_by(user_id=journalist.id).delete()
        
        from src.utils.team_resolver import resolve_latest_team_id
        
        assignments = []
        for tid in team_ids:
            try:
                tid_int = int(tid)
            except (TypeError, ValueError):
                print(f"[ASSIGN TEAMS] Skipping invalid team id: {tid}")
                continue

            # Frontend sends API team_ids; resolve them to the current season's DB PK
            latest_team_id = resolve_latest_team_id(tid_int, assume_api_id=True)
            
            if latest_team_id:
                assign = JournalistTeamAssignment(
                    user_id=journalist.id,
                    team_id=latest_team_id,
                    assigned_by=None  # Could capture admin user if we had that context easily
                )
                db.session.add(assign)
                assignments.append(assign)
        
        db.session.commit()
        return jsonify({'message': 'Teams assigned', 'count': len(assignments)})
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to assign teams')), 500

@journalist_bp.route('/journalists/<int:journalist_id>/subscribe', methods=['POST'])
@require_user_auth
def subscribe_to_journalist(journalist_id):
    """Subscribe the current user to a journalist."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        subscriber = UserAccount.query.filter_by(email=email).first()
        if not subscriber:
            return jsonify({'error': 'Subscriber account not found'}), 404
            
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
            
        if subscriber.id == journalist.id:
            return jsonify({'error': 'Cannot subscribe to yourself'}), 400

        # Check existing subscription
        subscription = JournalistSubscription.query.filter_by(
            subscriber_user_id=subscriber.id,
            journalist_user_id=journalist.id
        ).first()

        if subscription:
            if not subscription.is_active:
                subscription.is_active = True
                subscription.updated_at = datetime.now(timezone.utc)
                db.session.commit()
            return jsonify({'message': 'Subscribed successfully', 'subscription': subscription.to_dict()})

        # Create new subscription
        new_subscription = JournalistSubscription(
            subscriber_user_id=subscriber.id,
            journalist_user_id=journalist.id,
            is_active=True
        )
        db.session.add(new_subscription)
        db.session.commit()
        
        return jsonify({'message': 'Subscribed successfully', 'subscription': new_subscription.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to subscribe')), 500

@journalist_bp.route('/journalists/<int:journalist_id>/unsubscribe', methods=['POST'])
@require_user_auth
def unsubscribe_from_journalist(journalist_id):
    """Unsubscribe the current user from a journalist."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        subscriber = UserAccount.query.filter_by(email=email).first()
        if not subscriber:
            return jsonify({'error': 'Subscriber account not found'}), 404

        subscription = JournalistSubscription.query.filter_by(
            subscriber_user_id=subscriber.id,
            journalist_user_id=journalist_id
        ).first()

        if subscription and subscription.is_active:
            subscription.is_active = False
            subscription.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
        return jsonify({'message': 'Unsubscribed successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to unsubscribe')), 500

@journalist_bp.route('/journalists/<int:journalist_id>/articles', methods=['GET'])
def get_journalist_articles(journalist_id):
    """Get articles (commentaries) by a journalist."""
    try:
        # Check if user is subscribed to see premium content
        user_id = None
        if hasattr(g, 'user_id'):
            user_id = g.user_id
            
        is_subscribed = False
        if user_id:
            # Check subscription
            sub = JournalistSubscription.query.filter_by(
                subscriber_user_id=user_id,
                journalist_user_id=journalist_id,
                is_active=True
            ).first()
            if sub:
                is_subscribed = True
        
        articles = NewsletterCommentary.query.filter_by(
            author_id=journalist_id,
            is_active=True
        ).order_by(NewsletterCommentary.created_at.desc()).all()

        results = []
        for a in articles:
            data = a.to_dict()
            # Attempt to resolve the published newsletter for this week/team
            try:
                week_start = a.week_start_date
                week_end = a.week_end_date
                team_id = a.team_id

                if team_id and week_start and week_end:
                    newsletter = Newsletter.query.filter_by(
                        team_id=team_id,
                        week_start_date=week_start,
                        week_end_date=week_end,
                        published=True,
                    ).first()
                    if newsletter:
                        data['newsletter_id'] = newsletter.id
                        data['newsletter_public_slug'] = newsletter.public_slug
                        # Ensure team name present for the card
                        if not data.get('team_name') and newsletter.team:
                            data['team_name'] = newsletter.team.name
            except Exception:
                pass

            # If premium and not subscribed, mask content
            if a.is_premium and not is_subscribed:
                # Create a preview snippet (first 200 chars, stripped of HTML)
                import re
                clean_text = re.sub('<[^<]+?>', '', data['content'])
                data['content'] = clean_text[:200] + '...' if len(clean_text) > 200 else clean_text
                data['is_locked'] = True # Flag for frontend
            else:
                data['is_locked'] = False
                
            results.append(data)
        
        return jsonify(results)

    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch articles')), 500


def _get_player_week_stats(player_id: int, week_start, week_end) -> list:
    """Get player stats for fixtures within a specific week range."""
    from src.models.weekly import FixturePlayerStats, Fixture

    if not player_id or not week_start or not week_end:
        return []

    try:
        player_id = int(player_id)
    except Exception:
        # If the player id cannot be coerced, skip stats to avoid DB errors
        return []

    try:
        # Query fixture stats for this player within the date range
        stats_query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_id,
            Fixture.date_utc >= datetime.combine(week_start, datetime.min.time()),
            Fixture.date_utc <= datetime.combine(week_end, datetime.max.time().replace(microsecond=0))
        ).order_by(
            Fixture.date_utc.asc()
        ).all()
        
        results = []
        for stats, fixture in stats_query:
            # Get team names
            home_team = Team.query.filter_by(team_id=fixture.home_team_api_id).first()
            away_team = Team.query.filter_by(team_id=fixture.away_team_api_id).first()
            is_home = stats.team_api_id == fixture.home_team_api_id
            
            fixture_data = {
                'fixture_id': fixture.fixture_id_api,
                'date': fixture.date_utc.isoformat() if fixture.date_utc else None,
                'competition': fixture.competition_name,
                'home_team': {
                    'name': home_team.name if home_team else 'Unknown',
                    'logo': home_team.logo if home_team else None,
                    'score': fixture.home_goals,
                },
                'away_team': {
                    'name': away_team.name if away_team else 'Unknown', 
                    'logo': away_team.logo if away_team else None,
                    'score': fixture.away_goals,
                },
                'is_home': is_home,
                'stats': {
                    # Basic stats (flat)
                    'minutes': stats.minutes or 0,
                    'position': stats.position,
                    'rating': stats.rating,
                    'goals': stats.goals or 0,
                    'assists': stats.assists or 0,
                    'yellows': stats.yellows or 0,
                    'reds': stats.reds or 0,
                    'substitute': stats.substitute,
                    # Flat keys for chart compatibility
                    'shots_total': stats.shots_total or 0,
                    'shots_on': stats.shots_on or 0,
                    'passes_total': stats.passes_total or 0,
                    'passes_key': stats.passes_key or 0,
                    'passes_accuracy': stats.passes_accuracy or 0,
                    'tackles_total': stats.tackles_total or 0,
                    'tackles_blocks': stats.tackles_blocks or 0,
                    'tackles_interceptions': stats.tackles_interceptions or 0,
                    'duels_total': stats.duels_total or 0,
                    'duels_won': stats.duels_won or 0,
                    'dribbles_attempts': stats.dribbles_attempts or 0,
                    'dribbles_success': stats.dribbles_success or 0,
                    'fouls_drawn': stats.fouls_drawn or 0,
                    'fouls_committed': stats.fouls_committed or 0,
                    # Goalkeeper specific
                    'saves': stats.saves or 0,
                    'goals_conceded': stats.goals_conceded or 0,
                    # Keep nested structure for match cards (backward compat)
                    'shots': {
                        'total': stats.shots_total,
                        'on_target': stats.shots_on,
                    },
                    'passes': {
                        'total': stats.passes_total,
                        'key': stats.passes_key,
                        'accuracy': stats.passes_accuracy,
                    },
                    'tackles': {
                        'total': stats.tackles_total,
                        'blocks': stats.tackles_blocks,
                        'interceptions': stats.tackles_interceptions,
                    },
                    'duels': {
                        'total': stats.duels_total,
                        'won': stats.duels_won,
                    },
                    'dribbles': {
                        'attempts': stats.dribbles_attempts,
                        'success': stats.dribbles_success,
                    },
                    'fouls': {
                        'drawn': stats.fouls_drawn,
                        'committed': stats.fouls_committed,
                    },
                }
            }
            results.append(fixture_data)
        
        return results
    except Exception as e:
        logger.warning(f"Failed to get player week stats: {e}")
        # Rollback to handle PostgreSQL aborted transaction state
        try:
            db.session.rollback()
        except Exception:
            pass
        return []


# Available stat keys for charts
AVAILABLE_CHART_STATS = {
    'basic': ['minutes', 'rating'],
    'attacking': ['goals', 'assists', 'shots_total', 'shots_on'],
    'passing': ['passes_total', 'passes_key', 'passes_accuracy'],
    'defending': ['tackles_total', 'tackles_blocks', 'tackles_interceptions'],
    'duels': ['duels_total', 'duels_won'],
    'discipline': ['yellows', 'reds'],
    'goalkeeper': ['saves', 'goals_conceded'],
    'dribbles': ['dribbles_attempts', 'dribbles_success'],
}

ALL_STAT_KEYS = [stat for stats in AVAILABLE_CHART_STATS.values() for stat in stats]


def _aggregate_player_stats(fixtures_data: list, stat_keys: list, average_stats: bool = False) -> dict:
    """Aggregate player stats across multiple fixtures for radar/bar charts.
    
    Args:
        fixtures_data: List of fixture data with stats
        stat_keys: List of stat keys to aggregate
        average_stats: If True, return averages instead of totals (useful for radar charts)
    """
    if not fixtures_data:
        return {}
    
    aggregated = {key: 0 for key in stat_keys}
    counts = {key: 0 for key in stat_keys}
    
    for fixture in fixtures_data:
        stats = fixture.get('stats', {})
        for key in stat_keys:
            # Handle nested stats (e.g., shots.total)
            if key in stats:
                val = stats[key]
                if val is not None:
                    aggregated[key] += val
                    counts[key] += 1
            elif '_' in key:
                # Try nested lookup: shots_total -> stats.shots.total
                parts = key.split('_')
                nested = stats.get(parts[0], {})
                if isinstance(nested, dict):
                    nested_key = '_'.join(parts[1:]) if len(parts) > 2 else parts[1]
                    # Map common suffixes
                    key_map = {'total': 'total', 'on': 'on_target', 'key': 'key', 
                              'blocks': 'blocks', 'interceptions': 'interceptions',
                              'won': 'won', 'attempts': 'attempts', 'success': 'success'}
                    lookup_key = key_map.get(parts[-1], parts[-1])
                    val = nested.get(lookup_key)
                    if val is not None:
                        aggregated[key] += val
                        counts[key] += 1
    
    # Rating is always averaged
    if 'rating' in aggregated and counts.get('rating', 0) > 0:
        aggregated['rating'] = round(aggregated['rating'] / counts['rating'], 2)
    
    # If averaging requested (for radar charts), convert all sums to averages
    if average_stats:
        for key in stat_keys:
            if key != 'rating' and counts.get(key, 0) > 0:  # Rating already averaged
                aggregated[key] = round(aggregated[key] / counts[key], 2)
    
    return aggregated


def _get_season_stats(player_id: int, season: int = None) -> list:
    """Get all player stats for a season."""
    from src.models.weekly import FixturePlayerStats, Fixture
    
    if not player_id:
        return []
    
    try:
        player_id = int(player_id)
    except Exception:
        # If the player id cannot be coerced, skip stats to avoid DB errors
        return []
    
    try:
        query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_id
        )
        
        if season:
            query = query.filter(Fixture.season == season)
        
        query = query.order_by(Fixture.date_utc.asc())
        stats_query = query.all()
        
        results = []
        for stats, fixture in stats_query:
            home_team = Team.query.filter_by(team_id=fixture.home_team_api_id).first()
            away_team = Team.query.filter_by(team_id=fixture.away_team_api_id).first()
            is_home = stats.team_api_id == fixture.home_team_api_id
            
            fixture_data = {
                'fixture_id': fixture.fixture_id_api,
                'date': fixture.date_utc.isoformat() if fixture.date_utc else None,
                'competition': fixture.competition_name,
                'home_team': {
                    'name': home_team.name if home_team else 'Unknown',
                    'logo': home_team.logo if home_team else None,
                    'score': fixture.home_goals,
                },
                'away_team': {
                    'name': away_team.name if away_team else 'Unknown',
                    'logo': away_team.logo if away_team else None,
                    'score': fixture.away_goals,
                },
                'is_home': is_home,
                'stats': {
                    # Basic stats (flat)
                    'minutes': stats.minutes or 0,
                    'position': stats.position,
                    'rating': stats.rating,
                    'goals': stats.goals or 0,
                    'assists': stats.assists or 0,
                    'yellows': stats.yellows or 0,
                    'reds': stats.reds or 0,
                    'substitute': stats.substitute,
                    # Flat keys for chart compatibility
                    'shots_total': stats.shots_total or 0,
                    'shots_on': stats.shots_on or 0,
                    'passes_total': stats.passes_total or 0,
                    'passes_key': stats.passes_key or 0,
                    'passes_accuracy': stats.passes_accuracy or 0,
                    'tackles_total': stats.tackles_total or 0,
                    'tackles_blocks': stats.tackles_blocks or 0,
                    'tackles_interceptions': stats.tackles_interceptions or 0,
                    'duels_total': stats.duels_total or 0,
                    'duels_won': stats.duels_won or 0,
                    'dribbles_attempts': stats.dribbles_attempts or 0,
                    'dribbles_success': stats.dribbles_success or 0,
                    'fouls_drawn': stats.fouls_drawn or 0,
                    'fouls_committed': stats.fouls_committed or 0,
                    # Goalkeeper specific
                    'saves': stats.saves or 0,
                    'goals_conceded': stats.goals_conceded or 0,
                    # Keep nested structure for match cards (backward compat)
                    'shots': {
                        'total': stats.shots_total,
                        'on_target': stats.shots_on,
                    },
                    'passes': {
                        'total': stats.passes_total,
                        'key': stats.passes_key,
                        'accuracy': stats.passes_accuracy,
                    },
                    'tackles': {
                        'total': stats.tackles_total,
                        'blocks': stats.tackles_blocks,
                        'interceptions': stats.tackles_interceptions,
                    },
                    'duels': {
                        'total': stats.duels_total,
                        'won': stats.duels_won,
                    },
                    'dribbles': {
                        'attempts': stats.dribbles_attempts,
                        'success': stats.dribbles_success,
                    },
                    'fouls': {
                        'drawn': stats.fouls_drawn,
                        'committed': stats.fouls_committed,
                    },
                }
            }
            results.append(fixture_data)
        
        return results
    except Exception as e:
        logger.warning(f"Failed to get season stats: {e}")
        # Rollback to handle PostgreSQL aborted transaction state
        try:
            db.session.rollback()
        except Exception:
            pass
        return []


def _get_primary_position(fixtures_data: list) -> str:
    """Determine the player's most common position from fixtures."""
    if not fixtures_data:
        return 'Unknown'
    
    positions = {}
    for fixture in fixtures_data:
        pos = fixture.get('stats', {}).get('position')
        if pos:
            positions[pos] = positions.get(pos, 0) + 1
    
    if not positions:
        return 'Unknown'
    
    # Return most frequent position
    return max(positions, key=positions.get)


def _categorize_position(position: str) -> str:
    """Categorize position into Forward, Midfielder, Defender, or Goalkeeper."""
    if not position:
        return 'Midfielder'  # Default
    
    pos_upper = position.upper()
    
    # Goalkeeper
    if pos_upper in ('G', 'GK', 'GOALKEEPER'):
        return 'Goalkeeper'
    
    # Defenders
    if any(x in pos_upper for x in ('CB', 'LB', 'RB', 'LWB', 'RWB', 'DEFENDER', 'BACK')):
        return 'Defender'
    
    # Forwards/Attackers
    if any(x in pos_upper for x in ('ST', 'CF', 'LW', 'RW', 'FORWARD', 'STRIKER', 'WINGER', 'F')):
        return 'Forward'
    
    # Midfielders (CDM, CM, CAM, LM, RM, etc.)
    if any(x in pos_upper for x in ('M', 'MID', 'DM', 'AM', 'CM', 'CDM', 'CAM')):
        return 'Midfielder'
    
    return 'Midfielder'  # Default fallback


def _get_position_max_values(position_category: str) -> dict:
    """Get position-appropriate max values for stat normalization.
    
    These represent realistic top-end per-game averages for each position.
    """
    # Base values that apply to all positions
    base = {
        'minutes': 90,
        'rating': 10,
        'yellows': 1,
        'reds': 1,
        'fouls_drawn': 4,
        'fouls_committed': 3,
    }
    
    if position_category == 'Forward':
        return {
            **base,
            'goals': 1.5,           # Elite strikers average ~0.7-1 per game
            'assists': 0.8,         # Decent but not primary creator
            'shots_total': 5,       # High volume
            'shots_on': 3,          # Good accuracy expected
            'passes_total': 35,     # Lower involvement
            'passes_key': 2,        # Some creativity
            'passes_accuracy': 85,  # Less pressured passes
            'tackles_total': 1.5,   # Minimal defensive work
            'tackles_blocks': 0.5,
            'tackles_interceptions': 0.5,
            'duels_total': 12,      # Physical battles
            'duels_won': 6,
            'dribbles_attempts': 5, # Key skill for forwards
            'dribbles_success': 3,
            'saves': 0,
            'goals_conceded': 0,
        }
    
    elif position_category == 'Midfielder':
        return {
            **base,
            'goals': 0.5,           # Occasional goals
            'assists': 0.6,         # Creative role
            'shots_total': 2,       # Moderate
            'shots_on': 1,
            'passes_total': 55,     # High involvement
            'passes_key': 2.5,      # Playmaking
            'passes_accuracy': 88,  # Good retention
            'tackles_total': 3,     # Defensive duties
            'tackles_blocks': 1,
            'tackles_interceptions': 2,
            'duels_total': 15,      # Heavy involvement
            'duels_won': 8,
            'dribbles_attempts': 3,
            'dribbles_success': 2,
            'saves': 0,
            'goals_conceded': 0,
        }
    
    elif position_category == 'Defender':
        return {
            **base,
            'goals': 0.15,          # Rare
            'assists': 0.2,         # Occasional from crosses
            'shots_total': 1,       # Minimal
            'shots_on': 0.5,
            'passes_total': 60,     # Building from back
            'passes_key': 1,        # Long balls
            'passes_accuracy': 85,  # Under pressure
            'tackles_total': 4,     # Primary job
            'tackles_blocks': 2,    # Key defensive stat
            'tackles_interceptions': 3,  # Reading the game
            'duels_total': 12,      # Aerial and ground
            'duels_won': 7,
            'dribbles_attempts': 1,
            'dribbles_success': 0.5,
            'saves': 0,
            'goals_conceded': 0,
        }
    
    elif position_category == 'Goalkeeper':
        return {
            **base,
            'goals': 0.01,          # Almost never
            'assists': 0.05,        # Long kicks occasionally
            'shots_total': 0,
            'shots_on': 0,
            'passes_total': 35,     # Distribution
            'passes_key': 0.5,      # Launch balls
            'passes_accuracy': 75,  # Long kicks lower accuracy
            'tackles_total': 0.2,   # Rare
            'tackles_blocks': 0,
            'tackles_interceptions': 0.3,
            'duels_total': 2,       # 1v1s
            'duels_won': 1.5,
            'dribbles_attempts': 0,
            'dribbles_success': 0,
            'saves': 4,             # Key GK stat
            'goals_conceded': 1.5,  # Lower is better - inverted later
        }
    
    # Default fallback
    return {
        **base,
        'goals': 0.5, 'assists': 0.5, 'shots_total': 3, 'shots_on': 1.5,
        'passes_total': 50, 'passes_key': 2, 'passes_accuracy': 85,
        'tackles_total': 3, 'tackles_blocks': 1, 'tackles_interceptions': 2,
        'duels_total': 12, 'duels_won': 6, 'dribbles_attempts': 2,
        'dribbles_success': 1, 'saves': 0, 'goals_conceded': 0,
    }


@journalist_bp.route('/journalists/chart-data', methods=['GET'])
def get_chart_data():
    """Fetch aggregated player stats for chart rendering.
    
    Query Parameters:
    - player_id (int, required): The player's API ID
    - chart_type (str): Type of chart - radar, bar, line, match_card, stat_table
    - stat_keys (list): Comma-separated stat keys to include
    - date_range (str): week, month, or season
    - week_start (str): ISO date for week start (required if date_range=week)
    - week_end (str): ISO date for week end (required if date_range=week)
    
    Returns aggregated data appropriate for the requested chart type.
    """
    try:
        player_id = request.args.get('player_id', type=int)
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400
        
        chart_type = request.args.get('chart_type', 'match_card')
        stat_keys_param = request.args.get('stat_keys', '')
        date_range = request.args.get('date_range', 'week')
        
        # Parse stat keys
        stat_keys = [k.strip() for k in stat_keys_param.split(',') if k.strip()]
        if not stat_keys:
            # Default stats based on chart type
            if chart_type == 'radar':
                stat_keys = ['rating', 'goals', 'assists', 'passes_key', 'tackles_total', 'duels_won']
            elif chart_type in ('bar', 'line'):
                stat_keys = ['goals', 'assists', 'rating']
            else:
                stat_keys = ALL_STAT_KEYS[:10]  # First 10 stats
        
        # Validate stat keys
        stat_keys = [k for k in stat_keys if k in ALL_STAT_KEYS]
        
        # Get fixtures data based on date range
        fixtures_data = []
        
        if date_range == 'week':
            week_start = request.args.get('week_start')
            week_end = request.args.get('week_end')
            if week_start and week_end:
                from datetime import date
                try:
                    start_date = datetime.fromisoformat(week_start).date() if isinstance(week_start, str) else week_start
                    end_date = datetime.fromisoformat(week_end).date() if isinstance(week_end, str) else week_end
                    fixtures_data = _get_player_week_stats(player_id, start_date, end_date)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid date format: {e}")
            else:
                return jsonify({'error': 'week_start and week_end required for date_range=week'}), 400
        
        elif date_range == 'month':
            from datetime import timedelta
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=30)
            fixtures_data = _get_player_week_stats(player_id, start_date, end_date)
        
        elif date_range == 'season':
            # Get current season (assume July-June cycle)
            now_utc = datetime.now(timezone.utc)
            current_year = now_utc.year
            current_month = now_utc.month
            season = current_year if current_month >= 7 else current_year - 1
            fixtures_data = _get_season_stats(player_id, season)
        
        # Get player info
        player_info = None
        lp = LoanedPlayer.query.filter_by(player_id=player_id).order_by(LoanedPlayer.updated_at.desc()).first()
        if lp:
            player_info = {
                'player_id': lp.player_id,
                'name': lp.player_name,
                'loan_team': lp.loan_team_name,
            }
        else:
            p = Player.query.filter_by(player_id=player_id).first()
            if p:
                player_info = {
                    'player_id': p.player_id,
                    'name': p.name,
                }
        
        # Format response based on chart type
        response = {
            'player': player_info,
            'chart_type': chart_type,
            'date_range': date_range,
            'stat_keys': stat_keys,
            'available_stats': AVAILABLE_CHART_STATS,
        }
        
        if chart_type == 'match_card':
            # Return raw fixture data for match cards
            response['fixtures'] = fixtures_data
        
        elif chart_type == 'radar':
            # Aggregate stats for radar chart (use averages per game for fair comparison)
            aggregated = _aggregate_player_stats(fixtures_data, stat_keys, average_stats=True)
            totals = _aggregate_player_stats(fixtures_data, stat_keys, average_stats=False)
            
            # Determine player's primary position from fixtures
            player_position = _get_primary_position(fixtures_data)
            position_category = _categorize_position(player_position)
            
            # Position-based max values for realistic normalization
            stat_max_values = _get_position_max_values(position_category)
            
            response['position'] = player_position
            response['position_category'] = position_category
            response['data'] = [
                {
                    'stat': key,
                    'value': aggregated.get(key, 0),  # Average per game
                    'total': totals.get(key, 0),      # Total across all matches
                    'label': key.replace('_', ' ').title(),
                    'max_value': stat_max_values.get(key, 5),  # Position-adjusted max
                    'normalized': min(100, round((aggregated.get(key, 0) / max(stat_max_values.get(key, 5), 0.1)) * 100, 1))
                }
                for key in stat_keys
            ]
            response['matches_count'] = len(fixtures_data)
        
        elif chart_type == 'bar':
            # Per-match data for bar chart
            response['data'] = [
                {
                    'match': f"{f['home_team']['name']} vs {f['away_team']['name']}",
                    'date': f['date'],
                    **{key: f['stats'].get(key, 0) for key in stat_keys}
                }
                for f in fixtures_data
            ]
        
        elif chart_type == 'line':
            # Time series data for line chart
            response['data'] = [
                {
                    'date': f['date'],
                    'match': f"{f['home_team']['name']} vs {f['away_team']['name']}",
                    **{key: f['stats'].get(key, 0) for key in stat_keys}
                }
                for f in fixtures_data
            ]
        
        elif chart_type == 'stat_table':
            # Detailed table view
            response['data'] = [
                {
                    'date': f['date'],
                    'opponent': f['away_team']['name'] if f['is_home'] else f['home_team']['name'],
                    'is_home': f['is_home'],
                    'competition': f['competition'],
                    'result': f"{f['home_team']['score']}-{f['away_team']['score']}",
                    **f['stats']
                }
                for f in fixtures_data
            ]
            # Include totals
            totals = _aggregate_player_stats(fixtures_data, stat_keys)
            response['totals'] = totals
            response['matches_count'] = len(fixtures_data)
        
        return jsonify(response)
    
    except Exception as e:
        logger.exception('Failed to get chart data')
        return jsonify(_safe_error_payload(e, 'Failed to fetch chart data')), 500


@journalist_bp.route('/journalists/commentaries/<int:commentary_id>', methods=['GET'])
def get_commentary_public(commentary_id: int):
    """Public endpoint to fetch a single commentary with fallback metadata.

    - If premium and requester is not subscribed, content is previewed.
    - Includes resolved team/logo and best-effort player info (name/photo) when available.
    - For player commentaries, includes player stats for the week's fixtures.
    """
    try:
        commentary = NewsletterCommentary.query.filter_by(id=commentary_id, is_active=True).first()
        if not commentary:
            return jsonify({'error': 'Commentary not found'}), 404

        # Resolve requester subscription (optional auth)
        is_subscribed = False
        user = None
        try:
            email = getattr(g, 'user_email', None)
            if email:
                user = UserAccount.query.filter_by(email=email).first()
        except Exception:
            pass
        if user:
            sub = JournalistSubscription.query.filter_by(
                subscriber_user_id=user.id,
                journalist_user_id=commentary.author_id,
                is_active=True
            ).first()
            is_subscribed = bool(sub)

        data = commentary.to_dict()

        # If premium and not subscribed, mask content to preview
        if commentary.is_premium and not is_subscribed:
            clean_text = re.sub('<[^<]+?>', '', data['content'] or '')
            data['content'] = clean_text[:200] + ('...' if len(clean_text) > 200 else '')
            data['is_locked'] = True
        else:
            data['is_locked'] = False

        # Attach team details
        team = Team.query.get(commentary.team_id) if commentary.team_id else None
        if team:
            data['team'] = {
                'id': team.id,
                'team_id': team.team_id,
                'name': team.name,
                'logo': team.logo,
                'season': team.season,
            }

        # Try to resolve player info and get week stats
        player_info = None
        week_stats = []
        
        if commentary.player_id:
            # First look in LoanedPlayer for current season
            lp = LoanedPlayer.query.filter_by(player_id=commentary.player_id).order_by(LoanedPlayer.updated_at.desc()).first()
            # Also try to get photo from Player table
            p = Player.query.filter_by(player_id=commentary.player_id).first()
            photo_url = p.photo_url if p else None
            
            if lp:
                # Get loan team logo if available
                loan_team_logo = None
                if lp.loan_team_id:
                    loan_team = Team.query.get(lp.loan_team_id)
                    if loan_team:
                        loan_team_logo = loan_team.logo
                
                player_info = {
                    'player_id': lp.player_id,
                    'name': lp.player_name,
                    'nationality': lp.nationality,
                    'photo_url': photo_url,
                    'loan_team': lp.loan_team_name,
                    'loan_team_logo': loan_team_logo,
                    'age': lp.age,
                }
            elif p:
                player_info = {
                    'player_id': p.player_id,
                    'name': p.name,
                    'nationality': p.nationality,
                    'photo_url': photo_url,
                }
            
            # Get player stats for this week's fixtures
            if commentary.week_start_date and commentary.week_end_date:
                week_stats = _get_player_week_stats(
                    commentary.player_id,
                    commentary.week_start_date,
                    commentary.week_end_date
                )
        
        if player_info:
            data['player'] = player_info
        if week_stats:
            data['week_fixtures'] = week_stats

        # Get author info
        author = UserAccount.query.get(commentary.author_id)
        if author:
            data['author'] = {
                'id': author.id,
                'display_name': author.display_name,
                'bio': author.bio,
                'profile_image_url': author.profile_image_url,
            }

        # Provide link to newsletter if it exists
        if commentary.newsletter_id:
            n = Newsletter.query.get(commentary.newsletter_id)
            if n:
                data['newsletter_id'] = n.id
                data['newsletter_public_slug'] = n.public_slug

        return jsonify(data)

    except Exception as e:
        logger.exception('Failed to fetch commentary')
        return jsonify(_safe_error_payload(e, 'Failed to fetch commentary')), 500

@journalist_bp.route('/my-subscriptions', methods=['GET'])
@require_user_auth
def get_my_subscriptions():
    """Get list of journalists the current user is subscribed to."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        subs = JournalistSubscription.query.filter_by(
            subscriber_user_id=user.id,
            is_active=True
        ).all()
        
        # Return journalist details
        result = []
        for sub in subs:
            journalist = UserAccount.query.get(sub.journalist_user_id)
            if journalist:
                data = journalist.to_dict()
                data['subscription_id'] = sub.id
                result.append(data)
                
        return jsonify(result)

    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch subscriptions')), 500

# --- Writer Platform Endpoints ---

@journalist_bp.route('/writer/loan-destinations', methods=['GET'])
@require_user_auth
def get_loan_destinations():
    """Get list of active loan destinations with player counts."""
    try:
        # Group by loan team name and ID
        # We use loan_team_name as the primary grouping since ID might be null for some
        results = db.session.query(
            LoanedPlayer.loan_team_name,
            LoanedPlayer.loan_team_id,
            func.count(LoanedPlayer.id).label('player_count')
        ).filter(
            LoanedPlayer.is_active.is_(True),
            LoanedPlayer.loan_team_name.isnot(None),
            LoanedPlayer.loan_team_name != ''
        ).group_by(
            LoanedPlayer.loan_team_name,
            LoanedPlayer.loan_team_id
        ).order_by(
            func.count(LoanedPlayer.id).desc()
        ).all()

        destinations = []
        for r in results:
            destinations.append({
                'name': r.loan_team_name,
                'team_id': r.loan_team_id,
                'player_count': r.player_count
            })

        return jsonify({'destinations': destinations})

    except Exception as e:
        logger.exception('Failed to fetch loan destinations')
        return jsonify({'error': 'Failed to fetch loan destinations'}), 500


@journalist_bp.route('/writer/profile', methods=['GET'])
@require_user_auth
def get_writer_profile():
    """Get current writer's profile data."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
            
        return jsonify({
            'bio': user.bio,
            'profile_image_url': user.profile_image_url,
            'attribution_url': user.attribution_url,
            'attribution_name': user.attribution_name,
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch writer profile')), 500

@journalist_bp.route('/writer/profile', methods=['POST'])
@require_user_auth
def update_writer_profile():
    """Update current writer's profile data."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
            
        data = request.get_json() or {}
        
        if 'bio' in data:
            user.bio = data.get('bio', '').strip()
            
        if 'profile_image_url' in data:
            user.profile_image_url = data.get('profile_image_url', '').strip()

        if 'attribution_url' in data:
            url = data.get('attribution_url', '').strip()
            # Basic validation
            if url and not (url.startswith('http://') or url.startswith('https://')):
                url = 'https://' + url
            user.attribution_url = url
            
        if 'attribution_name' in data:
            user.attribution_name = data.get('attribution_name', '').strip()
            
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated',
            'user': user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update writer profile')), 500

@journalist_bp.route('/writer/teams', methods=['GET'])
@require_user_auth
def get_writer_teams():
    """Get teams assigned to the current writer (both parent clubs and loan teams)."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
        
        # Get parent club assignments (existing)
        parent_assignments = JournalistTeamAssignment.query.filter_by(user_id=user.id).all()
        
        # Get loan team assignments (new)
        loan_assignments = JournalistLoanTeamAssignment.query.filter_by(user_id=user.id).all()
        
        return jsonify({
            'parent_club_assignments': [a.to_dict() for a in parent_assignments],
            'loan_team_assignments': [a.to_dict() for a in loan_assignments],
            # Legacy format for backwards compatibility
            'assignments': [a.to_dict() for a in parent_assignments]
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch assigned teams')), 500


@journalist_bp.route('/writer/available-players', methods=['GET'])
@require_user_auth
def get_writer_available_players_endpoint():
    """Get all players the current writer can cover based on their assignments."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
        
        players = get_writer_available_players(user.id)
        
        # Group players by how they're accessible
        result = {
            'players': [],
            'by_parent_club': {},
            'by_loan_team': {}
        }
        
        # Get writer's assignments for grouping
        parent_assignments = JournalistTeamAssignment.query.filter_by(user_id=user.id).all()
        parent_team_ids = {a.team_id for a in parent_assignments}
        
        loan_assignments = JournalistLoanTeamAssignment.query.filter_by(user_id=user.id).all()
        loan_team_ids = {a.loan_team_id for a in loan_assignments if a.loan_team_id}
        loan_team_names = {a.loan_team_name for a in loan_assignments}
        
        for player in players:
            player_data = player.to_dict()
            result['players'].append(player_data)
            
            # Group by parent club if writer is assigned to parent
            if player.primary_team_id in parent_team_ids:
                team_name = player.primary_team_name
                if team_name not in result['by_parent_club']:
                    result['by_parent_club'][team_name] = []
                result['by_parent_club'][team_name].append(player_data)
            
            # Group by loan team if writer is assigned to loan team
            is_loan_covered = (
                player.loan_team_id in loan_team_ids or 
                player.loan_team_name in loan_team_names
            )
            if is_loan_covered:
                team_name = player.loan_team_name
                if team_name not in result['by_loan_team']:
                    result['by_loan_team'][team_name] = []
                result['by_loan_team'][team_name].append(player_data)
        
        return jsonify(result)
    except Exception as e:
        logger.exception('Failed to fetch available players')
        return jsonify(_safe_error_payload(e, 'Failed to fetch available players')), 500

@journalist_bp.route('/writer/commentaries', methods=['GET'])
@require_user_auth
def get_writer_commentaries():
    """Get commentaries authored by the current writer."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
            
        commentaries = NewsletterCommentary.query.filter_by(author_id=user.id).order_by(NewsletterCommentary.created_at.desc()).all()
        return jsonify([c.to_dict() for c in commentaries])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch commentaries')), 500

def _validate_structured_blocks(blocks: list) -> tuple[bool, str]:
    """Validate structured blocks array.
    
    Returns (is_valid, error_message).
    """
    if not isinstance(blocks, list):
        return False, "structured_blocks must be an array"
    
    valid_types = {'text', 'chart', 'divider'}
    valid_chart_types = {'match_card', 'radar', 'bar', 'line', 'stat_table'}
    
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            return False, f"Block {i} must be an object"
        
        block_type = block.get('type')
        if block_type not in valid_types:
            return False, f"Block {i} has invalid type '{block_type}'"
        
        if 'id' not in block:
            return False, f"Block {i} missing required 'id' field"
        
        if block_type == 'text' and 'content' not in block:
            return False, f"Text block {i} missing 'content' field"
        
        if block_type == 'chart':
            chart_type = block.get('chart_type')
            if chart_type not in valid_chart_types:
                return False, f"Block {i} has invalid chart_type '{chart_type}'"
            if 'chart_config' not in block:
                return False, f"Chart block {i} missing 'chart_config' field"
    
    return True, ""


def _render_blocks_to_html(blocks: list, player_id: int = None, week_start: str = None, week_end: str = None) -> str:
    """Render structured blocks to HTML for backwards compatibility.
    
    Text blocks are included directly, chart blocks are rendered as static images
    for email compatibility.
    
    Args:
        blocks: List of content blocks
        player_id: Player ID for chart data fetching
        week_start: Week start date (ISO format)
        week_end: Week end date (ISO format)
    """
    from src.utils.sanitize import sanitize_commentary_html
    
    html_parts = []
    for block in blocks:
        block_type = block.get('type')
        
        if block_type == 'text':
            content = block.get('content', '')
            html_parts.append(sanitize_commentary_html(content))
        
        elif block_type == 'chart':
            # Render chart as static image for email
            chart_html = _render_chart_block_to_html(block, player_id, week_start, week_end)
            html_parts.append(chart_html)
        
        elif block_type == 'divider':
            html_parts.append('<hr class="content-divider" />')
    
    return '\n'.join(html_parts)


def _render_chart_block_to_html(block: dict, player_id: int = None, week_start: str = None, week_end: str = None) -> str:
    """Render a chart block as a static image embedded in HTML.
    
    Args:
        block: Chart block configuration
        player_id: Player ID (from commentary or block config)
        week_start: Week start date
        week_end: Week end date
        
    Returns:
        HTML string with embedded chart image or fallback placeholder
    """
    try:
        from src.services.chart_renderer import render_chart_to_base64
        
        chart_type = block.get('chart_type', 'bar')
        chart_config = block.get('chart_config', {})
        
        # Get player_id from block config if not provided at commentary level
        effective_player_id = player_id or chart_config.get('player_id')
        
        if not effective_player_id:
            # Can't render chart without player data
            return _get_chart_placeholder_html(chart_type, "Player data not available")
        
        # Ensure player_id is an integer to avoid PostgreSQL type mismatch errors
        try:
            effective_player_id = int(effective_player_id)
        except (ValueError, TypeError):
            return _get_chart_placeholder_html(chart_type, "Invalid player data")
        
        # Fetch chart data
        chart_data = _fetch_chart_data_for_rendering(
            player_id=effective_player_id,
            chart_type=chart_type,
            stat_keys=chart_config.get('stat_keys', ['goals', 'assists', 'rating']),
            date_range=chart_config.get('date_range', 'week'),
            week_start=week_start,
            week_end=week_end
        )
        
        if not chart_data:
            return _get_chart_placeholder_html(chart_type, "No data available")
        
        # Render chart to base64 image
        image_data_url = render_chart_to_base64(chart_type, chart_data, width=480, height=300)
        
        # Return HTML with embedded image
        return f'''
        <div class="chart-image" style="margin: 16px 0; text-align: center;">
            <img src="{image_data_url}" alt="{chart_type.replace('_', ' ').title()} Chart" 
                 style="max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #e5e7eb;" />
        </div>
        '''
    except Exception as e:
        logger.warning(f"Failed to render chart image: {e}")
        chart_type = block.get('chart_type', 'chart')
        return _get_chart_placeholder_html(chart_type, "Chart unavailable")


def _get_chart_placeholder_html(chart_type: str, message: str = None) -> str:
    """Get a styled placeholder HTML for charts that can't be rendered."""
    display_name = chart_type.replace('_', ' ').title()
    msg = message or f"View {display_name} in the web version"
    return f'''
    <div class="chart-placeholder" style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); 
         border: 2px dashed #cbd5e1; border-radius: 8px; padding: 24px; margin: 16px 0; text-align: center;">
        <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
        <div style="font-weight: 600; color: #475569; margin-bottom: 4px;">{display_name}</div>
        <div style="font-size: 13px; color: #94a3b8;">{msg}</div>
    </div>
    '''


def _fetch_chart_data_for_rendering(player_id: int, chart_type: str, stat_keys: list,
                                     date_range: str, week_start: str = None, week_end: str = None) -> dict:
    """Fetch chart data for server-side rendering.
    
    This mirrors the logic in the get_chart_data API endpoint but for internal use.
    """
    try:
        try:
            player_id = int(player_id)
        except Exception:
            return None

        from datetime import date, timedelta
        
        # Get fixtures data based on date range
        fixtures_data = []
        
        if date_range == 'week' and week_start and week_end:
            try:
                start_date = datetime.fromisoformat(week_start).date() if isinstance(week_start, str) else week_start
                end_date = datetime.fromisoformat(week_end).date() if isinstance(week_end, str) else week_end
                fixtures_data = _get_player_week_stats(player_id, start_date, end_date)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid date format for chart rendering: {e}")
                return None
        elif date_range == 'month':
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=30)
            fixtures_data = _get_player_week_stats(player_id, start_date, end_date)
        elif date_range == 'season':
            now_utc = datetime.now(timezone.utc)
            current_year = now_utc.year
            current_month = now_utc.month
            season = current_year if current_month >= 7 else current_year - 1
            fixtures_data = _get_season_stats(player_id, season)
        else:
            # Default to last 30 days if no specific range
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=30)
            fixtures_data = _get_player_week_stats(player_id, start_date, end_date)
        
        if not fixtures_data:
            return None
        
        # Get player info
        player_info = None
        lp = LoanedPlayer.query.filter_by(player_id=player_id).order_by(LoanedPlayer.updated_at.desc()).first()
        if lp:
            player_info = {
                'player_id': lp.player_id,
                'name': lp.player_name,
                'loan_team': lp.loan_team_name,
            }
        else:
            p = Player.query.filter_by(player_id=player_id).first()
            if p:
                player_info = {
                    'player_id': p.player_id,
                    'name': p.name,
                }
        
        # Format response based on chart type
        response = {
            'player': player_info,
            'chart_type': chart_type,
            'date_range': date_range,
            'stat_keys': stat_keys,
        }
        
        if chart_type == 'match_card':
            response['fixtures'] = fixtures_data
        
        elif chart_type == 'radar':
            aggregated = _aggregate_player_stats(fixtures_data, stat_keys, average_stats=True)
            totals = _aggregate_player_stats(fixtures_data, stat_keys, average_stats=False)
            player_position = _get_primary_position(fixtures_data)
            position_category = _categorize_position(player_position)
            stat_max_values = _get_position_max_values(position_category)
            
            response['position'] = player_position
            response['position_category'] = position_category
            response['data'] = [
                {
                    'stat': key,
                    'value': aggregated.get(key, 0),
                    'total': totals.get(key, 0),
                    'label': key.replace('_', ' ').title(),
                    'max_value': stat_max_values.get(key, 5),
                    'normalized': min(100, round((aggregated.get(key, 0) / max(stat_max_values.get(key, 5), 0.1)) * 100, 1))
                }
                for key in stat_keys
            ]
            response['matches_count'] = len(fixtures_data)
        
        elif chart_type == 'bar':
            response['data'] = [
                {
                    'match': f"{f['home_team']['name']} vs {f['away_team']['name']}",
                    'date': f['date'],
                    **{key: f['stats'].get(key, 0) for key in stat_keys}
                }
                for f in fixtures_data
            ]
        
        elif chart_type == 'line':
            response['data'] = [
                {
                    'date': f['date'],
                    'match': f"{f['home_team']['name']} vs {f['away_team']['name']}",
                    **{key: f['stats'].get(key, 0) for key in stat_keys}
                }
                for f in fixtures_data
            ]
        
        elif chart_type == 'stat_table':
            response['data'] = [
                {
                    'date': f['date'],
                    'opponent': f['away_team']['name'] if f['is_home'] else f['home_team']['name'],
                    'is_home': f['is_home'],
                    'competition': f['competition'],
                    'result': f"{f['home_team']['score']}-{f['away_team']['score']}",
                    **f['stats']
                }
                for f in fixtures_data
            ]
            totals = _aggregate_player_stats(fixtures_data, stat_keys)
            response['totals'] = totals
            response['matches_count'] = len(fixtures_data)
        
        return response
        
    except Exception as e:
        logger.exception(f"Failed to fetch chart data for rendering: {e}")
        # Rollback to handle PostgreSQL aborted transaction state
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


@journalist_bp.route('/writer/commentaries', methods=['POST'])
@require_user_auth
def create_update_commentary():
    """Create or update a commentary.
    
    Supports both legacy single-content format and new structured_blocks format.
    If structured_blocks is provided, it takes precedence and the rendered HTML
    is stored in the content field for backwards compatibility.
    """
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
            
        data = request.get_json() or {}
        
        # If ID provided, update
        commentary_id = data.get('id')
        if commentary_id:
            commentary = NewsletterCommentary.query.filter_by(id=commentary_id).first()
            if not commentary:
                return jsonify({'error': 'Commentary not found'}), 404
            if commentary.author_id != user.id:
                return jsonify({'error': 'Not authorized to edit this commentary'}), 403
            
            # Handle structured_blocks if provided
            if 'structured_blocks' in data:
                blocks = data['structured_blocks']
                if blocks:
                    is_valid, error_msg = _validate_structured_blocks(blocks)
                    if not is_valid:
                        return jsonify({'error': error_msg}), 400
                    
                    # Store blocks and render to HTML with chart images
                    commentary.structured_blocks = blocks
                    commentary.content = _render_blocks_to_html(
                        blocks,
                        player_id=commentary.player_id,
                        week_start=commentary.week_start_date.isoformat() if commentary.week_start_date else None,
                        week_end=commentary.week_end_date.isoformat() if commentary.week_end_date else None
                    )
                    
                    # Determine global is_premium from blocks (premium if ANY block is premium)
                    commentary.is_premium = any(b.get('is_premium', False) for b in blocks)
                else:
                    commentary.structured_blocks = None
                    
            # Update other fields
            elif 'content' in data:
                from src.utils.sanitize import sanitize_commentary_html
                commentary.content = sanitize_commentary_html(data['content'])
                
            if 'title' in data:
                commentary.title = data['title']
            if 'player_id' in data:
                # Allow changing player (empty string or None means no player)
                player_id = data['player_id']
                commentary.player_id = int(player_id) if player_id else None
            if 'commentary_type' in data:
                new_type = data['commentary_type']
                if new_type not in ('player', 'intro', 'summary'):
                    return jsonify({'error': 'commentary_type must be "player", "intro", or "summary"'}), 400
                if new_type == 'player' and not commentary.player_id:
                    return jsonify({'error': 'player_id is required for player commentary'}), 400
                commentary.commentary_type = new_type
                # Re-validate after type change
                commentary.validate_commentary_type()
                commentary.validate_player_commentary()
            if 'is_premium' in data and 'structured_blocks' not in data:
                commentary.is_premium = bool(data['is_premium'])
            if 'is_active' in data:
                commentary.is_active = bool(data['is_active'])
            if 'week_start_date' in data:
                from datetime import date
                commentary.week_start_date = date.fromisoformat(data['week_start_date']) if data['week_start_date'] else None
            if 'week_end_date' in data:
                from datetime import date
                commentary.week_end_date = date.fromisoformat(data['week_end_date']) if data['week_end_date'] else None
                
            commentary.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return jsonify(commentary.to_dict())
            
        # Create new commentary
        team_id = data.get('team_id')
        if not team_id:
            return jsonify({'error': 'team_id is required'}), 400
            
        try:
            team_id = int(team_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid team_id format'}), 400
        
        # Get player_id for access check
        player_id_for_check = data.get('player_id')
        if player_id_for_check == "":
            player_id_for_check = None
        try:
            player_id_for_check = int(player_id_for_check) if player_id_for_check else None
        except (ValueError, TypeError):
            player_id_for_check = None
        
        commentary_type = data.get('commentary_type', 'summary')
        if commentary_type not in ('player', 'intro', 'summary'):
            return jsonify({'error': 'commentary_type must be "player", "intro", or "summary"'}), 400
        if commentary_type == 'player' and not player_id_for_check:
            return jsonify({'error': 'player_id is required for player commentary'}), 400
        
        # Access check based on commentary type
        # For player commentaries: check if writer can cover the player (parent club OR loan team)
        # For intro/summary: check if writer is assigned to the parent club
        has_access = False
        
        if commentary_type == 'player' and player_id_for_check:
            # Check if writer can cover this specific player
            has_access = can_writer_cover_player(user.id, player_id_for_check, team_id)
        else:
            # For team-wide content (intro/summary), require parent club assignment
            has_access = can_writer_cover_team(user.id, team_id)
        
        if not has_access:
            return jsonify({'error': 'You are not authorized to write about this team/player'}), 403

        # Resolve to latest season team id to ensure newsletter generation finds it
        # (Writer might be assigned to an older season row)
        from src.utils.team_resolver import resolve_latest_team_id
        latest_team_id = resolve_latest_team_id(team_id)
        if latest_team_id:
            team_id = latest_team_id
        
        # Parse week dates if provided
        from datetime import date
        week_start = None
        week_end = None
        if data.get('week_start_date'):
            week_start = date.fromisoformat(data['week_start_date'])
        if data.get('week_end_date'):
            week_end = date.fromisoformat(data['week_end_date'])
        
        # Try to find existing newsletter for this team and week
        newsletter_id = None
        if week_start and week_end:
            newsletter = Newsletter.query.filter(
                Newsletter.team_id == team_id,
                Newsletter.week_start_date == week_start,
                Newsletter.week_end_date == week_end
            ).first()
            if newsletter:
                newsletter_id = newsletter.id
        
        # Create commentary with or without newsletter
        from src.utils.sanitize import sanitize_commentary_html
        
        # Normalize player_id to int (or None) once
        player_id_raw = data.get('player_id')
        if player_id_raw == "":
            player_id_raw = None
        try:
            player_id_norm = int(player_id_raw) if player_id_raw is not None else None
        except Exception:
            player_id_norm = None
        
        # Handle structured_blocks if provided
        structured_blocks = data.get('structured_blocks')
        is_premium = bool(data.get('is_premium', True))
        
        if structured_blocks:
            is_valid, error_msg = _validate_structured_blocks(structured_blocks)
            if not is_valid:
                return jsonify({'error': error_msg}), 400
            # Render blocks with chart images for emails
            sanitized_content = _render_blocks_to_html(
                structured_blocks,
                player_id=player_id_norm,
                week_start=week_start.isoformat() if week_start else None,
                week_end=week_end.isoformat() if week_end else None
            )
            # Determine global is_premium from blocks
            is_premium = any(b.get('is_premium', False) for b in structured_blocks)
        else:
            sanitized_content = sanitize_commentary_html(data.get('content', ''))
            structured_blocks = None
        
        print(f"\n{'='*60}")
        print(f"[CREATE COMMENTARY DEBUG]")
        print(f"{'='*60}")
        print(f"Creating commentary with:")
        print(f"  team_id (after resolution): {team_id}")
        print(f"  player_id: {data.get('player_id')}")
        print(f"  commentary_type: {data.get('commentary_type', 'summary')}")
        print(f"  week_start_date: {week_start} (type: {type(week_start)})")
        print(f"  week_end_date: {week_end} (type: {type(week_end)})")
        print(f"  title: {data.get('title')}")
        print(f"  has_structured_blocks: {structured_blocks is not None}")
        print(f"{'='*60}\n")
            
        commentary = NewsletterCommentary(
            newsletter_id=newsletter_id,  # Can be None
            team_id=team_id,
            author_id=user.id,
            author_name=user.display_name,
            commentary_type=data.get('commentary_type', 'summary'),
            content=sanitized_content,
            structured_blocks=structured_blocks,
            player_id=player_id_norm,
            position=data.get('position', 0),
            title=data.get('title'),
            is_premium=is_premium,
            week_start_date=week_start,
            week_end_date=week_end
        )
        
        # Validate
        commentary.validate_commentary_type()
        commentary.validate_player_commentary()
        
        db.session.add(commentary)
        db.session.commit()
        
        return jsonify(commentary.to_dict()), 201
        
    except Exception as e:
        logger.exception("Failed to save commentary")
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to save commentary')), 500

@journalist_bp.route('/writer/commentaries/<int:commentary_id>', methods=['DELETE'])
@require_user_auth
def delete_writer_commentary(commentary_id):
    """Delete a commentary authored by the authenticated journalist."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401

        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403

        commentary = NewsletterCommentary.query.get(commentary_id)
        if not commentary:
            return jsonify({'error': 'Commentary not found'}), 404

        if commentary.author_id != user.id:
            return jsonify({'error': 'Not authorized to delete this commentary'}), 403

        db.session.delete(commentary)
        db.session.commit()
        return jsonify({'message': 'Commentary deleted'})
    except Exception as e:
        logger.exception("Failed to delete commentary")
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to delete commentary')), 500


# --- Writer Coverage Request Endpoints ---

@journalist_bp.route('/writer/coverage-requests', methods=['GET'])
@require_user_auth
def get_writer_coverage_requests():
    """Get coverage requests submitted by the current writer."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
        
        # Get status filter
        status = request.args.get('status')
        
        query = WriterCoverageRequest.query.filter_by(user_id=user.id)
        if status:
            query = query.filter_by(status=status)
        
        requests = query.order_by(WriterCoverageRequest.requested_at.desc()).all()
        
        return jsonify([r.to_dict() for r in requests])
    except Exception as e:
        logger.exception('Failed to fetch coverage requests')
        return jsonify(_safe_error_payload(e, 'Failed to fetch coverage requests')), 500


@journalist_bp.route('/writer/coverage-requests', methods=['POST'])
@require_user_auth
def submit_coverage_request():
    """Submit a new coverage request.
    
    Body:
        coverage_type: 'parent_club' | 'loan_team'
        team_id: Optional team database ID (if team is in our system)
        team_name: Team name (required)
        request_message: Optional message explaining why they want coverage
    """
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
        
        data = request.get_json() or {}
        
        # Validate required fields
        coverage_type = data.get('coverage_type')
        if coverage_type not in ('parent_club', 'loan_team'):
            return jsonify({'error': 'coverage_type must be "parent_club" or "loan_team"'}), 400
        
        team_name = (data.get('team_name') or '').strip()
        if not team_name:
            return jsonify({'error': 'team_name is required'}), 400
        
        # Parse optional team_id
        team_id = data.get('team_id')
        if team_id:
            try:
                team_id = int(team_id)
                # Verify team exists
                team = Team.query.get(team_id)
                if not team:
                    team_id = None  # Invalid team ID, treat as custom
            except (ValueError, TypeError):
                team_id = None
        
        # Check for duplicate pending request
        existing = WriterCoverageRequest.query.filter_by(
            user_id=user.id,
            coverage_type=coverage_type,
            team_name=team_name,
            status='pending'
        ).first()
        
        if existing:
            return jsonify({'error': 'You already have a pending request for this team'}), 400
        
        # Check if already assigned
        if coverage_type == 'parent_club' and team_id:
            existing_assignment = JournalistTeamAssignment.query.filter_by(
                user_id=user.id,
                team_id=team_id
            ).first()
            if existing_assignment:
                return jsonify({'error': 'You are already assigned to this parent club'}), 400
        elif coverage_type == 'loan_team':
            existing_loan = JournalistLoanTeamAssignment.query.filter_by(
                user_id=user.id,
                loan_team_name=team_name
            ).first()
            if existing_loan:
                return jsonify({'error': 'You are already assigned to this loan team'}), 400
        
        # Create the request
        coverage_request = WriterCoverageRequest(
            user_id=user.id,
            coverage_type=coverage_type,
            team_id=team_id,
            team_name=team_name,
            status='pending',
            request_message=data.get('request_message', '').strip() or None,
            requested_at=datetime.now(timezone.utc)
        )
        
        db.session.add(coverage_request)
        db.session.commit()
        
        logger.info(f"Writer {user.id} ({user.email}) submitted coverage request for {coverage_type}: {team_name}")
        
        return jsonify({
            'message': 'Coverage request submitted',
            'request': coverage_request.to_dict()
        }), 201
        
    except Exception as e:
        logger.exception('Failed to submit coverage request')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to submit coverage request')), 500


@journalist_bp.route('/writer/coverage-requests/<int:request_id>', methods=['DELETE'])
@require_user_auth
def cancel_coverage_request(request_id):
    """Cancel a pending coverage request."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403
        
        coverage_request = WriterCoverageRequest.query.get(request_id)
        if not coverage_request:
            return jsonify({'error': 'Request not found'}), 404
        
        if coverage_request.user_id != user.id:
            return jsonify({'error': 'Not authorized to cancel this request'}), 403
        
        if coverage_request.status != 'pending':
            return jsonify({'error': 'Can only cancel pending requests'}), 400
        
        db.session.delete(coverage_request)
        db.session.commit()
        
        return jsonify({'message': 'Coverage request cancelled'})
        
    except Exception as e:
        logger.exception('Failed to cancel coverage request')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to cancel coverage request')), 500


@journalist_bp.route('/journalists/players/<int:player_id>/stats', methods=['GET'])
@require_user_auth
def get_player_stats(player_id):
    """Get historical stats for a player."""
    try:
        # Verify user is a journalist
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a writer'}), 403

        # Import models here to avoid circular imports if any
        from src.models.weekly import FixturePlayerStats, Fixture
        from src.models.league import Team

        # Query stats joined with fixture to get date
        stats_query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_id
        ).order_by(
            Fixture.date_utc.asc()
        ).all()

        result = []
        for stats, fixture in stats_query:
            # Get opponent name
            opponent_name = "Unknown"
            is_home = (stats.team_api_id == fixture.home_team_api_id)
            opponent_api_id = fixture.away_team_api_id if is_home else fixture.home_team_api_id
            
            # Try to resolve opponent name from DB or just use ID
            # Ideally we'd join Team table but opponent might not be in our Team table if it's obscure
            # Let's try a quick lookup if we have it
            opponent = Team.query.filter_by(team_id=opponent_api_id).first()
            if opponent:
                opponent_name = opponent.name
            
            stats_dict = stats.to_dict()
            stats_dict['fixture_date'] = fixture.date_utc.isoformat() if fixture.date_utc else None
            stats_dict['opponent'] = opponent_name
            stats_dict['is_home'] = is_home
            stats_dict['competition'] = fixture.competition_name
            
            result.append(stats_dict)

        return jsonify(result)

    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch player stats')), 500


# --- Subscription Statistics Endpoints ---

@journalist_bp.route('/journalist/stats', methods=['GET'])
@require_user_auth
def get_journalist_own_stats():
    """Get subscription statistics for the authenticated journalist."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'User not authenticated'}), 401
            
        user = UserAccount.query.filter_by(email=email).first()
        if not user or not user.is_journalist:
            return jsonify({'error': 'Not authorized as a journalist'}), 403
        
        # Get total active subscribers
        total_subscribers = JournalistSubscription.query.filter_by(
            journalist_user_id=user.id,
            is_active=True
        ).count()
        
        # Get subscribers by team
        from sqlalchemy import and_
        team_stats = []
        for assignment in user.assigned_teams:
            if assignment.team:
                # Count subscribers to this journalist who also subscribe to this team's newsletters
                # This is an approximation - we're counting unique subscribers
                team_stats.append({
                    'team_id': assignment.team.id,
                    'team_name': assignment.team.name,
                    'team_logo': assignment.team.logo,
                    'subscriber_count': total_subscribers  # For now, all subscribers see all teams
                })
        
        # Calculate growth metrics (last 7 and 30 days)
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        
        subscribers_last_7_days = JournalistSubscription.query.filter(
            JournalistSubscription.journalist_user_id == user.id,
            JournalistSubscription.is_active == True,
            JournalistSubscription.created_at >= seven_days_ago
        ).count()
        
        subscribers_last_30_days = JournalistSubscription.query.filter(
            JournalistSubscription.journalist_user_id == user.id,
            JournalistSubscription.is_active == True,
            JournalistSubscription.created_at >= thirty_days_ago
        ).count()
        
        # Get subscription timeline for charts (last 90 days, grouped by week)
        ninety_days_ago = now - timedelta(days=90)
        all_subs = JournalistSubscription.query.filter(
            JournalistSubscription.journalist_user_id == user.id,
            JournalistSubscription.created_at >= ninety_days_ago
        ).order_by(JournalistSubscription.created_at.asc()).all()
        
        # Group by week for timeline
        timeline = {}
        for sub in all_subs:
            # Get week start (Monday)
            week_start = sub.created_at - timedelta(days=sub.created_at.weekday())
            week_key = week_start.strftime('%Y-%m-%d')
            if week_key not in timeline:
                timeline[week_key] = {'new_subscribers': 0, 'unsubscribes': 0}
            if sub.is_active:
                timeline[week_key]['new_subscribers'] += 1
            else:
                timeline[week_key]['unsubscribes'] += 1
        
        timeline_data = [
            {'week': k, **v} for k, v in sorted(timeline.items())
        ]
        
        return jsonify({
            'total_subscribers': total_subscribers,
            'subscribers_last_7_days': subscribers_last_7_days,
            'subscribers_last_30_days': subscribers_last_30_days,
            'team_breakdown': team_stats,
            'timeline': timeline_data
        })
        
    except Exception as e:
        logger.exception('Failed to fetch journalist stats')
        return jsonify(_safe_error_payload(e, 'Failed to fetch statistics')), 500


# --- Newsletter Journalist View Endpoints ---

def _get_journalists_with_writeups_for_newsletter(newsletter, current_user_id=None):
    """
    Get all journalists who have writeups for a newsletter's week/team.
    Returns list with subscription status and writeup counts.
    """
    if not newsletter:
        return []
    
    week_start = newsletter.week_start_date
    week_end = newsletter.week_end_date
    team_id = newsletter.team_id
    
    if not week_start or not week_end or not team_id:
        return []
    
    # Get API team ID for cross-season matching
    api_team_id = db.session.query(Team.team_id).filter(Team.id == team_id).scalar()
    
    # Query commentaries for this week/team, grouped by author
    # Include both newsletter_id match and week-based match
    base_query = NewsletterCommentary.query.filter(
        NewsletterCommentary.is_active.is_(True)
    )
    
    # Build OR conditions for matching
    from sqlalchemy import or_, and_
    
    conditions = []
    
    # Match by newsletter_id
    if newsletter.id:
        conditions.append(NewsletterCommentary.newsletter_id == newsletter.id)
    
    # Match by week dates and team
    if api_team_id:
        conditions.append(and_(
            NewsletterCommentary.week_start_date == week_start,
            NewsletterCommentary.week_end_date == week_end,
            NewsletterCommentary.team_id.in_(
                db.session.query(Team.id).filter(Team.team_id == api_team_id)
            )
        ))
    
    # Also match by direct team_id
    conditions.append(and_(
        NewsletterCommentary.week_start_date == week_start,
        NewsletterCommentary.week_end_date == week_end,
        NewsletterCommentary.team_id == team_id
    ))
    
    if not conditions:
        return []
    
    commentaries = base_query.filter(or_(*conditions)).all()
    
    # Group by author
    author_data = {}
    for c in commentaries:
        author_id = c.author_id
        if author_id not in author_data:
            author_data[author_id] = {
                'writeup_count': 0,
                'has_premium': False,
                'has_public': False,
            }
        author_data[author_id]['writeup_count'] += 1
        if c.is_premium:
            author_data[author_id]['has_premium'] = True
        else:
            author_data[author_id]['has_public'] = True
    
    # Get subscription status for each author
    subscribed_journalist_ids = set()
    if current_user_id:
        subs = JournalistSubscription.query.filter(
            JournalistSubscription.subscriber_user_id == current_user_id,
            JournalistSubscription.journalist_user_id.in_(author_data.keys()),
            JournalistSubscription.is_active.is_(True)
        ).all()
        subscribed_journalist_ids = {s.journalist_user_id for s in subs}
    
    # Build result with journalist details
    result = []
    author_ids = list(author_data.keys())
    if author_ids:
        journalists = UserAccount.query.filter(UserAccount.id.in_(author_ids)).all()
        journalist_map = {j.id: j for j in journalists}
        
        for author_id, data in author_data.items():
            journalist = journalist_map.get(author_id)
            if not journalist:
                continue
            
            result.append({
                'id': journalist.id,
                'display_name': journalist.display_name,
                'profile_image_url': journalist.profile_image_url,
                'bio': journalist.bio,
                'attribution_url': journalist.attribution_url,
                'attribution_name': journalist.attribution_name,
                'is_subscribed': author_id in subscribed_journalist_ids,
                'is_self': author_id == current_user_id,  # For writer preview mode
                'writeup_count': data['writeup_count'],
                'has_premium': data['has_premium'],
                'has_public': data['has_public'],
            })
    
    # Sort by: self first, then subscribed, then by writeup count
    result.sort(key=lambda x: (not x.get('is_self', False), not x['is_subscribed'], -x['writeup_count']))
    
    return result


def _mask_premium_content(content):
    """Create a preview snippet from premium content."""
    if not content:
        return ''
    clean_text = re.sub('<[^<]+?>', '', content)
    return clean_text[:200] + ('...' if len(clean_text) > 200 else '')


@journalist_bp.route('/newsletters/<int:newsletter_id>/journalist-view', methods=['GET'])
def get_newsletter_journalist_view(newsletter_id):
    """
    Get a newsletter with journalist writeups filtered and organized.
    
    Query params:
    - journalist_ids: comma-separated list of journalist IDs to include writeups from
    
    Returns newsletter data with commentaries grouped by type and available journalists list.
    """
    try:
        newsletter = Newsletter.query.get(newsletter_id)
        if not newsletter:
            return jsonify({'error': 'Newsletter not found'}), 404
        
        # Determine current user
        current_user = None
        current_user_id = None
        try:
            email = getattr(g, 'user_email', None)
            if email:
                current_user = UserAccount.query.filter_by(email=email).first()
                current_user_id = current_user.id if current_user else None
        except Exception:
            pass
        
        # Parse journalist_ids param
        journalist_ids_param = request.args.get('journalist_ids', '')
        requested_journalist_ids = set()
        if journalist_ids_param:
            try:
                requested_journalist_ids = {
                    int(x.strip()) for x in journalist_ids_param.split(',') 
                    if x.strip().isdigit()
                }
            except ValueError:
                pass
        
        # Get available journalists for this newsletter
        available_journalists = _get_journalists_with_writeups_for_newsletter(
            newsletter, current_user_id
        )
        available_journalist_ids = {j['id'] for j in available_journalists}
        
        # Determine which journalists to show writeups from
        # If no specific IDs requested, show none by default (user must toggle)
        active_journalist_ids = requested_journalist_ids & available_journalist_ids
        
        # Get subscription status for requested journalists
        subscribed_journalist_ids = set()
        if current_user_id and active_journalist_ids:
            subs = JournalistSubscription.query.filter(
                JournalistSubscription.subscriber_user_id == current_user_id,
                JournalistSubscription.journalist_user_id.in_(active_journalist_ids),
                JournalistSubscription.is_active.is_(True)
            ).all()
            subscribed_journalist_ids = {s.journalist_user_id for s in subs}
        
        # Collect commentaries for active journalists
        week_start = newsletter.week_start_date
        week_end = newsletter.week_end_date
        team_id = newsletter.team_id
        api_team_id = db.session.query(Team.team_id).filter(Team.id == team_id).scalar() if team_id else None
        
        from sqlalchemy import or_, and_
        
        conditions = []
        if newsletter.id:
            conditions.append(NewsletterCommentary.newsletter_id == newsletter.id)
        if week_start and week_end:
            if api_team_id:
                conditions.append(and_(
                    NewsletterCommentary.week_start_date == week_start,
                    NewsletterCommentary.week_end_date == week_end,
                    NewsletterCommentary.team_id.in_(
                        db.session.query(Team.id).filter(Team.team_id == api_team_id)
                    )
                ))
            if team_id:
                conditions.append(and_(
                    NewsletterCommentary.week_start_date == week_start,
                    NewsletterCommentary.week_end_date == week_end,
                    NewsletterCommentary.team_id == team_id
                ))
        
        # Organize commentaries by type
        commentaries = {
            'intro': [],
            'player': {},
            'summary': []
        }
        
        if conditions and active_journalist_ids:
            all_commentaries = NewsletterCommentary.query.filter(
                NewsletterCommentary.is_active.is_(True),
                NewsletterCommentary.author_id.in_(active_journalist_ids),
                or_(*conditions)
            ).order_by(
                NewsletterCommentary.position.asc(),
                NewsletterCommentary.created_at.asc()
            ).all()
            
            # Deduplicate by id
            seen_ids = set()
            unique_commentaries = []
            for c in all_commentaries:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    unique_commentaries.append(c)
            
            for c in unique_commentaries:
                data = c.to_dict()
                
                # Apply content masking for premium content
                is_subscribed = c.author_id in subscribed_journalist_ids
                if c.is_premium and not is_subscribed:
                    data['content'] = _mask_premium_content(data.get('content', ''))
                    data['is_locked'] = True
                else:
                    data['is_locked'] = False
                
                # Add author color index for UI differentiation
                try:
                    author_idx = list(active_journalist_ids).index(c.author_id)
                    data['author_color_index'] = author_idx % 6  # 6 color palette
                except ValueError:
                    data['author_color_index'] = 0
                
                # Group by type
                if c.commentary_type == 'intro':
                    commentaries['intro'].append(data)
                elif c.commentary_type == 'summary':
                    commentaries['summary'].append(data)
                elif c.commentary_type == 'player' and c.player_id:
                    player_id = c.player_id
                    if player_id not in commentaries['player']:
                        commentaries['player'][player_id] = []
                    commentaries['player'][player_id].append(data)
        
        # Build newsletter payload
        newsletter_data = newsletter.to_dict()
        
        # Include team info
        if newsletter.team:
            newsletter_data['team'] = {
                'id': newsletter.team.id,
                'team_id': newsletter.team.team_id,
                'name': newsletter.team.name,
                'logo': newsletter.team.logo,
            }
        
        # Extract structured content and rendered HTML
        import json
        player_info_map = {}  # player_id -> {name, photo, loan_team, etc.}
        sections = []
        
        try:
            content_obj = json.loads(newsletter.structured_content or newsletter.content or '{}')
            if isinstance(content_obj, dict):
                # Get rendered HTML
                rendered = content_obj.get('rendered')
                if isinstance(rendered, dict):
                    newsletter_data['rendered'] = {
                        k: (v if isinstance(v, str) else '') for k, v in rendered.items()
                    }
                
                # Extract sections with player info for commentary context
                raw_sections = content_obj.get('sections', [])
                if isinstance(raw_sections, list):
                    for sec in raw_sections:
                        if not isinstance(sec, dict):
                            continue
                        section_data = {
                            'title': sec.get('title', ''),
                            'players': []
                        }
                        items = sec.get('items', [])
                        if isinstance(items, list):
                            for item in items:
                                if not isinstance(item, dict):
                                    continue
                                player_id = item.get('player_id')
                                if player_id:
                                    player_data = {
                                        'player_id': player_id,
                                        'player_name': item.get('player_name', 'Unknown Player'),
                                        'player_photo': item.get('player_photo'),
                                        'loan_team': item.get('loan_team') or item.get('loan_team_name'),
                                        'loan_team_logo': item.get('loan_team_logo'),
                                        'stats': item.get('stats'),
                                        'narrative': item.get('narrative'),
                                    }
                                    section_data['players'].append(player_data)
                                    # Build player info map for commentary enrichment
                                    player_info_map[player_id] = {
                                        'name': player_data['player_name'],
                                        'photo': player_data['player_photo'],
                                        'loan_team': player_data['loan_team'],
                                        'loan_team_logo': player_data['loan_team_logo'],
                                    }
                        if section_data['players']:
                            sections.append(section_data)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Enrich player commentaries with player info
        enriched_player_commentaries = {}
        for player_id, player_comms in commentaries['player'].items():
            player_id_int = int(player_id) if isinstance(player_id, str) else player_id
            player_info = player_info_map.get(player_id_int, {})
            enriched_player_commentaries[player_id] = {
                'player_info': player_info,
                'commentaries': player_comms
            }
        
        return jsonify({
            'newsletter': newsletter_data,
            'commentaries': {
                'intro': commentaries['intro'],
                'summary': commentaries['summary'],
                'player': enriched_player_commentaries,
            },
            'sections': sections,
            'player_info_map': player_info_map,
            'available_journalists': available_journalists,
            'active_journalist_ids': list(active_journalist_ids),
        })
        
    except Exception as e:
        logger.exception('Failed to fetch newsletter journalist view')
        return jsonify(_safe_error_payload(e, 'Failed to fetch newsletter view')), 500


@journalist_bp.route('/journalists/<int:journalist_id>/stats/public', methods=['GET'])
def get_journalist_public_stats(journalist_id):
    """Get public subscription statistics for a specific journalist."""
    try:
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
        
        # Get total active subscribers
        total_subscribers = JournalistSubscription.query.filter_by(
            journalist_user_id=journalist_id,
            is_active=True
        ).count()
        
        # Get per-team subscriber counts
        team_stats = []
        for assignment in journalist.assigned_teams:
            if assignment.team:
                team_stats.append({
                    'team_id': assignment.team.id,
                    'team_name': assignment.team.name,
                    'team_logo': assignment.team.logo,
                    'subscriber_count': total_subscribers  # Simplified for now
                })
        
        return jsonify({
            'journalist_id': journalist_id,
            'total_subscribers': total_subscribers,
            'team_breakdown': team_stats
        })
        
    except Exception as e:
        logger.exception('Failed to fetch public journalist stats')
        return jsonify(_safe_error_payload(e, 'Failed to fetch statistics')), 500




@journalist_bp.route('/admin/journalist-stats', methods=['GET'])
@require_api_key
def get_admin_journalist_stats():
    """(Admin) Get subscription statistics for all journalists."""
    try:
        journalists = UserAccount.query.filter_by(is_journalist=True).all()
        
        result = []
        for journalist in journalists:
            # Count active subscribers
            subscriber_count = JournalistSubscription.query.filter_by(
                journalist_user_id=journalist.id,
                is_active=True
            ).count()
            
            # Get team breakdown
            team_breakdown = []
            for assignment in journalist.assigned_teams:
                if assignment.team:
                    team_breakdown.append({
                        'team_id': assignment.team.id,
                        'team_name': assignment.team.name,
                        'team_logo': assignment.team.logo,
                        'subscriber_count': subscriber_count  # Simplified
                    })
            
            result.append({
                'journalist_id': journalist.id,
                'journalist_name': journalist.display_name,
                'journalist_email': journalist.email,
                'profile_image_url': journalist.profile_image_url,
                'total_subscribers': subscriber_count,
                'team_breakdown': team_breakdown,
                'teams_count': len(team_breakdown)
            })
        
        # Sort by subscriber count (descending)
        result.sort(key=lambda x: x['total_subscribers'], reverse=True)
        
        return jsonify({
            'journalists': result,
            'total_journalists': len(result),
            'total_subscriptions': sum(j['total_subscribers'] for j in result)
        })
        
    except Exception as e:
        logger.exception('Failed to fetch admin journalist stats')
        return jsonify(_safe_error_payload(e, 'Failed to fetch statistics')), 500


# --- Admin Coverage Request Management Endpoints ---

@journalist_bp.route('/admin/coverage-requests', methods=['GET'])
@require_api_key
def admin_list_coverage_requests():
    """(Admin) List all coverage requests with optional filters."""
    try:
        query = WriterCoverageRequest.query
        
        # Filter by status
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
        
        # Filter by coverage type
        coverage_type = request.args.get('coverage_type')
        if coverage_type:
            query = query.filter_by(coverage_type=coverage_type)
        
        # Filter by user
        user_id = request.args.get('user_id', type=int)
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        # Order by most recent first, pending first
        requests = query.order_by(
            WriterCoverageRequest.status.asc(),  # pending < approved < denied
            WriterCoverageRequest.requested_at.desc()
        ).all()
        
        # Count by status for summary
        pending_count = WriterCoverageRequest.query.filter_by(status='pending').count()
        approved_count = WriterCoverageRequest.query.filter_by(status='approved').count()
        denied_count = WriterCoverageRequest.query.filter_by(status='denied').count()
        
        return jsonify({
            'requests': [r.to_dict() for r in requests],
            'summary': {
                'pending': pending_count,
                'approved': approved_count,
                'denied': denied_count,
                'total': pending_count + approved_count + denied_count
            }
        })
        
    except Exception as e:
        logger.exception('Failed to list coverage requests')
        return jsonify(_safe_error_payload(e, 'Failed to list coverage requests')), 500


@journalist_bp.route('/admin/coverage-requests/<int:request_id>/approve', methods=['POST'])
@require_api_key
def admin_approve_coverage_request(request_id):
    """(Admin) Approve a coverage request and create the assignment."""
    try:
        coverage_request = WriterCoverageRequest.query.get(request_id)
        if not coverage_request:
            return jsonify({'error': 'Request not found'}), 404
        
        if coverage_request.status != 'pending':
            return jsonify({'error': 'Request is not pending'}), 400
        
        # Create the appropriate assignment
        if coverage_request.coverage_type == 'parent_club':
            if not coverage_request.team_id:
                return jsonify({'error': 'Cannot approve parent club request without valid team_id'}), 400
            
            # Check if assignment already exists
            existing = JournalistTeamAssignment.query.filter_by(
                user_id=coverage_request.user_id,
                team_id=coverage_request.team_id
            ).first()
            
            if not existing:
                assignment = JournalistTeamAssignment(
                    user_id=coverage_request.user_id,
                    team_id=coverage_request.team_id,
                    assigned_by=None  # Could add admin user tracking
                )
                db.session.add(assignment)
        
        elif coverage_request.coverage_type == 'loan_team':
            # Check if assignment already exists
            existing = JournalistLoanTeamAssignment.query.filter_by(
                user_id=coverage_request.user_id,
                loan_team_name=coverage_request.team_name
            ).first()
            
            if not existing:
                assignment = JournalistLoanTeamAssignment(
                    user_id=coverage_request.user_id,
                    loan_team_id=coverage_request.team_id,  # May be None for custom teams
                    loan_team_name=coverage_request.team_name,
                    assigned_by=None
                )
                db.session.add(assignment)
        
        # Update request status
        coverage_request.status = 'approved'
        coverage_request.reviewed_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        logger.info(f"Approved coverage request {request_id} for user {coverage_request.user_id}")
        
        return jsonify({
            'message': 'Coverage request approved',
            'request': coverage_request.to_dict()
        })
        
    except Exception as e:
        logger.exception('Failed to approve coverage request')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to approve coverage request')), 500


@journalist_bp.route('/admin/coverage-requests/<int:request_id>/deny', methods=['POST'])
@require_api_key
def admin_deny_coverage_request(request_id):
    """(Admin) Deny a coverage request with optional reason."""
    try:
        coverage_request = WriterCoverageRequest.query.get(request_id)
        if not coverage_request:
            return jsonify({'error': 'Request not found'}), 404
        
        if coverage_request.status != 'pending':
            return jsonify({'error': 'Request is not pending'}), 400
        
        data = request.get_json() or {}
        
        # Update request status
        coverage_request.status = 'denied'
        coverage_request.denial_reason = data.get('reason', '').strip() or None
        coverage_request.reviewed_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        logger.info(f"Denied coverage request {request_id} for user {coverage_request.user_id}")
        
        return jsonify({
            'message': 'Coverage request denied',
            'request': coverage_request.to_dict()
        })
        
    except Exception as e:
        logger.exception('Failed to deny coverage request')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to deny coverage request')), 500


@journalist_bp.route('/admin/journalists/<int:journalist_id>/loan-team-assignments', methods=['POST'])
@require_api_key
def admin_assign_loan_teams(journalist_id):
    """(Admin) Directly assign loan teams to a journalist.
    
    Body:
        loan_teams: Array of {loan_team_id: int|null, loan_team_name: str}
    """
    try:
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
        
        data = request.get_json() or {}
        loan_teams = data.get('loan_teams', [])
        
        # Clear existing loan team assignments
        JournalistLoanTeamAssignment.query.filter_by(user_id=journalist.id).delete()
        
        assignments = []
        for lt in loan_teams:
            team_name = (lt.get('loan_team_name') or '').strip()
            if not team_name:
                continue
            
            team_id = lt.get('loan_team_id')
            if team_id:
                try:
                    team_id = int(team_id)
                except (ValueError, TypeError):
                    team_id = None
            
            assignment = JournalistLoanTeamAssignment(
                user_id=journalist.id,
                loan_team_id=team_id,
                loan_team_name=team_name,
                assigned_by=None
            )
            db.session.add(assignment)
            assignments.append(assignment)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Loan team assignments updated',
            'count': len(assignments),
            'assignments': [a.to_dict() for a in assignments]
        })
        
    except Exception as e:
        logger.exception('Failed to assign loan teams')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to assign loan teams')), 500


@journalist_bp.route('/admin/journalists/<int:journalist_id>/all-assignments', methods=['GET'])
@require_api_key
def admin_get_journalist_assignments(journalist_id):
    """(Admin) Get all assignments (parent clubs and loan teams) for a journalist."""
    try:
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
        
        parent_assignments = JournalistTeamAssignment.query.filter_by(user_id=journalist.id).all()
        loan_assignments = JournalistLoanTeamAssignment.query.filter_by(user_id=journalist.id).all()
        
        return jsonify({
            'journalist_id': journalist.id,
            'journalist_name': journalist.display_name,
            'parent_club_assignments': [a.to_dict() for a in parent_assignments],
            'loan_team_assignments': [a.to_dict() for a in loan_assignments]
        })
        
    except Exception as e:
        logger.exception('Failed to get journalist assignments')
        return jsonify(_safe_error_payload(e, 'Failed to get assignments')), 500


@journalist_bp.route('/writer/manual-players', methods=['POST'])
@require_user_auth
def submit_manual_player():
    """Submit a manual player for tracking."""
    try:
        user = g.user
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can submit manual players'}), 403
            
        data = request.get_json() or {}
        player_name = (data.get('player_name') or '').strip()
        team_name = (data.get('team_name') or '').strip()
        
        if not player_name or not team_name:
            return jsonify({'error': 'Player name and team name are required'}), 400
            
        submission = ManualPlayerSubmission(
            user_id=user.id,
            player_name=player_name,
            team_name=team_name,
            league_name=(data.get('league_name') or '').strip() or None,
            position=(data.get('position') or '').strip() or None,
            notes=(data.get('notes') or '').strip() or None,
            status='pending'
        )
        
        db.session.add(submission)
        db.session.commit()
        
        return jsonify(submission.to_dict()), 201
        
    except Exception as e:
        logger.exception('Failed to submit manual player')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to submit manual player')), 500


@journalist_bp.route('/writer/manual-players', methods=['GET'])
@require_user_auth
def list_manual_submissions():
    """List manual player submissions for the current writer."""
    try:
        user = g.user
        submissions = ManualPlayerSubmission.query.filter_by(user_id=user.id).order_by(
            ManualPlayerSubmission.created_at.desc()
        ).all()
        
        return jsonify([s.to_dict() for s in submissions])
        
    except Exception as e:
        logger.exception('Failed to list manual submissions')
        return jsonify(_safe_error_payload(e, 'Failed to list manual submissions')), 500


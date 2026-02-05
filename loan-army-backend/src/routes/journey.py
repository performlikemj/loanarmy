"""Player Journey API endpoints.

Handles:
- Player career journey retrieval for map visualization
- Career stint management (admin)
"""
from flask import Blueprint, request, jsonify
from src.models.league import db, PlayerCareerStint, LoanedPlayer, Team, TeamProfile
from src.routes.api import require_api_key
from src.utils.geocoding import get_team_coordinates
from datetime import datetime, timezone
from collections import defaultdict
import logging
import re

journey_bp = Blueprint('journey', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Public Endpoints
# =============================================================================

@journey_bp.route('/players/<int:player_id>/journey', methods=['GET'])
def get_player_journey(player_id):
    """Get a player's career journey for map visualization.

    Returns all career stints ordered by sequence, with coordinates.
    """
    # Get the primary team from any LoanedPlayer record for this player
    sample_loan = LoanedPlayer.query.filter_by(player_id=player_id).first()
    primary_team_id = sample_loan.primary_team_id if sample_loan else None

    journey_data = _build_complete_journey(player_id, primary_team_id)

    return jsonify({
        'player_id': player_id,
        **journey_data,
    })


@journey_bp.route('/loans/<int:loaned_player_id>/journey', methods=['GET'])
def get_loan_journey(loaned_player_id):
    """Get journey for a specific LoanedPlayer record.

    Returns the complete journey for the player, including all loan stints
    across their career (not just the current loan).
    """
    loan = LoanedPlayer.query.get_or_404(loaned_player_id)

    # Build complete journey from all LoanedPlayer records for this player
    journey_data = _build_complete_journey(loan.player_id, loan.primary_team_id)

    return jsonify({
        'loaned_player_id': loaned_player_id,
        'player_id': loan.player_id,
        'player_name': loan.player_name,
        **journey_data,
    })


# =============================================================================
# Admin Endpoints
# =============================================================================

@journey_bp.route('/admin/journey/stints', methods=['POST'])
@require_api_key
def create_career_stint():
    """Create a new career stint for a player."""
    data = request.get_json() or {}

    required = ['player_id', 'player_name', 'team_api_id', 'team_name', 'stint_type']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    if data['stint_type'] not in ('academy', 'loan', 'first_team', 'permanent_transfer'):
        return jsonify({'error': 'Invalid stint_type'}), 400

    # Get coordinates from city
    coords = None
    city = data.get('city')
    country = data.get('country')
    if city:
        coords = get_team_coordinates(city, country)

    # Get next sequence number
    max_seq = db.session.query(db.func.max(PlayerCareerStint.sequence))\
        .filter_by(player_id=data['player_id']).scalar() or 0

    stint = PlayerCareerStint(
        player_id=data['player_id'],
        player_name=data['player_name'],
        loaned_player_id=data.get('loaned_player_id'),
        team_api_id=data['team_api_id'],
        team_name=data['team_name'],
        team_logo=data.get('team_logo'),
        city=city,
        country=country,
        latitude=coords[0] if coords else data.get('latitude'),
        longitude=coords[1] if coords else data.get('longitude'),
        stint_type=data['stint_type'],
        level=data.get('level'),
        start_date=datetime.fromisoformat(data['start_date']).date() if data.get('start_date') else None,
        end_date=datetime.fromisoformat(data['end_date']).date() if data.get('end_date') else None,
        is_current=data.get('is_current', False),
        sequence=data.get('sequence', max_seq + 1),
    )

    db.session.add(stint)
    db.session.commit()

    return jsonify({
        'message': 'Stint created',
        'stint': stint.to_dict(),
    }), 201


@journey_bp.route('/admin/journey/stints/<int:stint_id>', methods=['PUT'])
@require_api_key
def update_career_stint(stint_id):
    """Update a career stint."""
    stint = PlayerCareerStint.query.get_or_404(stint_id)
    data = request.get_json() or {}

    if 'team_name' in data:
        stint.team_name = data['team_name']
    if 'team_logo' in data:
        stint.team_logo = data['team_logo']
    if 'city' in data:
        stint.city = data['city']
        # Re-geocode if city changed
        coords = get_team_coordinates(data['city'], data.get('country', stint.country))
        if coords:
            stint.latitude, stint.longitude = coords
    if 'country' in data:
        stint.country = data['country']
    if 'latitude' in data:
        stint.latitude = data['latitude']
    if 'longitude' in data:
        stint.longitude = data['longitude']
    if 'stint_type' in data:
        stint.stint_type = data['stint_type']
    if 'level' in data:
        stint.level = data['level']
    if 'start_date' in data:
        stint.start_date = datetime.fromisoformat(data['start_date']).date() if data['start_date'] else None
    if 'end_date' in data:
        stint.end_date = datetime.fromisoformat(data['end_date']).date() if data['end_date'] else None
    if 'is_current' in data:
        stint.is_current = data['is_current']
    if 'sequence' in data:
        stint.sequence = data['sequence']

    stint.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'message': 'Stint updated',
        'stint': stint.to_dict(),
    })


@journey_bp.route('/admin/journey/stints/<int:stint_id>', methods=['DELETE'])
@require_api_key
def delete_career_stint(stint_id):
    """Delete a career stint."""
    stint = PlayerCareerStint.query.get_or_404(stint_id)
    db.session.delete(stint)
    db.session.commit()

    return jsonify({'message': 'Stint deleted'})


@journey_bp.route('/admin/journey/generate/<int:loaned_player_id>', methods=['POST'])
@require_api_key
def generate_journey(loaned_player_id):
    """Auto-generate journey stints from a LoanedPlayer record."""
    loan = LoanedPlayer.query.get_or_404(loaned_player_id)

    # Clear existing stints for this loan
    PlayerCareerStint.query.filter_by(loaned_player_id=loaned_player_id).delete()

    stints = _generate_journey_from_loan_record(loan, persist=True)

    return jsonify({
        'message': f'Generated {len(stints)} stints',
        'stints': [s.to_dict() for s in stints],
    })


# =============================================================================
# Helper Functions
# =============================================================================

def _get_team_venue_info(team_api_id: int) -> dict:
    """Get venue info for a team from TeamProfile or Team."""
    # Try TeamProfile first (cached API data)
    profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
    if profile:
        return {
            'city': profile.venue_city,
            'country': profile.country,
            'logo': profile.logo_url,
        }

    # Try Team table
    team = Team.query.filter_by(team_id=team_api_id).first()
    if team:
        return {
            'city': team.venue_city,
            'country': team.country,
            'logo': team.logo,
        }

    return {}


def _parse_window_key(window_key: str) -> tuple:
    """Parse window_key for chronological sorting.

    Window keys are formatted as "2023-24::SUMMER" or "2023-24::WINTER" or "2023-24::FULL".
    Returns (season_start_year, window_order) for sorting.

    Window order: SUMMER=0, FULL=1, WINTER=2
    """
    if not window_key:
        return (0, 0)

    # Extract season and window type
    match = re.match(r'(\d{4})-\d{2}::(\w+)', window_key)
    if not match:
        return (0, 0)

    season_start = int(match.group(1))
    window_type = match.group(2).upper()

    window_order = {'SUMMER': 0, 'FULL': 1, 'WINTER': 2}.get(window_type, 1)

    return (season_start, window_order)


def _extract_season_from_window(window_key: str) -> str:
    """Extract season string from window_key (e.g., '2023-24' from '2023-24::SUMMER')."""
    if not window_key:
        return ''
    match = re.match(r'(\d{4}-\d{2})', window_key)
    return match.group(1) if match else ''


def _dedupe_loan_stints(loans: list) -> list:
    """Deduplicate loan records to one stint per (loan_team_id, season).

    A player may have multiple LoanedPlayer records for the same loan
    (e.g., listed in both SUMMER and WINTER windows for the same season).
    We deduplicate to show one stint per unique (loan_team_id, season).
    """
    seen = {}  # (loan_team_id, season) -> loan record

    for loan in loans:
        season = _extract_season_from_window(loan.window_key)
        key = (loan.loan_team_id, season)

        if key not in seen:
            seen[key] = loan
        else:
            # Keep the most recent record (higher window order or later is_active)
            existing = seen[key]
            existing_order = _parse_window_key(existing.window_key)
            new_order = _parse_window_key(loan.window_key)

            # Prefer active loan, or later window
            if loan.is_active and not existing.is_active:
                seen[key] = loan
            elif new_order > existing_order:
                seen[key] = loan

    return list(seen.values())


def _build_complete_journey(player_id: int, primary_team_id: int = None) -> dict:
    """Build the complete journey for a player.

    Returns:
        dict with keys:
        - stints: list of PlayerCareerStint-like dicts
        - total_stints: count of stints
        - countries: list of {name, stint_count} for each country
        - is_multi_country: boolean
        - moved_on: boolean if player has left parent club
    """
    # Query ALL LoanedPlayer records for this player, sorted by window_key
    loans = LoanedPlayer.query.filter_by(player_id=player_id)\
        .order_by(LoanedPlayer.window_key).all()

    if not loans:
        return {
            'stints': [],
            'total_stints': 0,
            'countries': [],
            'is_multi_country': False,
            'moved_on': False,
        }

    # Get parent team info from first loan or provided primary_team_id
    first_loan = loans[0]
    parent_team_api_id = None
    if primary_team_id:
        parent_team = Team.query.get(primary_team_id)
        if parent_team:
            parent_team_api_id = parent_team.team_id
    elif first_loan.parent_team:
        parent_team_api_id = first_loan.parent_team.team_id

    parent_venue = _get_team_venue_info(parent_team_api_id) if parent_team_api_id else {}
    parent_coords = get_team_coordinates(parent_venue.get('city'), parent_venue.get('country'))

    stints = []
    sequence = 1
    country_counts = defaultdict(int)

    # Track pathway statuses across all records
    has_academy = any(l.pathway_status == 'academy' or l.current_level in ('U18', 'U21', 'U23') for l in loans)
    has_first_team = any(l.pathway_status == 'first_team' for l in loans)
    most_recent = max(loans, key=lambda l: _parse_window_key(l.window_key))

    # Stint 1: Academy (if player was ever in academy)
    if has_academy:
        academy_stint = _create_stint_dict(
            player_id=player_id,
            player_name=first_loan.player_name,
            team_api_id=parent_team_api_id,
            team_name=first_loan.primary_team_name,
            team_logo=parent_venue.get('logo'),
            city=parent_venue.get('city'),
            country=parent_venue.get('country'),
            latitude=parent_coords[0] if parent_coords else None,
            longitude=parent_coords[1] if parent_coords else None,
            stint_type='academy',
            level='Academy',
            is_current=False,
            sequence=sequence,
        )
        stints.append(academy_stint)
        if academy_stint['country']:
            country_counts[academy_stint['country']] += 1
        sequence += 1

    # Sort loans chronologically and deduplicate
    sorted_loans = sorted(loans, key=lambda l: _parse_window_key(l.window_key))
    deduped_loans = _dedupe_loan_stints(sorted_loans)
    # Re-sort after deduplication
    deduped_loans = sorted(deduped_loans, key=lambda l: _parse_window_key(l.window_key))

    # Build loan stints
    for loan in deduped_loans:
        if not loan.loan_team_id and not loan.loan_team_name:
            continue

        loan_team_api_id = None
        if loan.borrowing_team:
            loan_team_api_id = loan.borrowing_team.team_id

        loan_venue = _get_team_venue_info(loan_team_api_id) if loan_team_api_id else {}
        loan_coords = get_team_coordinates(loan_venue.get('city'), loan_venue.get('country'))

        # Determine if this is the current stint
        is_current = loan.is_active and loan.id == most_recent.id

        loan_stint = _create_stint_dict(
            player_id=player_id,
            player_name=loan.player_name,
            team_api_id=loan_team_api_id,
            team_name=loan.loan_team_name,
            team_logo=loan_venue.get('logo'),
            city=loan_venue.get('city'),
            country=loan_venue.get('country'),
            latitude=loan_coords[0] if loan_coords else None,
            longitude=loan_coords[1] if loan_coords else None,
            stint_type='loan',
            level='Senior',
            is_current=is_current,
            sequence=sequence,
            window_key=loan.window_key,
            loaned_player_id=loan.id,
        )
        stints.append(loan_stint)
        if loan_stint['country']:
            country_counts[loan_stint['country']] += 1
        sequence += 1

    # First team stint (if player made it to first team)
    if has_first_team:
        first_team_stint = _create_stint_dict(
            player_id=player_id,
            player_name=first_loan.player_name,
            team_api_id=parent_team_api_id,
            team_name=first_loan.primary_team_name,
            team_logo=parent_venue.get('logo'),
            city=parent_venue.get('city'),
            country=parent_venue.get('country'),
            latitude=parent_coords[0] if parent_coords else None,
            longitude=parent_coords[1] if parent_coords else None,
            stint_type='first_team',
            level='Senior',
            is_current=most_recent.pathway_status == 'first_team',
            sequence=sequence,
        )
        stints.append(first_team_stint)
        if first_team_stint['country']:
            country_counts[first_team_stint['country']] += 1

    # Detect "moved on" status
    # Player has moved on if: released, OR most recent loan is inactive and never made first team
    moved_on = (
        most_recent.pathway_status == 'released' or
        (not most_recent.is_active and not has_first_team and most_recent.pathway_status != 'academy')
    )

    # Build countries list
    countries = [
        {'name': name, 'stint_count': count}
        for name, count in sorted(country_counts.items())
    ]

    return {
        'stints': stints,
        'total_stints': len(stints),
        'countries': countries,
        'is_multi_country': len(country_counts) > 1,
        'moved_on': moved_on,
    }


def _create_stint_dict(
    player_id: int,
    player_name: str,
    team_api_id: int,
    team_name: str,
    team_logo: str,
    city: str,
    country: str,
    latitude: float,
    longitude: float,
    stint_type: str,
    level: str,
    is_current: bool,
    sequence: int,
    window_key: str = None,
    loaned_player_id: int = None,
) -> dict:
    """Create a stint dictionary matching PlayerCareerStint.to_dict() format."""
    return {
        'id': f'{player_id}-{sequence}',  # Synthetic ID for frontend key
        'player_id': player_id,
        'player_name': player_name,
        'loaned_player_id': loaned_player_id,
        'team_api_id': team_api_id or 0,
        'team_name': team_name,
        'team_logo': team_logo,
        'city': city,
        'country': country,
        'latitude': latitude,
        'longitude': longitude,
        'stint_type': stint_type,
        'level': level,
        'start_date': None,
        'end_date': None,
        'is_current': is_current,
        'sequence': sequence,
        'window_key': window_key,
    }


def _generate_journey_from_loan_record(loan: LoanedPlayer, persist: bool = False) -> list:
    """Generate journey stints from a single LoanedPlayer record.

    DEPRECATED: Use _build_complete_journey instead for full journey.
    This function is kept for backwards compatibility with admin endpoints.
    """
    journey_data = _build_complete_journey(loan.player_id, loan.primary_team_id)
    stints = journey_data['stints']

    if persist:
        # Convert dicts to PlayerCareerStint objects for persistence
        for stint_dict in stints:
            stint = PlayerCareerStint(
                player_id=stint_dict['player_id'],
                player_name=stint_dict['player_name'],
                loaned_player_id=stint_dict.get('loaned_player_id'),
                team_api_id=stint_dict['team_api_id'],
                team_name=stint_dict['team_name'],
                team_logo=stint_dict.get('team_logo'),
                city=stint_dict.get('city'),
                country=stint_dict.get('country'),
                latitude=stint_dict.get('latitude'),
                longitude=stint_dict.get('longitude'),
                stint_type=stint_dict['stint_type'],
                level=stint_dict.get('level'),
                is_current=stint_dict.get('is_current', False),
                sequence=stint_dict['sequence'],
            )
            db.session.add(stint)
        db.session.commit()

    # Return as PlayerCareerStint-like objects for compatibility
    class StintProxy:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
        def to_dict(self):
            return {k: v for k, v in self.__dict__.items()}

    return [StintProxy(s) for s in stints]

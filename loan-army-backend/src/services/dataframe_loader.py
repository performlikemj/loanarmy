"""
DataFrame Loader for Academy Watch Agent

Loads database data into pandas DataFrames for the analytics sandbox.
Uses SQLAlchemy ORM only — never raw SQL.
"""

import logging
from typing import Optional

import pandas as pd
from src.models.league import (
    db, Team, LoanedPlayer, Player, League,
)
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.weekly import FixturePlayerStats

logger = logging.getLogger(__name__)


def load_context(
    team_id: Optional[int] = None,
    league_id: Optional[int] = None,
    player_ids: Optional[list[int]] = None,
) -> dict[str, pd.DataFrame]:
    """Load DB data into read-only DataFrames for the analytics sandbox.

    Args:
        team_id: DB primary key of a parent team to scope data.
        league_id: DB primary key of a league to scope data.
        player_ids: Explicit list of player API IDs to include.

    Returns:
        Dict with keys: df_players, df_loans, df_matches, df_journeys
    """
    # --- Build loan query ---
    loan_query = LoanedPlayer.query.filter_by(is_active=True)
    if team_id is not None:
        loan_query = loan_query.filter_by(primary_team_id=team_id)
    if league_id is not None:
        # Filter loans whose parent team belongs to the given league
        loan_query = loan_query.join(
            Team, Team.id == LoanedPlayer.primary_team_id
        ).filter(Team.league_id == league_id)
    if player_ids:
        loan_query = loan_query.filter(LoanedPlayer.player_id.in_(player_ids))

    # If no filters provided, cap results to prevent huge queries
    if team_id is None and league_id is None and not player_ids:
        loan_query = loan_query.limit(500)

    loans = loan_query.all()

    if not loans:
        empty = pd.DataFrame()
        return {
            'df_players': empty.copy(),
            'df_loans': empty.copy(),
            'df_matches': empty.copy(),
            'df_journeys': empty.copy(),
        }

    # Collect player API IDs from the loans
    api_ids = list({loan.player_id for loan in loans})

    # --- df_loans ---
    loan_rows = []
    for loan in loans:
        loan_rows.append({
            'loan_id': loan.id,
            'player_id': loan.player_id,
            'player_name': loan.player_name,
            'age': loan.age,
            'nationality': loan.nationality,
            'primary_team_id': loan.primary_team_id,
            'primary_team_name': loan.primary_team_name,
            'loan_team_id': loan.loan_team_id,
            'loan_team_name': loan.loan_team_name,
            'appearances': loan.appearances,
            'goals': loan.goals,
            'assists': loan.assists,
            'minutes_played': loan.minutes_played,
            'yellows': loan.yellows,
            'reds': loan.reds,
            'pathway_status': loan.pathway_status,
            'current_level': loan.current_level,
            'is_active': loan.is_active,
        })
    df_loans = pd.DataFrame(loan_rows)

    # --- df_players ---
    players = Player.query.filter(Player.player_id.in_(api_ids)).all()
    player_rows = []
    for p in players:
        player_rows.append({
            'player_id': p.player_id,
            'name': p.name,
            'firstname': p.firstname,
            'lastname': p.lastname,
            'nationality': p.nationality,
            'age': p.age,
            'height': p.height,
            'weight': p.weight,
            'position': p.position,
        })
    df_players = pd.DataFrame(player_rows) if player_rows else pd.DataFrame()

    # --- df_matches (from FixturePlayerStats) ---
    match_query = FixturePlayerStats.query.filter(
        FixturePlayerStats.player_api_id.in_(api_ids)
    ).limit(10000)
    matches = match_query.all()
    match_rows = []
    for m in matches:
        match_rows.append({
            'player_api_id': m.player_api_id,
            'fixture_api_id': m.fixture_api_id,
            'team_api_id': m.team_api_id,
            'minutes': m.minutes,
            'goals': m.goals,
            'assists': m.assists,
            'rating': m.rating,
            'shots_total': m.shots_total,
            'shots_on': m.shots_on,
            'passes_key': m.passes_key,
            'tackles_total': m.tackles_total,
            'tackles_interceptions': m.tackles_interceptions,
            'dribbles_success': m.dribbles_success,
            'dribbles_attempts': m.dribbles_attempts,
            'duels_won': m.duels_won,
            'duels_total': m.duels_total,
            'yellows': m.yellows,
            'reds': m.reds,
            'saves': m.saves,
        })
    df_matches = pd.DataFrame(match_rows) if match_rows else pd.DataFrame()

    # --- df_journeys ---
    journeys = PlayerJourney.query.filter(
        PlayerJourney.player_api_id.in_(api_ids)
    ).all()
    journey_rows = []
    for j in journeys:
        entries = PlayerJourneyEntry.query.filter_by(journey_id=j.id).order_by(
            PlayerJourneyEntry.season
        ).all()
        for e in entries:
            journey_rows.append({
                'player_api_id': j.player_api_id,
                'player_name': j.player_name,
                'club_name': e.club_name,
                'club_api_id': e.club_api_id,
                'season': e.season,
                'level': e.level,
                'appearances': e.appearances,
                'goals': e.goals,
                'assists': e.assists,
                'minutes': e.minutes,
            })
    df_journeys = pd.DataFrame(journey_rows) if journey_rows else pd.DataFrame()

    return {
        'df_players': df_players.copy(),
        'df_loans': df_loans.copy(),
        'df_matches': df_matches.copy(),
        'df_journeys': df_journeys.copy(),
    }

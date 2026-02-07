"""
Academy Watch Chat Agent

Interactive AI analyst for football academy players, loans, and player
development pathways. Uses OpenAI Agents SDK with tools for:
- Refreshing player stats from API-Football
- Querying player career journeys
- Running sandboxed Python analytics code
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from agents import Agent, FunctionTool, set_default_openai_client

from src.api_football_client import APIFootballClient
from src.models.league import db
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.services.analytics_sandbox import execute_sandboxed_code
from src.services.dataframe_loader import load_context

import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

logger = logging.getLogger(__name__)

api_client = APIFootballClient()

aio_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(aio_client)

# ---------- System Prompt ----------

SYSTEM_PROMPT = """You are the Academy Watch analyst — an AI expert on football academy players, \
loans, and player development pathways.

The user has selected a context (team/league/players) and the following \
DataFrames are pre-loaded in your analytics sandbox:
- df_players: Player profiles (name, position, age, nationality, etc.)
- df_loans: Active loan records (player, parent team, loan team, stats)
- df_matches: Match appearances with stats (goals, assists, minutes, rating, etc.)
- df_journeys: Career path entries (club, season, level, appearances, goals)

You can:
1. Write Python code (pandas/matplotlib/plotly) to analyze these DataFrames \
   using the `run_analytics` tool — code runs in a secure sandbox
2. Refresh live data from API-Football using `refresh_player_stats` when needed
3. Look up a player's career journey with `get_player_journey`
4. Generate charts (returned as images) and tables (returned as JSON)

Be conversational but data-driven. Always cite specific stats when making claims.
If you don't have data on something, say so honestly.
Write efficient pandas code. Use matplotlib or plotly for visualizations.
Call output_chart(fig) to return a chart, output_table(df) to return a table.
"""

# ---------- Pydantic Tool Schemas ----------


class RefreshPlayerStatsArgs(BaseModel):
    player_id: int = Field(..., description="Player API-Football ID", ge=1, le=999999)
    season: int = Field(2025, description="Season year", ge=2015, le=2030)


class GetPlayerJourneyArgs(BaseModel):
    player_id: int = Field(..., description="Player API-Football ID", ge=1, le=999999)


class RunAnalyticsArgs(BaseModel):
    code: str = Field(
        ...,
        description=(
            "Python code to execute against the pre-loaded DataFrames. "
            "Available: df_players, df_loans, df_matches, df_journeys. "
            "Use pandas for analysis, matplotlib/plotly for charts. "
            "Call output_chart(fig) to return a chart, output_table(df) to return a table."
        ),
        max_length=5000,
    )
    description: str = Field("", description="What this analysis does", max_length=200)


# ---------- Tool Implementations ----------

# Storage for session DataFrames (keyed by chat session id)
_session_dataframes: dict[int, dict] = {}


def set_session_dataframes(session_id: int, dataframes: dict) -> None:
    """Register DataFrames for a chat session."""
    _session_dataframes[session_id] = dataframes


def clear_session_dataframes(session_id: int) -> None:
    """Clean up DataFrames when a session ends."""
    _session_dataframes.pop(session_id, None)


def _get_session_dataframes(ctx: Any) -> dict:
    """Retrieve DataFrames from the run context."""
    # The context object carries the session_id set by the route handler
    session_id = getattr(ctx, 'session_id', None) if ctx else None
    if session_id and session_id in _session_dataframes:
        return _session_dataframes[session_id]
    # Fallback: return empty DataFrames
    import pandas as pd
    return {
        'df_players': pd.DataFrame(),
        'df_loans': pd.DataFrame(),
        'df_matches': pd.DataFrame(),
        'df_journeys': pd.DataFrame(),
    }


async def refresh_player_stats(ctx, args_str: str) -> str:
    """Fetch fresh stats from API-Football for a player."""
    args = RefreshPlayerStatsArgs.model_validate_json(args_str)
    try:
        stats = api_client.get_player_statistics(args.player_id, args.season)
        return json.dumps({
            'status': 'refreshed',
            'player_id': args.player_id,
            'season': args.season,
            'stats': stats if isinstance(stats, (dict, list)) else str(stats),
        }, default=str)
    except Exception as e:
        logger.error("Failed to refresh player stats: %s", e)
        return json.dumps({'error': str(e)})


async def get_player_journey(ctx, args_str: str) -> str:
    """Get a player's career journey from academy to current."""
    args = GetPlayerJourneyArgs.model_validate_json(args_str)
    journey = PlayerJourney.query.filter_by(
        player_api_id=args.player_id
    ).first()

    if not journey:
        return json.dumps({'error': 'No journey data available for this player'})

    entries = PlayerJourneyEntry.query.filter_by(
        journey_id=journey.id
    ).order_by(PlayerJourneyEntry.season).all()

    return json.dumps({
        'player_name': journey.player_name,
        'player_api_id': journey.player_api_id,
        'nationality': journey.nationality,
        'origin': {
            'club': journey.origin_club_name,
            'year': journey.origin_year,
        } if journey.origin_club_name else None,
        'entries': [
            {
                'club': e.club_name,
                'season': e.season,
                'level': e.level,
                'appearances': e.appearances,
                'goals': e.goals,
                'assists': e.assists,
                'minutes': e.minutes,
            }
            for e in entries
        ],
    }, default=str)


async def run_analytics(ctx, args_str: str) -> str:
    """Execute Python code in a sandboxed subprocess against pre-loaded DataFrames."""
    args = RunAnalyticsArgs.model_validate_json(args_str)
    dataframes = _get_session_dataframes(ctx)

    result = execute_sandboxed_code(
        code=args.code,
        dataframes=dataframes,
    )
    return json.dumps(result, default=str)


# ---------- Tool Definitions ----------

refresh_player_stats_tool = FunctionTool(
    name="refresh_player_stats",
    description="Fetch fresh player statistics from API-Football. Use when the pre-loaded data may be stale.",
    params_json_schema=RefreshPlayerStatsArgs.model_json_schema(),
    on_invoke_tool=refresh_player_stats,
)

get_player_journey_tool = FunctionTool(
    name="get_player_journey",
    description="Get a player's career path from academy through loans to first team.",
    params_json_schema=GetPlayerJourneyArgs.model_json_schema(),
    on_invoke_tool=get_player_journey,
)

run_analytics_tool = FunctionTool(
    name="run_analytics",
    description=(
        "Execute Python code against pre-loaded DataFrames (df_players, df_loans, "
        "df_matches, df_journeys). Use pandas for analysis, matplotlib/plotly "
        "for charts. Call output_chart(fig) and output_table(df) to return results."
    ),
    params_json_schema=RunAnalyticsArgs.model_json_schema(),
    on_invoke_tool=run_analytics,
)


# ---------- Agent Factory ----------

def build_academy_watch_agent() -> Agent:
    """Build and return the Academy Watch analyst agent."""
    return Agent(
        name="Academy Watch Analyst",
        instructions=SYSTEM_PROMPT,
        model="gpt-4.1-mini",
        tools=[
            refresh_player_stats_tool,
            get_player_journey_tool,
            run_analytics_tool,
        ],
    )

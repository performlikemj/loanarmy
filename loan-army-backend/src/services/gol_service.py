"""
GOL Assistant Service

AI-powered chat service using OpenAI GPT-4.1-mini with tool calling
for querying the Go On Loan database and providing football insights.
"""

import json
import logging
import os
from typing import Generator, Optional

from openai import OpenAI
from sqlalchemy import func

from src.models.league import db, LoanedPlayer, Team, CommunityTake
from src.models.weekly import Fixture, FixturePlayerStats
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.cohort import AcademyCohort, CohortMember

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the GOL Assistant — a knowledgeable football scout and analyst \
for the Go On Loan platform. You help users explore loan players, academy pathways, \
and career journeys across European football.

Rules:
- Only reference data returned by your tools. Never fabricate player stats or facts.
- When you have data from a tool call, present it clearly with context and analysis.
- Use the data_card protocol: after tool calls, the system will display rich cards \
with the data inline in the conversation.
- Be conversational but precise. Use football terminology naturally.
- If you're unsure, say so rather than guessing.
- Keep responses concise — 2-3 paragraphs max unless the user asks for detail.
- When comparing players or analyzing trends, ground observations in the data."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_players",
            "description": "Search for players by name. Returns top 5 matches with basic info and current loan status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Player name to search for"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_journey",
            "description": "Get a player's complete career journey — all clubs, levels, and statistics from academy through first team.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_api_id": {"type": "integer", "description": "API-Football player ID"}
                },
                "required": ["player_api_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_stats",
            "description": "Get recent match-by-match statistics for a player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_api_id": {"type": "integer", "description": "API-Football player ID"},
                    "limit": {"type": "integer", "description": "Number of recent matches (default 5)", "default": 5}
                },
                "required": ["player_api_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_community_takes",
            "description": "Get approved fan commentary and opinions about a player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_api_id": {"type": "integer", "description": "API-Football player ID"}
                },
                "required": ["player_api_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_loans",
            "description": "Get all active loan players for a club.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team_api_id": {"type": "integer", "description": "API-Football team ID"}
                },
                "required": ["team_api_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cohort",
            "description": "Get an academy cohort — players who were in a club's youth setup for a given season, with 'where are they now' data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team_api_id": {"type": "integer", "description": "API-Football team ID"},
                    "season": {"type": "integer", "description": "Season year (e.g. 2022)"}
                },
                "required": ["team_api_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for recent football news about a player, team, or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
]


class GolService:
    """AI chat service with tool-calling for football data queries."""

    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        self.client = OpenAI(api_key=api_key)
        self.model = 'gpt-4.1-mini'

    def chat(self, message: str, history: list, session_id: str) -> Generator[dict, None, None]:
        """
        Process a chat message and yield SSE events.

        Args:
            message: User's message
            history: Previous messages [{role, content}]
            session_id: Session identifier

        Yields:
            Dict events: {event: str, data: dict}
        """
        try:
            # Build messages with system prompt
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            # Add history (cap at 20 messages = 10 turns)
            if history:
                messages.extend(history[-20:])

            messages.append({"role": "user", "content": message})

            # Initial completion
            yield from self._run_completion(messages)

        except Exception as e:
            logger.error(f"GOL chat error: {e}")
            yield {"event": "error", "data": {"message": str(e)}}

    def _run_completion(self, messages: list, depth: int = 0) -> Generator[dict, None, None]:
        """Run a streaming completion, handling tool calls recursively."""
        if depth > 5:
            yield {"event": "error", "data": {"message": "Too many tool call rounds"}}
            return

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            stream=True,
        )

        # Collect stream chunks
        content_buffer = ""
        tool_calls_buffer = {}

        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            finish_reason = chunk.choices[0].finish_reason

            # Text content
            if delta.content:
                content_buffer += delta.content
                yield {"event": "token", "data": {"content": delta.content}}

            # Tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": "",
                            "function": {"name": "", "arguments": ""}
                        }
                    if tc.id:
                        tool_calls_buffer[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_buffer[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

            # Handle finish
            if finish_reason == "tool_calls":
                # Process all tool calls
                if content_buffer:
                    messages.append({"role": "assistant", "content": content_buffer})

                # Build the assistant message with tool_calls
                assistant_tool_calls = []
                for idx in sorted(tool_calls_buffer.keys()):
                    tc = tool_calls_buffer[idx]
                    assistant_tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"]
                    })

                messages.append({
                    "role": "assistant",
                    "content": content_buffer or None,
                    "tool_calls": assistant_tool_calls
                })

                for idx in sorted(tool_calls_buffer.keys()):
                    tc = tool_calls_buffer[idx]
                    func_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    yield {"event": "tool_call", "data": {"name": func_name}}

                    # Execute tool
                    result = self._execute_tool(func_name, args)

                    # Emit data card
                    yield {"event": "data_card", "data": {"type": func_name, "payload": result}}

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result)
                    })

                # Continue with next completion round
                yield from self._run_completion(messages, depth + 1)
                return

            if finish_reason == "stop":
                yield {"event": "done", "data": {}}
                return

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool and return the result."""
        try:
            if name == "search_players":
                return self._tool_search_players(args.get("query", ""))
            elif name == "get_player_journey":
                return self._tool_get_player_journey(args.get("player_api_id"))
            elif name == "get_player_stats":
                return self._tool_get_player_stats(args.get("player_api_id"), args.get("limit", 5))
            elif name == "get_community_takes":
                return self._tool_get_community_takes(args.get("player_api_id"))
            elif name == "get_team_loans":
                return self._tool_get_team_loans(args.get("team_api_id"))
            elif name == "get_cohort":
                return self._tool_get_cohort(args.get("team_api_id"), args.get("season"))
            elif name == "search_web":
                return self._tool_search_web(args.get("query", ""))
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"error": str(e)}

    def _tool_search_players(self, query: str) -> dict:
        """Search for players by name."""
        players = LoanedPlayer.query.filter(
            LoanedPlayer.player_name.ilike(f"%{query}%"),
            LoanedPlayer.is_active == True
        ).limit(5).all()

        return {
            "players": [{
                "player_id": p.player_id,
                "player_name": p.player_name,
                "age": p.age,
                "nationality": p.nationality,
                "parent_club": p.primary_team_name,
                "loan_club": p.loan_team_name,
                "appearances": p.appearances,
                "goals": p.goals,
                "assists": p.assists,
            } for p in players],
            "total": len(players)
        }

    def _tool_get_player_journey(self, player_api_id: int) -> dict:
        """Get full career journey for a player."""
        journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
        if not journey:
            return {"error": "No journey data found for this player"}
        return journey.to_dict(include_entries=True)

    def _tool_get_player_stats(self, player_api_id: int, limit: int = 5) -> dict:
        """Get recent match stats for a player."""
        stats = db.session.query(FixturePlayerStats, Fixture).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_api_id
        ).order_by(Fixture.date_utc.desc()).limit(limit).all()

        return {
            "matches": [{
                "date": f.date_utc.isoformat() if f.date_utc else None,
                "competition": f.competition_name,
                "minutes": s.minutes,
                "goals": s.goals,
                "assists": s.assists,
                "rating": s.rating,
                "shots_on": s.shots_on,
                "passes_key": s.passes_key,
                "tackles": s.tackles_total,
                "dribbles_success": s.dribbles_success,
            } for s, f in stats],
            "total": len(stats)
        }

    def _tool_get_community_takes(self, player_api_id: int) -> dict:
        """Get approved community takes for a player."""
        takes = CommunityTake.query.filter_by(
            player_id=player_api_id,
            status='approved'
        ).order_by(CommunityTake.curated_at.desc()).limit(5).all()

        return {
            "takes": [{
                "content": t.content,
                "author": t.source_author,
                "source": t.source_type,
                "platform": t.source_platform,
                "upvotes": t.upvotes,
            } for t in takes],
            "total": len(takes)
        }

    def _tool_get_team_loans(self, team_api_id: int) -> dict:
        """Get all active loans for a team."""
        # Find team by API ID
        team = Team.query.filter_by(api_team_id=team_api_id).first()
        if not team:
            # Try searching by parent team
            loans = LoanedPlayer.query.filter(
                LoanedPlayer.is_active == True,
                LoanedPlayer.team_ids.like(f"%{team_api_id}%")
            ).all()
        else:
            loans = LoanedPlayer.query.filter(
                LoanedPlayer.is_active == True,
                db.or_(
                    LoanedPlayer.primary_team_id == team.id,
                    LoanedPlayer.loan_team_id == team.id
                )
            ).all()

        return {
            "loans": [{
                "player_id": l.player_id,
                "player_name": l.player_name,
                "age": l.age,
                "parent_club": l.primary_team_name,
                "loan_club": l.loan_team_name,
                "appearances": l.appearances,
                "goals": l.goals,
                "assists": l.assists,
                "pathway_status": l.pathway_status,
            } for l in loans],
            "total": len(loans)
        }

    def _tool_get_cohort(self, team_api_id: int, season: Optional[int] = None) -> dict:
        """Get academy cohort data."""
        query = AcademyCohort.query.filter_by(team_api_id=team_api_id)
        if season:
            query = query.filter_by(season=season)

        cohorts = query.order_by(AcademyCohort.season.desc()).limit(3).all()
        if not cohorts:
            return {"error": "No cohort data found for this team"}

        return {
            "cohorts": [c.to_dict(include_members=True) for c in cohorts]
        }

    def _tool_search_web(self, query: str) -> dict:
        """Search the web using Brave Search API."""
        import requests as req

        api_key = os.getenv('BRAVE_SEARCH_KEY')
        if not api_key:
            return {"error": "Web search not configured"}

        try:
            resp = req.get(
                'https://api.search.brave.com/res/v1/web/search',
                headers={'X-Subscription-Token': api_key, 'Accept': 'application/json'},
                params={'q': query, 'count': 3},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get('web', {}).get('results', [])[:3]:
                results.append({
                    'title': item.get('title'),
                    'url': item.get('url'),
                    'description': item.get('description'),
                })

            return {"results": results}

        except Exception as e:
            logger.warning(f"Web search failed: {e}")
            return {"error": f"Search failed: {str(e)}"}

    def get_suggestions(self) -> list:
        """Generate conversation starter suggestions based on recent data."""
        suggestions = []

        # Recent active loan players
        recent_players = LoanedPlayer.query.filter_by(
            is_active=True
        ).order_by(func.random()).limit(4).all()

        for p in recent_players:
            suggestions.append(f"How is {p.player_name} doing at {p.loan_team_name}?")

        if not suggestions:
            suggestions = [
                "Which Big 6 academy is producing the most first-team players?",
                "Show me all players on loan from Arsenal",
                "Who are the top-performing loan players this season?",
                "Tell me about Chelsea's academy pipeline",
            ]

        return suggestions[:4]

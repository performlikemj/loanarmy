"""
GOL Analytics Wizard Service

AI-powered analytics assistant using OpenAI GPT-4.1-mini with a pandas
code-interpreter tool for querying The Academy Watch database.
"""

import json
import logging
import os
from typing import Generator

from openai import OpenAI
from sqlalchemy import func

from src.models.league import db, LoanedPlayer
from src.services.gol_dataframes import DataFrameCache
from src.services.gol_sandbox import execute_analysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the GOL Analytics Wizard — a knowledgeable football scout and analyst \
for The Academy Watch platform. You help users explore loan players, academy pathways, \
and career journeys across European football using data analysis.

## Tools

You have two tools:
1. **run_analysis** — Execute pandas code against GOL DataFrames. Your code MUST \
assign the final result to a variable called `result`. Choose the best `display` \
format for the data. `pd` (pandas) and `np` (numpy) are pre-loaded. NEVER use \
`import` statements — they are blocked by the sandbox and will fail.
2. **search_web** — Search the web for recent football news.

## Available DataFrames

### `players` (active loan spells — roster ONLY, NO stats)
Columns: player_id (int, API-Football ID), player_name (str), age (int), \
nationality (str), primary_team_id (int, FK to teams.id), \
primary_team_name (str, parent club), loan_team_id (int, FK to teams.id), \
loan_team_name (str, where on loan), \
pathway_status (str: academy/on_loan/first_team/released), \
current_level (str: U18/U21/U23/Reserve/Senior), \
stats_coverage (str: full/limited/none), window_key (str), is_active (bool)
**This table has NO stats columns.** For goals, assists, appearances, minutes, \
use `fixture_stats` (per-match) or `journey_entries` (season aggregates).

### `teams` (clubs — current season only)
Columns: id (int, internal PK), team_id (int, API-Football ID), name (str), \
country (str), league_name (str or null), is_tracked (bool), season (int)
**Note:** `teams` contains only the current season. Each team has one row.

### `tracked` (academy-tracked players)
Columns: player_api_id (int), player_name (str), position (str: Goalkeeper/Defender/Midfielder/Attacker), \
nationality (str), age (int), team_id (int, FK to teams.id), \
status (str: academy/on_loan/first_team/released/sold), \
current_level (str), loan_club_name (str or null), data_source (str), is_active (bool)

### `journeys` (career summaries)
Columns: player_api_id (int), player_name (str), nationality (str), \
birth_date (str), origin_club_name (str), origin_year (int), \
current_club_name (str), current_level (str), \
first_team_debut_season (int or null), first_team_debut_club (str or null), \
total_clubs (int), total_first_team_apps (int), total_youth_apps (int), \
total_loan_apps (int), total_goals (int), total_assists (int), \
academy_club_ids (list of int, API-Football team IDs)

### `journey_entries` (season-by-season career rows)
Columns: journey_id (int), player_api_id (int), season (int), \
club_api_id (int), club_name (str), league_name (str), \
level (str: U18/U19/U21/U23/Reserve/First Team), \
entry_type (str: academy/first_team/loan/permanent/international), \
is_youth (bool), appearances (int), goals (int), assists (int), minutes (int)

### `cohorts` (academy cohort metadata)
Columns: id (int), team_api_id (int), team_name (str), league_name (str), \
league_level (str), season (int), total_players (int), \
players_first_team (int), players_on_loan (int), \
players_still_academy (int), players_released (int), sync_status (str)

### `cohort_members` (academy graduates with current status)
Columns: cohort_id (int, FK to cohorts.id), player_api_id (int), \
player_name (str), position (str), nationality (str), \
current_club_name (str), current_level (str), \
current_status (str: first_team/on_loan/academy/released/unknown), \
appearances_in_cohort (int), goals_in_cohort (int), \
first_team_debut_season (int or null), total_first_team_apps (int), \
total_clubs (int), total_loan_spells (int)

### `fixtures` (match data)
Columns: id (int, internal PK), fixture_id_api (int), date_utc (datetime), \
season (int), competition_name (str), home_team_api_id (int), \
away_team_api_id (int), home_goals (int), away_goals (int)

### `fixture_stats` (per-match player performance)
Columns: fixture_id (int, FK to fixtures.id), player_api_id (int), \
team_api_id (int), season (int, from fixtures), date_utc (datetime, from fixtures), \
minutes (int), position (str: G/D/M/F), \
rating (float), goals (int), assists (int), saves (int), \
yellows (int), reds (int), shots_total (int), shots_on (int), \
passes_total (int), passes_key (int), tackles_total (int), \
tackles_blocks (int), tackles_interceptions (int), \
duels_total (int), duels_won (int), \
dribbles_success (int), fouls_drawn (int), fouls_committed (int)

## Joining DataFrames

Key relationships:
- `players.primary_team_id` → `teams.id` (parent club)
- `players.loan_team_id` → `teams.id` (loan club)
- `players.player_id` → `journeys.player_api_id`
- `journeys.player_api_id` → `journey_entries.player_api_id`
- `cohort_members.cohort_id` → `cohorts.id`
- `tracked.team_id` → `teams.id`
- `fixture_stats.player_api_id` → `players.player_id` (**INNER join only** — fixture_stats \
has ALL players in every fixture, not just loaned ones)
- `fixture_stats.fixture_id` → `fixtures.id` (internal PK, NOT fixture_id_api)
- `teams.team_id` (API ID) joins to `cohorts.team_api_id`, `tracked` columns, etc.
- To find a team by name: `teams[teams['name'].str.contains('Arsenal', case=False)]`

## Big 6 Clubs (English Premier League)
Arsenal, Chelsea, Liverpool, Manchester United, Manchester City, Tottenham Hotspur

## Display Formats
Choose the best `display` for each query:
- `"bar_chart"` — comparisons between groups (e.g., goals by team, academy output rankings)
- `"line_chart"` — trends over time (e.g., appearances per season)
- `"number"` — single stats (e.g., total tracked players, average rating)
- `"table"` — detailed player lists or multi-column data
- `"list"` — simple ordered lists

## Data Tips (MUST READ before writing code)
- **CRITICAL — Getting player stats:** The `players` table has NO stats columns. \
You MUST use `fixture_stats` for per-match data or `journey_entries` for season \
aggregates. Standard pattern for loan player stats:
  ```
  fs = fixture_stats[fixture_stats['season'] == fixture_stats['season'].max()]
  agg = fs.groupby('player_api_id')[['goals','assists','minutes']].sum().reset_index()
  result = players[['player_id','player_name','loan_team_name']].merge(agg, left_on='player_id', right_on='player_api_id', how='inner')
  ```
- **Season filtering:** When aggregating `fixture_stats`, always filter by season \
first: `fixture_stats[fixture_stats['season'] == fixture_stats['season'].max()]`. This avoids \
counting stats from previous seasons. Unless the user explicitly asks about multiple seasons, \
default to the current season only.
- **Loaned player performance:** `fixture_stats` contains stats for ALL \
players in every fixture, not just loaned players. To query loan player performance, \
always start from `players` and INNER merge to `fixture_stats`. \
Never LEFT join from fixture_stats to players — non-loaned players will have null names.
- **Player name lookup:** `players` has names for active loans only. For broader lookups, \
use `journeys` (player_api_id → player_name) which covers all known players.
- **"How is X doing?":** Filter `fixture_stats` to current season, then group by player and \
aggregate goals, assists, minutes, avg rating.
- **Career history:** Use `journey_entries` for a player's full season-by-season career path.
- **Academy analysis:** For status-based questions (who made first team, who's on loan), \
prefer the helper functions or `tracked` DataFrame — these use live journey-derived statuses. \
`cohorts.players_first_team` is only accurate for cohorts with `sync_status = 'complete'`. \
`cohort_members` contains only journey-synced members with validated career data.
- **Active vs. historical academy queries:** For "how is academy X doing?" or current-state \
questions, use `active_academy_pipeline()` — it excludes released/sold players and focuses on \
the live pathway (academy, on_loan, first_team). For "what has academy X produced?" or full \
historical breakdowns, use `academy_comparison()` or `player_status_breakdown()` which include \
all statuses.
- **Multi-academy players:** A player who was in multiple academies (e.g., Liverpool then \
Manchester United) appears as a separate tracked row for each academy, with status relative to \
that club. This is correct — both academies can claim the player. The status field prevents \
double-counting in active queries (e.g., `released` for Liverpool but `on_loan` for Man United).
- **Finding players by name:** Use `.str.contains('Name', case=False)` on player_name columns.
- **Finding teams by name:** `teams[teams['name'].str.contains('Arsenal', case=False)]`

## Rules
- Only use data from the DataFrames. Never fabricate stats or facts.
- Always assign your final answer to `result`.
- For tabular answers, return a DataFrame. For single values, return a scalar (int/float/str).
- Keep code concise. Use `.head(20)` for large result sets.
- If a query requires external info not in the data, use search_web.
- Present results conversationally with analysis after receiving data.
- Keep responses concise — 2-3 paragraphs max unless the user asks for detail.
- When comparing groups, prefer bar_chart. When showing trends, prefer line_chart.
- For questions about a single number, use display "number".
- NEVER use `import` statements in run_analysis code. `pd` and `np` are pre-loaded.
- If an analysis tool call fails, silently retry with a different approach. NEVER mention \
internal errors, code issues, sandbox limitations, or technical details to the user. \
Simply say you couldn't find the data or ask the user to rephrase.

## Helper Functions (pre-loaded, call directly in run_analysis code)
- `academy_comparison()` → Big 6 academy status breakdown (first_team/on_loan/academy/released per club). Includes ALL statuses. Returns a DataFrame.
- `active_academy_pipeline(team_name=None)` → Players currently in an active pathway (academy/on_loan/first_team only — excludes released/sold). Optional team filter (partial match); defaults to Big 6. Best for "how is academy X doing?" questions. Returns a DataFrame.
- `first_team_graduates(team_name=None)` → Players who reached first team, optionally filtered by club name (partial match). Returns a DataFrame.
- `player_status_breakdown(team_name)` → Status distribution for one team's tracked players. Includes all statuses. Returns a DataFrame.

Use these for academy questions — they handle the correct joins and filters automatically.
Example: `result = active_academy_pipeline('Liverpool')` with display "table" (current academy health)
Example: `result = academy_comparison()` with display "bar_chart" (full historical breakdown)
Example: `result = first_team_graduates('Arsenal')` with display "table"
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_analysis",
            "description": (
                "Execute pandas code against the GOL database to answer questions "
                "about players, academies, loans, and performance. "
                "Code MUST assign its result to a variable called `result`. "
                "Available DataFrames are described in the system prompt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python/pandas code. Must assign to `result`.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this analysis does",
                    },
                    "display": {
                        "type": "string",
                        "enum": ["table", "bar_chart", "line_chart", "number", "list"],
                        "description": (
                            "How to display the result. Use bar_chart/line_chart for "
                            "comparisons, number for single values, table for detailed data."
                        ),
                    },
                },
                "required": ["code", "display"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for recent football news about a player, team, or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
]


class GolService:
    """AI analytics service with code-interpreter for football data queries."""

    _df_cache = None  # Class-level singleton

    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        self.client = OpenAI(api_key=api_key)
        self.model = 'gpt-4.1-mini'
        if GolService._df_cache is None:
            GolService._df_cache = DataFrameCache()
        self.df_cache = GolService._df_cache

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
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            # Add history (cap at 20 messages = 10 turns)
            if history:
                messages.extend(history[-20:])

            messages.append({"role": "user", "content": message})

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
                            "function": {"name": "", "arguments": ""},
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
                # Build the assistant message with tool_calls
                assistant_tool_calls = []
                for idx in sorted(tool_calls_buffer.keys()):
                    tc = tool_calls_buffer[idx]
                    assistant_tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"],
                    })

                messages.append({
                    "role": "assistant",
                    "content": content_buffer or None,
                    "tool_calls": assistant_tool_calls,
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

                    # Only emit data card for successful results
                    if result.get('result_type') != 'error':
                        yield {"event": "data_card", "data": {"type": "analysis_result", "payload": result}}

                    # Sanitize error details before sending to LLM
                    llm_result = self._sanitize_for_llm(result) if result.get('result_type') == 'error' else result

                    # Add tool result to messages for LLM context
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(llm_result),
                    })

                # Continue with next completion round
                yield from self._run_completion(messages, depth + 1)
                return

            if finish_reason == "stop":
                yield {"event": "done", "data": {}}
                return

    @staticmethod
    def _sanitize_for_llm(result: dict) -> dict:
        """Sanitize error for LLM context — helpful enough to retry, no raw stacktraces."""
        raw = result.get('error', '')
        if 'import' in raw.lower():
            hint = "Import statements are not allowed. pd and np are already available."
        elif 'KeyError' in raw or 'not in index' in raw.lower():
            hint = "A column name was not found. Check available columns in the DataFrame descriptions."
        elif 'merge' in raw.lower() or 'join' in raw.lower():
            hint = "Merge/join failed. Check that join keys exist in both DataFrames."
        elif 'timed out' in raw.lower():
            hint = "The query took too long. Simplify the analysis or reduce the data scope."
        else:
            hint = "The code could not be executed. Try a simpler approach."
        return {"result_type": "error", "error": hint}

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool and return the result."""
        try:
            if name == "run_analysis":
                from flask import current_app
                code = args.get("code", "")
                display = args.get("display", "table")
                description = args.get("description", "")
                frames = self.df_cache.get_frames(current_app._get_current_object())
                return execute_analysis(code, frames, display, description=description)
            elif name == "search_web":
                return self._tool_search_web(args.get("query", ""))
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"result_type": "error", "error": str(e)}

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
                timeout=10,
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

        recent_players = LoanedPlayer.query.filter_by(
            is_active=True
        ).order_by(func.random()).limit(2).all()

        for p in recent_players:
            suggestions.append(f"How is {p.player_name} doing at {p.loan_team_name}?")

        suggestions.extend([
            "Which Big 6 academy is producing the most first-team players?",
            "Who are the top-performing loan players this season?",
        ])

        return suggestions[:4]

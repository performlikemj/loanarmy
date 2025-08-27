import os
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from agents import (
    set_default_openai_client
)
from openai import OpenAI  # OpenAI Agents SDK
from src.models.league import db, Team, LoanedPlayer, Newsletter
from src.api_football_client import APIFootballClient

# If you have an MCP client already for Brave (Model Context Protocol), import it here.
# This is a thin wrapper that exposes a Python function brave_search(query: str, since: str, until: str) -> List[dict]
from src.mcp.brave import brave_search  # implement this wrapper to call your MCP tool
from .weekly_agent import get_league_localization
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

# client = OpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=os.getenv("OPENROUTER_API_KEY")
# )
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(client)
print(f'newsletter client: {client}')
api_client = APIFootballClient()

SYSTEM_PROMPT = """You are an editorial assistant for a football club newsletter.
- Input: a weekly loan report JSON (player stats and match outcomes) + search context (articles/notes).
- Output: a concise, fan-friendly newsletter as JSON. Keep it factual, readable, with short paragraphs and bullet lists where helpful.
- Required JSON shape:
{
  "title": "...",
  "summary": "...",
  "season": "YYYY-YY",
  "range": ["YYYY-MM-DD","YYYY-MM-DD"],
  "highlights": ["...","..."],
  "sections": [
    {
      "title": "Active Loans",
      "items": [
        {
          "player_name": "...",
          "loan_team": "...",
          "week_summary": "...",             // 1–3 sentences
          "stats": {"minutes": 0,"goals": 0,"assists": 0,"yellows": 0,"reds": 0},
          "match_notes": ["..."],            // 0–3 bullets
          "links": ["https://...", "..."]    // from search results, 0–3 links
        }
      ]
    },
    {
      "title": "What the Internet is Saying",
      "items": [
        {"player_name": "J. Sancho", "links": [{"title": "...","url":"..."}]},
        {"player_name": "H. Mejbri", "links": [{"title": "...","url":"..."}]}
      ]
    }
  ]
}
- Always JSON-serialize your final answer. Do not include commentary outside JSON.
"""

def _monday_range(target: date) -> tuple[date, date]:
    # Monday–Sunday window for weekly issues
    start = target - timedelta(days=target.weekday())
    end = start + timedelta(days=6)
    return start, end

def fetch_weekly_report_tool(parent_team_db_id: int, season_start_year: int, start: date, end: date) -> Dict[str, Any]:
    # Resolve API id and name from DB
    team = Team.query.get(parent_team_db_id)
    if not team:
        raise ValueError(f"Team DB id {parent_team_db_id} not found")

    # Make sure API client season matches
    api_client.set_season_year(season_start_year)
    api_client._prime_team_cache(season_start_year)

    # Find active loanees exist; if none, we’ll still generate a short “No loans” issue
    has_loans = (
        db.session.query(LoanedPlayer)
        .filter(LoanedPlayer.primary_team_id == parent_team_db_id, LoanedPlayer.is_active.is_(True))
        .count()
        > 0
    )

    report = api_client.summarize_parent_loans_week(
        parent_team_db_id=team.id,
        parent_team_api_id=team.team_id,
        season=season_start_year,
        week_start=start,
        week_end=end,
        include_team_stats=False,
        db_session=db.session,
    )

    # Normalize parent team payload
    report["parent_team"] = {"db_id": team.id, "id": team.team_id, "name": team.name}
    db.session.commit()
    report["has_active_loans"] = has_loans
    return report

def brave_context_for_team_and_loans(team_name: str, report: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    # Build a small set of targeted queries for context enrichment
    start, end = report["range"]
    default_loc = get_league_localization("Premier League")
    queries: List[tuple[str, Dict[str, str]]] = []
    seen: set[str] = set()

    def add_query(q: str, loc: Dict[str, str]):
        if q not in seen:
            queries.append((q, loc))
            seen.add(q)

    add_query(f"{team_name} loan players {start}..{end}", default_loc)

    for loanee in report.get("loanees", []):
        pname = loanee.get("player_name")
        loan_team_name = loanee.get("loan_team_name")
        if pname and loan_team_name:
            league_name = "Premier League"
            loan_team_db_id = loanee.get("loan_team_db_id")
            if loan_team_db_id:
                loan_team = Team.query.get(loan_team_db_id)
                if loan_team and getattr(loan_team, "league", None):
                    league_name = loan_team.league.name
            localization = get_league_localization(league_name)
            add_query(f"{pname} {loan_team_name} {start}..{end}", localization)
            for m in loanee.get("matches", []):
                opponent = m.get("opponent")
                comp = m.get("competition")
                if opponent:
                    add_query(
                        f"{pname} {loan_team_name} vs {opponent} {comp} {start}..{end}",
                        localization,
                    )

    results = {}
    for q, loc in queries:
        try:
            hits = brave_search(
                query=q,
                since=start,
                until=end,
                country=loc.get("country", "GB"),
                search_lang=loc.get("search_lang", "en"),
                ui_lang=loc.get("ui_lang", "en-GB"),
            )  # returns list of {title, url, snippet, date, source}
            results[q] = hits[:5]
        except Exception:
            results[q] = []
    return results

def persist_newsletter(team_db_id: int, content_json_str: str, week_start: date, week_end: date, issue_date: date, newsletter_type: str = "weekly") -> Newsletter:
    parsed = json.loads(content_json_str)
    title = parsed.get("title") or "Weekly Loan Update"

    newsletter = Newsletter(
        team_id=team_db_id,
        newsletter_type=newsletter_type,
        title=title,
        content=content_json_str,           # store verbatim JSON as content
        structured_content=content_json_str,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=issue_date,
        generated_date=date.today(),
        published=True,
        published_date=date.today(),
    )
    db.session.add(newsletter)
    db.session.commit()
    return newsletter

def generate_team_weekly_newsletter(team_db_id: int, target_date: date) -> dict:
    # Compute week window
    week_start, week_end = _monday_range(target_date)

    # Derive season from the week we are processing (European season starts Aug 1)
    season_start_year = week_start.year if week_start.month >= 8 else week_start.year - 1
    api_client.set_season_year(season_start_year)
    api_client._prime_team_cache(season_start_year)

    # Fetch report via tool for the inferred season
    report = fetch_weekly_report_tool(team_db_id, season_start_year, week_start, week_end)

    # Brave context
    brave_ctx = brave_context_for_team_and_loans(report["parent_team"]["name"], report)

    # Compose agent input
    user_payload = {
        "task": "compose_weekly_newsletter",
        "team": report["parent_team"],
        "report": report,
        "search_context": brave_ctx
    }

    # In Agents SDK, create a transient thread and run with tool-less generation (we already fetched inputs)
    # You can also wire these as Tools the agent can call, if you prefer. For simplicity, pass both datasets.
    completion = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)}
        ],
        temperature=0.4,
    )

    content = completion.output_text or "{}"
    # Hard guard: ensure content is valid JSON
    try:
        json.loads(content)
    except Exception:
        # If model wrapped JSON in prose, try to extract JSON block
        import re
        blocks = re.findall(r"\{(?:.|\n)*\}", content)
        if blocks:
            content = blocks[0]
        json.loads(content)  # will raise if still invalid

    row = persist_newsletter(
        team_db_id=team_db_id,
        content_json_str=content,
        week_start=week_start,
        week_end=week_end,
        issue_date=target_date,
        newsletter_type="weekly"
    )
    return row.to_dict()
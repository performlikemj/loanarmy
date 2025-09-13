from __future__ import annotations
from src.mcp import brave as brave_api
import os
import json
import asyncio
import random
import shutil
import subprocess
import logging
import re
import unicodedata
from urllib.parse import urlparse
from datetime import date, timedelta
from typing import Any, Dict, Annotated
import dataclasses
from collections.abc import Mapping
from pydantic import BaseModel, Field, Json, StringConstraints
from openai import AsyncOpenAI
from agents import (Agent, 
                    FunctionTool, 
                    Runner,
                    set_default_openai_client,
                    ToolCallItem,
                    ToolCallOutputItem,
                    )
from agents.run_context import RunContextWrapper

from src.models.league import db, Team, LoanedPlayer, Newsletter, LeagueLocalization
from jinja2 import Environment, FileSystemLoader, select_autoescape
from src.api_football_client import APIFootballClient
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

# Debug flags for search logging
DEBUG_MCP = os.getenv("MCP_DEBUG") == "1"
try:
    MCP_LOG_SAMPLE_N = int(os.getenv("MCP_LOG_SAMPLE_N") or "2")
except Exception:
    MCP_LOG_SAMPLE_N = 2

# Freshness policy flags
STRICT_FRESHNESS = (os.getenv("MCP_STRICT_FRESHNESS", "1").lower() in ("1", "true", "yes"))
ALLOW_WIDE_FRESHNESS = (os.getenv("MCP_ALLOW_WIDE_FRESHNESS", "0").lower() in ("1", "true", "yes"))

def _log_sample(tag: str, pid: str, query: str, results: list[dict]):
    if not DEBUG_MCP:
        return
    log = logging.getLogger(__name__)
    try:
        log.info("BRAVE %s | pid=%s | q=%r | total=%d", tag, pid, query, len(results or []))
        for r in (results or [])[:MCP_LOG_SAMPLE_N]:
            title = (r.get('title') or '')[:140]
            url = (r.get('url') or '')[:160]
            pub = r.get('publisher')
            sent = r.get('sentiment')
            log.info("  · %s | %s | pub=%s | sent=%s", title, url, pub, sent)
        # also log raw JSON samples for debugging integration issues
        try:
            import json as _json
            log.info("BRAVE %s RAW | pid=%s | %s", tag, pid, _json.dumps((results or [])[:MCP_LOG_SAMPLE_N], ensure_ascii=False)[:1000])
        except Exception:
            pass
    except Exception:
        pass

# Module-level cache to make search_context available to persist tool when the agent omits it
_LATEST_SEARCH_CONTEXT: dict[str, dict] | None = None

# --- String sanitization helpers (remove ASCII control chars except \t, \n, \r) ---
import re
from urllib.parse import urlparse
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _clean_str(s: str) -> str:
    if not isinstance(s, str):
        return s
    return _CONTROL_RE.sub('', s)

def _sanitize(obj):
    if isinstance(obj, str):
        return _clean_str(obj)
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj

# ---------- Utilities ----------
def monday_range(target: date) -> tuple[date, date]:
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)

def freshness_range_str(start_date: date, end_date: date | None = None, *, fallback: str = "pw") -> str:
    """
    Build Brave MCP freshness strings. Always return a plain str.
    - If both dates provided: 'YYYY-MM-DDtoYYYY-MM-DD'
    - Else: fallback shorthand (pd|pw|pm|py)
    Strips any non-printable characters defensively.
    """
    try:
        s = str(start_date)[:10]
        if end_date is not None:
            e = str(end_date)[:10]
            val = f"{s}to{e}"
        else:
            val = fallback
        return "".join(ch for ch in val if ch.isprintable())
    except Exception:
        return fallback

def get_league_localization(league_name: str) -> dict:
    """
    Get Brave Search localization parameters based on league.
    Returns country code, search language, and UI language for optimal results.
    """
    try:
        loc = LeagueLocalization.query.filter_by(league_name=league_name).first()
        if loc:
            return {'country': loc.country, 'search_lang': loc.search_lang, 'ui_lang': loc.ui_lang}
    except Exception:
        # If DB is unavailable or query fails, fall back to hard-coded mapping
        pass

    localizations = {
        'Premier League': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'La Liga': {'country': 'ES', 'search_lang': 'es', 'ui_lang': 'es-ES'},
        'Segunda División': {'country': 'ES', 'search_lang': 'es', 'ui_lang': 'es-ES'},
        'Ligue 1': {'country': 'FR', 'search_lang': 'fr', 'ui_lang': 'fr-FR'},
        'Ligue 2': {'country': 'FR', 'search_lang': 'fr', 'ui_lang': 'fr-FR'},
        'Bundesliga': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        'Bundesliga 2': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        '2. Bundesliga': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        'Serie A': {'country': 'IT', 'search_lang': 'it', 'ui_lang': 'it-IT'},
        'Serie B': {'country': 'IT', 'search_lang': 'it', 'ui_lang': 'it-IT'},
        'Championship': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'League One': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'League Two': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'Eredivisie': {'country': 'NL', 'search_lang': 'nl', 'ui_lang': 'nl-NL'},
        'Eerste Divisie': {'country': 'NL', 'search_lang': 'nl', 'ui_lang': 'nl-NL'},
        'Primeira Liga': {'country': 'PT', 'search_lang': 'pt', 'ui_lang': 'pt-PT'},
        'Liga Portugal 2': {'country': 'PT', 'search_lang': 'pt', 'ui_lang': 'pt-PT'},
        'Scottish Premiership': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'Scottish Championship': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'MLS': {'country': 'US', 'search_lang': 'en', 'ui_lang': 'en-US'},
        'Major League Soccer': {'country': 'US', 'search_lang': 'en', 'ui_lang': 'en-US'},
        'Belgian Pro League': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Jupiler Pro League': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Belgian First Division A': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Belgian First Division B': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Süper Lig': {'country': 'TR', 'search_lang': 'tr', 'ui_lang': 'tr-TR'},
        'TFF First League': {'country': 'TR', 'search_lang': 'tr', 'ui_lang': 'tr-TR'},
    }
    return localizations.get(league_name, {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'})

def build_enhanced_queries(player: str, loan_team: str, opponent: str, competition: str, league_lang: str) -> list:
    """
    Build enhanced search queries with multiple synonyms and local language terms.
    Returns a list of query variations for better search coverage.
    """
    # Base English terms that work across all leagues
    base_terms = [
        "player ratings", "match reaction", "analysis", "performance review", 
        "what fans said", "match report", "player performance", "fan reaction"
    ]
    
    # Add local language terms based on league
    if league_lang == 'es':
        base_terms.extend([
            "análisis", "valoración", "reacción de aficionados", "reporte del partido",
            "rendimiento del jugador", "opinión de la afición"
        ])
    elif league_lang == 'fr':
        base_terms.extend([
            "analyse", "évaluation", "réaction des supporters", "rapport de match",
            "performance du joueur", "avis des fans"
        ])
    elif league_lang == 'de':
        base_terms.extend([
            "Analyse", "Bewertung", "Fan-Reaktionen", "Spielbericht",
            "Spielerleistung", "Fan-Meinung"
        ])
    elif league_lang == 'it':
        base_terms.extend([
            "analisi", "valutazione", "reazione dei tifosi", "rapporto partita",
            "prestazione giocatore", "opinione tifosi"
        ])
    
    # Build queries with different term combinations
    queries = []
    for term in base_terms:
        # Per-match specific query
        if opponent and competition:
            queries.append(f'"{player}" "{loan_team}" "{opponent}" "{competition}" {term}')
        # Weekly overview query
        queries.append(f'"{player}" "{loan_team}" {term}')
    
    # Add some broader queries for better coverage
    queries.extend([
        f'"{player}" {loan_team} {term}' for term in ["news", "latest", "update", "performance"]
    ])
    
    return queries[:8]  # Limit to 8 queries to avoid overwhelming the API

def categorize_and_deduplicate_results(web_results: list, news_results: list) -> dict:
    """
    Categorize and deduplicate search results for better organization.
    Returns categorized results with sentiment indicators.
    """
    # Deduplicate by URL
    seen_urls = set()
    unique_web = []
    unique_news = []
    
    for result in web_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_web.append(result)
    
    for result in news_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_news.append(result)
    
    # Categorize web results
    discussions = []
    videos = []
    articles = []
    
    for result in unique_web:
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        snippet = (result.get('description') or result.get('snippet') or '').lower()
        
        # Simple categorization based on URL patterns and content
        if any(word in url for word in ['forum', 'reddit', 'twitter', 'facebook', 'instagram']):
            discussions.append(result)
        elif any(word in url for word in ['youtube', 'vimeo', 'dailymotion', '.mp4', '.avi']):
            videos.append(result)
        else:
            articles.append(result)
    
    # Basic sentiment analysis based on keywords
    def analyze_sentiment(text: str) -> str:
        text_lower = text.lower()
        positive_words = ['excellent', 'outstanding', 'brilliant', 'amazing', 'fantastic', 'great', 'good', 'impressive']
        negative_words = ['poor', 'terrible', 'awful', 'disappointing', 'bad', 'weak', 'struggled', 'failed']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    # Add sentiment to all results
    for result in unique_web + unique_news:
        text = f"{result.get('title', '')} {(result.get('snippet') or result.get('description') or '')}"
        result['sentiment'] = analyze_sentiment(text)
    
    return {
        "web": articles[:10],
        "news": unique_news[:10],
        "discussions": discussions[:8],
        "videos": videos[:5],
        "summaries": [r.get('summary') for r in unique_web + unique_news if r.get('summary')],
        "sentiment_breakdown": {
            "positive": len([r for r in unique_web + unique_news if r.get('sentiment') == 'positive']),
            "negative": len([r for r in unique_web + unique_news if r.get('sentiment') == 'negative']),
            "neutral": len([r for r in unique_web + unique_news if r.get('sentiment') == 'neutral'])
        }
    }

# --- Post-filter helpers for Brave results (date/name/team/domain gates) ---
from datetime import datetime

_ALLOWED_FORUM_HOSTS = (
    "reddit.com",
    "old.reddit.com",
)

_DENY_WEB_HOST_SUBSTR = (
    "fandom.com",
    "ea.com/games/ea-sports-fc",
)

def _parse_any_date(val: str | None) -> date | None:
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    # ISO-like: 2024-10-31 or 2024-10-31T00:23:16
    try:
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return date.fromisoformat(s[:10])
    except Exception:
        pass
    # Common textual forms
    fmts = [
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
        "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def _text_matches_player_team(text: str, player_name: str, loan_team: str) -> bool:
    txt = strip_diacritics(text or '').lower()
    # Require last-name match
    last = strip_diacritics((player_name or '').split()[-1]).lower().strip('. ')
    if last and last not in txt:
        return False
    # Team match improves precision; allow transfer/global pieces if last name present
    team = strip_diacritics(loan_team or '').lower()
    if team and team in txt:
        return True
    # If team missing in text, still allow for purely transfer/rumour contexts.
    # Heuristic: presence of common transfer terms keeps it; otherwise drop.
    transfer_terms = ("transfer", "loan", "linked", "talks", "negotiation", "sign", "move")
    if any(t in txt for t in transfer_terms):
        return True
    return False

def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _filter_hits_for_player(cat: dict, player_name: str, loan_team: str, week_start: date, week_end: date) -> dict:
    """Apply date/name/team/domain gates to categorized results.
    - Keep items within week window ± (−2, +3) days when a usable date exists.
    - Require last name in title/snippet; prefer team mention or transfer terms.
    - Drop denylisted web hosts.
    - Limit discussions to forum domains (reddit) only for fan pulse.
    """
    lower = week_start - timedelta(days=2)
    upper = week_end + timedelta(days=3)

    def ok_item(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        url = (r.get('url') or r.get('link') or '').strip()
        if not url:
            return False
        h = _host(url)
        # deny some obviously noisy hosts for web/news
        if any(bad in h or bad in url for bad in _DENY_WEB_HOST_SUBSTR):
            return False
        title = r.get('title') or r.get('name') or ''
        snippet = r.get('snippet') or r.get('description') or ''
        if not _text_matches_player_team(f"{title} {snippet}", player_name, loan_team):
            return False
        # Date gate (if present)
        d = _parse_any_date(r.get('date') or r.get('published') or r.get('published_date') or r.get('age') or r.get('page_age'))
        if d is not None and not (lower <= d <= upper):
            return False
        return True

    def ok_forum(r: dict) -> bool:
        url = (r.get('url') or '').strip()
        h = _host(url)
        if not h:
            return False
        if h in _ALLOWED_FORUM_HOSTS or 'forum' in h:
            # name/team gate still applies
            title = r.get('title') or ''
            snip = r.get('snippet') or r.get('description') or ''
            if not _text_matches_player_team(f"{title} {snip}", player_name, loan_team):
                return False
            d = _parse_any_date(r.get('date') or r.get('published') or r.get('published_date') or r.get('age') or r.get('page_age'))
            if d is not None and not (lower <= d <= upper):
                return False
            return True
        return False

    try:
        web = [r for r in (cat.get('web') or []) if ok_item(r)]
        news = [r for r in (cat.get('news') or []) if ok_item(r)]
        disc = [r for r in (cat.get('discussions') or []) if ok_forum(r)]
        vids = [r for r in (cat.get('videos') or []) if ok_item(r)]
        return {
            **cat,
            'web': web,
            'news': news,
            'discussions': disc,
            'videos': vids,
        }
    except Exception:
        return cat

api_client = APIFootballClient()
# aio_client = AsyncOpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=os.getenv("OPENROUTER_API_KEY")
# )
aio_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(aio_client)
print(f'weekly agent client: {aio_client}')

# ---------- JSON safety helpers ----------

def _to_jsonable(obj: Any) -> Any:
    """Convert SDK/runtime objects (e.g., ResponseFunctionToolCall) into JSON-serializable data.

    - Preserves primitives and mappings
    - Recursively converts sequences
    - Supports dataclasses and Pydantic models
    - Falls back to extracting common tool-call fields (name, arguments)
    - Ultimately falls back to str(obj)
    """
    # Primitives and None
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Mappings
    if isinstance(obj, Mapping):
        return {str(_to_jsonable(k)): _to_jsonable(v) for k, v in obj.items()}

    # Common sequences
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(x) for x in obj]

    # Dataclasses
    if dataclasses.is_dataclass(obj):
        try:
            return _to_jsonable(dataclasses.asdict(obj))
        except Exception:
            pass

    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return _to_jsonable(obj.model_dump())
        except Exception:
            pass

    # Pydantic v1 style
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return _to_jsonable(obj.dict())
        except Exception:
            pass

    # Try to extract common tool-call fields if present
    try:
        name = getattr(obj, "name", None)
        arguments = getattr(obj, "arguments", None)
        if name is not None or arguments is not None:
            # arguments may be a JSON string or a dict
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except Exception:
                    # keep as string if not JSON
                    pass
            return {
                "type": obj.__class__.__name__,
                "name": name,
                "arguments": _to_jsonable(arguments),
            }
    except Exception:
        pass

    # Best-effort fallback
    try:
        return str(obj)
    except Exception:
        return repr(obj)

# reusable type for ISO-date string
DateStr = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        min_length=10,
        max_length=10
    )
]

class FetchWeeklyReportArgs(BaseModel):
    parent_team_db_id: int = Field(..., description="DB PK of the parent team")
    target_date: DateStr = Field(..., description="YYYY-MM-DD ISO date")

class PersistNewsletterArgs(BaseModel):
    team_db_id: int = Field(..., description="DB PK of the parent team")
    content_json: Json[Any] = Field(..., description="Structured newsletter payload")
    issue_date: DateStr = Field(..., description="YYYY-MM-DD ISO date")

SYSTEM_INSTRUCTIONS = """
You are a football newsletter editor. Tools available: Python tools. The search context is precomputed using the Brave Search API.

Workflow:
1) Call fetch_weekly_report(team, date). You get week_start/week_end, per-player matches, minutes, G/A, cards.
2) The search context is now pre-computed with enhanced Brave Search results including:
   - Localized searches based on league (country, language)
   - Multi-language queries for better coverage
   - Categorized results: web articles, news, discussions, videos
   - Sentiment analysis for each result
   - Summaries when available
   - Deduplicated and ranked results

Identity & naming (STRICT):
- Include the API-Football player_id on each item.
- Use first-initial + last-name for player_name (e.g., "H. Mejbri", "Á. Fernández").

The search_context now provides rich, organized data for each player:
{
  "web": [articles with sentiment],
  "news": [news articles with sentiment], 
  "discussions": [forum/social media posts],
  "videos": [video content],
  "summaries": [AI-generated summaries],
  "sentiment_breakdown": {"positive": X, "negative": Y, "neutral": Z}
}

When calling persist_newsletter, pass content_json as a JSON object (NOT a JSON-encoded string).
Include up to 3 links per player from search_context (news > web > discussions) and add a concise fan_pulse list drawn from notable forum items.

Quality rules (STRICT):
- If minutes==0 and role!=startXI → write "unused substitute" (not "appeared").
- If text says "started", minutes MUST be >0; otherwise rewrite as "did not play".
- Highlights must come from the same week’s stats.
- Use display_name (e.g., "Charlie Wellens") not full legal/middle names.

Scoring (for highlights):
score = goals*5 + assists*3 + (minutes/90)*1 - yellow*1 - red*3
Use top 3 for "highlights". Always include a "Loanee of the Week" in the summary.

Output JSON ONLY:
{
  "title": "...",
  "summary": "2–3 sentences: hero, clutch moment, narrative contrast.",
  "season": "YYYY-YY",
  "range": ["YYYY-MM-DD","YYYY-MM-DD"],
  "highlights": ["..."],
  "sections": [{"title":"Active Loans","items":[{...}]}],
  "by_numbers": {"minutes_leaders":[...], "ga_leaders":[...]},
  "fan_pulse": [{"player":"...","forum":"...","quote":"...","url":"..."}]
}
Respond with JSON only, no extra prose.
"""

# ---------- Python-native Tools (exposed to Agent) ----------

async def fetch_weekly_report(ctx, args) -> Dict[str, Any]:
    """
    SDK hands tool args either as a dict or a JSON‐encoded string.
    Normalize, extract expected fields, and run the weekly summary.
    """
    # Accept raw JSON string as well
    if isinstance(args, str):
        args = json.loads(args)

    parent_team_db_id = int(args["parent_team_db_id"])
    target_date = str(args["target_date"])

    tdate = date.fromisoformat(target_date)
    week_start, week_end = monday_range(tdate)

    team = Team.query.get(parent_team_db_id)
    if not team:
        raise ValueError(f"Team DB id {parent_team_db_id} not found")

    # Sync season to target date's season (European season starts Aug 1)
    season_start_year = tdate.year if tdate.month >= 8 else tdate.year - 1
    api_client.set_season_year(season_start_year)
    api_client._prime_team_cache(season_start_year)

    report = api_client.summarize_parent_loans_week(
        parent_team_db_id=team.id,
        parent_team_api_id=team.team_id,
        season=season_start_year,
        week_start=week_start,
        week_end=week_end,
        include_team_stats=False,
        db_session=db.session,
    )
    # normalize parent team payload shape
    report["parent_team"] = {"db_id": team.id, "id": team.team_id, "name": team.name}
    db.session.commit()
    return report

async def persist_newsletter(ctx, args) -> Dict[str, Any]:
    """
    Persist a generated JSON newsletter. Accepts a dict or JSON string payload.
    """
    if isinstance(args, str):
        args = json.loads(args)

    team_db_id = int(args["team_db_id"])
    # Robustly parse content_json which may be JSON text or already a dict.
    raw_content = args.get("content_json")
    search_context = args.get("search_context") if isinstance(args, dict) else None
    if search_context is None:
        # fallback to latest captured context from orchestrator
        try:
            global _LATEST_SEARCH_CONTEXT
            if isinstance(_LATEST_SEARCH_CONTEXT, dict):
                search_context = _LATEST_SEARCH_CONTEXT
        except Exception:
            pass
    if isinstance(raw_content, str):
        try:
            content_json = json.loads(raw_content)
        except Exception:
            # Attempt to extract a JSON object block from the string
            try:
                import re
                blocks = re.findall(r"\{(?:.|\n)*\}", raw_content)
                if blocks:
                    content_json = json.loads(blocks[0])
                else:
                    # Coerce to a minimal valid payload instead of raising
                    content_json = {"title": "Weekly Loan Update", "summary": "", "sections": []}
            except Exception:
                # Coerce to a minimal valid payload instead of raising
                content_json = {"title": "Weekly Loan Update", "summary": "", "sections": []}
    else:
        content_json = raw_content

    # Sanitize early, unwrap cases where summary accidentally contains JSON
    content_json, removed_a = _sanitize_with_count(content_json)
    try:
        if isinstance(content_json, dict) and isinstance(content_json.get("summary"), str):
            m = re.search(r"\{(?:.|\n)*\}", content_json["summary"])  # extract JSON block if embedded
            if m:
                content_json["summary"] = json.dumps(json.loads(m.group(0)))
    except Exception:
        pass
    issue_date = str(args["issue_date"])

    # If summary field contains an embedded JSON string, prefer its inner summary
    try:
        if isinstance(content_json, dict) and isinstance(content_json.get("summary"), str):
            s = content_json["summary"].strip()
            if s.startswith('{') and s.endswith('}'):
                inner = json.loads(s)
                if isinstance(inner, dict) and inner.get("summary"):
                    content_json["summary"] = inner["summary"]
    except Exception:
        pass

    # Sanitize all strings to strip control characters (e.g., \u0000)
    content_json = _sanitize(content_json)

    t = Team.query.get(team_db_id)
    if not t:
        raise ValueError(f"Team DB id {team_db_id} not found")

    issue = date.fromisoformat(issue_date)
    week_start, week_end = monday_range(issue)

    # Finalize only after the range closes (Sunday). Otherwise save as draft.
    is_final = issue >= week_end

    # Inject links/fan_pulse if available and missing
    try:
        updated, injected, added = _inject_links_from_search_context(content_json, search_context, max_links=3)
        content_json = updated
        if injected:
            logging.getLogger(__name__).info(f"Injected links from search_context: yes (+{added})")
        # Always append internet section if any web items exist
        content_json = _append_internet_section(content_json, search_context, max_items_per_player=2)
    except Exception:
        pass

    # Attach debug snapshot so we can "see it regardless" when MCP_DEBUG=1
    try:
        if DEBUG_MCP:
            def _trim_ctx(ctx: dict | None) -> dict:
                if not isinstance(ctx, dict):
                    return {}
                def take(lst, n):
                    try:
                        return list(lst)[:n]
                    except Exception:
                        return []
                return {
                    'web': take(ctx.get('web') or [], MCP_LOG_SAMPLE_N),
                    'news': take(ctx.get('news') or [], MCP_LOG_SAMPLE_N),
                    'discussions': take(ctx.get('discussions') or [], MCP_LOG_SAMPLE_N),
                    'videos': take(ctx.get('videos') or [], MCP_LOG_SAMPLE_N),
                }
            dbg_ctx: dict[str, dict] = {}
            if isinstance(search_context, dict):
                for k, v in list(search_context.items())[:10]:
                    dbg_ctx[k] = _trim_ctx(v if isinstance(v, dict) else {})
            content_json.setdefault('debug', {})
            content_json['debug'].update({
                'range': [week_start.isoformat(), week_end.isoformat()],
                'search_context_samples': dbg_ctx,
            })
    except Exception:
        pass

    # Lint + enrich before persisting
    try:
        content_json = lint_and_enrich(content_json)
    except Exception:
        # Non-fatal; continue with original
        pass

    # Sanitize again before serializing
    content_json = _sanitize(content_json)

    # Validate shape; if bad, raise to let orchestrator fallback persist a clean copy
    def _valid_content(payload: dict) -> bool:
        return isinstance(payload, dict) and payload.get("title") is not None and isinstance(payload.get("sections"), list)

    # Serialize content JSON for storage
    # Final sanitize before storage; guard against control chars
    content_json, removed_b = _sanitize_with_count(content_json)
    if (removed_a + removed_b) > 0:
        logging.getLogger(__name__).info(f"Sanitized strings: yes ({removed_a + removed_b} chars removed)")
    if not _valid_content(content_json):
        # Coerce to minimal valid payload instead of raising
        content_json = {"title": content_json.get("title") or "Weekly Loan Update", "summary": content_json.get("summary") or "", "sections": content_json.get("sections") or []}
    content_str = json.dumps(content_json, ensure_ascii=False)

    # Render and embed variants for convenience
    try:
        team_name = t.name if t else None
        variants = _render_variants(content_json, team_name)
        content_json['rendered'] = variants
        content_str = json.dumps(content_json, ensure_ascii=False)
    except Exception:
        pass

    nl = Newsletter(
        team_id=team_db_id,
        newsletter_type="weekly",
        title=content_json.get("title") or f"{t.name} Loan Update",
        content=content_str,
        structured_content=content_str,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=issue,
        generated_date=issue,
        published=is_final,
        published_date=issue if is_final else None,
    )
    db.session.add(nl)
    db.session.commit()
    return nl.to_dict()
# ------------------------
# Lint + enrichment helpers
# ------------------------
def _pick_links_from_ctx(ctx: dict, max_links: int = 3) -> list[dict]:
    if not isinstance(ctx, dict):
        return []
    buckets = [ctx.get('web') or [], ctx.get('discussions') or []]
    out = []
    for bucket in buckets:
        for r in bucket:
            url = (r or {}).get('url')
            title = (r or {}).get('title')
            if not url or not title:
                continue
            out.append({
                'title': title,
                'url': url,
                'publisher': (r or {}).get('publisher'),
                'sentiment': (r or {}).get('sentiment'),
                'description': (r or {}).get('snippet') or (r or {}).get('description')
            })
            if len(out) >= max_links:
                return out
    return out

def _inject_links_from_search_context(news: dict, search_context: dict, max_links: int = 3) -> dict:
    if not isinstance(news, dict) or not isinstance(search_context, dict):
        return news
    # Build a lowercase key map for robust lookups
    sc_map = { (k or '').strip().lower(): v for k, v in search_context.items() }

    # Attach per-player links
    for sec in news.get('sections', []) or []:
        for it in sec.get('items', []) or []:
            pname = (it.get('player_name') or it.get('player') or '').strip()
            key = pname.lower()
            ctx = sc_map.get(key)
            if not ctx:
                # try a relaxed match without diacritics/extra spaces
                for k in sc_map.keys():
                    if k.replace(' ', '') == key.replace(' ', ''):
                        ctx = sc_map.get(k)
                        break
            if not ctx:
                continue
            links = it.get('links') or []
            if not links:
                picked = _pick_links_from_ctx(ctx, max_links=max_links)
                if picked:
                    it['links'] = picked

    # Build fan_pulse from discussions if missing
    if not news.get('fan_pulse'):
        pulse = []
        for player_name, ctx in search_context.items():
            disc = (ctx or {}).get('discussions') or []
            for r in disc[:2]:  # at most 2 per player
                url = (r or {}).get('url')
                if not url:
                    continue
                host = ''
                try:
                    host = urlparse(url).netloc
                except Exception:
                    pass
                pulse.append({
                    'player': player_name,
                    'forum': host,
                    'quote': (r or {}).get('description') or (r or {}).get('snippet') or (r or {}).get('title') or '',
                    'url': url,
                })
        news['fan_pulse'] = pulse[:8]
    return news

def _append_internet_section(news: dict, search_context: dict, max_items_per_player: int = 2) -> dict:
    try:
        items = []
        for player_name, ctx in (search_context or {}).items():
            # Prefer web links. Fall back to news/discussions if web is empty
            candidates = list(ctx.get('web') or [])
            if not candidates:
                candidates = list(ctx.get('news') or []) + list(ctx.get('discussions') or [])
            links: list[str] = []
            for r in candidates:
                try:
                    u = (r or {}).get('url')
                except Exception:
                    u = None
                if not u:
                    continue
                links.append(u)
                if len(links) >= max_items_per_player:
                    break
            if links:
                items.append({'player_name': to_initial_last(player_name), 'links': links})
        if items:
            sections = news.get('sections') or []
            sections.append({'title': 'What the Internet is Saying', 'items': items})
            news['sections'] = sections
    except Exception:
        pass
    return news

# Wrap python tools for Agents SDK
fetch_weekly_report_tool = FunctionTool(
    name="fetch_weekly_report",
    description="Get the weekly loans performance summary for a parent club for the week containing target_date.",
    params_json_schema=FetchWeeklyReportArgs.model_json_schema(),
    on_invoke_tool=fetch_weekly_report,
)

persist_newsletter_tool = FunctionTool(
    name="persist_newsletter",
    description="Persist a generated JSON newsletter for a team and issue_date.",
    params_json_schema=PersistNewsletterArgs.model_json_schema(),
    on_invoke_tool=persist_newsletter,
)

# ---------- Agent factory (API-only) ----------

def build_weekly_agent() -> Agent:
    return Agent(
        name="Weekly Loans Newsletter Agent",
        instructions=SYSTEM_INSTRUCTIONS,
        model="gpt-4.1-mini",
        tools=[fetch_weekly_report_tool, persist_newsletter_tool],
    )

# ---------- Orchestration entrypoint ----------

async def generate_weekly_newsletter(team_db_id: int, target_date: date) -> Dict[str, Any]:
    # Precompute week window and report
    week_start, week_end = monday_range(target_date)
    news_end = week_end + timedelta(days=1)
    report = await fetch_weekly_report(ctx=None, args={
        "parent_team_db_id": team_db_id,
        "target_date": target_date.isoformat(),
    })
    # Build queries and gather web+news
    # Build both id- and name-indexed search contexts for deterministic merging
    run_context = RunContextWrapper(context=None)
    agent = build_weekly_agent()
    search_context: dict[str, dict[str, list[dict]]] = {}
    search_context_by_id: dict[str, dict[str, list[dict]]] = {}
    loanees = (report.get("loanees") or []) if isinstance(report, dict) else []
    full_name_cache: dict[str, str] = {}

    # Get team info for localization
    team = Team.query.get(team_db_id)
    # Use related League if available; fall back to default localization
    league_name = (team.league.name if (team and getattr(team, 'league', None)) else "Premier League")
    localization = get_league_localization(league_name)

    # Compute freshness range once for this run
    freshness_range = freshness_range_str(week_start, news_end)

    for loanee in loanees:
        player = loanee.get("player_name") or loanee.get("name") or ""
        pid = str(loanee.get("player_api_id") or loanee.get("player_id") or "")
        full_name = loanee.get("player_full_name") or player
        if pid and not full_name:
            try:
                # Fetch once per player for better queries
                if pid not in full_name_cache:
                    pdata = api_client.get_player_by_id(int(pid))
                    nm = (pdata or {}).get('player', {}).get('name') if isinstance(pdata, dict) else None
                    if nm:
                        full_name_cache[pid] = nm
                full_name = full_name_cache.get(pid) or player
            except Exception:
                full_name = player
        loan_team = loanee.get("loan_team_name") or loanee.get("loan_team") or ""
        if not player:
            continue
        items_web: list[dict] = []
        items_news: list[dict] = []

        # Enhanced per-player queries with localization
        # Strategy:
        #  - Prefer Full Name; fall back to display name
        #  - Query both web and news
        #  - Do not require opponent; add a weekly player+team query regardless
        #  - Widen freshness if strict pass yields no results
        intents_expr = "player ratings OR match reaction OR match report OR fan reaction OR analysis"

        # Build strict queries (week window)
        qname = (full_name or player).strip()
        match_queries: list[str] = []
        for m in loanee.get("matches", []) or []:
            opp = (m.get("opponent") or "").strip()
            comp = (m.get("competition") or "").strip()
            if opp and comp:
                match_queries.append(f'"{qname}" {loan_team} {opp} {comp} ({intents_expr})')
        # Weekly fallback queries (even if no matches/opponents present)
        weekly_queries = [
            f'"{qname}" {loan_team} player ratings',
            f'"{qname}" {loan_team} match report',
            f'{qname} {loan_team} fan reaction',
        ]

        # Strict pass (API-only): week freshness, discussions+web for web; include news
        strict_queries = (match_queries[:3] or []) + weekly_queries[:2]
        for query in strict_queries:
            # Convert freshness range to since/until
            try:
                since, until = freshness_range.split("to", 1)
            except Exception:
                since, until = week_start.isoformat(), news_end.isoformat()
            merged = brave_api.brave_search(
                query,
                since,
                until,
                country=localization.get('country', 'GB'),
                search_lang=localization.get('search_lang', 'en'),
                ui_lang=localization.get('ui_lang', 'en-GB'),
                result_filter=["discussions", "web"],
            )
            _log_sample("strict", pid, query, merged)
            # Split back into web/news buckets
            web_results = [r for r in merged if r.get("source") == "web"]
            news_results = [r for r in merged if r.get("source") == "news"]
            items_web.extend(web_results)
            items_news.extend(news_results)

        # Widened pass: if still empty, broaden freshness and drop result_filter
        if not (items_web or items_news) and (ALLOW_WIDE_FRESHNESS or (not STRICT_FRESHNESS)):
            wide_range = freshness_range_str(week_start - timedelta(days=14), week_end + timedelta(days=3))
            wide_queries = weekly_queries[:2] or [f'"{qname}" {loan_team}']
            for query in wide_queries:
                try:
                    s2, u2 = wide_range.split("to", 1)
                except Exception:
                    s2, u2 = (week_start - timedelta(days=14)).isoformat(), (week_end + timedelta(days=3)).isoformat()
                merged_wide = brave_api.brave_search(
                    query,
                    s2,
                    u2,
                    country=localization.get('country', 'GB'),
                    search_lang=localization.get('search_lang', 'en'),
                    ui_lang=localization.get('ui_lang', 'en-GB'),
                    result_filter=["discussions", "web"],
                )
                _log_sample("wide", pid, query, merged_wide)
                items_web.extend([r for r in merged_wide if r.get("source") == "web"])
                items_news.extend([r for r in merged_wide if r.get("source") == "news"])

        # Categorize and deduplicate results
        categorized_results = categorize_and_deduplicate_results(items_web, items_news)
        # Post-filter to remove out-of-window/off-topic/noisy hits
        categorized_results = _filter_hits_for_player(
            categorized_results,
            player_name=full_name or player,
            loan_team=loan_team,
            week_start=week_start,
            week_end=week_end,
        )
        if DEBUG_MCP:
            logging.getLogger(__name__).info(
                "BRAVE categorized | pid=%s | web=%d news=%d disc=%d vids=%d",
                pid,
                len(categorized_results["web"]),
                len(categorized_results["news"]),
                len(categorized_results["discussions"]),
                len(categorized_results["videos"]),
            )

        display = to_initial_last(player).strip()
        ctx_row = {
            "web": categorized_results["web"],
            "news": categorized_results["news"],
            "discussions": categorized_results["discussions"],
            "videos": categorized_results["videos"],
            "summaries": categorized_results["summaries"],
            "sentiment_breakdown": categorized_results["sentiment_breakdown"]
        }
        if pid:
            search_context_by_id[pid] = {"display": display, **ctx_row}
        search_context[display] = ctx_row

    # Cache latest context for the persist tool (in case the agent omits it)
    try:
        global _LATEST_SEARCH_CONTEXT
        _LATEST_SEARCH_CONTEXT = search_context
    except Exception:
        pass

    # High-level instruction payload (add What the Internet is Saying section seed)
    user_msg = {
        "task": "compose_and_persist_weekly_newsletter",
        "team_db_id": team_db_id,
        "target_date": target_date.isoformat(),
        "report": report,
        "search_context": search_context,
        "search_context_by_id": search_context_by_id if DEBUG_MCP else None,
        "guidance": {
            "search_context_precomputed": True,
            "max_links_per_player": 3
        }
    }

    # Run with brief retries to handle API hiccups
    def _has_rate_limit(items) -> bool:
        try:
            text = "\n".join(str(getattr(i, "raw_item", i)) for i in items)
        except Exception:
            text = "\n".join(str(i) for i in items)
        return ("Rate limit" in text) or ("429" in text)

    max_attempts = 3
    delay = 0.6
    for attempt in range(max_attempts):
        result = await Runner.run(
            starting_agent=agent,
            input=json.dumps(user_msg),
            context=run_context,
        )
        if not _has_rate_limit(result.new_items):
            break
        if attempt < max_attempts - 1:
            await asyncio.sleep(delay * (2 ** attempt) + random.random()*0.4)

    # last_response_id and final_output are the modern equivalents of run_id/output
    run_id = result.last_response_id
    raw_final_output = result.final_output
    final = _to_jsonable(raw_final_output)

    # collect tool call events; result.new_items is a list of RunItem instances
    tool_events = []
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            tool_events.append(_to_jsonable(item.raw_item))
        elif isinstance(item, ToolCallOutputItem):
            tool_events.append(_to_jsonable(item.output))

    # If the agent did not invoke persist_newsletter, persist as a safety net
    invoked_tool_names = set()
    for ev in tool_events:
        if isinstance(ev, dict) and ev.get("name"):
            invoked_tool_names.add(ev["name"])

    persisted_row: Dict[str, Any] | None = None
    if "persist_newsletter" not in invoked_tool_names:
        try:
            # Parse final content as JSON if it's a string-like content
            content_json: Any
            if isinstance(raw_final_output, str):
                try:
                    content_json = json.loads(raw_final_output)
                except Exception:
                    import re
                    blocks = re.findall(r"\{(?:.|\n)*\}", raw_final_output)
                    content_json = json.loads(blocks[0]) if blocks else {}
            else:
                content_json = raw_final_output
            # Merge Brave search links and fan pulse if missing
            try:
                content_json = _inject_links_from_search_context(content_json, search_context, max_links=3)
            except Exception:
                pass
            # Sanitize strings before further processing
            content_json = _sanitize(content_json)
            # Lint/enrich even on fallback
            try:
                content_json = lint_and_enrich(content_json)
            except Exception:
                pass
            args = {
                "team_db_id": team_db_id,
                "content_json": content_json,
                "issue_date": target_date.isoformat(),
                "search_context": search_context,
            }
            persisted_row = await persist_newsletter(ctx=None, args=args)
        except Exception:
            persisted_row = None

    return _to_jsonable({
        "last_response_id": run_id,
        "final_output": final,
        "tool_events": tool_events,
        "persisted_via_fallback": persisted_row is not None,
        "persisted_newsletter": persisted_row,
    })
    # end generate_weekly_newsletter

# Compatibility wrappers (legacy names)
async def generate_weekly_newsletter_with_mcp(team_db_id: int, target_date: date) -> Dict[str, Any]:
    return await generate_weekly_newsletter(team_db_id, target_date)

def generate_weekly_newsletter_with_mcp_sync(team_db_id: int, target_date: date) -> Dict[str, Any]:
    return asyncio.run(generate_weekly_newsletter(team_db_id, target_date))

# ------------------------
# Lint + enrichment helpers
# ------------------------
def _display_name(name: str) -> str:
    """Return first-initial + last-name when possible, preserving diacritics."""
    return to_initial_last(name)

def _fix_minutes_language(item: dict) -> None:
    """Normalize phrasing based on minutes to avoid contradictions."""
    s = item.get("stats", {}) or {}
    mins = int(s.get("minutes", 0) or 0)
    wsum = item.get("week_summary", "") or ""
    notes = item.get("match_notes", []) or []

    if mins == 0:
        # common phrasings → Unused substitute / did not play
        for token in ["Appeared", "Used as substitute", "Came on", "Substitute in"]:
            if token in wsum:
                wsum = wsum.replace(token, "Unused substitute")
        if "Started" in wsum or "Started and played" in wsum:
            wsum = wsum.replace("Started and played", "Did not play")
            wsum = wsum.replace("Started", "Did not play")
        # notes too
        new_notes = []
        for n in notes:
            n2 = n
            for token in ["Came on", "Substitute in"]:
                if token in n2:
                    n2 = n2.replace(token, "Unused substitute")
            new_notes.append(n2)
        notes = new_notes

    item["week_summary"] = wsum
    item["match_notes"] = notes

def strip_diacritics(s: str) -> str:
    try:
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    except Exception:
        return s

def to_initial_last(full: str) -> str:
    if not full:
        return full
    parts = str(full).split()
    if len(parts) == 1:
        return parts[0]
    first, last = parts[0], parts[-1]
    if not first:
        return last
    return f"{first[0]}. {last}"

def name_variants(full_name: str | None, display: str) -> list[str]:
    """Return name variants prioritized for search: full name, display, last name, plus ASCII forms."""
    import unicodedata as _ud
    def _ascii(s: str) -> str:
        try:
            return ''.join(c for c in _ud.normalize('NFKD', s) if not _ud.combining(c))
        except Exception:
            return s
    last = ((full_name or display or '').split()[-1] if (full_name or display) else '').strip()
    base = []
    for n in [full_name or '', display or '', last or '']:
        n = n.strip()
        if not n:
            continue
        base.append(n)
        base.append(_ascii(n))
    out: list[str] = []
    seen: set[str] = set()
    for n in base:
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _sanitize_value_with_count(text: str) -> tuple[str, int]:
    if not isinstance(text, str):
        return text, 0
    cleaned = _CONTROL_CHARS_RE.sub('', text)
    return cleaned, len(text) - len(cleaned)

def _sanitize_with_count(obj: Any) -> tuple[Any, int]:
    removed = 0
    if obj is None:
        return obj, 0
    if isinstance(obj, str):
        return _sanitize_value_with_count(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            vv, rr = _sanitize_with_count(v)
            out[k] = vv
            removed += rr
        return out, removed
    if isinstance(obj, list):
        out_list = []
        for v in obj:
            vv, rr = _sanitize_with_count(v)
            out_list.append(vv)
            removed += rr
        return out_list, removed
    return obj, 0

def _canonicalize_name(name: str) -> str:
    mapping = {
        "Ellis Galbraith": "Ethan Galbraith",
        "Harry Mejbri": "Hannibal Mejbri",
    }
    return mapping.get(name, name)

def _score_player(item: dict) -> float:
    s = item.get("stats", {}) or {}
    return 5*(s.get("goals",0) or 0) + 3*(s.get("assists",0) or 0) + (s.get("minutes",0) or 0)/90.0 - 1*(s.get("yellows",0) or 0) - 3*(s.get("reds",0) or 0)

def lint_and_enrich(news: dict) -> dict:
    if not isinstance(news, dict):
        return news

    # normalize display names and de-dupe within each section by stable identity
    for sec in news.get("sections", []) or []:
        seen: set[str] = set()
        items = []
        for it in sec.get("items", []) or []:
            nm = _display_name(it.get("player_name"))
            it["player_name"] = nm
            # coerce stats if provided as a string
            try:
                st = it.get("stats")
                if isinstance(st, str):
                    games = int(re.search(r"(\d+)\s*game", st) .group(1)) if re.search(r"(\d+)\s*game", st) else 0
                    minutes = int(re.search(r"(\d+)\s*minute", st).group(1)) if re.search(r"(\d+)\s*minute", st) else 0
                    goals = int(re.search(r"(\d+)\s*goal", st) .group(1)) if re.search(r"(\d+)\s*goal", st) else 0
                    assists = int(re.search(r"(\d+)\s*assist", st).group(1)) if re.search(r"(\d+)\s*assist", st) else 0
                    yellows = int(re.search(r"(\d+)\s*yellow", st).group(1)) if re.search(r"(\d+)\s*yellow", st) else 0
                    reds = int(re.search(r"(\d+)\s*red", st) .group(1)) if re.search(r"(\d+)\s*red", st) else 0
                    it["stats"] = {
                        "games": games,
                        "minutes": minutes,
                        "goals": goals,
                        "assists": assists,
                        "yellows": yellows,
                        "reds": reds,
                    }
            except Exception:
                pass
            _fix_minutes_language(it)
            pid = it.get("player_id")
            name_key = strip_diacritics(to_initial_last(it.get("player_name", ""))).lower().replace(' ', '')
            key = f"pid:{pid}" if pid else f"name:{name_key}"
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
        sec["items"] = items

    # recompute highlights from actual stats
    items = [it for sec in news.get("sections", []) or [] for it in sec.get("items", []) or []]
    top = sorted(items, key=_score_player, reverse=True)[:3]
    news["highlights"] = [
        f"{_display_name(it['player_name'])}: {int(it['stats'].get('goals',0))}G {int(it['stats'].get('assists',0))}A, {int(it['stats'].get('minutes',0))}’"
        for it in top
    ]

    # by-numbers blocks
    mins_leaders = sorted(items, key=lambda x: int(x.get('stats',{}).get('minutes',0) or 0), reverse=True)[:3]
    ga_leaders = sorted(items, key=lambda x: (int(x.get('stats',{}).get('goals',0) or 0) + int(x.get('stats',{}).get('assists',0) or 0)), reverse=True)[:3]
    news["by_numbers"] = {
        "minutes_leaders": [{"player": _display_name(i.get("player_name")), "minutes": int(i.get("stats",{}).get("minutes",0) or 0)} for i in mins_leaders],
        "ga_leaders": [{"player": _display_name(i.get("player_name")), "g": int(i.get("stats",{}).get("goals",0) or 0), "a": int(i.get("stats",{}).get("assists",0) or 0)} for i in ga_leaders],
    }

    return news

def _inject_links_from_search_context(content_json: dict, search_context: dict | None, max_links: int = 3) -> tuple[dict, bool, int]:
    """Inject up to max_links per player from search_context if links are missing.
    Returns (updated_json, injected_any, total_links_added)."""
    if not isinstance(content_json, dict) or not isinstance(search_context, dict):
        return content_json, False, 0
    added_total = 0
    injected_any = False
    # Build a simple accessor for context lists
    def _ctx_for(name: str) -> dict | None:
        if not name:
            return None
        # Try exact, then initial-last without diacritics
        if name in search_context:
            return search_context.get(name)
        alt = to_initial_last(name)
        return search_context.get(alt)

    for sec in content_json.get("sections", []) or []:
        for it in sec.get("items", []) or []:
            links = it.get("links") or []
            if isinstance(links, list) and len(links) >= max_links:
                continue
            ctx = _ctx_for(it.get("player_name") or "")
            if not isinstance(ctx, dict):
                continue
            urls: list[str] = []
            for bucket in ("web", "news", "discussions", "videos"):
                for r in ctx.get(bucket) or []:
                    url = (r.get("url") if isinstance(r, dict) else None) or None
                    if url and url not in urls:
                        urls.append(url)
                    if len(urls) >= max_links:
                        break
                if len(urls) >= max_links:
                    break
            if urls:
                it["links"] = urls[:max_links]
                added_total += len(urls[:max_links])
                injected_any = True
    return content_json, injected_any, added_total

# ------------------------
# Render helpers (web/email/txt)
# ------------------------

def _render_env() -> Environment:
    templates_path = os.path.join(os.path.dirname(__file__), '..', 'templates')
    templates_path = os.path.abspath(templates_path)
    env = Environment(
        loader=FileSystemLoader(templates_path),
        autoescape=select_autoescape(['html', 'xml'])
    )
    return env

def _build_template_context(news: dict, team_name: str | None) -> dict:
    return {
        'team_name': team_name or '',
        'title': news.get('title'),
        'range': news.get('range'),
        'summary': news.get('summary'),
        'highlights': news.get('highlights') or [],
        'sections': news.get('sections') or [],
        'by_numbers': news.get('by_numbers') or {},
        'fan_pulse': news.get('fan_pulse') or [],
        'meta': {},
    }

def _plain_text_from_news_only(news: dict) -> str:
    lines = []
    title = news.get('title') or 'Weekly Loan Update'
    rng = news.get('range') or [None, None]
    summary = news.get('summary') or ''
    lines.append(title)
    if rng and rng[0] and rng[1]:
        lines.append(f"Week: {rng[0]} – {rng[1]}")
    if summary:
        lines.append("")
        lines.append(summary)
    for sec in (news.get('sections') or []):
        st = sec.get('title') or ''
        items = sec.get('items') or []
        if st:
            lines.append("")
            lines.append(st)
        for it in items:
            pname = it.get('player_name') or ''
            loan_team = it.get('loan_team') or it.get('loan_team_name') or ''
            wsum = it.get('week_summary') or ''
            lines.append(f"• {pname} ({loan_team}) – {wsum}")
    return "\n".join(lines).strip() + "\n"

def _render_variants(news: dict, team_name: str | None) -> dict:
    try:
        env = _render_env()
        ctx = _build_template_context(news, team_name)
        web_t = env.get_template('newsletter_web.html')
        email_t = env.get_template('newsletter_email.html')
        web_html = web_t.render(**ctx)
        email_html = email_t.render(**ctx)
    except Exception:
        web_html = ''
        email_html = ''

    # plain-text
    try:
        text_body = _plain_text_from_news_only(news)
    except Exception:
        text_body = ''

    return {
        'web_html': web_html,
        'email_html': email_html,
        'text': text_body,
    }

# Synchronous convenience wrapper (for cron or Flask endpoint)
def generate_weekly_newsletter_with_mcp_sync(team_db_id: int, target_date: date) -> Dict[str, Any]:
    return asyncio.run(generate_weekly_newsletter_with_mcp(team_db_id, target_date))

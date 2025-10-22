import os
import json
import re
import requests
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
from typing import Any, Dict, List, Annotated
from pydantic import BaseModel, Field
from agents import (
    set_default_openai_client
)
from openai import OpenAI  # OpenAI Agents SDK
from src.models.league import db, Team, LoanedPlayer, Newsletter, AdminSetting
from src.api_football_client import APIFootballClient
from src.agents.errors import NoActiveLoaneesError
from src.agents.weekly_agent import (
    lint_and_enrich as legacy_lint_and_enrich,
    _apply_player_lookup,
    _set_latest_player_lookup,
    _normalize_player_key,
    to_initial_last,
    _render_variants,
)

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

# Always-on debug output during development
def _nl_dbg(*args):
    try:
        print("[NEWSLETTER DBG]", *args)
    except Exception:
        pass

# 
# Feature toggles (soft ranking, site boosts, cup synonyms)
# Default to conservative behavior: only cup synonyms enabled by default to improve recall.
ENV_SOFT_RANK = os.getenv("BRAVE_SOFT_RANK", "1").lower() in ("1", "true", "yes")
ENV_SITE_BOOST = os.getenv("BRAVE_SITE_BOOST", "1").lower() in ("1", "true", "yes")
ENV_USE_CUP_SYNS = os.getenv("BRAVE_CUP_SYNONYMS", "1").lower() in ("1", "true", "yes")
ENV_STRICT_RANGE = os.getenv("BRAVE_STRICT_RANGE", "0").lower() in ("1", "true", "yes")
ENV_CHECK_LINKS = os.getenv("NEWSLETTER_CHECK_LINKS", "1").lower() in ("1", "true", "yes")
ENV_VALIDATE_FINAL_LINKS = os.getenv("NEWSLETTER_VALIDATE_FINAL_LINKS", "1").lower() in ("1", "true", "yes")
LINK_TIMEOUT_SEC = float(os.getenv("NEWSLETTER_LINK_TIMEOUT", "6"))
LINK_MAX_WORKERS = int(os.getenv("NEWSLETTER_LINK_MAX_WORKERS", "8"))
LINKS_MAX_PER_ITEM = int(os.getenv("NEWSLETTER_LINKS_MAX_PER_ITEM", "3"))

# Minimal localization (GB defaults). We keep this simple here to avoid importing heavy modules.
LOCALIZATION_DEFAULT = {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"}

BRAVE_LOCALIZATION_BY_ISO = {
    "GB": {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"},
    "IE": {"country": "IE", "search_lang": "en", "ui_lang": "en-IE"},
    "US": {"country": "US", "search_lang": "en", "ui_lang": "en-US"},
    "CA": {"country": "CA", "search_lang": "en", "ui_lang": "en-CA"},
    "FR": {"country": "FR", "search_lang": "fr", "ui_lang": "fr-FR"},
    "ES": {"country": "ES", "search_lang": "es", "ui_lang": "es-ES"},
    "PT": {"country": "PT", "search_lang": "pt", "ui_lang": "pt-PT"},
    "BR": {"country": "BR", "search_lang": "pt", "ui_lang": "pt-BR"},
    "DE": {"country": "DE", "search_lang": "de", "ui_lang": "de-DE"},
    "AT": {"country": "AT", "search_lang": "de", "ui_lang": "de-AT"},
    "CH-DE": {"country": "CH", "search_lang": "de", "ui_lang": "de-CH"},
    "CH-FR": {"country": "CH", "search_lang": "fr", "ui_lang": "fr-CH"},
    "CH-IT": {"country": "CH", "search_lang": "it", "ui_lang": "it-CH"},
    "IT": {"country": "IT", "search_lang": "it", "ui_lang": "it-IT"},
    "NL": {"country": "NL", "search_lang": "nl", "ui_lang": "nl-NL"},
    "BE-NL": {"country": "BE", "search_lang": "nl", "ui_lang": "nl-BE"},
    "BE-FR": {"country": "BE", "search_lang": "fr", "ui_lang": "fr-BE"},
    "SE": {"country": "SE", "search_lang": "sv", "ui_lang": "sv-SE"},
    "NO": {"country": "NO", "search_lang": "no", "ui_lang": "no-NO"},
    "DK": {"country": "DK", "search_lang": "da", "ui_lang": "da-DK"},
    "FI": {"country": "FI", "search_lang": "fi", "ui_lang": "fi-FI"},
    "PL": {"country": "PL", "search_lang": "pl", "ui_lang": "pl-PL"},
    "HR": {"country": "HR", "search_lang": "hr", "ui_lang": "hr-HR"},
    "BA": {"country": "BA", "search_lang": "bs", "ui_lang": "bs-BA"},
}

COUNTRY_FALLBACKS = {
    "BE": ["BE-FR", "BE-NL", "NL", "FR"],
    "CH": ["CH-DE", "CH-FR", "CH-IT", "DE", "FR", "IT"],
    "CA": ["US", "GB"],
    "BR": ["PT"],
    "MX": ["ES", "US"],
    "AR": ["ES"],
    "CO": ["ES"],
    "JP": ["US"]
}

def resolve_localization_for_country(iso_code: str | None, default: dict[str, str] | None = None) -> dict[str, str]:
    base = dict(default or LOCALIZATION_DEFAULT)
    if not iso_code:
        return base
    key = iso_code.upper()
    if key in BRAVE_LOCALIZATION_BY_ISO:
        return dict(BRAVE_LOCALIZATION_BY_ISO[key])
    for fallback in COUNTRY_FALLBACKS.get(key, []):
        if fallback in BRAVE_LOCALIZATION_BY_ISO:
            return dict(BRAVE_LOCALIZATION_BY_ISO[fallback])
    return base


def _enforce_loanee_metadata(
    content: dict,
    meta_by_pid: dict[int, dict[str, Any]],
    meta_by_key: dict[str, dict[str, Any]],
) -> dict:
    if not isinstance(content, dict):
        return content

    sections = content.get('sections')
    if not isinstance(sections, list):
        return content

    internet_links: dict[str, list[Any]] = {}
    supplemental_items: list[dict[str, Any]] = []
    new_sections: list[dict[str, Any]] = []

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        raw_items = sec.get('items')
        if not isinstance(raw_items, list):
            continue
        title = (sec.get('title') or '').strip().lower()
        if title == 'what the internet is saying':
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                links = item.get('links')
                if not isinstance(links, list):
                    continue
                key = _normalize_player_key(item.get('player_name'))
                if not key:
                    continue
                bucket = internet_links.setdefault(key, [])
                bucket.extend(link for link in links if link)
            continue

        filtered_items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            meta = None
            pid = item.get('player_id')
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                pid_int = None
            if pid_int is not None and pid_int in meta_by_pid:
                meta = meta_by_pid[pid_int]
            else:
                key = _normalize_player_key(item.get('player_name'))
                if key:
                    meta = meta_by_key.get(key)

            can_track = bool(meta.get('can_fetch_stats', True) if meta else item.get('can_fetch_stats', True))
            item['can_fetch_stats'] = can_track
            if not can_track:
                item.pop('stats', None)

            if meta:
                sofa = meta.get('sofascore_player_id')
                if sofa and not item.get('sofascore_player_id'):
                    item['sofascore_player_id'] = sofa

            is_supplemental = item.get('source') == 'supplemental' or (not can_track and not item.get('player_id'))
            if is_supplemental:
                item['week_summary'] = "We can’t track detailed stats for this player yet."
                supplemental_items.append(item)
                continue

            filtered_items.append(item)

        if filtered_items:
            sec['items'] = filtered_items
            new_sections.append(sec)

    if supplemental_items:
        new_sections.append({'title': 'Supplemental Loans', 'items': supplemental_items})

    if internet_links:
        for sec in new_sections:
            items = sec.get('items') if isinstance(sec.get('items'), list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = _normalize_player_key(item.get('player_name'))
                if not key or key not in internet_links:
                    continue

                existing = item.get('links') if isinstance(item.get('links'), list) else []
                merged: list[Any] = []
                seen: set[str] = set()

                def _push(link: Any) -> None:
                    if isinstance(link, str):
                        url = link.strip()
                        payload = url
                    elif isinstance(link, dict):
                        url = str(link.get('url') or '').strip()
                        if not url:
                            return
                        payload = {k: v for k, v in link.items()}
                    else:
                        return
                    if not url or url in seen:
                        return
                    seen.add(url)
                    merged.append(payload)

                for link in existing:
                    _push(link)
                for link in internet_links.get(key, []):
                    _push(link)

                if merged:
                    item['links'] = merged[:LINKS_MAX_PER_ITEM]
                elif 'links' in item:
                    item['links'] = []

    content['sections'] = new_sections
    return content

# Cup synonyms to improve recall for competition names in headlines
CUP_SYNONYMS = {
    "EFL Trophy": ["Papa Johns Trophy", "E.F.L. Trophy", "Football League Trophy"],
    "FA Cup": ["Emirates FA Cup", "FA Cup First Round", "FA Cup Round One"],
    "League Cup": ["Carabao Cup", "EFL Cup"],
}

def _admin_bool(key: str, default: bool) -> bool:
    try:
        row = db.session.query(AdminSetting).filter_by(key=key).first()
        if row and row.value_json:
            return row.value_json.strip().lower() in ("1","true","yes","y")
    except Exception:
        pass
    return default

def _get_flags() -> dict:
    return {
        'soft_rank': _admin_bool('brave_soft_rank', ENV_SOFT_RANK),
        'site_boost': _admin_bool('brave_site_boost', ENV_SITE_BOOST),
        'cup_synonyms': _admin_bool('brave_cup_synonyms', ENV_USE_CUP_SYNS),
        'strict_range': _admin_bool('search_strict_range', ENV_STRICT_RANGE),
    }

def expand_competition_terms(comp: str, *, use_synonyms: bool) -> list[str]:
    base = [comp] if comp else []
    if not use_synonyms:
        return base
    return base + CUP_SYNONYMS.get(comp, [])

# Optional site boosts (only used if SITE_BOOST is enabled)
SITE_BOOSTS_BY_COUNTRY = {
    "GB": [
        "bbc.co.uk/sport", "yorkshirepost.co.uk", "manchesterworld.uk",
        # club sites
        "chelseafc.com", "nottinghamforest.co.uk", "rotherhamunited.co.uk",
        "cheltenhamtownfc.com", "doncasterroversfc.co.uk", "walsallfc.co.uk",
        "carlisleunited.co.uk",
    ]
}

# Soft ranking weights and helpers
RANK_WEIGHTS = {
    "domain_boost": 3,
    "name_team_match": 2,
    "opponent_match": 1,
    "recency": 1,
    "noisy_penalty": -2,
}
NOISY_HOST_SNIPS = ("fandom.com", "ea.com/games/ea-sports-fc")

def _strip_diacritics(s: str) -> str:
    try:
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    except Exception:
        return s

def _parse_any_date(s: str):
    if not s or not isinstance(s, str):
        return None
    st = s.strip()
    try:
        from datetime import datetime
        iso = st.replace('Z', '+00:00')
        return datetime.fromisoformat(iso)
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(st)
    except Exception:
        pass
    try:
        from datetime import date as _date
        return _date.fromisoformat(st[:10])
    except Exception:
        return None

def _score_hit(hit: dict, player_last: str, team_l: str, opponent: str | None, country: str, site_boost_flag: bool) -> int:
    try:
        url = (hit.get("url") or "").lower()
        title = (hit.get("title") or "").lower()
        snip = (hit.get("snippet") or "").lower()
        txt = f"{title} {snip}"
        score = 0
        if any(nh in url for nh in NOISY_HOST_SNIPS):
            score += RANK_WEIGHTS["noisy_penalty"]
        if site_boost_flag and any(site in url for site in SITE_BOOSTS_BY_COUNTRY.get(country, [])):
            score += RANK_WEIGHTS["domain_boost"]
        if player_last and player_last in txt and (team_l and team_l in txt):
            score += RANK_WEIGHTS["name_team_match"]
        elif player_last and player_last in txt:
            score += 1
        if opponent and opponent.lower() in txt:
            score += RANK_WEIGHTS["opponent_match"]
        if _parse_any_date(hit.get("date")):
            score += RANK_WEIGHTS["recency"]
        return score
    except Exception:
        return 0

def _gentle_filter(hit: dict, player_last: str, team_l: str) -> bool:
    # Keep transfers and match-intent pages; drop generic listicles if they lack both player+team
    title = (hit.get("title") or "").lower()
    snip = (hit.get("snippet") or "").lower()
    txt = f"{title} {snip}"
    if "transfer" in txt or "loan" in txt:
        return True
    match_terms = ("match report", "match reaction", "player ratings", "verdict", "talking points", "highlights")
    if any(t in txt for t in match_terms):
        return True
    if team_l and team_l in txt:
        return True
    if player_last and player_last in txt:
        return True
    return False

SYSTEM_PROMPT = """You are an editorial assistant for a football club newsletter.
- Input: a weekly loan report JSON (player + loan team context for the exact week) and a search context (articles/notes). The report.loanees[*] include per‑match data (result, home/away, opponent, minutes, goals, assists, cards) and comprehensive statistics (position, rating, saves, tackles, passes, shots, dribbles, duels, fouls), plus team_statistics when present.
- Output: a concise, fan-friendly newsletter as JSON. Keep it factual, readable, with short paragraphs and bullet lists where helpful. Base all stats and match details strictly on the provided weekly report; only use search_context for quotes/links and external color, never for stats.
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
          "week_summary": "...",             // 1–3 sentences: synthesize player + team context
          "stats": {
            "minutes": 0, "goals": 0, "assists": 0, "yellows": 0, "reds": 0,
            "position": "...", "rating": 0.0, "saves": 0, "goals_conceded": 0,
            "shots_total": 0, "shots_on": 0, "passes_total": 0, "passes_key": 0,
            "tackles_total": 0, "tackles_interceptions": 0, "duels_total": 0, "duels_won": 0,
            "dribbles_attempts": 0, "dribbles_success": 0, "fouls_drawn": 0, "fouls_committed": 0, "offsides": 0
          },
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
 - Guidance:
   - Use report.parent_team.name and report.range to frame the issue.
   - For each loanee, copy ALL fields from report.loanees[*].totals directly into the stats object. This includes position, rating, saves, tackles, passes, shots, and all other available stats.
   - Weave in notable per‑match details from report.loanees[*].matches. If team_statistics exist, reference key metrics that explain performance (e.g., shots, xG, possession) without dumping raw tables.
   - If a player had no minutes, note squad involvement (bench/not in squad) if role or played=false implies it.
   - Do not invent stats, fixtures, or opponents. Prefer brevity and clarity over speculation.
"""

# Structured output schema for strict Responses API validation
class NLLink(BaseModel):
    model_config = dict(extra='forbid')
    title: str
    url: str


class NLStats(BaseModel):
    model_config = dict(extra='forbid')
    minutes: int
    goals: int
    assists: int
    yellows: int
    reds: int


class NLSectionItem(BaseModel):
    model_config = dict(extra='forbid')
    player_name: str
    loan_team: str | None = None
    week_summary: str | None = None
    stats: NLStats | None = None
    match_notes: List[str] | None = None
    links: List[str | NLLink] | None = None


class NLSection(BaseModel):
    model_config = dict(extra='forbid')
    title: str
    items: List[NLSectionItem]


class NewsletterModel(BaseModel):
    model_config = dict(extra='forbid')
    title: str
    summary: str
    season: str
    range: Annotated[List[str], Field(min_items=2, max_items=2)]
    highlights: List[str] | None = None
    sections: List[NLSection]


def _newsletter_json_schema() -> dict:
    try:
        schema = NewsletterModel.model_json_schema()
        # Remove $schema to avoid draft-version conflicts with validators
        schema.pop("$schema", None)
        return schema
    except Exception:
        # Fallback to a minimal permissive schema if generation fails
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "season": {"type": "string"},
                "range": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "sections": {"type": "array"}
            },
            "required": ["title", "summary", "season", "range", "sections"],
            "additionalProperties": False
        }


NEWSLETTER_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "newsletter_response_format",
    "schema": _newsletter_json_schema(),
    # Use non-strict to allow optional fields like loan_team, week_summary, etc.
    # Strict mode in the Responses API requires 'required' to include all keys in 'properties'.
    "strict": False,
}

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

    _nl_dbg(
        "API-Football summarize_parent_loans_week params:",
        {
            "parent_team_db_id": team.id,
            "parent_team_api_id": team.team_id,
            "season": season_start_year,
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
        }
    )

    report = api_client.summarize_parent_loans_week(
        parent_team_db_id=team.id,
        parent_team_api_id=team.team_id,
        season=season_start_year,
        week_start=start,
        week_end=end,
        include_team_stats=True,
        db_session=db.session,
    )

    # Normalize parent team payload
    report["parent_team"] = {"db_id": team.id, "id": team.team_id, "name": team.name}
    db.session.commit()
    report["has_active_loans"] = has_loans
    return report

def brave_context_for_team_and_loans(team_name: str, report: Dict[str, Any], *, default_loc: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
    # Build a small set of targeted queries for context enrichment.
    # We avoid embedding date ranges inside the query text and rely on the
    # Brave API 'freshness' parameter, then strictly post-filter by date.
    start, end = report["range"]  # ISO strings
    queries = set()

    safe_team = f'"{team_name}"'
    queries.add(f"{safe_team} loan watch")
    queries.add(f"{safe_team} loan players")

    q_meta: Dict[str, Dict[str, str]] = {}
    flags = _get_flags()
    soft_rank = flags['soft_rank']
    site_boost = flags['site_boost']
    use_cup_syns = flags['cup_synonyms']
    strict_range = flags['strict_range']
    for loanee in report.get("loanees", []):
        pname = (loanee.get("player_name") or "").strip()
        loan_team = (loanee.get("loan_team_name") or "").strip()
        loan_country = (loanee.get("loan_team_country") or "").strip()
        loan_team_api_id = loanee.get("loan_team_api_id") or loanee.get("loan_team_id")
        if not pname or not loan_team:
            continue
        p = f'"{pname}"'
        lt = f'"{loan_team}"'
        # Core weekly query per loanee
        base_qs = [f"{p} {lt} match report", f"{p} {lt} performance"]
        for bq in base_qs:
            queries.add(bq)
            q_meta[bq] = {
                "player": pname,
                "loan_team": loan_team,
                "loan_team_country": loan_country,
                "loan_team_api_id": loan_team_api_id,
            }
        # Match-specific queries
        for m in loanee.get("matches", []):
            opponent = (m.get("opponent") or "").strip()
            comp = (m.get("competition") or "").strip()
            if opponent:
                o = f'"{opponent}"'
                if comp:
                    terms = expand_competition_terms(comp, use_synonyms=use_cup_syns)[:2]  # cap to 2 synonyms
                    if terms:
                        for t in terms:
                            c = f'"{t}"'
                            q = f"{p} {lt} {o} {c}"
                            queries.add(q)
                            q_meta[q] = {
                                "player": pname,
                                "loan_team": loan_team,
                                "opponent": opponent,
                                "loan_team_country": loan_country,
                                "loan_team_api_id": loan_team_api_id,
                            }
                    else:
                        q = f"{p} {lt} {o}"
                        queries.add(q)
                        q_meta[q] = {
                            "player": pname,
                            "loan_team": loan_team,
                            "opponent": opponent,
                            "loan_team_country": loan_country,
                            "loan_team_api_id": loan_team_api_id,
                        }
                else:
                    q = f"{p} {lt} {o}"
                    queries.add(q)
                    q_meta[q] = {
                        "player": pname,
                        "loan_team": loan_team,
                        "opponent": opponent,
                        "loan_team_country": loan_country,
                        "loan_team_api_id": loan_team_api_id,
                    }

    results: Dict[str, List[Dict[str, Any]]] = {}
    _nl_dbg(f"Brave context week start={start} end={end} loanees={len(report.get('loanees', []))} queries={len(queries)}")

    loc_cache: Dict[str, Dict[str, str]] = {}

    def _loc_for_meta(meta: Dict[str, Any]) -> Dict[str, str]:
        key = (meta.get("loan_team_country") or "").upper()
        if key:
            if key not in loc_cache:
                loc_cache[key] = resolve_localization_for_country(key, default=default_loc)
            return loc_cache[key]

        api_id = meta.get("loan_team_api_id")
        fallback_key = None
        if api_id:
            try:
                team = Team.query.filter(Team.team_id == int(api_id)).order_by(Team.updated_at.desc()).first()
                if team and getattr(team, 'country', None):
                    fallback_key = team.country.upper()
            except Exception:
                fallback_key = None

        if not fallback_key:
            fallback_key = ''

        if fallback_key not in loc_cache:
            loc_cache[fallback_key] = resolve_localization_for_country(fallback_key or None, default=default_loc)
        return loc_cache[fallback_key]

    # First pass: use Brave freshness window; strictness controlled by admin flag
    for q in queries:
        try:
            _nl_dbg(f"Searching (freshness, strict={strict_range}):", q)
            meta = q_meta.get(q, {})
            locale = _loc_for_meta(meta)
            hits = brave_search(query=q, since=start, until=end, count=8, strict_range=strict_range,
                                country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
            # Optional site boost: add 1–2 site‑scoped queries for better local coverage
            if site_boost:
                for site in SITE_BOOSTS_BY_COUNTRY.get(default_loc["country"], [])[:2]:
                    q_site = f"{q} site:{site}"
                    _nl_dbg("  Boost site query:", q_site)
                    extra = brave_search(query=q_site, since=start, until=end, count=6, strict_range=strict_range,
                                         country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
                    hits.extend(extra)

            # Gentle post-filter and soft ranking per query if enabled
            player_last = _strip_diacritics((meta.get("player") or "").split(" ")[-1]).lower()
            team_l = _strip_diacritics(meta.get("loan_team") or "").lower()
            opponent = meta.get("opponent")

            # Gentle filter
            filtered_hits = []
            for h in hits:
                try:
                    ok = _gentle_filter(h, player_last, team_l)
                except Exception:
                    ok = True
                if ok:
                    filtered_hits.append(h)

            # Soft rank
            if soft_rank:
                try:
                    filtered_hits.sort(key=lambda h: _score_hit(h, player_last, team_l, opponent, locale["country"], site_boost), reverse=True)
                    # Log top picks rationale
                    for h in filtered_hits[:2]:
                        sc = _score_hit(h, player_last, team_l, opponent, locale["country"], site_boost)
                        _nl_dbg("   rank pick:", meta.get("player"), sc, h.get("url"))
                except Exception:
                    pass

            hits = filtered_hits
            _nl_dbg(" -> hits:", len(hits))
            results[q] = hits[:5]
        except Exception as e:
            results[q] = []
            _nl_dbg(" -> error, recorded 0 hits", str(e))

    # If we got absolutely nothing, fallback to no date window (revert to prior behavior)
    try:
        total = sum(len(v) for v in results.values())
    except Exception:
        total = 0
    if total == 0 and not strict_range:
        _nl_dbg("No hits with freshness; falling back to open search")
        for q in queries:
            try:
                _nl_dbg("Searching (open):", q)
                meta = q_meta.get(q, {})
                locale = _loc_for_meta(meta)
                hits = brave_search(query=q, since="", until="", count=8, strict_range=False,
                                     country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
                _nl_dbg(" -> hits:", len(hits))
                results[q] = hits[:5]
            except Exception as e:
                results[q] = []
                _nl_dbg(" -> error, recorded 0 hits (open)", str(e))

    try:
        total = sum(len(v) for v in results.values())
        _nl_dbg("Brave total hits:", total)
    except Exception:
        total = 0

    # Optional: verify URLs resolve before passing to the LLM
    if ENV_CHECK_LINKS and total:
        try:
            # Collect unique URLs
            url_set = set()
            for arr in results.values():
                for h in arr:
                    u = (h.get("url") or "").strip()
                    if u:
                        url_set.add(u)

            ok_map = _check_urls_batch(list(url_set), timeout=LINK_TIMEOUT_SEC, max_workers=LINK_MAX_WORKERS)
            ok_urls = {u for u, ok in ok_map.items() if ok}
            _nl_dbg("Link check:", f"ok={len(ok_urls)} / total={len(url_set)}")

            # Filter per-query hits based on ok_urls
            for q, arr in list(results.items()):
                filtered = [h for h in (arr or []) if (h.get("url") or "") in ok_urls]
                if len(filtered) != len(arr or []):
                    _nl_dbg("Pruned dead links for query:", q, f"{len(arr or [])}->{len(filtered)}")
                results[q] = filtered
        except Exception as e:
            _nl_dbg("Link check failed:", str(e))

    return results

# ---- URL validation helpers ----
def _normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
        # Lowercase host, drop fragment
        netloc = (p.netloc or "").lower()
        return urlunparse((p.scheme, netloc, p.path or "", p.params or "", p.query or "", ""))
    except Exception:
        return u

def _url_ok(u: str, *, timeout: float = 6.0) -> bool:
    if not u or not isinstance(u, str):
        return False
    try:
        # Try HEAD first
        r = requests.head(u, allow_redirects=True, timeout=timeout)
        if 200 <= r.status_code < 400:
            return True
        # Some hosts reject HEAD; try a lightweight GET
        if r.status_code in (401, 403, 405, 501):
            r2 = requests.get(u, allow_redirects=True, timeout=timeout, stream=True)
            try:
                return 200 <= r2.status_code < 400
            finally:
                try:
                    r2.close()
                except Exception:
                    pass
        return False
    except Exception:
        return False

def _check_urls_batch(urls: list[str], *, timeout: float = 6.0, max_workers: int = 8) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if not urls:
        return out
    # Normalize and dedupe
    norm_map = {u: _normalize_url(u) for u in urls if u}
    uniq = list(set(norm_map.values()))
    # Map normalized back to original for stable keys
    rev_map: dict[str, list[str]] = {}
    for orig, norm in norm_map.items():
        rev_map.setdefault(norm, []).append(orig)
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_url_ok, nu, timeout=timeout): nu for nu in uniq}
            for fut in as_completed(futs):
                nu = futs[fut]
                ok = False
                try:
                    ok = bool(fut.result())
                except Exception:
                    ok = False
                # Assign result to all originals that normalize to this URL
                for orig in rev_map.get(nu, [nu]):
                    out[orig] = ok
    except Exception:
        # Best-effort fallback: sequential
        for nu in uniq:
            ok = _url_ok(nu, timeout=timeout)
            for orig in rev_map.get(nu, [nu]):
                out[orig] = ok
    return out


def _sanitize_links_in_content(obj: dict) -> dict:
    """
    Traverse the newsletter content and remove broken links. Keeps at most
    LINKS_MAX_PER_ITEM per section item. Supports both string links and
    objects with {title, url}.
    """
    if not isinstance(obj, dict):
        return obj

    # Collect all candidate URLs
    urls: list[str] = []
    sections = obj.get("sections") if isinstance(obj.get("sections"), list) else []
    for sec in sections:
        items = sec.get("items") if isinstance(sec, dict) and isinstance(sec.get("items"), list) else []
        for it in items:
            links = it.get("links") if isinstance(it, dict) else None
            if not isinstance(links, list):
                continue
            for l in links:
                if isinstance(l, str):
                    if l:
                        urls.append(l)
                elif isinstance(l, dict):
                    u = l.get("url")
                    if u:
                        urls.append(u)

    ok_map = _check_urls_batch(list(set(urls)), timeout=LINK_TIMEOUT_SEC, max_workers=LINK_MAX_WORKERS) if urls else {}

    # Rebuild links per item with only OK URLs
    pruned_count = 0
    for sec in sections:
        items = sec.get("items") if isinstance(sec, dict) and isinstance(sec.get("items"), list) else []
        for it in items:
            links = it.get("links") if isinstance(it, dict) else None
            if not isinstance(links, list):
                continue
            kept: list = []
            for l in links:
                if len(kept) >= LINKS_MAX_PER_ITEM:
                    break
                if isinstance(l, str):
                    ok = ok_map.get(l, False)
                    if ok:
                        kept.append(l)
                    else:
                        pruned_count += 1
                elif isinstance(l, dict):
                    u = l.get("url")
                    if u and ok_map.get(u, False):
                        kept.append(l)
                    else:
                        pruned_count += 1
                else:
                    pruned_count += 1
            it["links"] = kept

    try:
        _nl_dbg("final-link-sanitize:", f"checked={len(ok_map)} pruned={pruned_count}")
    except Exception:
        pass
    return obj

def persist_newsletter(team_db_id: int, content_json_str: str, week_start: date, week_end: date, issue_date: date, newsletter_type: str = "weekly") -> Newsletter:
    # Reset any prior failed transaction to avoid InFailedSqlTransaction
    try:
        db.session.rollback()
    except Exception:
        pass

    parsed = json.loads(content_json_str)
    title = parsed.get("title") or "Weekly Loan Update"

    # Get team info for rendering
    team = Team.query.get(team_db_id)
    team_name = team.name if team else None

    # Render and embed variants (web_html, email_html, text) for convenience
    try:
        variants = _render_variants(parsed, team_name)
        parsed['rendered'] = variants
        content_json_str = json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # Non-fatal; continue without rendered variants
        pass

    now = datetime.now(timezone.utc)
    newsletter = Newsletter(
        team_id=team_db_id,
        newsletter_type=newsletter_type,
        title=title,
        content=content_json_str,           # store JSON with rendered variants
        structured_content=content_json_str,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=issue_date,
        generated_date=now,
        # Leave unpublished by default so it can be reviewed/approved
        published=False,
        published_date=None,
    )
    db.session.add(newsletter)
    try:
        db.session.commit()
    except Exception:
        # Ensure session usable for subsequent requests
        db.session.rollback()
        raise
    return newsletter

def compose_team_weekly_newsletter(team_db_id: int, target_date: date) -> dict:
    """Compose (but do not persist) a weekly newsletter.
    Returns a dict with keys: content_json (str), week_start (date), week_end (date), season_start_year (int).
    """
    # Compute week window
    week_start, week_end = _monday_range(target_date)

    # Derive season from the week we are processing (European season starts Aug 1)
    season_start_year = week_start.year if week_start.month >= 8 else week_start.year - 1
    api_client.set_season_year(season_start_year)
    try:
        # Log current season view on the client after setting
        _nl_dbg(
            "Season inference:",
            {
                "target_date": target_date.isoformat(),
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "season_start_year": season_start_year,
                "api_client.current_season": getattr(api_client, "current_season", None),
                "api_client.current_season_start_year": getattr(api_client, "current_season_start_year", None),
                "api_client.current_season_end_year": getattr(api_client, "current_season_end_year", None),
            }
        )
    except Exception:
        pass
    api_client._prime_team_cache(season_start_year)

    # Fetch report via tool for the inferred season
    _nl_dbg("Compose for team:", team_db_id, "week:", week_start, week_end, "season:", season_start_year)
    report = fetch_weekly_report_tool(team_db_id, season_start_year, week_start, week_end)
    try:
        _nl_dbg(
            "Report summary:",
            {
                "report.season": report.get("season"),
                "report.range": report.get("range"),
                "loanees": len(report.get("loanees", [])),
            }
        )
    except Exception:
        _nl_dbg("Report loanees:", len(report.get("loanees", [])))

    loanees = report.get("loanees") or []
    if len(loanees) == 0:
        raise NoActiveLoaneesError(team_db_id, week_start, week_end)

    # Build player lookup to help post-processing attach player_id + sofascore ids later
    player_lookup: dict[str, list[dict[str, Any]]] = {}
    loanee_meta_by_pid: dict[int, dict[str, Any]] = {}
    loanee_meta_by_key: dict[str, dict[str, Any]] = {}

    def _register_alias(alias: str | None, entry: dict[str, Any]) -> None:
        if not alias:
            return
        key = _normalize_player_key(alias)
        if not key:
            return
        player_lookup.setdefault(key, []).append(entry)

    def _register_meta(alias: str | None, meta: dict[str, Any]) -> None:
        if not alias:
            return
        key = _normalize_player_key(alias)
        if not key:
            return
        loanee_meta_by_key[key] = meta

    for loanee in loanees:
        pid = loanee.get("player_api_id") or loanee.get("player_id")
        entry = None
        if pid:
            entry = {
                "player_id": int(pid),
                "loan_team_api_id": loanee.get("loan_team_api_id") or loanee.get("loan_team_id"),
                "loan_team_id": loanee.get("loan_team_db_id") or loanee.get("loan_team_id"),
                "loan_team_name": loanee.get("loan_team_name") or loanee.get("loan_team"),
            }
        meta_entry = {
            "can_fetch_stats": bool(loanee.get("can_fetch_stats", True)),
            "sofascore_player_id": loanee.get("sofascore_player_id"),
        }
        if pid:
            try:
                loanee_meta_by_pid[int(pid)] = meta_entry
            except Exception:
                pass
        primary_name = loanee.get("player_name") or loanee.get("name")
        full_name = loanee.get("player_full_name")
        display = to_initial_last(primary_name or full_name or "")
        if entry:
            _register_alias(primary_name, entry)
            _register_alias(full_name, entry)
            if display and display != primary_name:
                _register_alias(display, entry)
            if full_name:
                alt = to_initial_last(full_name)
                if alt and alt != display:
                    _register_alias(alt, entry)
        for alias in filter(None, [primary_name, full_name, display, to_initial_last(full_name or primary_name or "")]):
            _register_meta(alias, meta_entry)

    _set_latest_player_lookup(player_lookup)

    # Brave context
    brave_ctx = brave_context_for_team_and_loans(report["parent_team"]["name"], report, default_loc=LOCALIZATION_DEFAULT)
    try:
        total_links = sum(len(v) for v in brave_ctx.values())
        _nl_dbg("Search contexts:", len(brave_ctx), "total links:", total_links)
    except Exception:
        pass

    # Compose agent input
    user_payload = {
        "task": "compose_weekly_newsletter",
        "team": report["parent_team"],
        "report": report,
        "search_context": brave_ctx
    }

    # Try strict structured output; fall back to plain JSON extraction if schema not supported
    try:
        completion = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)}
            ],
            temperature=0.3,
            text={
                "format": NEWSLETTER_RESPONSE_FORMAT
            }
        )
    except Exception as e:
        _nl_dbg("Responses.create (structured) failed:", str(e))
        completion = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)}
            ],
            temperature=0.4,
            text={
                "format": {"type": "json_object"}
            }
        )

    # Extract JSON payload robustly
    def _extract_json(resp_obj) -> dict:
        # 1) Try output_text
        try:
            txt = getattr(resp_obj, "output_text", None)
            if isinstance(txt, str) and txt.strip():
                return json.loads(txt)
        except Exception:
            pass
        # 2) Walk response.output
        try:
            out = getattr(resp_obj, "output", None)
            if out and isinstance(out, list):
                for item in out:
                    content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else None)
                    if content and isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                if c.get("type") in ("output_json", "json"):
                                    j = c.get("json") or c.get("input_json")
                                    if j:
                                        return j
                                if "text" in c and isinstance(c["text"], str):
                                    try:
                                        return json.loads(c["text"])
                                    except Exception:
                                        continue
        except Exception:
            pass
        # 3) Regex last resort
        try:
            m = re.search(r"\{(?:.|\n)*\}", str(resp_obj))
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        raise ValueError("Unable to parse model JSON")

    parsed = _extract_json(completion)

    # Apply lookup + enrichment to ensure player ids and sofascore ids propagate
    try:
        if isinstance(parsed, dict):
            parsed, _ = _apply_player_lookup(parsed, player_lookup)
            parsed = legacy_lint_and_enrich(parsed)
            parsed = _enforce_loanee_metadata(parsed, loanee_meta_by_pid, loanee_meta_by_key)
    except Exception as enrich_error:
        _nl_dbg("lint-and-enrich failed:", str(enrich_error))

    # Post-process: validate outbound links in the final content
    if ENV_VALIDATE_FINAL_LINKS:
        try:
            parsed = _sanitize_links_in_content(parsed)
        except Exception as e:
            _nl_dbg("final-link-sanitize failed:", str(e))

    content = json.dumps(parsed, ensure_ascii=False)
    _nl_dbg("LLM content length:", len(content))

    return {
        "content_json": content,
        "week_start": week_start,
        "week_end": week_end,
        "season_start_year": season_start_year,
    }

def generate_team_weekly_newsletter(team_db_id: int, target_date: date) -> dict:
    """Compose and persist a weekly newsletter; returns row.to_dict().
    Used by batch jobs. For API routes, prefer composing then persisting at the route level.
    """
    out = compose_team_weekly_newsletter(team_db_id, target_date)
    row = persist_newsletter(
        team_db_id=team_db_id,
        content_json_str=out["content_json"],
        week_start=out["week_start"],
        week_end=out["week_end"],
        issue_date=target_date,
        newsletter_type="weekly",
    )
    return row.to_dict()
BRAVE_LOCALIZATION_BY_ISO = {
    "GB": {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"},
    "IE": {"country": "IE", "search_lang": "en", "ui_lang": "en-IE"},
    "FR": {"country": "FR", "search_lang": "fr", "ui_lang": "fr-FR"},
    "ES": {"country": "ES", "search_lang": "es", "ui_lang": "es-ES"},
    "DE": {"country": "DE", "search_lang": "de", "ui_lang": "de-DE"},
    "IT": {"country": "IT", "search_lang": "it", "ui_lang": "it-IT"},
    "PT": {"country": "PT", "search_lang": "pt", "ui_lang": "pt-PT"},
    "BR": {"country": "BR", "search_lang": "pt", "ui_lang": "pt-BR"},
    "NL": {"country": "NL", "search_lang": "nl", "ui_lang": "nl-NL"},
    "BE": {"country": "BE", "search_lang": "nl", "ui_lang": "nl-BE"},
    "BE-FR": {"country": "BE", "search_lang": "fr", "ui_lang": "fr-BE"},
    "SE": {"country": "SE", "search_lang": "sv", "ui_lang": "sv-SE"},
    "NO": {"country": "NO", "search_lang": "no", "ui_lang": "no-NO"},
    "DK": {"country": "DK", "search_lang": "da", "ui_lang": "da-DK"},
    "FI": {"country": "FI", "search_lang": "fi", "ui_lang": "fi-FI"},
    "CH": {"country": "CH", "search_lang": "de", "ui_lang": "de-CH"},
    "AT": {"country": "AT", "search_lang": "de", "ui_lang": "de-AT"},
    "PL": {"country": "PL", "search_lang": "pl", "ui_lang": "pl-PL"},
    "HR": {"country": "HR", "search_lang": "hr", "ui_lang": "hr-HR"},
    "BA": {"country": "BA", "search_lang": "bs", "ui_lang": "bs-BA"},
    "US": {"country": "US", "search_lang": "en", "ui_lang": "en-US"},
}

COUNTRY_FALLBACKS = {
    "BE": ["BE-FR", "FR", "NL"],
    "CA": ["US", "GB"],
    "CH": ["DE", "FR", "IT"],
    "BR": ["PT"],
    "MX": ["ES", "US"],
    "AR": ["ES"],
    "CO": ["ES"],
    "JP": ["US"],
}

def resolve_localization_for_country(iso_code: str | None, *, default: dict[str, str] | None = None) -> dict[str, str]:
    default_loc = default or LOCALIZATION_DEFAULT
    if not iso_code:
        return dict(default_loc)
    code = iso_code.upper()
    if code in BRAVE_LOCALIZATION_BY_ISO:
        return dict(BRAVE_LOCALIZATION_BY_ISO[code])
    for fallback in COUNTRY_FALLBACKS.get(code, []):
        if fallback in BRAVE_LOCALIZATION_BY_ISO:
            return dict(BRAVE_LOCALIZATION_BY_ISO[fallback])
    return dict(default_loc)

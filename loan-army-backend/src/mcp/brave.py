from typing import List, Dict, Any, Tuple
import os
import requests

BASE_URL = "https://api.search.brave.com/res/v1"
WEB_ENDPOINT = f"{BASE_URL}/web/search"
NEWS_ENDPOINT = f"{BASE_URL}/news/search"

# Header per Brave docs: X-Subscription-Token is required for auth
# https://api-dashboard.search.brave.com/app/documentation/web-search/request-headers

_DEF_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}

class BraveApiError(Exception):
    pass


def _headers() -> Dict[str, str]:
    token = os.getenv("BRAVE_API_KEY", "").strip()
    if not token:
        raise BraveApiError("BRAVE_API_KEY is not set")
    h = dict(_DEF_HEADERS)
    h["X-Subscription-Token"] = token
    return h


def _split_range(freshness: str) -> Tuple[str, str]:
    """Accepts a `YYYY-MM-DDtoYYYY-MM-DD` string and returns (since, until).
    Falls back to ("", "") if malformed.
    """
    try:
        if "to" in freshness:
            s, u = freshness.split("to", 1)
            return s[:10], u[:10]
    except Exception:
        pass
    return "", ""


def _normalize_items(kind: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Brave returns rich objects; we normalize a small subset for the newsletter pipeline
    out: List[Dict[str, Any]] = []
    items = []
    try:
        if kind == "web":
            # web results live under multiple keys (e.g., web, articles, discussions)
            if isinstance(data.get("web"), dict):
                items += data.get("web", {}).get("results", []) or []
            if isinstance(data.get("discussions"), dict):
                items += data.get("discussions", {}).get("results", []) or []
            if isinstance(data.get("knowledge_graph"), dict):
                items += data.get("knowledge_graph", {}).get("results", []) or []
        elif kind == "news":
            if isinstance(data.get("news"), dict):
                items += data.get("news", {}).get("results", []) or []
    except Exception:
        items = []

    for r in items:
        url = (r.get("url") or r.get("link") or "").strip()
        if not url:
            continue
        out.append({
            "title": r.get("title") or r.get("name") or "",
            "url": url,
            "snippet": r.get("description") or r.get("snippet") or "",
            "date": r.get("date") or r.get("published") or r.get("published_date") or r.get("age") or r.get("page_age") or "",
            "source": kind,
        })
    return out


def _search_once(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.get(endpoint, params=params, headers=_headers(), timeout=15)
    if resp.status_code == 401:
        raise BraveApiError("Unauthorized: check BRAVE_API_KEY")
    if resp.status_code >= 400:
        raise BraveApiError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except Exception as e:
        raise BraveApiError(f"Invalid JSON: {e}")


def brave_search(
    query: str,
    since: str,
    until: str,
    *,
    count: int = 8,
    country: str = "GB",
    search_lang: str = "en",
    ui_lang: str = "en-GB",
    result_filter: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Query Brave Search API for both Web and News results within a date window.
    Returns merged, de-duplicated results with fields: title, url, snippet, date, source (web|news).

    - since/until should be YYYY-MM-DD strings. If empty, Brave will accept `freshness` shorthands
      but this helper expects explicit range and will omit freshness if either bound is missing.
    """
    q = (query or "").strip()
    if not q:
        return []

    freshness = None
    if since and until:
        freshness = f"{since[:10]}to{until[:10]}"

    common = {
        "q": q,
        "count": min(max(int(count or 8), 1), 20),
        "country": country,
        "search_lang": search_lang,
        "ui_lang": ui_lang,
        "extra_snippets": True,
        "safesearch": "moderate",
    }
    if freshness:
        common["freshness"] = freshness

    # Web
    web_params = dict(common)
    if result_filter:
        web_params["result_filter"] = result_filter
    web_json = _search_once(WEB_ENDPOINT, web_params)
    web_items = _normalize_items("web", web_json)

    # News
    news_json = _search_once(NEWS_ENDPOINT, dict(common))
    news_items = _normalize_items("news", news_json)

    # Merge & de-dup by URL
    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for lst in (web_items, news_items):
        for r in lst:
            u = r.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            merged.append(r)

    return merged[:count]
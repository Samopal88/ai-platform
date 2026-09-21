"""
AI Workspace Platform - Web Search Service

Providers (priority order when WEB_SEARCH_PROVIDER=auto):
  1. searxng    — self-hosted, free, no API key needed
  2. yandex_xml — RU-friendly, requires YANDEX_XML_USER + YANDEX_XML_KEY
  3. serpapi    — paid, Google results
  4. serper     — paid, Google results

All providers return normalized: [{title, url, snippet}, ...]
"""
from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds per provider
_MAX_RESULTS = 8
_SEARX_HEALTH_TIMEOUT = float(os.environ.get("SEARXNG_HEALTH_TIMEOUT", "0.6"))
_SEARX_HEALTH_TTL_UP = float(os.environ.get("SEARXNG_HEALTH_TTL_UP", "30"))
_SEARX_HEALTH_TTL_DOWN = float(os.environ.get("SEARXNG_HEALTH_TTL_DOWN", "10"))
_searx_health_state: Optional[bool] = None
_searx_health_checked_at: float = 0.0


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _searxng_search(query: str, base_url: str) -> list[dict]:
    """SearxNG self-hosted instance. GET /search?q=...&format=json"""
    base_url = base_url.rstrip("/")
    url = f"{base_url}/search"
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo",
        "language": "ru-RU",
        "safesearch": 0,
    }
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", [])[:_MAX_RESULTS]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", "") or item.get("snippet", ""),
        })
    return results


def _set_searxng_health(healthy: bool) -> None:
    global _searx_health_state, _searx_health_checked_at
    _searx_health_state = bool(healthy)
    _searx_health_checked_at = time.monotonic()


def _searxng_health_ok(base_url: str, force: bool = False) -> bool:
    """
    Fast health check with cached availability state.
    Avoids expensive request-time timeouts when SearxNG is clearly down.
    """
    global _searx_health_state, _searx_health_checked_at
    now = time.monotonic()
    if not force and _searx_health_state is not None:
        ttl = _SEARX_HEALTH_TTL_UP if _searx_health_state else _SEARX_HEALTH_TTL_DOWN
        if now - _searx_health_checked_at < ttl:
            return _searx_health_state

    try:
        # Root endpoint is lightweight enough for liveness in local deployment.
        resp = requests.get(base_url.rstrip("/") + "/", timeout=_SEARX_HEALTH_TIMEOUT)
        healthy = 200 <= resp.status_code < 500
        _set_searxng_health(healthy)
        return healthy
    except Exception:
        _set_searxng_health(False)
        return False


def _yandex_xml_search(query: str, user: str, api_key: str) -> list[dict]:
    """Yandex XML search API. Returns XML with <doc> elements."""
    url = "https://yandex.ru/search/xml"
    params = {
        "user": user,
        "key": api_key,
        "query": query,
        "l10n": "ru",
        "sortby": "rlv",
        "filter": "none",
        "maxpassages": 1,
        "groupby": f"attr%3D%22%22.mode%3Dflat.groups-on-page%3D{_MAX_RESULTS}.docs-in-group%3D1",
    }
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    results = []
    for doc in root.iter("doc"):
        title_el = doc.find("title")
        url_el = doc.find("url")
        passage_el = doc.find(".//passage")
        headline_el = doc.find("headline")

        title = "".join(title_el.itertext()) if title_el is not None else ""
        link = url_el.text.strip() if url_el is not None and url_el.text else ""
        snippet = (
            "".join(passage_el.itertext()) if passage_el is not None
            else "".join(headline_el.itertext()) if headline_el is not None
            else ""
        )

        if link:
            results.append({"title": title.strip(), "url": link, "snippet": snippet.strip()})
        if len(results) >= _MAX_RESULTS:
            break
    return results


def _serpapi_search(query: str, api_key: str) -> list[dict]:
    url = "https://serpapi.com/search"
    params = {"q": query, "api_key": api_key, "engine": "google", "num": _MAX_RESULTS, "hl": "ru"}
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("organic_results", [])[:_MAX_RESULTS]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


def _serper_search(query: str, api_key: str) -> list[dict]:
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": _MAX_RESULTS, "gl": "ru", "hl": "ru"}
    resp = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("organic", [])[:_MAX_RESULTS]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })
    return results


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(results: list[dict]) -> list[dict]:
    """Remove duplicate URLs, preserving first-seen order."""
    seen: set[str] = set()
    out = []
    for r in results:
        url = r.get("url", "")
        # Normalise: strip trailing slash and fragment
        try:
            parsed = urlparse(url)
            key = parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")
        except Exception:
            key = url
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out[:_MAX_RESULTS]


# ---------------------------------------------------------------------------
# Provider chain helpers
# ---------------------------------------------------------------------------

def _try_provider(name: str, fn, *args) -> Optional[list[dict]]:
    """Call a provider function; log and return None on any error."""
    try:
        results = fn(*args)
        if results:
            logger.info("web_search: provider '%s' returned %d results", name, len(results))
            return results
    except requests.exceptions.Timeout:
        logger.warning("web_search: provider '%s' timed out", name)
        if name == "searxng":
            _set_searxng_health(False)
    except Exception as exc:
        logger.warning("web_search: provider '%s' failed: %s", name, exc)
        if name == "searxng":
            _set_searxng_health(False)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def web_search(query: str) -> Optional[list[dict]]:
    """
    Run a web search using the configured provider.
    Returns list of {title, url, snippet} dicts (max 8, deduplicated), or None.

    WEB_SEARCH_PROVIDER=auto  → try searxng → yandex_xml → serpapi/serper
    WEB_SEARCH_PROVIDER=<name> → use that provider only
    """
    provider = os.environ.get("WEB_SEARCH_PROVIDER", "").strip().lower()

    if provider == "auto" or provider == "":
        results = _auto_search(query)
    elif provider == "searxng":
        searxng_url = os.environ.get("SEARXNG_URL", "http://localhost:8080").strip()
        if not _searxng_health_ok(searxng_url):
            logger.warning("web_search: searxng is unhealthy, skipping provider call")
            results = None
        else:
            results = _try_provider("searxng", _searxng_search, query, searxng_url)
    elif provider == "yandex_xml":
        user = os.environ.get("YANDEX_XML_USER", "").strip()
        key = os.environ.get("YANDEX_XML_KEY", "").strip()
        results = _try_provider("yandex_xml", _yandex_xml_search, query, user, key) if user and key else None
    elif provider == "serpapi":
        key = os.environ.get("SERPAPI_API_KEY", "").strip()
        results = _try_provider("serpapi", _serpapi_search, query, key) if key else None
    elif provider == "serper":
        key = os.environ.get("SERPER_API_KEY", "").strip()
        results = _try_provider("serper", _serper_search, query, key) if key else None
    else:
        logger.warning("web_search: unknown provider '%s'", provider)
        results = None

    if results:
        return _deduplicate(results)
    return None


def _auto_search(query: str) -> Optional[list[dict]]:
    """Priority chain: searxng → yandex_xml → serpapi → serper."""
    # 1. SearxNG
    searxng_url = os.environ.get("SEARXNG_URL", "http://localhost:8080").strip()
    if _searxng_health_ok(searxng_url):
        results = _try_provider("searxng", _searxng_search, query, searxng_url)
        if results:
            return results
    else:
        logger.warning("web_search: searxng healthcheck failed; fast-fallback to next provider")

    # 2. Yandex XML
    yandex_user = os.environ.get("YANDEX_XML_USER", "").strip()
    yandex_key = os.environ.get("YANDEX_XML_KEY", "").strip()
    if yandex_user and yandex_key:
        results = _try_provider("yandex_xml", _yandex_xml_search, query, yandex_user, yandex_key)
        if results:
            return results

    # 3. SerpAPI
    serpapi_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if serpapi_key:
        results = _try_provider("serpapi", _serpapi_search, query, serpapi_key)
        if results:
            return results

    # 4. Serper
    serper_key = os.environ.get("SERPER_API_KEY", "").strip()
    if serper_key:
        results = _try_provider("serper", _serper_search, query, serper_key)
        if results:
            return results

    return None


# ---------------------------------------------------------------------------
# Formatting helpers (unchanged API)
# ---------------------------------------------------------------------------

def format_search_results_for_llm(results: list[dict]) -> str:
    """Format search results into a system prompt block for the LLM."""
    lines = ["Результаты веб-поиска:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] {r['title']}")
        lines.append(f"URL: {r['url']}")
        if r.get("snippet"):
            lines.append(f"{r['snippet']}")
    lines.append(
        "\nИспользуй эти результаты в ответе. В конце обязательно добавь раздел "
        "'Источники:' со списком использованных ссылок."
    )
    return "\n".join(lines)


def format_search_results_for_user(results: list[dict]) -> str:
    """Format search results as a markdown list appended to AI answer."""
    if not results:
        return ""
    lines = ["\n\n**Источники:**"]
    for r in results:
        title = r.get("title") or r.get("url", "")
        url = r.get("url", "")
        if url:
            lines.append(f"- [{title}]({url})")
    return "\n".join(lines)

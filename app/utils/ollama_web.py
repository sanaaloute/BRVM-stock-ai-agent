"""Ollama Cloud web search & web fetch (https://docs.ollama.com/capabilities/web-search).

Uses the Ollama Cloud API key (OLLAMA_API_KEY). Serves as a fallback fetch
channel when Tavily fails or returns empty (e.g. Cloudflare-blocked sources
like Sika Finance)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)

_API_BASE = "https://ollama.com/api"


def available() -> bool:
    """Web search/fetch needs the Ollama Cloud API key."""
    return bool(getattr(config, "OLLAMA_API_KEY", "") or "")


def web_fetch(url: str, timeout: float = 30.0) -> dict[str, Any] | None:
    """Fetch one page via Ollama Cloud. Returns {"title", "content", "links"} or None."""
    if not available():
        return None
    try:
        resp = httpx.post(
            f"{_API_BASE}/web_fetch",
            headers={"Authorization": f"Bearer {config.OLLAMA_API_KEY}"},
            json={"url": url},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and str(data.get("content") or "").strip():
            return data
        return None
    except Exception as e:
        logger.warning("Ollama web_fetch failed for %s: %s", url, e)
        return None


def web_search(query: str, max_results: int = 5, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Web search via Ollama Cloud. Returns [{"title", "url", "content"}] or []."""
    if not available():
        return []
    try:
        resp = httpx.post(
            f"{_API_BASE}/web_search",
            headers={"Authorization": f"Bearer {config.OLLAMA_API_KEY}"},
            json={"query": query, "max_results": max(1, min(int(max_results), 10))},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") if isinstance(data, dict) else None
        return results if isinstance(results, list) else []
    except Exception as e:
        logger.warning("Ollama web_search failed for %r: %s", query, e)
        return []

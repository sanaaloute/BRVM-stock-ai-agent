"""Per-symbol detail sections (dividends, news, prediction) served from a
daily-refreshed store instead of live scrapes on every request.

The mobile symbol-detail endpoint used to scrape richbourse.com three times
per request (~4-5 s of latency). Sections now read from a disk-persisted
cache refreshed once per weekday after market close (scheduler
`symbol_sections_loop`). A request that finds the cache empty or expired
scrapes on demand and back-fills it; when a scrape fails, the last known
good value is served (stale-if-error), mirroring the palmarès cache.

Refresh cadence: dividends/news/predictions change at most once per session
(announcements, post-close prediction), so one post-close refresh per weekday
suffices. The 60 h TTL spans the weekend without a live scrape (Fri 16:30
refresh expires Mon early morning, when the market was closed anyway).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.utils.cache import MarketDataCache

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "symbol_sections_cache.json"
_TTL_SECONDS = 60 * 3600

_cache = MarketDataCache(ttl_seconds=_TTL_SECONDS, persist_path=_CACHE_PATH)

_DIVIDENDS_KEY = "dividends:ALL"  # one shared page, filtered per symbol


def _serve(key: str, fetch: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
    """Cache-first read: fresh entry, else live fetch (cached on success),
    else stale entry, else the (error) value the fetch returned."""
    fresh = _cache.get(key)
    if fresh is not None:
        return fresh
    try:
        value = fetch()
    except Exception as e:  # noqa: BLE001 - fall through to stale
        logger.info("Live fetch failed for %s, serving stale: %s", key, e)
        value = None
    if value and not value.get("error"):
        _cache.set(key, value)
        return value
    return _cache.get_stale(key) or value


def dividends_for(symbol: str) -> dict[str, Any]:
    """Announced dividends for one symbol, from the shared cached page."""
    from app.utils.news import get_richbourse_dividends

    page = _serve(_DIVIDENDS_KEY, lambda: get_richbourse_dividends(50, None)) or {}
    items = [
        it
        for it in page.get("items") or []
        if (it.get("symbol") or "").strip().upper() == symbol
    ]
    out = dict(page)
    out["items"] = items
    return out


def news_for(symbol: str) -> dict[str, Any]:
    """Company news, cached per symbol."""
    from app.utils.news import get_company_news

    return _serve(f"news:{symbol}", lambda: get_company_news(symbol)) or {}


def prediction_for(symbol: str) -> dict[str, Any]:
    """Technical prediction, cached per symbol."""
    from app.utils.news import get_richbourse_prediction

    return _serve(f"prediction:{symbol}", lambda: get_richbourse_prediction(symbol)) or {}


def refresh_all(symbols: list[str] | None = None) -> dict[str, int]:
    """Refresh every section for all symbols (daily post-close job). The
    dividends page is shared: one scrape covers all symbols. Scrapers apply
    their own politeness sleep between HTTP calls."""
    from app.utils.brvm_companies import get_valid_symbols
    from app.utils.news import (
        get_company_news,
        get_richbourse_dividends,
        get_richbourse_prediction,
    )

    stats = {"dividends": 0, "news": 0, "prediction": 0}
    try:
        page = get_richbourse_dividends(50, None)
        if page and not page.get("error"):
            _cache.set(_DIVIDENDS_KEY, page)
            stats["dividends"] = 1
    except Exception as e:  # noqa: BLE001 - keep refreshing the other sections
        logger.warning("Dividends page refresh failed: %s", e)

    for sym in sorted(symbols or get_valid_symbols()):
        for kind, fetch in (("news", get_company_news), ("prediction", get_richbourse_prediction)):
            try:
                value = fetch(sym)
            except Exception as e:  # noqa: BLE001 - one symbol must not stop the run
                logger.info("%s refresh failed for %s: %s", kind, sym, e)
                continue
            if value and not value.get("error"):
                _cache.set(f"{kind}:{sym}", value)
                stats[kind] += 1
    return stats

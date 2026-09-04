"""Market data lifecycle: fetch once, store locally, refresh on a schedule.

Rationale: most BRVM data is statistical and only changes once per day after
market close (~15:00 GMT). Instead of scraping on every API request:

- `refresh_daily_snapshots()` — post-close snapshot of the full palmarès into
  `market_snapshots` (one row per symbol per day). Run by the scheduler every
  weekday after close, and triggered on demand when the snapshot is missing.
- `get_palmares()` — serve the latest snapshot from the DB (instant); fall
  back to a live scrape only when no snapshot exists yet.
- Slowly-varying data (company fiches, SGI brokers) is refreshed weekly by the
  existing entrypoint/job; this module only adds the daily layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models as db_models

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def save_daily_snapshot(stocks: list[dict[str, Any]], day: str | None = None) -> int:
    """Persist one palmarès row per symbol for `day` (default today), replacing
    any existing rows for that day. Returns the number of symbols stored."""
    if not stocks:
        return 0
    day = day or _today()
    db_migrate.ensure_schema()
    rows = []
    for s in stocks:
        symbol = (s.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "day": day,
            "name": s.get("name"),
            "price": s.get("cours_actuel"),
            "prev_price": s.get("cours_veille"),
            "variation_pct": s.get("variation_pct"),
            "volume": s.get("volume"),
            "value_fcfa": s.get("value_fcfa"),
            "capitalisation": s.get("capitalisation"),
        })
    with db_engine.session_scope() as s:
        s.execute(delete(db_models.MarketSnapshot).where(db_models.MarketSnapshot.day == day))
        if rows:
            s.execute(db_models.MarketSnapshot.__table__.insert(), rows)
    return len(rows)


def refresh_daily_snapshots() -> int:
    """Scrape the palmarès and store today's snapshot (blocking; run off the
    event loop). Returns the number of symbols stored."""
    from app.utils._data import fetch_palmares

    stocks = fetch_palmares(period="veille", progression="tout", force_refresh=True)
    return save_daily_snapshot(stocks)


def get_snapshot(day: str | None = None) -> list[dict[str, Any]]:
    """Snapshot rows for `day` (default: the most recent day with data)."""
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        if day is None:
            day = s.execute(select(db_models.MarketSnapshot.day).order_by(db_models.MarketSnapshot.day.desc())).scalars().first()
        if day is None:
            return []
        rows = s.execute(
            select(db_models.MarketSnapshot).where(db_models.MarketSnapshot.day == day)
        ).scalars().all()
    out = []
    for r in rows:
        out.append({
            "symbol": r.symbol,
            "name": r.name,
            "cours_actuel": r.price,
            "cours_veille": r.prev_price,
            "variation_pct": r.variation_pct,
            "volume": r.volume,
            "value_fcfa": r.value_fcfa,
            "capitalisation": r.capitalisation,
            "day": r.day,
        })
    return out


def latest_snapshot_day() -> str | None:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        return s.execute(
            select(db_models.MarketSnapshot.day).order_by(db_models.MarketSnapshot.day.desc())
        ).scalars().first()


def _with_names(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every row carries the full company name (fall back to the
    companies registry when the scrape/snapshot lacks it)."""
    missing = [s for s in stocks if s.get("symbol") and not s.get("name")]
    if not missing:
        return stocks
    try:
        from app.utils.brvm_companies import get_symbol_to_name

        names = get_symbol_to_name()
        for s in missing:
            s["name"] = names.get((s.get("symbol") or "").strip().upper())
    except Exception:
        pass
    return stocks


def palmares_for_api() -> list[dict[str, Any]]:
    """Palmares rows for the mobile API: local snapshot first, live fallback."""
    stocks = get_snapshot()
    if stocks:
        return _with_names(stocks)
    from app.utils._data import fetch_palmares

    stocks = fetch_palmares(period="veille", progression="tout")
    if stocks:
        try:
            save_daily_snapshot(stocks)
        except Exception as e:
            logger.warning("Could not persist snapshot: %s", e)
    return _with_names(stocks)


# --- Scheduler hook -----------------------------------------------------------

def due_daily_refresh(now_utc: datetime | None = None) -> bool:
    """True once per weekday after 16:30 GMT (market closes ~15:00 GMT)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    snap_day = latest_snapshot_day()
    if snap_day == now_utc.date().isoformat():
        return False
    return (now_utc.hour, now_utc.minute) >= (16, 30)


async def scheduled_refresh_loop() -> None:
    """Background task: every 10 minutes, take the daily post-close snapshot
    when due. Runs in the API process (both run_api.py and main.py)."""
    import asyncio

    while True:
        await asyncio.sleep(600)
        try:
            if due_daily_refresh():
                await asyncio.to_thread(refresh_daily_snapshots)
                logger.info("Daily market snapshot refreshed after close.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Scheduled market refresh failed: %s", e)

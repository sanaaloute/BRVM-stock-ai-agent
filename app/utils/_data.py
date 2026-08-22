"""Data access: palmarès (Rich Bourse), time series CSV."""
from __future__ import annotations

import csv
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.scrapers.richbourse import RichBourseScraper
from app.scrapers.richbourse_timeseries import RichBourseTimeseriesScraper
from app.utils.cache import get_palmares_cache

logger = logging.getLogger(__name__)

DATA_SERIES_DIR = Path(__file__).resolve().parent.parent / "data" / "series"
MAX_AGE_DAYS = 1  # CSV considered stale if last date is older than this

# Silent scraper breakage detector: count consecutive refresh failures and
# escalate to ERROR (log-based alerting) after a few in a row.
_FAILURE_ALERT_THRESHOLD = 3
_consecutive_failures: dict[str, int] = {}
_failures_lock = threading.Lock()

# One refresh per cache key at a time: on TTL expiry, concurrent callers serve
# the current snapshot (stale-while-revalidate) instead of stampeding the source.
_refresh_locks: dict[str, threading.Lock] = {}
_refresh_locks_guard = threading.Lock()


def _get_refresh_lock(key: str) -> threading.Lock:
    with _refresh_locks_guard:
        lock = _refresh_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _refresh_locks[key] = lock
        return lock

_FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12, "decembre": 12,
}


def _parse_french_date(text: str) -> date | None:
    """Parse 'Vendredi 20 Février 2026' -> date(2026, 2, 20). None if not found."""
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûùàâêîôäëïüçÉÛÙÀÂÊÎÔÄËÏÜÇ]+)\s+(\d{4})", text or "")
    if not m:
        return None
    month = _FRENCH_MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def _note_refresh_success(key: str) -> None:
    with _failures_lock:
        _consecutive_failures[key] = 0


def _note_refresh_failure(key: str) -> None:
    with _failures_lock:
        n = _consecutive_failures.get(key, 0) + 1
        _consecutive_failures[key] = n
    if n >= _FAILURE_ALERT_THRESHOLD:
        logger.error(
            "Palmarès refresh failed (%s) %d times in a row — the scraper may be broken "
            "(site layout change or block). Serving stale data until it recovers.",
            key, n,
        )
    else:
        logger.warning("Palmarès refresh failed (%s) (%d/%d before alert)", key, n, _FAILURE_ALERT_THRESHOLD)


def fetch_palmares(period: str = "veille", progression: str = "tout", *, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch palmarès from Rich Bourse (cached).

    Returns list of stocks with symbol, cours_actuel, volume, variation_pct,
    capitalisation, etc. The page is scraped at most once per
    PALMARES_CACHE_TTL_SECONDS (default 300s). If a refresh fails or returns
    nothing, the last known good snapshot is served (stale-if-error) so the
    bot keeps answering during source outages.
    """
    cache = get_palmares_cache()
    key = f"{period}|{progression}"
    if not force_refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached
        # BRVM trades Mon–Fri: on Saturday/Sunday serve the cached snapshot
        # without re-scraping. Abidjan is GMT year-round (no DST), so the UTC
        # weekday is the market weekday.
        if datetime.now(timezone.utc).weekday() >= 5:
            stale = cache.get_stale(key)
            if stale is not None:
                logger.info("Serving cached palmarès (%s): BRVM closed (weekend)", key)
                return stale
    lock = _get_refresh_lock(key)
    if not lock.acquire(blocking=False):
        # A refresh is already in flight: serve the existing snapshot immediately.
        stale = cache.get_stale(key)
        if stale is not None:
            logger.debug("Palmarès refresh in flight (%s): serving current snapshot", key)
            return stale
        # Nothing cached yet (first run): wait for the in-flight refresh to finish.
        with lock:
            return cache.get(key) or cache.get_stale(key) or []
    try:
        # Re-check inside the lock: another thread may have just refreshed.
        if not force_refresh:
            cached = cache.get(key)
            if cached is not None:
                return cached
        stocks: list[dict[str, Any]] = []
        result: dict[str, Any] = {}
        try:
            scraper = RichBourseScraper(period=period, progression=progression)
            result = scraper.scrape() or {}
            if not result.get("error"):
                stocks = result.get("stocks") or []
        except Exception as e:
            logger.warning("Palmarès scrape raised (%s): %s", key, e)
        if stocks:
            _note_refresh_success(key)
            data_date = _parse_french_date(result.get("date") or "")
            if data_date:
                age_days = (date.today() - data_date).days
                if age_days > 4:
                    logger.warning("Palmarès (%s) data is %d days old (%s)", key, age_days, result.get("date"))
            cache.set(key, stocks)
            return stocks
        _note_refresh_failure(key)
        stale = cache.get_stale(key)
        if stale is not None:
            logger.info("Serving stale palmarès (%s): refresh failed or returned empty", key)
            return stale
        return []
    finally:
        lock.release()


def _find_series_csv(symbol: str) -> Path | None:
    symbol = symbol.strip().upper()
    if not DATA_SERIES_DIR.exists():
        return None
    candidates = list(DATA_SERIES_DIR.glob(f"{symbol}_*.csv"))
    if not candidates:
        return None
    # Filename: SYMBOL_YYYY-MM-DD_YYYY-MM-DD.csv — use last date (end_date)
    def end_date_from_path(p: Path) -> date:
        try:
            parts = p.stem.split("_")
            if len(parts) >= 3:
                return date.fromisoformat(parts[-1][:10])
        except ValueError:
            pass
        return date.min

    return max(candidates, key=end_date_from_path)


def get_series_status(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    out: dict[str, Any] = {"symbol": symbol, "path": None, "last_date": None, "up_to_date": False}
    p = _find_series_csv(symbol)
    if not p or not p.exists():
        return out
    out["path"] = str(p)
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    try:
        parts = p.stem.split("_")
        if len(parts) >= 3:
            out["last_date"] = parts[-1][:10]
            last_data_date = date.fromisoformat(out["last_date"])
            # Up-to-date if data extends to recent OR the file was refreshed
            # recently (avoids re-scraping every run).
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime).date()
            except OSError:
                mtime = date.min
            out["up_to_date"] = last_data_date >= cutoff or mtime >= cutoff
    except ValueError:
        pass
    return out


def ensure_series_csv(symbol: str) -> Path | None:
    p = _find_series_csv(symbol)
    if p is not None:
        return p
    scraper = RichBourseTimeseriesScraper(symbol=symbol, output_dir=DATA_SERIES_DIR)
    result = scraper.scrape()
    if result.get("error") or not result.get("csv_path"):
        return None
    return Path(result["csv_path"])


def ensure_timeseries_up_to_date(symbol: str) -> dict[str, Any]:
    status = get_series_status(symbol)
    if status["up_to_date"] and status["path"]:
        return {"symbol": symbol, "action": "skipped", "path": status["path"], "message": "Déjà à jour."}
    scraper = RichBourseTimeseriesScraper(symbol=symbol, output_dir=DATA_SERIES_DIR)
    result = scraper.scrape()
    if result.get("error"):
        return {"symbol": symbol, "action": "error", "error": result["error"]}
    return {
        "symbol": symbol,
        "action": "updated",
        "path": result.get("csv_path"),
        "rows": result.get("rows", 0),
        "date_range": result.get("date_range"),
    }


def list_series_status(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    if symbols:
        return [get_series_status(s) for s in symbols]
    if not DATA_SERIES_DIR.exists():
        return []
    seen: set[str] = set()
    statuses: list[dict[str, Any]] = []
    for p in DATA_SERIES_DIR.glob("*_*.csv"):
        sym = p.stem.split("_")[0].upper()
        if sym not in seen:
            seen.add(sym)
            statuses.append(get_series_status(sym))
    return statuses


def run_daily_timeseries_update(symbols: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        results.append(ensure_timeseries_up_to_date(symbol))
    return results


def load_price_on_or_before(symbol: str, d: date, lookback_days: int = 7) -> dict[str, Any] | None:
    """Most recent series row on or before date d.

    BRVM is closed on weekends and holidays, so an exact-date lookup often
    returns nothing. This looks back up to `lookback_days` and returns the
    last available trading day (row has keys: date, price, open, high, low, volume).
    """
    rows = load_series(
        symbol,
        start_date=d - timedelta(days=lookback_days),
        end_date=d,
        fetch_if_missing=True,
    )
    return rows[-1] if rows else None


def load_series(
    symbol: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    *,
    fetch_if_missing: bool = True,
) -> list[dict[str, Any]]:
    """Load series rows from the symbol's CSV, sorted by date, filtered to [start_date, end_date].

    Each row always has keys: date (datetime.date), price (float, = close), and
    open/high/low/volume (float or None when the CSV lacks those columns — legacy
    2-column files — or the cells are empty).
    """
    if fetch_if_missing:
        # Ensure CSV exists and is up-to-date before reading (scrape & save if stale)
        ensure_timeseries_up_to_date(symbol)
    p = _find_series_csv(symbol)
    if not p or not p.exists():
        return []

    def parse_dt(s: str) -> date:
        try:
            return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return date.min

    def parse_opt(s: str | None) -> float | None:
        # Optional numeric cell (Open/High/Low/Volume): None when the column is
        # absent (legacy CSV) or the cell is empty/unparseable.
        if not s:
            return None
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None

    rows: list[dict[str, Any]] = []
    with open(p, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            dt_str = row.get("Date", "")
            price_str = row.get("Price", "")
            if not dt_str or not price_str:
                continue
            d = parse_dt(dt_str)
            try:
                price = float(price_str.replace(",", "."))
            except ValueError:
                continue
            if start_date is not None and d < (start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date)[:10])):
                continue
            if end_date is not None and d > (end_date if isinstance(end_date, date) else date.fromisoformat(str(end_date)[:10])):
                continue
            rows.append({
                "date": d,
                "price": price,
                "open": parse_opt(row.get("Open")),
                "high": parse_opt(row.get("High")),
                "low": parse_opt(row.get("Low")),
                "volume": parse_opt(row.get("Volume")),
            })

    rows.sort(key=lambda r: r["date"])
    return rows

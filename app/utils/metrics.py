"""Service: average, median, and other stats for a stock over a period."""
from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from app.utils._data import load_series


def compute_metrics(
    symbol: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    *,
    fetch_if_missing: bool = True,
) -> dict[str, Any]:
    """
    Compute average, median, min, max, stdev, count for a stock over a date range.
    If no range given, uses full series in CSV.
    """
    symbol = (symbol or "").strip().upper()
    start = None
    end = None
    if start_date is not None:
        start = start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date)[:10])
    if end_date is not None:
        end = end_date if isinstance(end_date, date) else date.fromisoformat(str(end_date)[:10])

    rows = load_series(symbol, start_date=start, end_date=end, fetch_if_missing=fetch_if_missing)
    prices = [r["price"] for r in rows]

    out: dict[str, Any] = {
        "symbol": symbol,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "count": len(prices),
        "average": None,
        "median": None,
        "min": None,
        "max": None,
        "stdev": None,
    }

    if not prices:
        return out

    out["min"] = min(prices)
    out["max"] = max(prices)
    out["average"] = statistics.mean(prices)
    out["median"] = statistics.median(prices)
    if len(prices) >= 2:
        out["stdev"] = statistics.stdev(prices)
    return out

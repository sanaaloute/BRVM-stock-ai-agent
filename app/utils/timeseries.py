"""Service: time series for a stock over a date range (for charts)."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.utils._data import coerce_day, load_series


def get_timeseries(
    symbol: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    *,
    fetch_if_missing: bool = True,
) -> dict[str, Any]:
    """
    Get time series (date, price) for a symbol in the given range (full series
    when dates are omitted — LLM tools may send "None"/blank for them).
    Returns {"symbol", "start_date", "end_date", "points": [{"date": "YYYY-MM-DD", "price": float}, ...]}.
    """
    symbol = (symbol or "").strip().upper()
    start = coerce_day(start_date)
    end = coerce_day(end_date)

    rows = load_series(symbol, start_date=start, end_date=end, fetch_if_missing=fetch_if_missing)
    points = [{"date": r["date"].isoformat(), "price": r["price"]} for r in rows]

    return {
        "symbol": symbol,
        "start_date": points[0]["date"] if points else (start.isoformat() if start else None),
        "end_date": points[-1]["date"] if points else (end.isoformat() if end else None),
        "points": points,
    }

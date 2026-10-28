"""Service: time series for a stock over a date range (for charts)."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.utils._data import load_series


def get_timeseries(
    symbol: str,
    start_date: date | str,
    end_date: date | str,
    *,
    fetch_if_missing: bool = True,
) -> dict[str, Any]:
    """
    Get time series (date, price) for a symbol in the given range.
    Returns {"symbol", "start_date", "end_date", "points": [{"date": "YYYY-MM-DD", "price": float}, ...]}.
    """
    symbol = (symbol or "").strip().upper()
    start = start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date)[:10])
    end = end_date if isinstance(end_date, date) else date.fromisoformat(str(end_date)[:10])

    rows = load_series(symbol, start_date=start, end_date=end, fetch_if_missing=fetch_if_missing)
    points = [{"date": r["date"].isoformat(), "price": r["price"]} for r in rows]

    return {
        "symbol": symbol,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "points": points,
    }

"""Service: current or given-time price, volume, growth, loss for a stock."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.utils._data import fetch_palmares, load_price_on_or_before
from app.utils.brvm_companies import get_valid_symbols
from app.utils.market_hours import expected_data_date, market_note


def get_stock_metrics(
    symbol: str,
    at_time: date | datetime | str | None = None,
    *,
    period: str = "veille",
) -> dict[str, Any]:
    """
    Get price, volume, growth, loss for a stock.
    If at_time is None: current data from palmarès (Rich Bourse).
    If at_time is set: historical price from time series (volume/growth/loss may be N/A).
    """
    symbol = (symbol or "").strip().upper()
    out: dict[str, Any] = {
        "symbol": symbol,
        "price": None,
        "volume": None,
        "growth_pct": None,
        "loss_pct": None,
        "capitalisation": None,
        "at_time": None,
        "source": "palmares",
    }

    valid = get_valid_symbols()
    if symbol and symbol not in valid:
        out["error"] = f"{symbol} n'est pas un symbole BRVM coté. Cet assistant ne couvre que la BRVM (Bourse Régionale des Valeurs Mobilières)."
        return out

    if at_time is None:
        stocks = fetch_palmares(period=period, progression="tout")
        for s in stocks:
            if (s.get("symbol") or "").strip().upper() == symbol:
                out["price"] = s.get("cours_actuel")
                out["volume"] = s.get("volume")
                out["capitalisation"] = s.get("capitalisation")
                var = s.get("variation_pct")
                if var is not None:
                    out["growth_pct"] = var if var >= 0 else None
                    out["loss_pct"] = -var if var < 0 else None
                out["at_time"] = "current"
                break
        # BRVM timing: before the ~15:00 GMT close (and on weekends) sources
        # show the LAST close; the palmarès may even lack a price cell for a
        # symbol on those days. Fall back to the last close from the series.
        if out["price"] is None:
            row = load_price_on_or_before(symbol, date.today())
            if row:
                out["price"] = row["price"]
                out["price_date"] = row["date"].isoformat()
                out["source"] = "timeseries_last_close"
        # Always attach the timing semantics so the LLM phrases the answer
        # correctly (dernière clôture vs clôture du jour).
        out["market_note"] = market_note()
        out["data_as_of"] = expected_data_date().isoformat()
        return out

    # Historical: resolve date and look up in series
    if isinstance(at_time, datetime):
        d = at_time.date()
    elif isinstance(at_time, str):
        d = date.fromisoformat(at_time.strip()[:10])
    else:
        d = at_time
    out["at_time"] = d.isoformat()
    out["source"] = "timeseries"

    # Exact-date lookup fails on weekends/holidays: fall back to the most
    # recent trading day on or before the requested date.
    row = load_price_on_or_before(symbol, d)
    if row:
        out["price"] = row["price"]
        out["price_date"] = row["date"].isoformat()
    # Volume/growth/loss not in chart data
    return out

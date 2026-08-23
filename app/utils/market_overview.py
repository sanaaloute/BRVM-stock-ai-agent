"""BRVM market overview: top stocks by volume, top gainers, top losers. Only BRVM-listed symbols."""
from __future__ import annotations

from typing import Any

from app.utils._data import fetch_palmares
from app.utils.brvm_companies import get_valid_symbols, get_symbol_to_name, get_symbol_to_sector
from app.utils.market_hours import expected_data_date, market_note


def _filter_brvm(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only stocks whose symbol is in the official BRVM list."""
    valid = get_valid_symbols()
    return [s for s in stocks if (s.get("symbol") or "").strip().upper() in valid]


def get_brvm_market_overview(top_n: int = 10) -> dict[str, Any]:
    """
    Return BRVM market overview from palmarès: top stocks by volume, top gainers, top losers.
    Only includes symbols from the official BRVM list (data/BRVM_Companies.xlsx).
    Price rankings use cours_actuel when published, else cours_veille (last close:
    weekends and before the ~15:00 GMT closing), so they never come back empty on
    a closed market.
    """
    stocks = fetch_palmares(period="veille", progression="tout")
    brvm_only = _filter_brvm(stocks)
    symbol_to_name = get_symbol_to_name()
    symbol_to_sector = get_symbol_to_sector()

    def _enrich(s: dict[str, Any]) -> dict[str, Any]:
        sym = (s.get("symbol") or "").strip().upper()
        cours = s.get("cours_actuel")
        cours_veille = s.get("cours_veille")
        row = {
            "symbol": sym,
            "company_name": symbol_to_name.get(sym) or s.get("name") or sym,
            "volume": s.get("volume"),
            "cours_actuel": cours,
            # Effective ranked price: live quote when present, else last close.
            "price": cours if cours is not None else cours_veille,
            "variation_pct": s.get("variation_pct"),
            "capitalisation": s.get("capitalisation"),
        }
        sector = symbol_to_sector.get(sym)
        if sector:
            row["sector"] = sector
        return row

    enriched = [_enrich(s) for s in brvm_only]

    # Top by volume (descending; None volume last)
    by_volume = sorted(
        enriched,
        key=lambda x: (x["volume"] is None, -(x["volume"] or 0)),
    )[:top_n]

    # Highest prices (most expensive stocks) — by effective price descending
    highest_prices = sorted(
        [e for e in enriched if e.get("price") is not None],
        key=lambda x: -(x["price"] or 0),
    )[:top_n]

    # Lowest prices (cheapest stocks) — by effective price ascending, exclude zero
    lowest_prices = sorted(
        [e for e in enriched if e.get("price") is not None and (e["price"] or 0) > 0],
        key=lambda x: (x["price"] or 0),
    )[:top_n]

    # Top gainers (variation_pct descending, positive first)
    gainers = sorted(
        [e for e in enriched if e.get("variation_pct") is not None and e["variation_pct"] > 0],
        key=lambda x: -(x["variation_pct"] or 0),
    )[:top_n]

    # Top losers (variation_pct ascending, negative first)
    losers = sorted(
        [e for e in enriched if e.get("variation_pct") is not None and e["variation_pct"] < 0],
        key=lambda x: (x["variation_pct"] or 0),
    )[:top_n]

    return {
        "source": "BRVM palmarès (Rich Bourse)",
        "data_as_of": expected_data_date().isoformat(),
        "market_note": market_note(),
        "top_by_volume": by_volume,
        "highest_prices": highest_prices,
        "lowest_prices": lowest_prices,
        "top_gainers": gainers,
        "top_losers": losers,
        "total_brvm_stocks": len(enriched),
    }

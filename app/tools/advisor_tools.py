"""Investment-advice tools backed by the deterministic scoring engine.

app.services.scoring is imported lazily inside each function: the engine is
built in parallel and this module must import cleanly even when the service
module is not present yet. No URL fetching here — the engine reads local data.

Security: like portfolio_tools, the user identity is NEVER taken from the
model's tool arguments. It is injected server-side from the verified chat
context via RunnableConfig. The pydantic schemas expose no telegram_id field.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from app.utils import user_db
from app.utils.brvm_companies import get_valid_symbols
from .portfolio_tools import _current_telegram_id
from .schemas import (
    GetMarketRecommendationsInput,
    GetPortfolioAdviceInput,
    GetStockAdviceInput,
)

_NO_USER_CONTEXT = {
    "ok": False,
    "error": "Portfolio advice is only available from a registered chat account (not available in this context).",
}

# Raw metrics surfaced to the advisor agent when the engine exposes them
# (first match wins; technicals are checked before fundamentals).
_METRIC_KEYS = ("close", "rsi", "rsi14", "momentum", "momentum_3m", "per", "pe", "dividend_yield", "yield")


def _key_metrics(*dicts: Any) -> dict[str, Any]:
    """Pick the well-known raw metrics out of the engine's technicals/fundamentals."""
    out: dict[str, Any] = {}
    for d in dicts:
        if not isinstance(d, dict):
            continue
        lower = {str(k).lower(): v for k, v in d.items()}
        for key in _METRIC_KEYS:
            if key in lower and key not in out:
                out[key] = lower[key]
    return out


def _get_stock_advice(symbol: str, **kwargs: Any) -> str:
    """Score one BRVM symbol and return a compact advice payload."""
    sym = (symbol or "").strip().upper()
    if sym not in get_valid_symbols():
        return json.dumps({"error": f"Symbole inconnu : {symbol}. Utilisez un symbole BRVM valide."}, ensure_ascii=False)
    from app.services.scoring import score_symbol
    result = score_symbol(sym) or {}
    return json.dumps(
        {
            "symbol": sym,
            "company_name": result.get("company_name"),
            "score": result.get("score"),
            "signal": result.get("signal"),
            "reasons": (result.get("reasons") or [])[:5],
            "metrics": _key_metrics(result.get("technicals"), result.get("fundamentals")),
            "data_warnings": result.get("data_warnings") or [],
            "error": result.get("error"),
        },
        ensure_ascii=False,
        default=str,
    )


def _get_market_recommendations(top_n: int = 5, **kwargs: Any) -> str:
    """Rank all BRVM symbols and return the top buy / top sell candidates."""
    from app.services.scoring import score_all
    n = max(1, min(int(top_n or 5), 10))
    data = score_all() or {}
    ranked = [r for r in (data.get("ranked") or []) if r.get("score") is not None]

    def _brief(entry: dict) -> dict:
        return {
            "symbol": entry.get("symbol"),
            "company_name": entry.get("company_name"),
            "score": entry.get("score"),
            "signal": entry.get("signal"),
            "reasons": (entry.get("reasons") or [])[:2],
        }

    top_buys = [_brief(r) for r in ranked[:n]]
    buy_symbols = {b["symbol"] for b in top_buys}
    top_sells = [_brief(r) for r in reversed(ranked[-n:]) if r.get("symbol") not in buy_symbols]
    return json.dumps(
        {
            "as_of": data.get("as_of"),
            "top_buys": top_buys,
            "top_sells": top_sells,
            "insufficient_count": len(data.get("insufficient") or []),
        },
        ensure_ascii=False,
        default=str,
    )


def _get_portfolio_advice(*, config: RunnableConfig, **kwargs: Any) -> str:
    """Score each position of the verified user's portfolio."""
    tid = _current_telegram_id(config)
    if tid is None:
        return json.dumps(_NO_USER_CONTEXT)
    positions = user_db.portfolio_with_prices(tid)
    if not positions:
        return json.dumps(
            {"ok": True, "positions": [], "summary_hint": "Portefeuille vide : aucune position à analyser."},
            ensure_ascii=False,
        )
    from app.services.scoring import score_symbol
    advice = []
    for pos in positions:
        sym = (pos.get("symbol") or "").strip().upper()
        scored = score_symbol(sym) or {}
        reasons = scored.get("reasons") or []
        advice.append(
            {
                "symbol": sym,
                "company_name": scored.get("company_name"),
                "gain_loss_pct": pos.get("gain_loss_pct"),
                "score": scored.get("score"),
                "signal": scored.get("signal"),
                "top_reason": reasons[0] if reasons else None,
                "error": scored.get("error"),
            }
        )
    n_buy = sum(1 for a in advice if a.get("signal") in ("Achat", "Accumuler"))
    n_sell = sum(1 for a in advice if a.get("signal") == "Alléger")
    summary_hint = (
        f"{len(advice)} position(s) analysée(s) : {n_buy} en signal achat/accumulation, "
        f"{n_sell} en signal allègement."
    )
    return json.dumps(
        {"ok": True, "positions": advice, "summary_hint": summary_hint},
        ensure_ascii=False,
        default=str,
    )


get_stock_advice_tool = StructuredTool.from_function(
    func=_get_stock_advice,
    name="get_stock_advice",
    description="Get deterministic investment advice for one BRVM symbol: score (0-100), signal (Achat/Accumuler/Neutre/Alléger), main reasons and key metrics. Use for 'faut-il acheter/vendre X ?', 'avis sur X', 'garder ou vendre X ?'.",
    args_schema=GetStockAdviceInput,
)

get_market_recommendations_tool = StructuredTool.from_function(
    func=_get_market_recommendations,
    name="get_market_recommendations",
    description="Get market-wide BRVM recommendations: top buy candidates and top sell/reduce candidates with scores, signals and reasons. No symbol needed. Use for 'quelles actions acheter ?', 'top actions BRVM', 'quelles actions vendre/alléger ?'.",
    args_schema=GetMarketRecommendationsInput,
)

get_portfolio_advice_tool = StructuredTool.from_function(
    func=_get_portfolio_advice,
    name="get_portfolio_advice",
    description="Analyze the user's portfolio positions with the scoring engine: gain/loss %, score, signal and main reason per position. Use for 'conseil sur mon portefeuille', 'que penses-tu de mon portefeuille ?'.",
    args_schema=GetPortfolioAdviceInput,
)

ADVISOR_TOOLS = [
    get_stock_advice_tool,
    get_market_recommendations_tool,
    get_portfolio_advice_tool,
]

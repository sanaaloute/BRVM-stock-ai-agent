"""Daily post-close AI predictions ("prévisions") for every BRVM symbol.

Deterministic numbers, LLM only words the explanation: the direction and
confidence come from a confluence vote over the short-term signals already
computed by the scoring engine (trend vs MM20/MM50, momentum, RSI zone,
volume trend, Sika Finance technical consensus, composite score), and the
expected move from the 20-session daily volatility projected to a ~1 week
horizon. Rows are persisted in the ai_predictions table (one per symbol per
day) and served by the mobile API.

Every public function is total: bad or missing data yields an `error` string,
never an exception (same contract as app/services/scoring.py).
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import config
from app.models.llm import get_llm
from app.services import scoring
# Imported into this module's namespace on purpose: tests monkeypatch them here.
from app.utils._data import fetch_palmares, load_series
from app.utils import market_hours, user_db
from app.utils.brvm_companies import get_valid_symbols

logger = logging.getLogger(__name__)

DIRECTION_HAUSSE = "hausse"
DIRECTION_BAISSE = "baisse"
DIRECTION_NEUTRE = "neutre"

HORIZON_DAYS = 5  # ~1 trading week: daily vol projected with sqrt(5)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def _fmt_fr(x: float, decimals: int = 1) -> str:
    return f"{x:.{decimals}f}".replace(".", ",")


def _daily_volatility(closes: list[float], window: int = 20) -> float | None:
    """Std-dev of the last `window` daily returns (None when not enough data)."""
    if len(closes) < window + 1:
        return None
    rets = []
    for i in range(len(closes) - window, len(closes)):
        prev = closes[i - 1]
        rets.append(closes[i] / prev - 1.0 if prev > 0 else 0.0)
    return statistics.stdev(rets) if len(rets) >= 2 else None


def _current_price(symbol: str, closes: list[float]) -> float | None:
    """Last close, falling back to the palmarès snapshot."""
    if closes and closes[-1] > 0:
        return closes[-1]
    try:
        for row in fetch_palmares():
            if str(row.get("symbol", "")).strip().upper() == symbol:
                price = scoring._parse_fr_number(row.get("cours_actuel"))
                if price is not None and price > 0:
                    return price
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Confluence vote
# ---------------------------------------------------------------------------
def _votes(price: float, technicals: dict, score: float) -> list[dict]:
    """One vote per available short-term signal: +1 hausse, -1 baisse,
    0 neutre. Unavailable signals cast no vote."""
    votes: list[dict] = []

    def add(label: str, vote: int) -> None:
        votes.append({"label": label, "vote": vote})

    sma20 = technicals.get("sma20")
    if sma20:
        add("Cours vs MM20", 1 if price > sma20 else -1)
    sma50 = technicals.get("sma50")
    if sma50:
        add("Cours vs MM50", 1 if price > sma50 else -1)
    r63 = technicals.get("return_63d")
    if r63 is not None:
        add("Momentum 3 mois", 1 if r63 > 0 else (-1 if r63 < 0 else 0))
    rsi = technicals.get("rsi_14")
    if rsi is not None:
        if rsi >= 70:
            add("RSI 14 (surachat)", -1)
        elif rsi <= 30:
            add("RSI 14 (survente)", 1)
        else:
            add("RSI 14", 1 if rsi > 50 else -1)
    volume_ratio = technicals.get("volume_ratio")
    if volume_ratio is not None:
        add("Tendance des volumes",
            1 if volume_ratio >= 1.2 else (-1 if volume_ratio <= 0.8 else 0))
    cons_up = technicals.get("sika_consensus_up")
    cons_down = technicals.get("sika_consensus_down")
    if cons_up is not None and cons_down is not None:
        add("Consensus technique Sika Finance",
            1 if cons_up > cons_down else (-1 if cons_down > cons_up else 0))
    add("Score composite vs 50", 1 if score > 50 else (-1 if score < 50 else 0))
    return votes


def _direction_and_confidence(votes: list[dict]) -> tuple[str, int]:
    """Direction = sign of the vote sum; confidence = 50 + 45 x fraction of
    votes agreeing with it (capped at 95 — never a certainty)."""
    total = len(votes)
    if not total:
        return DIRECTION_NEUTRE, 50
    net = sum(v["vote"] for v in votes)
    if net > 0:
        direction = DIRECTION_HAUSSE
        agreeing = sum(1 for v in votes if v["vote"] > 0)
    elif net < 0:
        direction = DIRECTION_BAISSE
        agreeing = sum(1 for v in votes if v["vote"] < 0)
    else:
        direction = DIRECTION_NEUTRE
        agreeing = sum(1 for v in votes if v["vote"] == 0)
    confidence = min(95, round(50 + 45 * agreeing / total))
    return direction, confidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_prediction(symbol: str, *, per_median: Any = scoring._PER_MEDIAN_UNSET) -> dict[str, Any]:
    """Prediction for one symbol from the cached data (no live scrape).

    Returns the full prediction dict, or {"symbol", "error"} when the data is
    insufficient (same error contract as scoring.score_symbol). Never raises.
    """
    sym = (symbol or "").strip().upper()
    base = scoring.score_symbol(sym, _fetch_if_missing=False, _per_median=per_median)
    if base.get("score") is None:
        return {"symbol": sym, "error": base.get("error") or "Score indisponible."}

    try:
        rows = load_series(sym, fetch_if_missing=False)
    except Exception as e:
        logger.debug("load_series failed for %s: %s", sym, e)
        rows = []
    closes = [float(r["price"]) for r in (rows or []) if r.get("price") is not None]
    price = _current_price(sym, closes)
    if price is None:
        return {"symbol": sym, "error": "Cours indisponible pour la prévision."}

    technicals = base.get("technicals") or {}
    score = float(base["score"])
    votes = _votes(price, technicals, score)
    direction, confidence = _direction_and_confidence(votes)

    daily_vol = _daily_volatility(closes)
    move = daily_vol * math.sqrt(HORIZON_DAYS) if daily_vol is not None else None
    return {
        "symbol": sym,
        "company_name": base.get("company_name"),
        "price": round(price, 2),
        "direction": direction,
        "confidence_pct": confidence,
        "expected_move_pct": round(move * 100, 1) if move is not None else None,
        "target_low": round(price * (1 - move), 2) if move is not None else None,
        "target_high": round(price * (1 + move), 2) if move is not None else None,
        "score": score,
        "signal": base.get("signal"),
        "reasons": base.get("reasons") or [],
        "data_warnings": base.get("data_warnings") or [],
        "technicals": technicals,
        "fundamentals": base.get("fundamentals") or {},
        "votes": votes,
        "explanation": "",
        "error": None,
    }


def _fallback_explanation(pred: dict) -> str:
    """Deterministic French explanation from the computed metrics (no LLM)."""
    tendency = {
        DIRECTION_HAUSSE: "une tendance haussière",
        DIRECTION_BAISSE: "une tendance baissière",
        DIRECTION_NEUTRE: "une tendance neutre",
    }.get(pred.get("direction"), "une tendance neutre")
    lines = [
        f"{pred.get('symbol')} : les indicateurs court terme suggèrent {tendency} "
        f"à horizon d'environ une semaine (confiance {pred.get('confidence_pct')} %).",
    ]
    if pred.get("score") is not None:
        lines.append(
            f"Score composite : {_fmt_fr(float(pred['score']))}/100 "
            f"({pred.get('signal') or '—'})."
        )
    reasons = pred.get("reasons") or []
    if reasons:
        lines.append("Facteurs clés : " + " ; ".join(reasons[:3]) + ".")
    if pred.get("expected_move_pct") is not None and pred.get("target_low") is not None:
        lines.append(
            f"Amplitude attendue : ±{_fmt_fr(float(pred['expected_move_pct']))} % "
            f"(zone {_fmt_fr(float(pred['target_low']), 0)} - "
            f"{_fmt_fr(float(pred['target_high']), 0)} FCFA)."
        )
    lines.append("Prévision indicative — pas un conseil en investissement.")
    return "\n".join(lines)


def _explanation_prompt(pred: dict) -> str:
    """Metrics payload + strict grounding instruction (the LLM only words the
    explanation; it must not invent any number — same stance as the agent
    graph's _GROUNDING_SUFFIX)."""
    try:
        note = market_hours.market_note()
    except Exception:
        note = ""
    payload = {
        "symbole": pred.get("symbol"),
        "societe": pred.get("company_name"),
        "cours_fcfa": pred.get("price"),
        "direction": pred.get("direction"),
        "confiance_pct": pred.get("confidence_pct"),
        "amplitude_attendue_pct": pred.get("expected_move_pct"),
        "cible_basse_fcfa": pred.get("target_low"),
        "cible_haute_fcfa": pred.get("target_high"),
        "score_sur_100": pred.get("score"),
        "signal": pred.get("signal"),
        "raisons": pred.get("reasons") or [],
        "indicateurs_techniques": pred.get("technicals") or {},
        "fondamentaux": pred.get("fundamentals") or {},
        "avertissements_donnees": pred.get("data_warnings") or [],
        "contexte_marche": note,
    }
    return (
        "Tu es un analyste financier de la BRVM. Rédige en français une "
        "prévision courte (4 à 8 lignes) pour cette action, à horizon d'environ "
        "une semaine : justifie la tendance annoncée, cite les supports et "
        "risques clés, et termine par un rappel qu'il s'agit d'une prévision "
        "indicative et non d'un conseil en investissement.\n"
        "N'invente AUCUN chiffre : chaque nombre, cours, score ou pourcentage "
        "cité DOIT provenir des données ci-dessous. Si une donnée manque, ne la "
        "mentionne pas. N'invente pas non plus le nom de la société.\n"
        "Données :\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def explain_with_llm(pred: dict) -> str:
    """LLM-worded French explanation of one prediction. One LLM call; any
    failure (provider down, timeout, empty answer) falls back to the
    deterministic explanation."""
    try:
        resp = get_llm().invoke(_explanation_prompt(pred))
        text = str(getattr(resp, "content", resp) or "").strip()
        if not text:
            raise ValueError("empty LLM response")
        return text
    except Exception as e:
        logger.warning("LLM explanation failed for %s (%s): using fallback",
                       pred.get("symbol"), e)
        return _fallback_explanation(pred)


def _details_payload(pred: dict) -> dict:
    """details_json payload: full metrics + votes for the app detail view."""
    return {
        "reasons": pred.get("reasons") or [],
        "data_warnings": pred.get("data_warnings") or [],
        "technicals": pred.get("technicals") or {},
        "fundamentals": pred.get("fundamentals") or {},
        "votes": pred.get("votes") or [],
    }


def run_daily_predictions(symbols: list[str] | None = None) -> dict[str, Any]:
    """Job body: compute and persist today's prediction for every symbol
    (default: all valid BRVM symbols). Reads only the local caches (the daily
    refresh job pre-warms them) and computes the market PER median once.
    Never raises; returns {"day", "count", "errors"}."""
    if not getattr(config, "PREDICTIONS_ENABLED", True):
        logger.info("Predictions disabled (PREDICTIONS_ENABLED): skipping run")
        return {"day": None, "count": 0, "errors": 0}
    if symbols is None:
        try:
            symbols = sorted(get_valid_symbols())
        except Exception:
            symbols = []
    try:
        per_median = scoring._market_per_median()
    except Exception as e:
        logger.warning("Predictions: market PER median unavailable: %s", e)
        per_median = None
    day = datetime.now(timezone.utc).date().isoformat()

    preds: list[dict] = []
    errors = 0
    for sym in symbols:
        try:
            pred = compute_prediction(sym, per_median=per_median)
        except Exception as e:
            logger.warning("Prediction failed for %s: %s", sym, e)
            errors += 1
            continue
        if not pred or pred.get("error"):
            errors += 1
            continue
        preds.append(pred)

    if getattr(config, "PREDICTIONS_LLM_ENABLED", True) and preds:
        workers = max(1, int(getattr(config, "PREDICTIONS_LLM_CONCURRENCY", 3) or 3))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            explanations = list(pool.map(explain_with_llm, preds))
        for pred, text in zip(preds, explanations):
            pred["explanation"] = text
    else:
        for pred in preds:
            pred["explanation"] = _fallback_explanation(pred)

    rows = [{
        "symbol": p["symbol"],
        "day": day,
        "direction": p.get("direction"),
        "confidence_pct": p.get("confidence_pct"),
        "expected_move_pct": p.get("expected_move_pct"),
        "price": p.get("price"),
        "target_low": p.get("target_low"),
        "target_high": p.get("target_high"),
        "score": p.get("score"),
        "signal": p.get("signal"),
        "explanation": p.get("explanation") or "",
        "details_json": json.dumps(_details_payload(p), ensure_ascii=False),
    } for p in preds]
    try:
        user_db.save_predictions(rows)
    except Exception as e:
        logger.exception("Predictions: could not persist rows: %s", e)
    logger.info("Predictions for %s: %d computed, %d errors", day, len(preds), errors)
    return {"day": day, "count": len(preds), "errors": errors}


def predictions_due(now_utc: datetime | None = None) -> bool:
    """True once per weekday after 16:30 GMT (market closes ~15:00 GMT), until
    today's predictions are computed (same gate as due_daily_refresh)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    if user_db.get_latest_prediction_day() == now_utc.date().isoformat():
        return False
    return (now_utc.hour, now_utc.minute) >= (16, 30)

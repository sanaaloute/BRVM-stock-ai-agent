"""Deterministic BRVM stock scoring engine ("which stock to buy / cash out").

Pure Python, no LLM calls, no network access of its own: it only reads the
local data loaders (price-series CSV cache, Sika Finance company-details JSON
cache, Rich Bourse palmarès snapshot). Every public function is total: bad or
missing data yields an `error` string and/or French `data_warnings`, never an
exception.

Score = TECHNICAL_WEIGHT * technical block (0-100)
      + FUNDAMENTAL_WEIGHT * fundamental block (0-100),
mapped to a French signal: Achat / Accumuler / Neutre / Alléger.
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import date
from typing import Any

import config
# Imported into this module's namespace on purpose: tests monkeypatch them here.
from app.scrapers.sikafinance_company import load_company_details
from app.utils._data import fetch_palmares, load_series
from app.utils.brvm_companies import get_symbol_to_name, get_valid_symbols

logger = logging.getLogger(__name__)

# Tunables (overridable via config.SCORING_* without code change).
TECHNICAL_WEIGHT = getattr(config, "SCORING_TECHNICAL_WEIGHT", 0.6)
FUNDAMENTAL_WEIGHT = getattr(config, "SCORING_FUNDAMENTAL_WEIGHT", 0.4)

MIN_HISTORY_ROWS = 60  # fewer price rows -> insufficient-data error, no score

SIGNAL_BUY = "Achat"
SIGNAL_ACCUMULATE = "Accumuler"
SIGNAL_NEUTRAL = "Neutre"
SIGNAL_REDUCE = "Alléger"

# Sentinel for the optional per-call overrides below: "not supplied" (compute
# lazily, the default single-symbol behavior). Distinct from None, which is a
# real computed value ("no market median available").
_PER_MEDIAN_UNSET: Any = object()


def signal_for_score(score: float | None) -> str:
    """Map a 0-100 score to a French signal label."""
    if score is None:
        return SIGNAL_NEUTRAL
    if score >= 70:
        return SIGNAL_BUY
    if score >= 55:
        return SIGNAL_ACCUMULATE
    if score >= 40:
        return SIGNAL_NEUTRAL
    return SIGNAL_REDUCE


# ---------------------------------------------------------------------------
# Parsing / math helpers
# ---------------------------------------------------------------------------
def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _parse_fr_number(value: Any) -> float | None:
    """Parse a French-formatted number ("32 348", "1 234,56", NBSP variants).

    Spaces/NBSP are thousands separators, comma is the decimal separator.
    Returns None for empty/unparseable input instead of raising.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\xa0", " ").replace("\u202f", " ")
    s = s.replace(" ", "").replace(",", ".").rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(value: Any) -> int:
    """int() that never raises (Sika consensus counts); 0 on bad input."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder RSI on closes. None when fewer than period+1 closes."""
    if len(closes) < period + 1:
        return None
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        avg_gain += max(d, 0.0) / period
        avg_loss += max(-d, 0.0) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _return_over(closes: list[float], n: int) -> float | None:
    """Simple return over the last n sessions. None when not enough data."""
    if len(closes) < n + 1:
        return None
    base = closes[-1 - n]
    if base <= 0:
        return None
    return closes[-1] / base - 1.0


def _max_drawdown(closes: list[float]) -> float:
    """Max peak-to-trough decline (positive fraction) over the given closes."""
    peak = None
    max_dd = 0.0
    for c in closes:
        if c <= 0:
            continue
        if peak is None or c > peak:
            peak = c
        dd = (peak - c) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _metric_series(perf: dict, metric: str) -> list[tuple[int, float]]:
    """Parsed (year, value) pairs of a performance metric, oldest first."""
    series = (perf or {}).get(metric) or {}
    out: list[tuple[int, float]] = []
    for year, raw in series.items():
        try:
            y = int(str(year).strip())
        except (TypeError, ValueError):
            continue
        val = _parse_fr_number(raw)
        if val is not None:
            out.append((y, val))
    out.sort(key=lambda t: t[0])
    return out


def _latest_metric(perf: dict, metric: str) -> float | None:
    vals = _metric_series(perf, metric)
    return vals[-1][1] if vals else None


def _dividend_history(market: Any) -> list[tuple[int, float, float]]:
    """(year, montant, rendement_pct) triples from Sika's dividend history,
    oldest first. Entries missing montant or rendement are dropped."""
    entries = market.get("dividend_history") if isinstance(market, dict) else None
    if not isinstance(entries, list):
        return []
    out: list[tuple[int, float, float]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            year = int(entry.get("year"))
        except (TypeError, ValueError):
            continue
        montant = _parse_fr_number(entry.get("montant"))
        rendement = _parse_fr_number(entry.get("rendement_pct"))
        if montant is None or rendement is None:
            continue
        out.append((year, montant, rendement))
    out.sort(key=lambda t: t[0])
    return out


def _growth_fraction(perf: dict, growth_key: str, level_key: str) -> float | None:
    """Latest growth as a fraction (0.16 = +16%).

    Reads the growth metric directly (French percent string like "16,08");
    falls back to YoY computed from the level series (e.g. resultat_net).
    """
    raw = _latest_metric(perf, growth_key)
    if raw is not None:
        return raw / 100.0
    vals = _metric_series(perf, level_key)
    if len(vals) >= 2 and vals[-2][1] != 0:
        return (vals[-1][1] - vals[-2][1]) / abs(vals[-2][1])
    return None


def _market_per_median() -> float | None:
    """Median PER across ALL cached company details (None when unavailable)."""
    try:
        symbols = get_valid_symbols()
    except Exception:
        symbols = []
    pers: list[float] = []
    for sym in symbols:
        try:
            details = load_company_details(sym)
        except Exception:
            continue
        per = _latest_metric((details or {}).get("performance") or {}, "per")
        if per is not None and per > 0:
            pers.append(per)
    if not pers:
        return None
    return statistics.median(pers)


def _current_price(symbol: str, closes: list[float]) -> float | None:
    """Last close, falling back to the palmarès snapshot."""
    if closes and closes[-1] > 0:
        return closes[-1]
    try:
        for row in fetch_palmares():
            if str(row.get("symbol", "")).strip().upper() == symbol:
                price = _parse_fr_number(row.get("cours_actuel"))
                if price is not None and price > 0:
                    return price
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Subscore blocks
# ---------------------------------------------------------------------------
def _beta_points(beta: float) -> float:
    """Beta (1 an) subscore 0-2: <= 0.8 -> 2 pts, >= 1.5 -> 0, linear between."""
    if beta <= 0.8:
        return 2.0
    if beta >= 1.5:
        return 0.0
    return 2.0 * (1.5 - beta) / 0.7


def _compute_technicals(
    symbol: str,
    rows: list[dict],
    closes: list[float],
) -> tuple[dict, list[str]]:
    """Technical block (0-100) + French data warnings."""
    warnings: list[str] = []
    price = closes[-1]
    try:
        details = load_company_details(symbol)
    except Exception:
        details = None
    market = (details or {}).get("market")
    if not isinstance(market, dict):
        market = {}

    # --- Trend (0-30): SMA20/50/200 alignment + price position (6 pts each) ---
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    checks: list[bool] = []
    if sma50 is not None:
        checks.append(price > sma50)
    if sma200 is not None:
        checks.append(price > sma200)
    if sma20 is not None and sma50 is not None:
        checks.append(sma20 > sma50)
    if sma50 is not None and sma200 is not None:
        checks.append(sma50 > sma200)
    if sma50 is not None and len(closes) >= 60:
        # SMA50 rising: compare with its value 10 sessions ago.
        checks.append(sma50 > sum(closes[-60:-10]) / 50)
    if sma200 is None:
        warnings.append("Historique limité (< 200 séances) : MM200 non prise en compte")
    trend = 30.0 * sum(1 for c in checks if c) / len(checks) if checks else 0.0

    # --- Momentum (0-25): blended 63d/126d/252d returns ---
    r63 = _return_over(closes, 63)
    r126 = _return_over(closes, 126)
    r252 = _return_over(closes, 252)
    available = [(w, r) for w, r in ((0.5, r63), (0.3, r126), (0.2, r252)) if r is not None]
    if available:
        wsum = sum(w for w, _ in available)
        blend = sum(w * r for w, r in available) / wsum
        # blend <= -20% -> 0 pts, >= +30% -> 25 pts, linear between.
        momentum = _clamp((blend + 0.20) / 0.50) * 25.0
    else:
        momentum = 12.5
        blend = None
        warnings.append("Historique limité : momentum indisponible")

    # --- RSI(14) (0-20): sweet spot 45-65 ---
    rsi_val = _rsi(closes, 14)
    if rsi_val is None:
        rsi_pts = 10.0
        warnings.append("RSI indisponible")
    elif 45 <= rsi_val <= 65:
        rsi_pts = 20.0
    elif 35 <= rsi_val < 45 or 65 < rsi_val <= 70:
        rsi_pts = 14.0
    elif 25 <= rsi_val < 35:
        rsi_pts = 8.0
    elif rsi_val > 70:
        rsi_pts = 6.0  # surachat
    else:
        rsi_pts = 4.0  # < 25

    # --- Risk (0-15): 20d annualized volatility (8) + 12m max drawdown (7) ---
    rets = []
    for i in range(len(closes) - 20, len(closes)):
        prev = closes[i - 1]
        rets.append(closes[i] / prev - 1.0 if prev > 0 else 0.0)
    vol = statistics.stdev(rets) * math.sqrt(252) if len(rets) >= 2 else None
    if vol is None:
        vol_pts = 4.0
    elif vol <= 0.15:
        vol_pts = 8.0
    elif vol >= 0.60:
        vol_pts = 0.0
    else:
        vol_pts = 8.0 * (0.60 - vol) / 0.45
    dd = _max_drawdown(closes[-252:])
    if dd <= 0.10:
        dd_pts = 7.0
    elif dd >= 0.50:
        dd_pts = 0.0
    else:
        dd_pts = 7.0 * (0.50 - dd) / 0.40
    risk = vol_pts + dd_pts
    # Sika Finance beta (1 an): when a positive beta is available, rebalance
    # risk to vol (0-7) + drawdown (0-6) + beta (0-2). Absent/invalid beta
    # keeps the legacy 8/7 split untouched.
    beta_val = _parse_fr_number(market.get("beta_1an"))
    if beta_val is not None and beta_val <= 0:
        beta_val = None
    if beta_val is not None:
        vol_pts = vol_pts * 7.0 / 8.0
        dd_pts = dd_pts * 6.0 / 7.0
        risk = vol_pts + dd_pts + _beta_points(beta_val)

    # --- Volume trend (0-10): avg volume last 20 sessions vs previous 40 ---
    vols = [float(r["volume"]) for r in rows if r.get("volume") is not None]
    volume_pts = None
    volume_ratio = None
    if len(vols) >= 40:
        recent_avg = sum(vols[-20:]) / 20
        prior = vols[-60:-20]
        prior_avg = sum(prior) / len(prior) if prior else 0.0
        if prior_avg > 0:
            volume_ratio = recent_avg / prior_avg
            if volume_ratio >= 1.2:
                volume_pts = 10.0
            elif volume_ratio >= 0.9:
                volume_pts = 6.0
            else:
                volume_pts = 3.0
        else:
            volume_pts = 6.0  # zero prior volume: neutral-ish, avoid div by 0
    # Sika Finance technical consensus: max(-2, min(2, up - down)) * 2 points
    # (so -4..+4) added to the block, only when >= 3 signals are available.
    ta = (details or {}).get("technical_analysis")
    ta_present = isinstance(ta, dict) and bool(ta)
    cons_up = cons_down = cons_neutral = 0
    cons_adj = 0
    if ta_present:
        cons_up = _safe_int(ta.get("up"))
        cons_down = _safe_int(ta.get("down"))
        cons_neutral = _safe_int(ta.get("neutral"))
        signals = ta.get("signals")
        if isinstance(signals, list) and len(signals) >= 3:
            cons_adj = max(-2, min(2, cons_up - cons_down)) * 2

    if volume_pts is None:
        # No usable volume data: rescale the other subscores to keep 0-100.
        warnings.append("Volumes indisponibles")
        block = (trend + momentum + rsi_pts + risk) / 90.0 * 100.0
    else:
        block = trend + momentum + rsi_pts + risk + volume_pts
    block = _clamp(block + cons_adj, 0.0, 100.0)

    technicals = {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "rsi": round(rsi_pts, 2),
        "risk": round(risk, 2),
        "volume": round(volume_pts, 2) if volume_pts is not None else None,
        "block": round(block, 2),
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma50": round(sma50, 2) if sma50 is not None else None,
        "sma200": round(sma200, 2) if sma200 is not None else None,
        "rsi_14": round(rsi_val, 2) if rsi_val is not None else None,
        "return_63d": round(r63, 4) if r63 is not None else None,
        "return_126d": round(r126, 4) if r126 is not None else None,
        "return_252d": round(r252, 4) if r252 is not None else None,
        "momentum_blend": round(blend, 4) if blend is not None else None,
        "volatility_20d": round(vol, 4) if vol is not None else None,
        "max_drawdown_1y": round(dd, 4),
        "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
    }
    if beta_val is not None:
        technicals["beta_1an"] = round(beta_val, 2)
    if ta_present:
        technicals["sika_consensus_up"] = cons_up
        technicals["sika_consensus_down"] = cons_down
        technicals["sika_consensus_neutral"] = cons_neutral
        technicals["sika_consensus_adj"] = cons_adj
    return technicals, warnings


def _compute_fundamentals(
    symbol: str,
    price: float | None,
    per_median: Any = _PER_MEDIAN_UNSET,
) -> tuple[dict, list[str]]:
    """Fundamental block (0-100) + French data warnings.

    `per_median`: batch callers (score_all) pass the market PER median computed
    once for the whole run; the default recomputes it lazily when needed.
    """
    warnings: list[str] = []
    try:
        details = load_company_details(symbol)
    except Exception:
        details = None
    perf = (details or {}).get("performance") or {}

    # --- Growth (0-40): résultat net (20) + chiffre d'affaires (20) ---
    g_rn = _growth_fraction(perf, "croissance_rn", "resultat_net")
    g_ca = _growth_fraction(perf, "croissance_ca", "chiffre_affaires")
    if g_rn is None:
        rn_pts = 10.0
        warnings.append("Résultat net indisponible")
    else:
        # <= -10% -> 0, >= +15% -> 20, linear between.
        rn_pts = _clamp((g_rn + 0.10) / 0.25) * 20.0
    if g_ca is None:
        ca_pts = 10.0
        warnings.append("Chiffre d'affaires indisponible")
    else:
        ca_pts = _clamp((g_ca + 0.10) / 0.25) * 20.0
    growth = rn_pts + ca_pts

    # --- Valuation (0-35): PER vs BRVM median PER ---
    per = _latest_metric(perf, "per")
    median = None
    if per is None or per <= 0:
        valuation = 17.5
        warnings.append("PER indisponible")
    else:
        median = _market_per_median() if per_median is _PER_MEDIAN_UNSET else per_median
        if median is None or median <= 0:
            valuation = 17.5
            warnings.append("Médiane PER du marché indisponible")
        else:
            # per <= 0.5*median -> 35, per >= 2*median -> 0, linear between.
            valuation = _clamp((2.0 * median - per) / (1.5 * median)) * 35.0

    # --- Dividend (0-25): 5-year average yield when Sika's dividend history
    # has >= 3 yearly entries, else single-year yield = dividende / price ---
    div = _latest_metric(perf, "dividende")
    div_yield = None
    div_yield_avg = None
    div_years = 0
    div_never_cut = False
    div_history = _dividend_history((details or {}).get("market"))
    if len(div_history) >= 3:
        # Same 0% -> 5 / >= 6% -> 25 mapping on the average rendement_pct,
        # plus a consistency modifier on the montant: +3 when never cut,
        # -3 when cut at least twice.
        avg_pct = sum(h[2] for h in div_history) / len(div_history)
        base = 5.0 + _clamp((avg_pct / 100.0) / 0.06) * 20.0
        cuts = sum(
            1 for i in range(1, len(div_history))
            if div_history[i][1] < div_history[i - 1][1]
        )
        modifier = 3.0 if cuts == 0 else (-3.0 if cuts >= 2 else 0.0)
        dividend_pts = _clamp(base + modifier, 0.0, 25.0)
        div_yield_avg = avg_pct / 100.0
        div_years = len(div_history)
        div_never_cut = cuts == 0
    elif div is None:
        dividend_pts = 12.5
        warnings.append("Dividende indisponible")
    elif price is None or price <= 0:
        dividend_pts = 12.5
        warnings.append("Cours indisponible pour le rendement du dividende")
    else:
        div_yield = max(div, 0.0) / price
        # 0% -> 5 pts, >= 6% -> 25 pts, linear between.
        dividend_pts = 5.0 + _clamp(div_yield / 0.06) * 20.0

    fundamentals = {
        "growth": round(growth, 2),
        "valuation": round(valuation, 2),
        "dividend": round(dividend_pts, 2),
        "block": round(growth + valuation + dividend_pts, 2),
        "croissance_rn": round(g_rn, 4) if g_rn is not None else None,
        "croissance_ca": round(g_ca, 4) if g_ca is not None else None,
        "per": per,
        "per_median": median,
        "dividende": div,
        "dividend_yield": round(div_yield, 4) if div_yield is not None else None,
    }
    if div_yield_avg is not None:
        fundamentals["dividend_yield_avg_5y"] = round(div_yield_avg, 4)
        fundamentals["dividend_history_years"] = div_years
        fundamentals["dividend_never_cut"] = div_never_cut
    return fundamentals, warnings


# ---------------------------------------------------------------------------
# Reasons (French, plain language)
# ---------------------------------------------------------------------------
def _fmt_fr(x: float, decimals: int = 1) -> str:
    return f"{x:.{decimals}f}".replace(".", ",")


def _fmt_pct_signed(ratio: float) -> str:
    return f"{ratio * 100:+.1f}".replace(".", ",") + " %"


def _build_reasons(technicals: dict, fundamentals: dict) -> list[str]:
    """Most influential first: order by absolute deviation from each
    component's neutral (mid-band) value. Max 6 reasons."""
    candidates: list[tuple[float, str]] = []

    def add(dev: float, text: str) -> None:
        candidates.append((abs(dev), text))

    sma50 = technicals.get("sma50")
    sma200 = technicals.get("sma200")
    trend = technicals["trend"]
    if sma50 is not None and sma200 is not None:
        if trend >= 24:
            add(trend - 15.0, "Tendance haussière : cours au-dessus des MM50 et MM200")
        elif trend <= 6:
            add(trend - 15.0, "Tendance baissière : cours sous les MM50 et MM200")
    elif sma50 is not None:
        if trend >= 20:
            add(trend - 15.0, "Tendance haussière : cours au-dessus de la MM50")
        elif trend <= 5:
            add(trend - 15.0, "Tendance baissière : cours sous la MM50")

    r126 = technicals.get("return_126d")
    r63 = technicals.get("return_63d")
    r252 = technicals.get("return_252d")
    momentum = technicals["momentum"]
    shown = None
    for label, r in (("6 mois", r126), ("3 mois", r63), ("12 mois", r252)):
        if r is not None and abs(r) >= 0.02:
            add(momentum - 12.5, f"Momentum {label} : {_fmt_pct_signed(r)}")
            shown = label
            break
    if r63 is not None and r63 <= -0.10 and shown != "3 mois":
        add(momentum - 12.5, f"Forte baisse récente : {_fmt_pct_signed(r63)} sur 3 mois")

    rsi_val = technicals.get("rsi_14")
    if rsi_val is not None:
        if rsi_val > 70:
            add(technicals["rsi"] - 10.0, f"RSI {rsi_val:.0f} : surachat, prudence")
        elif rsi_val < 25:
            add(technicals["rsi"] - 10.0, f"RSI {rsi_val:.0f} : survendu")

    g_rn = fundamentals.get("croissance_rn")
    if g_rn is not None:
        if g_rn >= 0.15:
            add(fundamentals["growth"] - 20.0, f"Croissance du résultat net : {_fmt_pct_signed(g_rn)}")
        elif g_rn <= -0.10:
            add(fundamentals["growth"] - 20.0, f"Résultat net en baisse : {_fmt_pct_signed(g_rn)}")

    per = fundamentals.get("per")
    median = fundamentals.get("per_median")
    if per and median and median > 0:
        if per < median:
            add(fundamentals["valuation"] - 17.5,
                f"PER {_fmt_fr(per)} inférieur à la médiane BRVM {_fmt_fr(median)}")
        elif per > 1.3 * median:
            add(fundamentals["valuation"] - 17.5,
                f"PER {_fmt_fr(per)} supérieur à la médiane BRVM {_fmt_fr(median)}")

    div = fundamentals.get("dividende")
    div_yield = fundamentals.get("dividend_yield")
    div_yield_avg = fundamentals.get("dividend_yield_avg_5y")
    if div_yield_avg is not None:
        years = fundamentals.get("dividend_history_years") or 5
        text = f"Rendement moyen du dividende sur {years} ans : {_fmt_fr(div_yield_avg * 100)} %"
        if fundamentals.get("dividend_never_cut"):
            text += f", dividende jamais baissé depuis {years} ans"
        add(fundamentals["dividend"] - 12.5, text)
    elif div is not None and div <= 0:
        add(fundamentals["dividend"] - 12.5, "Pas de dividende")
    elif div_yield is not None and div_yield >= 0.005:
        add(fundamentals["dividend"] - 12.5,
            f"Rendement du dividende : {_fmt_fr(div_yield * 100)} %")

    vol = technicals.get("volatility_20d")
    if vol is not None and vol >= 0.40:
        add(technicals["risk"] - 7.5, f"Volatilité élevée : {vol * 100:.0f} % annualisée")
    dd = technicals.get("max_drawdown_1y")
    if dd is not None and dd >= 0.30:
        add(technicals["risk"] - 7.5, f"Drawdown important : -{dd * 100:.0f} % sur 12 mois")

    beta = technicals.get("beta_1an")
    if beta is not None and beta > 0:
        if beta <= 0.8:
            sensitivity = "faible sensibilité au marché"
        elif beta >= 1.2:
            sensitivity = "sensibilité élevée au marché"
        else:
            sensitivity = "sensibilité moyenne au marché"
        add(_beta_points(beta) - 1.0, f"Bêta 1 an : {_fmt_fr(beta, 2)} ({sensitivity})")

    cons_adj = technicals.get("sika_consensus_adj")
    if cons_adj:
        add(float(cons_adj),
            f"Analyse technique Sika Finance : "
            f"{technicals.get('sika_consensus_up') or 0} signaux haussiers, "
            f"{technicals.get('sika_consensus_down') or 0} baissiers")

    # Stable sort: biggest absolute contribution first, insertion order on ties.
    candidates.sort(key=lambda t: -t[0])
    return [text for _, text in candidates[:6]]


def _sector_context(symbol: str) -> str | None:
    """Informational sector-rank line from Sika's peer table (None when the
    symbol or its peers have no usable YTD variation). No score impact."""
    try:
        details = load_company_details(symbol)
    except Exception:
        return None
    sector = (details or {}).get("sector")
    if not isinstance(sector, dict):
        return None
    peers = sector.get("peers")
    if not isinstance(peers, list):
        return None
    self_ytd = None
    ytds: list[float] = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        ytd = _parse_fr_number(peer.get("variation_ytd_pct"))
        if str(peer.get("symbol") or "").strip().upper() == symbol:
            self_ytd = ytd
        if ytd is not None:
            ytds.append(ytd)
    if self_ytd is None or not ytds:
        return None
    rank = 1 + sum(1 for y in ytds if y > self_ytd)
    median = statistics.median(ytds)
    name = str(sector.get("name") or "").strip()
    if name.startswith("BRVM - "):
        name = name[len("BRVM - "):]
    line = f"Secteur {name} : {_fmt_pct_signed(self_ytd / 100.0)} depuis janvier"
    if rank == 1:
        return line + " — 1er du secteur"
    if self_ytd < median:
        return line + " — à la traîne du secteur"
    return line + f" — {rank}e du secteur"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_symbol(
    symbol: str,
    *,
    _fetch_if_missing: bool = True,
    _per_median: Any = _PER_MEDIAN_UNSET,
) -> dict[str, Any]:
    """Score one BRVM symbol. Never raises: bad/missing data -> error/warnings.

    Internal batch knobs (keyword-only, underscore-prefixed; the public
    contract is score_symbol(symbol)):
    - _fetch_if_missing=False reads only the cached CSV (no live scrape);
      score_all uses it so a cold cache cannot trigger ~47 live scrapes.
    - _per_median threads a precomputed market PER median (score_all computes
      it once per run instead of once per symbol).
    """
    sym = (symbol or "").strip().upper()
    out: dict[str, Any] = {
        "symbol": sym,
        # Official company name from the BRVM list — so the LLM never has to
        # invent it (hallucination guard, e.g. ETIT = Ecobank Transnational).
        "company_name": get_symbol_to_name().get(sym) or None,
        "score": None,
        "signal": None,
        "reasons": [],
        "technicals": {},
        "fundamentals": {},
        "data_warnings": [],
        "error": None,
    }
    if not sym:
        out["error"] = "Symbole vide : indiquez un symbole BRVM coté."
        return out
    try:
        valid = get_valid_symbols()
    except Exception:
        valid = None  # validation source unavailable: let the loaders decide
    if valid is not None and sym not in valid:
        out["error"] = f"{sym} n'est pas un symbole BRVM coté."
        return out

    try:
        rows = load_series(sym, fetch_if_missing=_fetch_if_missing)
    except Exception as e:
        logger.debug("load_series failed for %s: %s", sym, e)
        rows = []
    rows = [r for r in (rows or []) if r.get("price") is not None]
    if not rows and not _fetch_if_missing:
        out["error"] = "Pas de série historique en cache"
        return out
    if len(rows) < MIN_HISTORY_ROWS:
        out["error"] = (
            f"Données historiques insuffisantes "
            f"({len(rows)} séances, minimum {MIN_HISTORY_ROWS})."
        )
        return out

    closes = [float(r["price"]) for r in rows]
    technicals, tech_warnings = _compute_technicals(sym, rows, closes)
    price = _current_price(sym, closes)
    fundamentals, fund_warnings = _compute_fundamentals(sym, price, per_median=_per_median)

    score = round(
        _clamp(
            technicals["block"] * TECHNICAL_WEIGHT
            + fundamentals["block"] * FUNDAMENTAL_WEIGHT,
            0.0,
            100.0,
        ),
        1,
    )
    reasons = _build_reasons(technicals, fundamentals)
    sector_line = _sector_context(sym)
    if sector_line:
        # Informational only, appended after the score-driving reasons
        # (the usual 6-reason cap becomes 7 with a sector line).
        reasons.append(sector_line)
    out.update({
        "score": score,
        "signal": signal_for_score(score),
        "reasons": reasons,
        "technicals": technicals,
        "fundamentals": fundamentals,
        "data_warnings": tech_warnings + fund_warnings,
    })
    logger.debug("score_symbol %s -> %s (%s)", sym, score, out["signal"])
    return out


def score_all(symbols: list[str] | None = None) -> dict[str, Any]:
    """Score and rank every symbol (default: all valid BRVM symbols).

    Batch mode: reads only the cached CSVs (fetch_if_missing=False — the daily
    timeseries job pre-warms the cache, so a cold cache must not fan out into
    ~47 live scrapes) and computes the market PER median once for the run.
    """
    if symbols is None:
        try:
            symbols = sorted(get_valid_symbols())
        except Exception:
            symbols = []
    per_median = _market_per_median()
    ranked: list[dict] = []
    insufficient: list[dict] = []
    for sym in symbols:
        res = score_symbol(sym, _fetch_if_missing=False, _per_median=per_median)
        if res.get("score") is not None:
            ranked.append(res)
        else:
            insufficient.append(res)
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {
        "as_of": date.today().isoformat(),
        "ranked": ranked,
        "insufficient": insufficient,
    }

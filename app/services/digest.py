"""Scheduled BRVM market digest ("résumé du marché") pushed to subscribers.

Pure composition logic: no Telegram imports, no network access of its own.
The scheduled job (run_telegram_bot.py / app/main.py) calls run_digest(),
which scores the market once via the deterministic engine, persists the
snapshot rows (day-over-day signal changes), then composes one French text
per subscriber. Everything is total: scoring/persistence failures yield an
empty list, per-subscriber failures are logged and skipped — never an
exception.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import config
from app.services import scoring
from app.utils import user_db

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "⚠️ Ceci n'est pas un conseil financier personnalisé. "
    "Faites vos propres vérifications ou consultez un conseiller agréé."
)

TOP_N = 3  # top picks shown per section

# Locale-independent French calendar names (server locale is not reliable).
_DAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MONTHS_FR = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
)

_BUY_SIGNALS = (scoring.SIGNAL_BUY, scoring.SIGNAL_ACCUMULATE)
# Signal strength ordering, used for the up/down arrow on signal changes.
_SIGNAL_RANK = {
    scoring.SIGNAL_REDUCE: 0,
    scoring.SIGNAL_NEUTRAL: 1,
    scoring.SIGNAL_ACCUMULATE: 2,
    scoring.SIGNAL_BUY: 3,
}


def _fmt_fr(x: float, decimals: int = 1) -> str:
    return f"{x:.{decimals}f}".replace(".", ",")


def _fmt_date_fr(d: date) -> str:
    """'vendredi 21 août 2026' — no locale dependency."""
    return f"{_DAYS_FR[d.weekday()]} {d.day} {_MONTHS_FR[d.month - 1]} {d.year}"


def _details(row: dict) -> dict:
    """Parsed snapshot details_json (reasons + warnings); {} when absent/bad."""
    try:
        data = json.loads(row.get("details_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _pick_line(row: dict) -> str:
    """'NTLC — 73,3/100 (Achat) : <top reason>' (reason omitted when none)."""
    line = f"{row['symbol']} — {_fmt_fr(float(row['score']))}/100 ({row.get('signal') or '—'})"
    reasons = _details(row).get("reasons") or []
    if reasons:
        line += f" : {reasons[0]}"
    return line


def _position_line(symbol: str, current: dict[str, dict], previous: dict[str, dict]) -> str:
    """Signal change vs the previous snapshot: 'NTLC : Accumuler → Achat ⬆️'."""
    cur = current.get(symbol)
    if cur is None:
        return f"{symbol} : pas de score disponible (données insuffisantes)"
    sig = cur.get("signal") or "—"
    prev = previous.get(symbol)
    prev_sig = (prev or {}).get("signal")
    if not prev_sig:
        return f"{symbol} : {sig} ({_fmt_fr(float(cur['score']))}/100)"
    if prev_sig == sig:
        return f"{symbol} : {sig} — inchangé"
    arrow = "⬆️" if _SIGNAL_RANK.get(sig, 1) > _SIGNAL_RANK.get(prev_sig, 1) else "⬇️"
    return f"{symbol} : {prev_sig} → {sig} {arrow}"


def compose_digest(telegram_id: int, frequency: str) -> str | None:
    """French digest text for one subscriber; None when there is nothing useful
    to send (no score snapshots at all)."""
    snapshots = user_db.get_latest_snapshots()
    if not snapshots:
        return None
    try:
        snap_day = date.fromisoformat(str(snapshots[0].get("day") or "")[:10])
    except ValueError:
        snap_day = date.today()

    scored = [s for s in snapshots if s.get("score") is not None]
    if not scored:
        return None
    scored.sort(key=lambda s: float(s["score"]), reverse=True)

    frequency = (frequency or "daily").strip().lower()
    if frequency == "weekly":
        monday = snap_day - timedelta(days=snap_day.weekday())
        header = f"📊 Résumé hebdo BRVM — semaine du {_fmt_date_fr(monday)}"
    else:
        header = f"📊 Résumé BRVM du {_fmt_date_fr(snap_day)}"

    sections: list[str] = [header, ""]

    buys = [s for s in scored if s.get("signal") in _BUY_SIGNALS][:TOP_N]
    sections.append("🟢 À l'achat")
    if buys:
        sections.extend(f"• {_pick_line(s)}" for s in buys)
    else:
        sections.append("• Aucun signal Achat/Accumuler aujourd'hui.")

    buy_symbols = {s["symbol"] for s in buys}
    watch = [s for s in reversed(scored) if s["symbol"] not in buy_symbols][:TOP_N]
    if watch:
        sections.append("")
        sections.append("🔴 À surveiller / alléger")
        sections.extend(f"• {_pick_line(s)}" for s in watch)

    # Signal changes for the subscriber's own symbols (vs the previous day
    # with snapshots). Sections omitted when the user tracks nothing.
    previous = {s["symbol"]: s for s in user_db.get_previous_snapshots(snap_day.isoformat())}
    current = {s["symbol"]: s for s in snapshots}
    try:
        portfolio = [{"symbol": sym} for sym in user_db.portfolio_symbols(telegram_id)]
        tracking = user_db.tracking_list(telegram_id)
    except Exception as e:
        logger.warning("Digest: could not load positions for %s: %s", telegram_id, e)
        portfolio, tracking = [], []
    if portfolio:
        sections.append("")
        sections.append("📁 Vos positions")
        sections.extend(
            f"• {_position_line(r['symbol'], current, previous)}" for r in portfolio
        )
    if tracking:
        sections.append("")
        sections.append("👀 Votre liste de suivi")
        sections.extend(
            f"• {_position_line(r['symbol'], current, previous)}" for r in tracking
        )

    sections.append("")
    sections.append(DISCLAIMER)
    return "\n".join(sections)


def _snapshot_rows(ranked: list[dict], day: str) -> list[dict]:
    """save_score_snapshots-shaped rows: reasons + warnings kept as details."""
    rows = []
    for r in ranked:
        rows.append({
            "symbol": r.get("symbol"),
            "day": day,
            "score": r.get("score"),
            "signal": r.get("signal"),
            "details_json": json.dumps(
                {
                    "reasons": r.get("reasons") or [],
                    "data_warnings": r.get("data_warnings") or [],
                },
                ensure_ascii=False,
            ),
        })
    return rows


def run_digest(frequency: str) -> list[tuple[int, str]]:
    """Job body: score the market once, persist today's snapshots, then compose
    one digest per subscriber of `frequency` ('daily' | 'weekly').

    Returns [(telegram_id, text), ...]. Never raises: a scoring/persistence
    failure yields [], per-subscriber failures are logged and skipped.
    """
    if not getattr(config, "DIGEST_ENABLED", True):
        logger.info("Digest disabled (DIGEST_ENABLED): skipping %s run", frequency)
        return []
    frequency = (frequency or "daily").strip().lower()

    try:
        data: dict[str, Any] = scoring.score_all() or {}
    except Exception as e:
        logger.exception("Digest %s: scoring failed: %s", frequency, e)
        return []
    day = data.get("as_of") or date.today().isoformat()
    try:
        user_db.save_score_snapshots(_snapshot_rows(data.get("ranked") or [], day))
    except Exception as e:
        # Composing from the previous snapshots is still useful; carry on.
        logger.exception("Digest %s: could not persist score snapshots: %s", frequency, e)

    try:
        subscribers = user_db.digest_subscribers(frequency)
    except Exception as e:
        logger.exception("Digest %s: could not list subscribers: %s", frequency, e)
        return []

    out: list[tuple[int, str]] = []
    for telegram_id in subscribers:
        try:
            text = compose_digest(telegram_id, frequency)
        except Exception as e:
            logger.warning("Digest %s: compose failed for user %s: %s", frequency, telegram_id, e)
            continue
        if text:
            out.append((telegram_id, text))
    return out

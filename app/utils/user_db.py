"""User database: portfolio, tracking list, price targets, daily usage,
digest subscriptions, score snapshots. BRVM only.

Persistence: SQLAlchemy (app/db) — PostgreSQL when config.DATABASE_URL is set
(production / docker compose), else a local SQLite file at DB_PATH. The schema
is managed by Alembic (app/db/migrations) and applied lazily once per target,
so rebinding DB_PATH (tests) yields a fresh migrated database.

All public functions keep identical signatures on both backends.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Text, cast, delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models
from app.utils._data import fetch_palmares
from app.utils.brvm_companies import get_valid_symbols

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "brvm_bot.db"


# --- Engine / schema plumbing ---
def _ensure_ready() -> None:
    """Apply migrations for the current DB target (once per target per process)."""
    db_migrate.ensure_schema()


def init_db() -> None:
    """Back-compat alias for _ensure_ready() (tests call it after rebinding DB_PATH)."""
    _ensure_ready()


def reset_engine() -> None:
    """Drop cached engines and migration markers (tests)."""
    db_engine.reset_engines()
    db_migrate.reset_cache()


def _dialect_insert(table):
    """Dialect-specific INSERT (enables ON CONFLICT clauses on both backends)."""
    return db_engine.dialect_insert(table)


def _today_utc() -> str:
    """Current UTC day (UTC == local time for UEMOA users)."""
    return datetime.now(timezone.utc).date().isoformat()


# --- Daily usage quota ---
def _usage_increment_stmt(dialect_name: str, user_id: str, day: str):
    """Atomic usage upsert returning the new count (dialect-specific ON CONFLICT).

    The DO UPDATE clause uses the table-qualified `usage_daily.count + 1`: bare
    `count` is ambiguous in Postgres upserts (table vs EXCLUDED).
    """
    t = models.UsageDaily.__table__
    if dialect_name == "postgresql":
        from sqlalchemy.dialects import postgresql

        insert = postgresql.insert
    else:
        from sqlalchemy.dialects import sqlite

        insert = sqlite.insert
    stmt = insert(t).values(user_id=user_id, day=day, count=1)
    return stmt.on_conflict_do_update(
        index_elements=["user_id", "day"],
        set_={"count": t.c.count + 1},
    ).returning(t.c.count)


def get_daily_usage(user_id: str) -> int:
    """Number of requests used today by this user key."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        value = s.execute(
            select(models.UsageDaily.count).where(
                models.UsageDaily.user_id == str(user_id),
                models.UsageDaily.day == _today_utc(),
            )
        ).scalar_one_or_none()
        return int(value) if value is not None else 0


def increment_daily_usage(user_id: str) -> int:
    """Count one more request for today; return the new count. Prunes old days."""
    _ensure_ready()
    today = _today_utc()
    engine = db_engine.get_engine()
    with db_engine.session_scope() as s:
        value = s.execute(
            _usage_increment_stmt(engine.dialect.name, str(user_id), today)
        ).scalar_one_or_none()
        s.execute(delete(models.UsageDaily).where(models.UsageDaily.day < today))
        return int(value) if value is not None else 0


def decrement_daily_usage(user_id: str) -> None:
    """Refund one request for today (used when a counted request fails)."""
    _ensure_ready()
    t = models.UsageDaily.__table__
    if db_engine.get_engine().dialect.name == "postgresql":
        floor = func.greatest(t.c.count - 1, 0)
    else:
        floor = func.max(t.c.count - 1, 0)  # SQLite scalar max
    with db_engine.session_scope() as s:
        s.execute(
            update(models.UsageDaily)
            .where(t.c.user_id == str(user_id), t.c.day == _today_utc())
            .values(count=floor)
        )


# --- Users / welcome message ---
def get_or_create_user(telegram_id: int) -> None:
    """Ensure user exists."""
    _ensure_ready()
    stmt = _dialect_insert(models.User.__table__).values(telegram_id=telegram_id)
    with db_engine.session_scope() as s:
        s.execute(stmt.on_conflict_do_nothing())


def has_sent_help(telegram_id: int) -> bool:
    """True if we have already sent the help/welcome message to this user."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        value = s.execute(
            select(models.User.help_sent_at).where(
                models.User.telegram_id == telegram_id
            )
        ).scalar_one_or_none()
        return value is not None


def mark_help_sent(telegram_id: int) -> None:
    """Mark that we have sent the help message to this user."""
    get_or_create_user(telegram_id)
    with db_engine.session_scope() as s:
        s.execute(
            update(models.User)
            .where(models.User.telegram_id == telegram_id)
            .values(help_sent_at=cast(func.now(), Text))
        )


# --- Portfolio ---
def portfolio_add(telegram_id: int, symbol: str, buy_price: float, buy_date: str, quantity: float = 1.0) -> dict[str, Any]:
    """Add or update a position. Returns {ok, message, error}."""
    get_or_create_user(telegram_id)
    symbol = (symbol or "").strip().upper()
    if symbol not in get_valid_symbols():
        return {"ok": False, "error": f"{symbol} n'est pas un symbole BRVM coté."}
    try:
        d = date.fromisoformat(buy_date.strip()[:10])
        buy_date_str = d.isoformat()
    except ValueError:
        return {"ok": False, "error": "Date d'achat invalide. Utilisez AAAA-MM-JJ."}
    if buy_price <= 0 or quantity <= 0:
        return {"ok": False, "error": "Le prix d'achat et la quantité doivent être positifs."}
    t = models.Portfolio.__table__
    stmt = _dialect_insert(t).values(
        telegram_id=telegram_id,
        symbol=symbol,
        buy_price=buy_price,
        buy_date=buy_date_str,
        quantity=quantity,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["telegram_id", "symbol"],
        set_={
            "buy_price": stmt.excluded.buy_price,
            "buy_date": stmt.excluded.buy_date,
            "quantity": stmt.excluded.quantity,
        },
    )
    try:
        with db_engine.session_scope() as s:
            s.execute(stmt)
        return {"ok": True, "message": f"Ajout/mise à jour : {symbol} : {quantity} @ {buy_price} F CFA le {buy_date_str}."}
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def portfolio_list(telegram_id: int) -> list[dict[str, Any]]:
    """List portfolio rows for user."""
    get_or_create_user(telegram_id)
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(
                models.Portfolio.symbol,
                models.Portfolio.buy_price,
                models.Portfolio.buy_date,
                models.Portfolio.quantity,
                models.Portfolio.created_at,
            )
            .where(models.Portfolio.telegram_id == telegram_id)
            .order_by(models.Portfolio.symbol)
        ).mappings().all()
        return [dict(r) for r in rows]


def portfolio_remove(telegram_id: int, symbol: str) -> dict[str, Any]:
    """Remove a symbol from portfolio."""
    _ensure_ready()
    symbol = (symbol or "").strip().upper()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.Portfolio).where(
                models.Portfolio.telegram_id == telegram_id,
                models.Portfolio.symbol == symbol,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": f"{symbol} retiré de votre portefeuille."}
        return {"ok": False, "error": f"Aucune position {symbol} dans votre portefeuille."}


def _current_price(symbol: str) -> float | None:
    """Current price from palmarès for one symbol."""
    stocks = fetch_palmares(period="veille", progression="tout")
    for s in stocks:
        if (s.get("symbol") or "").strip().upper() == symbol:
            return s.get("cours_actuel")
    return None


def portfolio_with_prices(telegram_id: int) -> list[dict[str, Any]]:
    """Portfolio rows with current_price and gain_loss_pct (when current price available)."""
    rows = portfolio_list(telegram_id)
    out = []
    for r in rows:
        sym = r["symbol"]
        current = _current_price(sym)
        buy = r["buy_price"]
        gain_pct = None
        if current is not None and buy and buy > 0:
            gain_pct = round((current - buy) / buy * 100, 2)
        out.append({
            **r,
            "current_price": current,
            "gain_loss_pct": gain_pct,
        })
    return out


def portfolio_summary(telegram_id: int) -> dict[str, Any]:
    """Total cost, total value, overall gain/loss %."""
    rows = portfolio_with_prices(telegram_id)
    total_cost = sum(r["buy_price"] * r["quantity"] for r in rows)
    total_value = 0.0
    for r in rows:
        p = r.get("current_price")
        if p is not None:
            total_value += p * r["quantity"]
        else:
            total_value += r["buy_price"] * r["quantity"]  # fallback to cost
    gain_pct = None
    if total_cost and total_value > 0:
        gain_pct = round((total_value - total_cost) / total_cost * 100, 2)
    return {
        "total_cost_fcfa": round(total_cost, 2),
        "total_value_fcfa": round(total_value, 2),
        "gain_loss_pct": gain_pct,
        "positions_count": len(rows),
    }


# --- Tracking ---
def tracking_list(telegram_id: int) -> list[dict[str, Any]]:
    get_or_create_user(telegram_id)
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(models.Tracking.symbol, models.Tracking.created_at)
            .where(models.Tracking.telegram_id == telegram_id)
            .order_by(models.Tracking.symbol)
        ).mappings().all()
        return [dict(r) for r in rows]


def tracking_add(telegram_id: int, symbol: str) -> dict[str, Any]:
    symbol = (symbol or "").strip().upper()
    if symbol not in get_valid_symbols():
        return {"ok": False, "error": f"{symbol} n'est pas un symbole BRVM coté."}
    get_or_create_user(telegram_id)
    stmt = _dialect_insert(models.Tracking.__table__).values(
        telegram_id=telegram_id, symbol=symbol
    )
    try:
        with db_engine.session_scope() as s:
            s.execute(stmt.on_conflict_do_nothing())
        return {"ok": True, "message": f"{symbol} ajouté à votre liste de suivi."}
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def tracking_remove(telegram_id: int, symbol: str) -> dict[str, Any]:
    _ensure_ready()
    symbol = (symbol or "").strip().upper()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.Tracking).where(
                models.Tracking.telegram_id == telegram_id,
                models.Tracking.symbol == symbol,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": f"{symbol} retiré du suivi."}
        return {"ok": False, "error": f"{symbol} n'était pas dans votre liste de suivi."}


# --- Target alerts ---
def target_add(telegram_id: int, symbol: str, target_price: float, direction: str = "above") -> dict[str, Any]:
    symbol = (symbol or "").strip().upper()
    if symbol not in get_valid_symbols():
        return {"ok": False, "error": f"{symbol} n'est pas un symbole BRVM coté."}
    if target_price <= 0:
        return {"ok": False, "error": "Le prix cible doit être positif."}
    direction = (direction or "above").strip().lower()
    if direction not in ("above", "below"):
        direction = "above"
    get_or_create_user(telegram_id)
    try:
        with db_engine.session_scope() as s:
            s.execute(
                models.TargetAlert.__table__.insert().values(
                    telegram_id=telegram_id,
                    symbol=symbol,
                    target_price=target_price,
                    direction=direction,
                )
            )
        dir_fr = "au-dessus" if direction == "above" else "en dessous"
        return {"ok": True, "message": f"Alerte définie : notification quand {symbol} atteint {target_price} F CFA ({dir_fr})."}
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def target_list(telegram_id: int) -> list[dict[str, Any]]:
    get_or_create_user(telegram_id)
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(
                models.TargetAlert.symbol,
                models.TargetAlert.target_price,
                models.TargetAlert.direction,
                models.TargetAlert.notified,
                models.TargetAlert.created_at,
            )
            .where(models.TargetAlert.telegram_id == telegram_id)
            .order_by(models.TargetAlert.symbol)
        ).mappings().all()
        return [dict(r) for r in rows]


def target_remove(telegram_id: int, symbol: str) -> dict[str, Any]:
    _ensure_ready()
    symbol = (symbol or "").strip().upper()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.TargetAlert).where(
                models.TargetAlert.telegram_id == telegram_id,
                models.TargetAlert.symbol == symbol,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": f"Alerte de prix supprimée pour {symbol}."}
        return {"ok": False, "error": f"Aucune alerte définie pour {symbol}."}


def get_pending_alerts() -> list[dict[str, Any]]:
    """All target alerts that are not yet notified."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(
                models.TargetAlert.id,
                models.TargetAlert.telegram_id,
                models.TargetAlert.symbol,
                models.TargetAlert.target_price,
                models.TargetAlert.direction,
            ).where(models.TargetAlert.notified == 0)
        ).mappings().all()
        return [dict(r) for r in rows]


def mark_alert_notified(alert_id: int) -> None:
    _ensure_ready()
    with db_engine.session_scope() as s:
        s.execute(
            update(models.TargetAlert)
            .where(models.TargetAlert.id == alert_id)
            .values(notified=1)
        )


def check_targets_and_notify() -> list[tuple[int, str]]:
    """For each pending alert, check current price; if target reached, return (telegram_id, message) and mark notified."""
    alerts = get_pending_alerts()
    to_send: list[tuple[int, str]] = []
    for a in alerts:
        symbol = a["symbol"]
        target = a["target_price"]
        direction = a["direction"]
        current = _current_price(symbol)
        if current is None:
            continue
        triggered = False
        if direction == "above" and current >= target:
            triggered = True
        elif direction == "below" and current <= target:
            triggered = True
        if triggered:
            to_send.append((
                a["telegram_id"],
                f"Alert: {symbol} is now {current} F CFA (target {direction} {target} F CFA).",
            ))
            mark_alert_notified(a["id"])
    return to_send


# --- Digest subscriptions ---
DIGEST_FREQUENCIES = ("daily", "weekly")


def digest_set(telegram_id: int, frequency: str) -> dict[str, Any]:
    """Subscribe (or re-subscribe) a user to the daily/weekly digest."""
    frequency = (frequency or "").strip().lower()
    if frequency not in DIGEST_FREQUENCIES:
        return {"ok": False, "error": "Fréquence invalide. Choisissez 'daily' ou 'weekly'."}
    get_or_create_user(telegram_id)
    t = models.DigestSubscription.__table__
    stmt = _dialect_insert(t).values(
        telegram_id=telegram_id, frequency=frequency, enabled=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["telegram_id"],
        set_={"frequency": stmt.excluded.frequency, "enabled": 1},
    )
    try:
        with db_engine.session_scope() as s:
            s.execute(stmt)
        freq_fr = "quotidien" if frequency == "daily" else "hebdomadaire"
        return {"ok": True, "message": f"Digest {freq_fr} activé : vous recevrez un résumé du marché BRVM."}
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def digest_get(telegram_id: int) -> dict[str, Any] | None:
    """Digest subscription row for a user (None when never subscribed)."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        row = s.execute(
            select(
                models.DigestSubscription.telegram_id,
                models.DigestSubscription.frequency,
                models.DigestSubscription.enabled,
                models.DigestSubscription.created_at,
            ).where(models.DigestSubscription.telegram_id == telegram_id)
        ).mappings().first()
        return dict(row) if row else None


def digest_unsubscribe(telegram_id: int) -> dict[str, Any]:
    """Disable the digest subscription (row kept for re-subscribe)."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        res = s.execute(
            update(models.DigestSubscription)
            .where(models.DigestSubscription.telegram_id == telegram_id)
            .values(enabled=0)
        )
        if res.rowcount:
            return {"ok": True, "message": "Digest désactivé : vous ne recevrez plus de résumé automatique."}
        return {"ok": False, "error": "Aucun abonnement digest pour ce compte."}


def digest_subscribers(frequency: str | None = None) -> list[int]:
    """Telegram ids with an enabled subscription, optionally filtered by frequency."""
    _ensure_ready()
    stmt = select(models.DigestSubscription.telegram_id).where(
        models.DigestSubscription.enabled == 1
    )
    if frequency:
        stmt = stmt.where(
            models.DigestSubscription.frequency == frequency.strip().lower()
        )
    with db_engine.session_scope() as s:
        return [int(r[0]) for r in s.execute(stmt).all()]


# --- Score snapshots ---
def save_score_snapshots(rows: list[dict]) -> None:
    """Persist one score snapshot per symbol for a day (default: today UTC).

    Idempotent daily write: existing rows for the same (symbol, day) are
    replaced. Row keys: symbol, score, signal; optional day, details (object)
    or details_json (pre-serialized string).
    """
    if not rows:
        return
    _ensure_ready()
    today = _today_utc()
    normalized = []
    for r in rows:
        symbol = str(r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        details = r.get("details_json")
        if details is None:
            details = json.dumps(r.get("details") or {}, ensure_ascii=False)
        normalized.append({
            "symbol": symbol,
            "day": str(r.get("day") or today),
            "score": float(r.get("score") or 0.0),
            "signal": str(r.get("signal") or ""),
            "details_json": details,
        })
    with db_engine.session_scope() as s:
        for symbol, day in {(r["symbol"], r["day"]) for r in normalized}:
            s.execute(
                delete(models.ScoreSnapshot).where(
                    models.ScoreSnapshot.symbol == symbol,
                    models.ScoreSnapshot.day == day,
                )
            )
        if normalized:
            s.execute(models.ScoreSnapshot.__table__.insert(), normalized)


def _snapshots_for_day(day: str) -> list[dict[str, Any]]:
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(
                models.ScoreSnapshot.symbol,
                models.ScoreSnapshot.day,
                models.ScoreSnapshot.score,
                models.ScoreSnapshot.signal,
                models.ScoreSnapshot.details_json,
                models.ScoreSnapshot.created_at,
            )
            .where(models.ScoreSnapshot.day == day)
            .order_by(models.ScoreSnapshot.symbol)
        ).mappings().all()
        return [dict(r) for r in rows]


def get_latest_snapshots(day: str | None = None) -> list[dict[str, Any]]:
    """Snapshots for `day` (default: the most recent day with data)."""
    _ensure_ready()
    if day is None:
        with db_engine.session_scope() as s:
            day = s.execute(select(func.max(models.ScoreSnapshot.day))).scalar()
        if day is None:
            return []
    return _snapshots_for_day(day)


def get_previous_snapshots(before_day: str) -> list[dict[str, Any]]:
    """Snapshots of the most recent day strictly before `before_day`."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        day = s.execute(
            select(func.max(models.ScoreSnapshot.day)).where(
                models.ScoreSnapshot.day < before_day
            )
        ).scalar()
    if day is None:
        return []
    return _snapshots_for_day(day)

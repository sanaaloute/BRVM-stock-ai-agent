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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Text, cast, delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models
from app.utils._data import fetch_palmares, load_price_on_or_before, load_series
from app.utils.brvm_companies import get_symbol_to_sector, get_valid_symbols

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


# --- Portfolio (buy lots: one row per purchase; positions are aggregates) ----
def portfolio_add(telegram_id: int, symbol: str, buy_price: float, buy_date: str, quantity: float = 1.0, sgi: str | None = None) -> dict[str, Any]:
    """Record one buy lot with its SGI, without overwriting earlier purchases."""
    get_or_create_user(telegram_id)
    symbol = (symbol or "").strip().upper()
    sgi_name = (sgi or "Non affecté").strip() or "Non affecté"
    if symbol not in get_valid_symbols():
        return {"ok": False, "error": f"{symbol} n'est pas un symbole BRVM coté."}
    try:
        d = date.fromisoformat(buy_date.strip()[:10])
        buy_date_str = d.isoformat()
    except ValueError:
        return {"ok": False, "error": "Date d'achat invalide. Utilisez AAAA-MM-JJ."}
    if buy_price <= 0 or quantity <= 0:
        return {"ok": False, "error": "Le prix d'achat et la quantité doivent être positifs."}
    try:
        with db_engine.session_scope() as s:
            s.execute(
                models.Portfolio.__table__.insert().values(
                    telegram_id=telegram_id,
                    symbol=symbol,
                    sgi=sgi_name,
                    buy_price=buy_price,
                    buy_date=buy_date_str,
                    quantity=quantity,
                )
            )
        return {"ok": True, "message": f"Achat enregistré : {symbol} : {quantity} @ {buy_price} F CFA le {buy_date_str}."}
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def portfolio_list(telegram_id: int) -> list[dict[str, Any]]:
    """All buy lots for the user (newest first), each with its lot id and SGI."""
    get_or_create_user(telegram_id)
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(
                models.Portfolio.id,
                models.Portfolio.symbol,
                models.Portfolio.sgi,
                models.Portfolio.buy_price,
                models.Portfolio.buy_date,
                models.Portfolio.quantity,
                models.Portfolio.created_at,
            )
            .where(models.Portfolio.telegram_id == telegram_id)
            .order_by(models.Portfolio.symbol, models.Portfolio.buy_date)
        ).mappings().all()
        return [dict(r) for r in rows]


def portfolio_positions(telegram_id: int) -> list[dict[str, Any]]:
    """Aggregate lots by symbol and SGI, keeping each broker's positions separate."""
    positions: dict[tuple[str, str], dict[str, Any]] = {}
    for lot in portfolio_list(telegram_id):
        key = (lot["symbol"], lot.get("sgi") or "Non affecté")
        pos = positions.setdefault(key, {
            "symbol": lot["symbol"],
            "sgi": lot.get("sgi") or "Non affecté",
            "quantity": 0.0,
            "total_cost": 0.0,
            "lots": [],
        })
        pos["quantity"] += lot["quantity"]
        pos["total_cost"] += lot["buy_price"] * lot["quantity"]
        pos["lots"].append(lot)
    out = []
    for pos in positions.values():
        pos["avg_buy_price"] = round(pos["total_cost"] / pos["quantity"], 2) if pos["quantity"] else None
        pos["total_cost"] = round(pos["total_cost"], 2)
        out.append(pos)
    return sorted(out, key=lambda p: (p["symbol"], p["sgi"]))


def portfolio_symbols(telegram_id: int) -> list[str]:
    """Distinct symbols held (one entry per symbol regardless of lot count)."""
    return sorted({p["symbol"] for p in portfolio_positions(telegram_id)})


def portfolio_remove(telegram_id: int, symbol: str) -> dict[str, Any]:
    """Remove ALL lots of a symbol from the portfolio."""
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
            return {"ok": True, "message": f"{res.rowcount} ligne(s) {symbol} retirée(s) de votre portefeuille."}
        return {"ok": False, "error": f"Aucune position {symbol} dans votre portefeuille."}


def portfolio_lot_update(telegram_id: int, lot_id: int, *, buy_price: float | None = None, buy_date: str | None = None, quantity: float | None = None, sgi: str | None = None) -> dict[str, Any]:
    """Edit one lot's SGI, price/date/quantity (mobile API)."""
    _ensure_ready()
    values: dict[str, Any] = {}
    if sgi is not None:
        values["sgi"] = sgi.strip() or "Non affecté"
    if buy_price is not None:
        if buy_price <= 0:
            return {"ok": False, "error": "Le prix d'achat doit être positif."}
        values["buy_price"] = buy_price
    if quantity is not None:
        if quantity <= 0:
            return {"ok": False, "error": "La quantité doit être positive."}
        values["quantity"] = quantity
    if buy_date is not None:
        try:
            values["buy_date"] = date.fromisoformat(buy_date.strip()[:10]).isoformat()
        except ValueError:
            return {"ok": False, "error": "Date d'achat invalide. Utilisez AAAA-MM-JJ."}
    if not values:
        return {"ok": False, "error": "Rien à modifier."}
    with db_engine.session_scope() as s:
        res = s.execute(
            update(models.Portfolio)
            .where(models.Portfolio.id == lot_id, models.Portfolio.telegram_id == telegram_id)
            .values(**values)
        )
        if res.rowcount:
            return {"ok": True, "message": "Ligne d'achat mise à jour."}
        return {"ok": False, "error": "Ligne d'achat introuvable."}


def portfolio_lot_remove(telegram_id: int, lot_id: int) -> dict[str, Any]:
    """Delete one lot (mobile API)."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.Portfolio).where(
                models.Portfolio.id == lot_id,
                models.Portfolio.telegram_id == telegram_id,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": "Ligne d'achat supprimée."}
        return {"ok": False, "error": "Ligne d'achat introuvable."}


def _current_price(symbol: str) -> float | None:
    """Live quote from the palmarès; on a closed market (weekend / before the
    ~15:00 GMT close) cours_actuel is empty — fall back to cours_veille, then
    to the last close from the time series."""
    stocks = fetch_palmares(period="veille", progression="tout")
    for s in stocks:
        if (s.get("symbol") or "").strip().upper() == symbol:
            price = s.get("cours_actuel")
            if price is not None:
                return price
            veille = s.get("cours_veille")
            if veille is not None:
                return veille
            break
    row = load_price_on_or_before(symbol, date.today())
    return row["price"] if row else None


def current_price(symbol: str) -> float | None:
    """Public wrapper over _current_price (used by the mobile API)."""
    return _current_price(symbol)


def portfolio_with_prices(telegram_id: int, sgi: str | None = None) -> list[dict[str, Any]]:
    """Aggregated positions with SGI, current value and gain/loss amount/percent."""
    positions = portfolio_positions(telegram_id)
    if sgi is not None:
        positions = [pos for pos in positions if (pos.get("sgi") or "Non affecté") == sgi]
    sectors = get_symbol_to_sector()
    rows = []
    for pos in positions:
        sym = pos["symbol"]
        avg = pos["avg_buy_price"]
        current = _current_price(sym)
        current_value = round(current * pos["quantity"], 2) if current is not None else None
        gain_loss = round(current_value - pos["total_cost"], 2) if current_value is not None else None
        gain_pct = None
        if current is not None and avg:
            gain_pct = round((current - avg) / avg * 100, 2)
        rows.append({
            "symbol": sym,
            "sgi": pos.get("sgi") or "Non affecté",
            "sector": sectors.get(sym, ""),
            "quantity": pos["quantity"],
            "avg_buy_price": avg,
            "buy_price": avg,  # back-compat: weighted average price
            "total_cost": pos["total_cost"],
            "current_price": current,
            "current_value_fcfa": current_value,
            "gain_loss_fcfa": gain_loss,
            "gain_loss_pct": gain_pct,
            "lots": pos["lots"],
        })
    return rows


def portfolio_dividend_add(telegram_id: int, symbol: str, amount: float, payment_date: str, sgi: str | None = None) -> dict[str, Any]:
    """Record one manually entered dividend payment."""
    get_or_create_user(telegram_id)
    symbol = (symbol or "").strip().upper()
    sgi_name = (sgi or "Non affecté").strip() or "Non affecté"
    if symbol not in get_valid_symbols():
        return {"ok": False, "error": f"{symbol} n'est pas un symbole BRVM coté."}
    try:
        payment_day = date.fromisoformat(payment_date.strip()[:10]).isoformat()
        dividend_amount = float(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Date ou montant de dividende invalide."}
    if dividend_amount <= 0:
        return {"ok": False, "error": "Le montant du dividende doit être positif."}
    try:
        with db_engine.session_scope() as s:
            result = s.execute(
                models.PortfolioDividend.__table__.insert().values(
                    telegram_id=telegram_id,
                    import_id=None,
                    sgi=sgi_name,
                    symbol=symbol,
                    amount=dividend_amount,
                    payment_date=payment_day,
                )
            )
        dividend_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        return {
            "ok": True,
            "id": dividend_id,
            "message": f"Dividende enregistré : {symbol} : {dividend_amount:g} F CFA le {payment_day}.",
        }
    except SQLAlchemyError as e:
        return {"ok": False, "error": str(e)}


def portfolio_dividends_total(telegram_id: int, sgi: str | None = None) -> float:
    """Total dividends received, optionally restricted to one SGI."""
    stmt = select(func.sum(models.PortfolioDividend.amount)).where(
        models.PortfolioDividend.telegram_id == telegram_id
    )
    if sgi is not None:
        stmt = stmt.where(models.PortfolioDividend.sgi == sgi)
    with db_engine.session_scope() as s:
        value = s.execute(stmt).scalar_one()
    return round(float(value or 0), 2)


def portfolio_dividends_list(telegram_id: int, sgi: str | None = None) -> list[dict[str, Any]]:
    """All recorded dividend payments (newest first), optionally by SGI."""
    _ensure_ready()
    stmt = select(
        models.PortfolioDividend.id,
        models.PortfolioDividend.symbol,
        models.PortfolioDividend.sgi,
        models.PortfolioDividend.amount,
        models.PortfolioDividend.payment_date,
    ).where(models.PortfolioDividend.telegram_id == telegram_id)
    if sgi is not None:
        stmt = stmt.where(models.PortfolioDividend.sgi == sgi)
    stmt = stmt.order_by(
        models.PortfolioDividend.payment_date.desc(),
        models.PortfolioDividend.id.desc(),
    )
    with db_engine.session_scope() as s:
        rows = s.execute(stmt).mappings().all()
    sectors = get_symbol_to_sector()
    return [
        {
            "id": row["id"],
            "symbol": row["symbol"],
            "sgi": row["sgi"] or "Non affecté",
            "amount": float(row["amount"]),
            "payment_date": row["payment_date"],
            "sector": sectors.get((row["symbol"] or "").strip().upper(), ""),
        }
        for row in rows
    ]


def portfolio_dividend_update(telegram_id: int, dividend_id: int, *, symbol: str | None = None, amount: float | None = None, payment_date: str | None = None, sgi: str | None = None) -> dict[str, Any]:
    """Edit one dividend payment (mobile API)."""
    _ensure_ready()
    values: dict[str, Any] = {}
    if symbol is not None:
        sym = symbol.strip().upper()
        if sym not in get_valid_symbols():
            return {"ok": False, "error": f"{sym} n'est pas un symbole BRVM coté."}
        values["symbol"] = sym
    if sgi is not None:
        values["sgi"] = sgi.strip() or "Non affecté"
    if amount is not None:
        if amount <= 0:
            return {"ok": False, "error": "Le montant du dividende doit être positif."}
        values["amount"] = float(amount)
    if payment_date is not None:
        try:
            values["payment_date"] = date.fromisoformat(payment_date.strip()[:10]).isoformat()
        except ValueError:
            return {"ok": False, "error": "Date de paiement invalide. Utilisez AAAA-MM-JJ."}
    if not values:
        return {"ok": False, "error": "Rien à modifier."}
    with db_engine.session_scope() as s:
        res = s.execute(
            update(models.PortfolioDividend)
            .where(models.PortfolioDividend.id == dividend_id, models.PortfolioDividend.telegram_id == telegram_id)
            .values(**values)
        )
        if res.rowcount:
            return {"ok": True, "message": "Dividende mis à jour."}
        return {"ok": False, "error": "Dividende introuvable."}


def portfolio_dividend_remove(telegram_id: int, dividend_id: int) -> dict[str, Any]:
    """Delete one dividend payment (mobile API)."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.PortfolioDividend).where(
                models.PortfolioDividend.id == dividend_id,
                models.PortfolioDividend.telegram_id == telegram_id,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": "Dividende supprimé."}
        return {"ok": False, "error": "Dividende introuvable."}


def portfolio_summary(telegram_id: int, sgi: str | None = None) -> dict[str, Any]:
    """Current value, latent performance, dividends and total return, optionally by SGI."""
    rows = portfolio_with_prices(telegram_id, sgi=sgi)
    total_cost = sum(r["total_cost"] for r in rows)
    total_value = 0.0
    for r in rows:
        p = r.get("current_price")
        if p is not None:
            total_value += p * r["quantity"]
        else:
            total_value += r["total_cost"]  # fallback to cost
    gain_loss = round(total_value - total_cost, 2)
    dividends = portfolio_dividends_total(telegram_id, sgi=sgi)
    total_gain_loss = round(gain_loss + dividends, 2)
    gain_pct = None
    total_gain_loss_pct = None
    if total_cost and total_value > 0:
        gain_pct = round(gain_loss / total_cost * 100, 2)
        total_gain_loss_pct = round(total_gain_loss / total_cost * 100, 2)
    return {
        "total_cost_fcfa": round(total_cost, 2),
        "total_value_fcfa": round(total_value, 2),
        "gain_loss_fcfa": gain_loss,
        "gain_loss_pct": gain_pct,
        "dividends_fcfa": dividends,
        "total_gain_loss_fcfa": total_gain_loss,
        "total_gain_loss_pct": total_gain_loss_pct,
        "positions_count": len(rows),
        "lots_count": sum(len(r["lots"]) for r in rows),
    }


def portfolio_sgi_breakdown(telegram_id: int) -> list[dict[str, Any]]:
    """Current value, gain/loss and dividend totals for each SGI."""
    with db_engine.session_scope() as s:
        dividend_rows = s.execute(
            select(
                models.PortfolioDividend.sgi,
                func.sum(models.PortfolioDividend.amount),
            )
            .where(models.PortfolioDividend.telegram_id == telegram_id)
            .group_by(models.PortfolioDividend.sgi)
        ).all()
    dividends: dict[str, float] = {}
    for row in dividend_rows:
        name = row[0] or "Non affecté"
        dividends[name] = dividends.get(name, 0.0) + float(row[1] or 0)

    def _new_group(name: str) -> dict[str, Any]:
        return {
            "sgi": name,
            "positions_count": 0,
            "quantity": 0.0,
            "total_cost_fcfa": 0.0,
            "current_value_fcfa": 0.0,
            "gain_loss_fcfa": 0.0,
            "dividends_fcfa": dividends.get(name, 0.0),
        }

    groups: dict[str, dict[str, Any]] = {}
    for row in portfolio_with_prices(telegram_id):
        name = row.get("sgi") or "Non affecté"
        group = groups.setdefault(name, _new_group(name))
        group["positions_count"] += 1
        group["quantity"] += row["quantity"]
        group["total_cost_fcfa"] += row["total_cost"]
        group["current_value_fcfa"] += row["current_value_fcfa"] if row["current_value_fcfa"] is not None else row["total_cost"]
        group["gain_loss_fcfa"] += row["gain_loss_fcfa"] if row["gain_loss_fcfa"] is not None else 0
    # An SGI with dividends but no current position still gets a group:
    # otherwise its dividends vanished from the breakdown (and the
    # "Répartition par SGI" dividend view showed nothing).
    for name in dividends:
        if name not in groups:
            groups[name] = _new_group(name)
    out = []
    for group in groups.values():
        for key in ("quantity", "total_cost_fcfa", "current_value_fcfa", "gain_loss_fcfa", "dividends_fcfa"):
            group[key] = round(group[key], 2)
        group["gain_loss_pct"] = (
            round(group["gain_loss_fcfa"] / group["total_cost_fcfa"] * 100, 2)
            if group["total_cost_fcfa"]
            else None
        )
        out.append(group)
    return sorted(out, key=lambda group: group["current_value_fcfa"], reverse=True)


def portfolio_apply_import(telegram_id: int, content_hash: str, transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply one validated SGI import atomically, including buys, SGI-specific sells and dividends."""
    get_or_create_user(telegram_id)
    if len(content_hash) != 64:
        return {"ok": False, "error": "Empreinte du document invalide."}
    try:
        int(content_hash, 16)
    except ValueError:
        return {"ok": False, "error": "Empreinte du document invalide."}
    if not transactions:
        return {"ok": False, "error": "Aucune transaction à appliquer."}

    cleaned = []
    valid_symbols = get_valid_symbols()
    for candidate in transactions:
        symbol = str(candidate.get("symbol") or "").strip().upper()
        side = candidate.get("side")
        sgi = str(candidate.get("sgi") or "Non affecté").strip() or "Non affecté"
        if symbol not in valid_symbols or side not in {"buy", "sell", "dividend"}:
            return {"ok": False, "error": "Symbole ou type de transaction invalide."}
        try:
            day = date.fromisoformat(str(candidate.get("date"))[:10]).isoformat()
            if side == "dividend":
                amount = float(candidate.get("amount"))
                quantity = price = 0.0
            else:
                quantity = float(candidate.get("quantity"))
                price = float(candidate.get("price"))
                amount = quantity * price
        except (TypeError, ValueError):
            return {"ok": False, "error": "Date, quantité, prix ou montant invalide."}
        if amount <= 0 or quantity < 0 or price < 0:
            return {"ok": False, "error": "Les montants, quantités et prix doivent être positifs."}
        cleaned.append({
            "symbol": symbol,
            "side": side,
            "date": day,
            "quantity": quantity,
            "price": price,
            "amount": amount,
            "sgi": sgi,
        })
    cleaned.sort(key=lambda tx: tx["date"])

    try:
        with db_engine.session_scope() as s:
            import_result = s.execute(
                models.PortfolioImport.__table__.insert().values(
                    telegram_id=telegram_id,
                    content_hash=content_hash,
                    transactions_json=json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")),
                )
            )
            import_id = import_result.inserted_primary_key[0] if import_result.inserted_primary_key else None
            buys = 0
            sells = 0
            dividends = 0
            for tx in cleaned:
                if tx["side"] == "dividend":
                    s.execute(
                        models.PortfolioDividend.__table__.insert().values(
                            telegram_id=telegram_id,
                            import_id=import_id,
                            sgi=tx["sgi"],
                            symbol=tx["symbol"],
                            amount=tx["amount"],
                            payment_date=tx["date"],
                        )
                    )
                    dividends += 1
                    continue
                if tx["side"] == "buy":
                    s.execute(
                        models.Portfolio.__table__.insert().values(
                            telegram_id=telegram_id,
                            symbol=tx["symbol"],
                            sgi=tx["sgi"],
                            buy_price=tx["price"],
                            buy_date=tx["date"],
                            quantity=tx["quantity"],
                        )
                    )
                    buys += 1
                    continue
                remaining = tx["quantity"]
                lots = s.execute(
                    select(models.Portfolio)
                    .where(
                        models.Portfolio.telegram_id == telegram_id,
                        models.Portfolio.symbol == tx["symbol"],
                        func.coalesce(models.Portfolio.sgi, "Non affecté") == tx["sgi"],
                    )
                    .order_by(models.Portfolio.buy_date, models.Portfolio.id)
                ).scalars().all()
                for lot in lots:
                    if remaining <= 0:
                        break
                    if lot.quantity > remaining:
                        lot.quantity -= remaining
                        remaining = 0.0
                    else:
                        remaining -= lot.quantity
                        s.delete(lot)
                if remaining > 1e-9:
                    raise ValueError(f"Vente supérieure aux titres détenus pour {tx['symbol']} chez {tx['sgi']}.")
                sells += 1
        return {
            "ok": True,
            "message": "Document importé avec succès.",
            "buy_count": buys,
            "sell_count": sells,
            "dividend_count": dividends,
        }
    except IntegrityError:
        return {"ok": False, "error": "already_imported"}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "error": str(exc)}


def portfolio_history(telegram_id: int, days: int = 90, sgi: str | None = None) -> list[dict[str, Any]]:
    """Estimate daily unrealized portfolio value and cumulative dividends, optionally by SGI.

    Buy events come from the CURRENT lot rows replayed from their buy dates:
    the lots table is the single source of truth the user edits, so every
    price/date/quantity edit or deletion is reflected in the curve as-is
    (replaying the frozen import snapshots instead desynced both: quantity
    edits were ignored, price/date edits double-counted the position). A
    position whose symbol has no available close is valued at cost — the same
    fallback as portfolio_summary — so missing data never shows as an
    artificial loss.
    """
    end = date.today()
    start = end - timedelta(days=max(7, min(days, 366)) - 1)

    # Dividends: manual entries + the ones captured in imported statements.
    dividend_events = []
    with db_engine.session_scope() as s:
        imports = s.execute(
            select(models.PortfolioImport.transactions_json).where(
                models.PortfolioImport.telegram_id == telegram_id
            )
        ).scalars().all()
        manual_dividends = s.execute(
            select(models.PortfolioDividend).where(
                models.PortfolioDividend.telegram_id == telegram_id,
                models.PortfolioDividend.import_id.is_(None),
            )
        ).scalars().all()
    for raw in imports:
        try:
            transactions = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        for tx in transactions:
            if tx.get("side") != "dividend":
                continue
            try:
                day = date.fromisoformat(tx["date"][:10])
                amount = float(tx.get("amount") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if amount > 0:
                dividend_events.append({
                    "date": day,
                    "symbol": tx.get("symbol"),
                    "amount": amount,
                    "sgi": tx.get("sgi") or "Non affecté",
                })
    for row in manual_dividends:
        try:
            payment_day = date.fromisoformat(row.payment_date[:10])
        except (TypeError, ValueError):
            continue
        dividend_events.append({
            "date": payment_day,
            "symbol": row.symbol,
            "amount": float(row.amount),
            "sgi": row.sgi or "Non affecté",
        })

    buy_events = []
    for lot in portfolio_list(telegram_id):
        try:
            day = date.fromisoformat(str(lot["buy_date"])[:10])
            quantity = float(lot["quantity"])
            price = float(lot["buy_price"])
        except (KeyError, TypeError, ValueError):
            continue
        if quantity <= 0 or price < 0:
            continue
        buy_events.append({
            "date": day,
            "symbol": lot["symbol"],
            "quantity": quantity,
            "price": price,
            "sgi": lot.get("sgi") or "Non affecté",
        })
    buy_events.sort(key=lambda tx: tx["date"])

    if sgi is not None:
        buy_events = [tx for tx in buy_events if tx["sgi"] == sgi]
        dividend_events = [tx for tx in dividend_events if tx["sgi"] == sgi]
    if not buy_events and not dividend_events:
        return []
    symbols = sorted({tx["symbol"] for tx in buy_events})
    # Full local series up to today: rows before the window seed the price
    # cursor, so a stale last close still values the position instead of
    # dropping it to zero until the first in-window close.
    series = {
        symbol: load_series(symbol, None, end, fetch_if_missing=False)
        for symbol in symbols
    }
    event_dates = [tx["date"] for tx in buy_events] + [tx["date"] for tx in dividend_events]
    first_day = max(start, min(event_dates))
    trading_days = sorted({
        row["date"]
        for rows in series.values()
        for row in rows
        if first_day <= row["date"] <= end
    } | {day for day in event_dates if first_day <= day <= end}
        # Always plot the window bounds: a portfolio of illiquid stocks (no
        # close inside the window) still gets a flat line instead of an
        # empty chart.
        | {day for day in (start, end) if first_day <= day <= end})
    if not trading_days:
        return []

    holdings: dict[tuple[str, str], list[dict[str, float]]] = {}
    prices: dict[str, float] = {}
    cursors = {symbol: 0 for symbol in symbols}
    event_index = 0
    points = []
    for day in trading_days:
        while event_index < len(buy_events) and buy_events[event_index]["date"] <= day:
            tx = buy_events[event_index]
            event_index += 1
            holdings.setdefault((tx["symbol"], tx["sgi"]), []).append({
                "quantity": tx["quantity"],
                "buy_price": tx["price"],
            })
        for symbol, rows in series.items():
            cursor = cursors[symbol]
            while cursor < len(rows) and rows[cursor]["date"] <= day:
                prices[symbol] = rows[cursor]["price"]
                cursor += 1
            cursors[symbol] = cursor
        total_cost = 0.0
        total_value = 0.0
        for (symbol, _), lots in holdings.items():
            price = prices.get(symbol)
            for lot in lots:
                cost = lot["quantity"] * lot["buy_price"]
                total_cost += cost
                total_value += lot["quantity"] * price if price is not None else cost
        total_cost = round(total_cost, 2)
        total_value = round(total_value, 2)
        gain_loss = round(total_value - total_cost, 2)
        gain_pct = round(gain_loss / total_cost * 100, 2) if total_cost else None
        dividends = round(sum(tx["amount"] for tx in dividend_events if tx["date"] <= day), 2)
        points.append({
            "day": day.isoformat(),
            "total_cost_fcfa": total_cost,
            "total_value_fcfa": total_value,
            "gain_loss_fcfa": gain_loss,
            "gain_loss_pct": gain_pct,
            "dividends_fcfa": dividends,
        })
    return points


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
                models.TargetAlert.id,
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


def target_remove_by_id(telegram_id: int, alert_id: int) -> dict[str, Any]:
    """Remove one alert by id (mobile API); refuses alerts owned by others."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        res = s.execute(
            delete(models.TargetAlert).where(
                models.TargetAlert.id == alert_id,
                models.TargetAlert.telegram_id == telegram_id,
            )
        )
        if res.rowcount:
            return {"ok": True, "message": "Alerte supprimée."}
        return {"ok": False, "error": "Alerte introuvable."}


def target_update(telegram_id: int, alert_id: int, *, target_price: float | None = None, direction: str | None = None) -> dict[str, Any]:
    """Edit one alert's target price/direction (mobile API).

    Any change re-arms the alert (notified back to False): the new condition
    has not been evaluated yet.
    """
    _ensure_ready()
    values: dict[str, Any] = {}
    if target_price is not None:
        if target_price <= 0:
            return {"ok": False, "error": "Le prix cible doit être positif."}
        values["target_price"] = target_price
    if direction is not None:
        direction = direction.strip().lower()
        if direction not in ("above", "below"):
            return {"ok": False, "error": "Direction invalide (above/below)."}
        values["direction"] = direction
    if not values:
        return {"ok": False, "error": "Rien à modifier."}
    values["notified"] = False
    with db_engine.session_scope() as s:
        res = s.execute(
            update(models.TargetAlert)
            .where(models.TargetAlert.id == alert_id, models.TargetAlert.telegram_id == telegram_id)
            .values(**values)
        )
        if res.rowcount:
            return {"ok": True, "message": "Alerte mise à jour."}
        return {"ok": False, "error": "Alerte introuvable."}


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
    """Principal ids with an enabled subscription, optionally filtered by frequency."""
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


# --- AI predictions ---
def save_predictions(rows: list[dict]) -> None:
    """Persist one AI prediction per symbol for a day (default: today UTC).

    Idempotent daily write: existing rows for the same (symbol, day) are
    replaced. Row keys: symbol, direction; optional day, confidence_pct,
    expected_move_pct, price, target_low, target_high, score, signal,
    explanation, details (object) or details_json (pre-serialized string).
    """
    if not rows:
        return
    _ensure_ready()
    today = _today_utc()

    def _f(value: Any) -> float | None:
        return float(value) if value is not None else None

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
            "direction": str(r.get("direction") or ""),
            "confidence_pct": _f(r.get("confidence_pct")),
            "expected_move_pct": _f(r.get("expected_move_pct")),
            "price": _f(r.get("price")),
            "target_low": _f(r.get("target_low")),
            "target_high": _f(r.get("target_high")),
            "score": _f(r.get("score")),
            "signal": str(r.get("signal") or ""),
            "explanation": str(r.get("explanation") or ""),
            "details_json": details,
        })
    with db_engine.session_scope() as s:
        for symbol, day in {(r["symbol"], r["day"]) for r in normalized}:
            s.execute(
                delete(models.AiPrediction).where(
                    models.AiPrediction.symbol == symbol,
                    models.AiPrediction.day == day,
                )
            )
        if normalized:
            s.execute(models.AiPrediction.__table__.insert(), normalized)


_PREDICTION_COLUMNS = (
    models.AiPrediction.symbol,
    models.AiPrediction.day,
    models.AiPrediction.direction,
    models.AiPrediction.confidence_pct,
    models.AiPrediction.expected_move_pct,
    models.AiPrediction.price,
    models.AiPrediction.target_low,
    models.AiPrediction.target_high,
    models.AiPrediction.score,
    models.AiPrediction.signal,
    models.AiPrediction.explanation,
    models.AiPrediction.details_json,
    models.AiPrediction.created_at,
)


def _predictions_for_day(day: str) -> list[dict[str, Any]]:
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(*_PREDICTION_COLUMNS)
            .where(models.AiPrediction.day == day)
            .order_by(models.AiPrediction.symbol)
        ).mappings().all()
        return [dict(r) for r in rows]


def get_latest_predictions(day: str | None = None) -> list[dict[str, Any]]:
    """Predictions for `day` (default: the most recent day with data)."""
    _ensure_ready()
    if day is None:
        day = get_latest_prediction_day()
        if day is None:
            return []
    return _predictions_for_day(day)


def get_prediction(symbol: str) -> dict[str, Any] | None:
    """Most recent prediction row for one symbol (None when never computed)."""
    _ensure_ready()
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    with db_engine.session_scope() as s:
        row = s.execute(
            select(*_PREDICTION_COLUMNS)
            .where(models.AiPrediction.symbol == sym)
            .order_by(models.AiPrediction.day.desc())
        ).mappings().first()
        return dict(row) if row else None


def get_latest_prediction_day() -> str | None:
    """Most recent day with predictions (None when never computed)."""
    _ensure_ready()
    with db_engine.session_scope() as s:
        return s.execute(select(func.max(models.AiPrediction.day))).scalar()

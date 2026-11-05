"""Admin dashboard backend (app.api.admin): env-credential sessions, platform
metrics and user management.

All reads/writes go through the shared user DB (app.db) and work on both
SQLite and PostgreSQL. Usage history comes from usage_daily (kept ~90 days by
app.utils.user_db); signups from app_users.created_at. There is no acquisition
source tracking in the product — the dashboard exposes signup/platform trends
as the available proxies.
"""
from __future__ import annotations

import hmac
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from sqlalchemy import delete, distinct, func, select, update

import config
from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models

logger = logging.getLogger(__name__)

_ALGO = "HS256"
_TOKEN_TYPE = "admin"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Admin sessions ------------------------------------------------------------

def admin_enabled() -> bool:
    """The dashboard needs env credentials and a JWT secret to sign sessions."""
    return bool(config.ADMIN_PASSWORD and config.JWT_SECRET)


def login(username: str, password: str) -> dict[str, Any] | None:
    """Verify the env credentials (constant-time) and mint a session token."""
    if not admin_enabled():
        return None
    ok = hmac.compare_digest((username or "").strip(), config.ADMIN_USERNAME) & hmac.compare_digest(
        password or "", config.ADMIN_PASSWORD
    )
    if not ok:
        return None
    now = _utcnow()
    ttl = config.ADMIN_TOKEN_TTL_SECONDS
    token = jwt.encode(
        {
            "sub": config.ADMIN_USERNAME,
            "typ": _TOKEN_TYPE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
            "jti": secrets.token_hex(16),
        },
        config.JWT_SECRET,
        algorithm=_ALGO,
    )
    return {"token": token, "token_type": "bearer", "expires_in": ttl}


def authenticate_token(token: str) -> bool:
    if not admin_enabled():
        return False
    try:
        payload = jwt.decode((token or "").strip(), config.JWT_SECRET, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return False
    return payload.get("typ") == _TOKEN_TYPE


# --- Metrics -------------------------------------------------------------------

def _scalar(session, stmt) -> int:
    return int(session.execute(stmt).scalar_one() or 0)


def overview() -> dict[str, Any]:
    """Platform snapshot: users, activity, feature adoption, system health.

    The 7-day metrics also carry the previous 7-day window (``*_prev_7d``) so
    the dashboard can show week-over-week deltas. Adoption counts are restricted
    to principals that exist in app_users — legacy rows (pre-mobile bot) would
    otherwise push percentages above 100%."""
    db_migrate.ensure_schema()
    now = _utcnow()
    today = now.date()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    day7_str = (today - timedelta(days=6)).isoformat()   # inclusive 7-day window
    day30_str = (today - timedelta(days=29)).isoformat()
    prev7_start_str = (today - timedelta(days=13)).isoformat()
    prev7_end_str = (today - timedelta(days=7)).isoformat()
    new7_from = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    new30_from = datetime.combine(today - timedelta(days=29), datetime.min.time(), tzinfo=timezone.utc)
    prev7_from = datetime.combine(today - timedelta(days=13), datetime.min.time(), tzinfo=timezone.utc)
    active_thread_cutoff = time.time() - 24 * 3600

    U = models.AppUser
    with db_engine.session_scope() as s:
        total_users = _scalar(s, select(func.count()).select_from(U))
        users = {
            "total": total_users,
            "active": _scalar(s, select(func.count()).select_from(U).where(U.is_active == 1)),
            "deactivated": _scalar(s, select(func.count()).select_from(U).where(U.is_active != 1)),
            "new_7d": _scalar(s, select(func.count()).select_from(U).where(U.created_at >= new7_from)),
            "new_prev_7d": _scalar(s, select(func.count()).select_from(U).where(
                U.created_at >= prev7_from, U.created_at < new7_from)),
            "new_30d": _scalar(s, select(func.count()).select_from(U).where(U.created_at >= new30_from)),
            "with_email": _scalar(s, select(func.count()).select_from(U).where(U.email.is_not(None))),
            "with_phone": _scalar(s, select(func.count()).select_from(U).where(U.phone.is_not(None))),
            "with_password": _scalar(s, select(func.count()).select_from(U).where(U.password_hash.is_not(None))),
            "live_sessions": _scalar(
                s,
                select(func.count(distinct(models.RefreshToken.user_id))).where(
                    models.RefreshToken.revoked == 0,
                    models.RefreshToken.expires_at > now,
                ),
            ),
        }

        D = models.UsageDaily
        messages_today = _scalar(
            s, select(func.coalesce(func.sum(D.count), 0)).where(D.day == today_str)
        )
        dau_today = _scalar(
            s, select(func.count(distinct(D.user_id))).where(D.day == today_str, D.count > 0)
        )
        dau_yesterday = _scalar(
            s, select(func.count(distinct(D.user_id))).where(D.day == yesterday_str, D.count > 0)
        )
        messages_yesterday = _scalar(
            s, select(func.coalesce(func.sum(D.count), 0)).where(D.day == yesterday_str)
        )
        wau = _scalar(
            s, select(func.count(distinct(D.user_id))).where(D.day >= day7_str, D.count > 0)
        )
        wau_prev = _scalar(
            s, select(func.count(distinct(D.user_id))).where(
                D.day >= prev7_start_str, D.day <= prev7_end_str, D.count > 0)
        )
        mau = _scalar(
            s, select(func.count(distinct(D.user_id))).where(D.day >= day30_str, D.count > 0)
        )
        messages_7d = _scalar(
            s, select(func.coalesce(func.sum(D.count), 0)).where(D.day >= day7_str)
        )
        messages_prev_7d = _scalar(
            s, select(func.coalesce(func.sum(D.count), 0)).where(
                D.day >= prev7_start_str, D.day <= prev7_end_str)
        )
        messages_30d = _scalar(
            s, select(func.coalesce(func.sum(D.count), 0)).where(D.day >= day30_str)
        )
        activity = {
            "day": today_str,
            "dau_today": dau_today,
            "dau_yesterday": dau_yesterday,
            "messages_today": messages_today,
            "messages_yesterday": messages_yesterday,
            "wau_7d": wau,
            "wau_prev_7d": wau_prev,
            "mau_30d": mau,
            "messages_7d": messages_7d,
            "messages_prev_7d": messages_prev_7d,
            "messages_30d": messages_30d,
            # DAU/WAU ("stickiness") — None until a full week of data exists.
            "stickiness": round(dau_today / wau, 3) if wau else None,
        }

        T = models.ThreadActivity
        conversations = {
            "total_threads": _scalar(s, select(func.count()).select_from(T)),
            "active_24h": _scalar(
                s, select(func.count()).select_from(T).where(T.last_seen >= active_thread_cutoff)
            ),
        }

        Dev = models.Device
        platform_rows = s.execute(
            select(Dev.platform, func.count()).group_by(Dev.platform)
        ).all()
        devices = {"total": sum(int(c) for _, c in platform_rows)}
        for platform, count in platform_rows:
            devices[str(platform)] = int(count)

        P, W, A, G = models.Portfolio, models.Tracking, models.TargetAlert, models.DigestSubscription
        app_principals = select(U.principal_id)
        features = {
            "portfolio_users": _scalar(s, select(func.count(distinct(P.telegram_id))).where(
                P.telegram_id.in_(app_principals))),
            "portfolio_lots": _scalar(s, select(func.count()).select_from(P)),
            "watchlist_users": _scalar(s, select(func.count(distinct(W.telegram_id))).where(
                W.telegram_id.in_(app_principals))),
            "watchlist_items": _scalar(s, select(func.count()).select_from(W)),
            "alert_users": _scalar(s, select(func.count(distinct(A.telegram_id))).where(
                A.telegram_id.in_(app_principals))),
            "alerts_pending": _scalar(s, select(func.count()).select_from(A).where(A.notified == 0)),
            "digest_users": _scalar(s, select(func.count()).select_from(G).where(
                G.enabled == 1, G.telegram_id.in_(app_principals))),
        }

        top_symbols = [
            {"symbol": sym, "watchers": int(n)}
            for sym, n in s.execute(
                select(W.symbol, func.count())
                .group_by(W.symbol)
                .order_by(func.count().desc())
                .limit(8)
            ).all()
        ]

        system = {
            "db": db_engine.get_engine().dialect.name,
            "market_snapshot_day": s.execute(select(func.max(models.MarketSnapshot.day))).scalar_one_or_none(),
            "predictions_day": s.execute(select(func.max(models.AiPrediction.day))).scalar_one_or_none(),
            "scores_day": s.execute(select(func.max(models.ScoreSnapshot.day))).scalar_one_or_none(),
            "daily_quota": config.DAILY_FREE_QUOTA,
            "quota_exempt_count": len(config.QUOTA_EXEMPT_IDS),
        }

    return {"generated_at": now.isoformat(), "users": users, "activity": activity,
            "conversations": conversations, "devices": devices, "features": features,
            "top_symbols": top_symbols, "system": system}


def timeseries(days: int = 30) -> dict[str, Any]:
    """Daily buckets for the dashboard charts: signups, messages, active users.

    usage_daily only retains ~90 days, so history starts at the deploy of this
    change; missing days are zero-filled."""
    days = max(7, min(int(days), 90))
    db_migrate.ensure_schema()
    today = _utcnow().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    buckets = [(start + timedelta(days=i)).isoformat() for i in range(days)]

    with db_engine.session_scope() as s:
        signup_rows = s.execute(
            select(func.date(models.AppUser.created_at), func.count())
            .where(models.AppUser.created_at >= start_dt)
            .group_by(func.date(models.AppUser.created_at))
        ).all()
        signups = {str(day): int(n) for day, n in signup_rows}

        D = models.UsageDaily
        usage_rows = s.execute(
            select(D.day, func.coalesce(func.sum(D.count), 0), func.count(distinct(D.user_id)))
            .where(D.day >= start.isoformat())
            .group_by(D.day)
        ).all()

    messages = {str(day): int(total) for day, total, _ in usage_rows}
    dau = {str(day): int(users) for day, _, users in usage_rows}
    return {
        "days": buckets,
        "signups": [signups.get(day, 0) for day in buckets],
        "messages": [messages.get(day, 0) for day in buckets],
        "active_users": [dau.get(day, 0) for day in buckets],
    }


# --- User management -----------------------------------------------------------

_PAGE_SIZE_MAX = 100


def _usage_keys(user_ids: list[uuid.UUID]) -> list[str]:
    return [f"app:{uid}" for uid in user_ids]


def list_users(q: str | None, page: int, page_size: int, status: str = "all", sort: str = "created_at") -> dict[str, Any]:
    """Paginated user list with per-user 30d usage summary.

    ``sort="created_at"`` paginates in SQL; the usage-based sorts
    (``last_active``/``messages``) need per-user aggregates, so they sort
    in Python after computing them — fine at admin-dashboard scale."""
    db_migrate.ensure_schema()
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), _PAGE_SIZE_MAX))
    U = models.AppUser
    today_str = _utcnow().date().isoformat()
    day30_str = (_utcnow().date() - timedelta(days=29)).isoformat()

    with db_engine.session_scope() as s:
        stmt = select(U)
        if status == "active":
            stmt = stmt.where(U.is_active == 1)
        elif status == "deactivated":
            stmt = stmt.where(U.is_active != 1)
        if q and q.strip():
            term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{term}%"
            stmt = stmt.where(
                (U.email.ilike(like, escape="\\"))
                | (U.phone.ilike(like, escape="\\"))
                | (U.display_name.ilike(like, escape="\\"))
            )
        total = _scalar(s, select(func.count()).select_from(stmt.subquery()))
        if sort == "created_at":
            rows = (
                s.execute(
                    stmt.order_by(U.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .scalars()
                .all()
            )
        else:
            rows = s.execute(stmt).scalars().all()
        if not rows:
            return {"total": total, "page": page, "page_size": page_size, "users": []}

        ids = [r.id for r in rows]
        keys = _usage_keys(ids)
        D = models.UsageDaily
        usage = {
            r.user_id: (int(r.total), str(r.last_day))
            for r in s.execute(
                select(
                    D.user_id,
                    func.coalesce(func.sum(D.count), 0).label("total"),
                    func.max(D.day).label("last_day"),
                )
                .where(D.user_id.in_(keys), D.day >= day30_str)
                .group_by(D.user_id)
            )
        }
        today_usage = {
            r.user_id: int(r.total)
            for r in s.execute(
                select(D.user_id, func.coalesce(func.sum(D.count), 0).label("total"))
                .where(D.user_id.in_(keys), D.day == today_str)
                .group_by(D.user_id)
            )
        }
        device_counts = {
            r.user_id: int(r.n)
            for r in s.execute(
                select(models.Device.user_id, func.count().label("n"))
                .where(models.Device.user_id.in_(ids))
                .group_by(models.Device.user_id)
            )
        }

    if sort == "messages":
        rows.sort(
            key=lambda r: (usage.get(f"app:{r.id}", (0, None))[0], r.created_at or datetime.min),
            reverse=True,
        )
    elif sort == "last_active":
        # Users with no recorded activity sink to the bottom ("" sorts lowest).
        rows.sort(
            key=lambda r: (usage.get(f"app:{r.id}", (0, None))[1] or "", r.created_at or datetime.min),
            reverse=True,
        )
    if sort != "created_at":
        rows = rows[(page - 1) * page_size: page * page_size]

    users = []
    for r in rows:
        key = f"app:{r.id}"
        msgs30, last_day = usage.get(key, (0, None))
        users.append({
            "id": str(r.id),
            "principal_id": r.principal_id,
            "display_name": r.display_name,
            "email": r.email,
            "phone": r.phone,
            "is_active": bool(r.is_active),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_active_day": last_day,
            "messages_30d": msgs30,
            "quota_used_today": today_usage.get(key, 0),
            "devices": device_counts.get(r.id, 0),
        })
    return {"total": total, "page": page, "page_size": page_size, "users": users}


def get_user(user_id: uuid.UUID) -> dict[str, Any] | None:
    """Full admin view of one account: profile, usage, feature footprint."""
    db_migrate.ensure_schema()
    U = models.AppUser
    today_str = _utcnow().date().isoformat()
    day7_str = (_utcnow().date() - timedelta(days=6)).isoformat()
    day30_str = (_utcnow().date() - timedelta(days=29)).isoformat()

    with db_engine.session_scope() as s:
        row = s.execute(select(U).where(U.id == user_id)).scalars().first()
        if row is None:
            return None
        key = f"app:{row.id}"
        pid = row.principal_id

        D = models.UsageDaily
        usage_rows = s.execute(
            select(D.day, D.count).where(D.user_id == key, D.day >= day30_str)
        ).all()
        by_day = {str(day): int(n) for day, n in usage_rows}
        usage = {
            "today": by_day.get(today_str, 0),
            "last_7d": sum(n for day, n in by_day.items() if day >= day7_str),
            "last_30d": sum(by_day.values()),
            "last_active_day": max(by_day) if by_day else None,
            "daily": [{"day": day, "count": by_day[day]} for day in sorted(by_day)],
        }

        devices = [
            {"platform": d.platform, "updated_at": d.updated_at.isoformat() if d.updated_at else None}
            for d in s.execute(
                select(models.Device).where(models.Device.user_id == row.id)
            ).scalars().all()
        ]

        count = lambda stmt: _scalar(s, stmt)  # noqa: E731 - tiny local helper
        threads = s.execute(
            select(func.count(), func.max(models.ThreadActivity.last_seen)).where(
                (models.ThreadActivity.thread_id == key)
                | models.ThreadActivity.thread_id.like(key + ":%")
            )
        ).one()
        digest = s.execute(
            select(models.DigestSubscription).where(models.DigestSubscription.telegram_id == pid)
        ).scalars().first()

        return {
            "id": str(row.id),
            "principal_id": pid,
            "display_name": row.display_name,
            "email": row.email,
            "phone": row.phone,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "has_password": row.password_hash is not None,
            "has_photo": row.photo_path is not None,
            "quota_exempt": key in config.QUOTA_EXEMPT_IDS,
            "usage": usage,
            "devices": devices,
            "sessions_live": count(
                select(func.count()).select_from(models.RefreshToken).where(
                    models.RefreshToken.user_id == row.id,
                    models.RefreshToken.revoked == 0,
                    models.RefreshToken.expires_at > _utcnow(),
                )
            ),
            "portfolio": {
                "lots": count(select(func.count()).select_from(models.Portfolio).where(models.Portfolio.telegram_id == pid)),
                "positions": count(select(func.count(distinct(models.Portfolio.symbol))).where(models.Portfolio.telegram_id == pid)),
                "imports": count(select(func.count()).select_from(models.PortfolioImport).where(models.PortfolioImport.telegram_id == pid)),
            },
            "watchlist": count(select(func.count()).select_from(models.Tracking).where(models.Tracking.telegram_id == pid)),
            "alerts": {
                "total": count(select(func.count()).select_from(models.TargetAlert).where(models.TargetAlert.telegram_id == pid)),
                "pending": count(select(func.count()).select_from(models.TargetAlert).where(
                    models.TargetAlert.telegram_id == pid, models.TargetAlert.notified == 0)),
            },
            "digest": None if digest is None else {"enabled": bool(digest.enabled), "frequency": digest.frequency},
            "threads": {
                "count": int(threads[0] or 0),
                "last_seen": float(threads[1]) if threads[1] else None,
            },
        }


def set_user_active(user_id: uuid.UUID, active: bool) -> bool:
    """Activate/deactivate an account. Deactivation revokes live sessions and
    blocks new logins (is_active is enforced in auth_service); reactivation
    restores login. Returns False when the user does not exist."""
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        res = s.execute(
            update(models.AppUser)
            .where(models.AppUser.id == user_id)
            .values(is_active=1 if active else 0)
        )
        if not res.rowcount:
            return False
        if not active:
            s.execute(
                update(models.RefreshToken)
                .where(models.RefreshToken.user_id == user_id, models.RefreshToken.revoked == 0)
                .values(revoked=1)
            )
    logger.info("Admin %s user %s", "activated" if active else "deactivated", user_id)
    return True


def reset_user_quota(user_id: uuid.UUID) -> int | None:
    """Clear today's chat-usage counter for the user. Rows deleted, or None
    when the user does not exist."""
    db_migrate.ensure_schema()
    today_str = _utcnow().date().isoformat()
    with db_engine.session_scope() as s:
        exists = s.execute(
            select(models.AppUser.id).where(models.AppUser.id == user_id)
        ).first()
        if exists is None:
            return None
        res = s.execute(
            delete(models.UsageDaily).where(
                models.UsageDaily.user_id == f"app:{user_id}",
                models.UsageDaily.day == today_str,
            )
        )
    logger.info("Admin reset daily quota for user %s", user_id)
    return int(res.rowcount or 0)


def delete_user(user_id: uuid.UUID) -> bool:
    """Permanently delete the account and all its data (full purge, same as the
    in-app account deletion). Returns False when the user does not exist."""
    from app.services import auth_service

    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        exists = s.execute(
            select(models.AppUser.id).where(models.AppUser.id == user_id)
        ).first()
    if exists is None:
        return False
    result = auth_service.delete_app_user({"id": user_id}, skip_password_check=True)
    if result.get("ok"):
        logger.info("Admin deleted user %s", user_id)
    return bool(result.get("ok"))

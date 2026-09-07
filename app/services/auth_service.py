"""Mobile app auth: OTP codes (email/SMS), JWT access/refresh tokens, and
app-user identity. The mobile API (app.api.mobile*) builds on this module.

Identity model: an AppUser owns a ``principal_id`` integer that doubles as the
``telegram_id`` key across the legacy user tables (see app.db.models.AppUser).
App-only users get a synthetic negative principal id; linked users share their
real Telegram id, so portfolio/watchlist/alerts are shared between the bot and
the app for the same person.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from sqlalchemy import delete, select, update

import config
from app.db import engine as db_engine
from app.db import models
from app.db import migrate as db_migrate

logger = logging.getLogger(__name__)

_ALGO = "HS256"
_PURPOSE_LOGIN = "login"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def auth_enabled() -> bool:
    """Mobile auth requires a configured JWT secret."""
    return bool(config.JWT_SECRET)


def _hash(secret_material: str) -> str:
    """HMAC-SHA256 with the server secret — codes/tokens are stored hashed."""
    return hmac.new(
        config.JWT_SECRET.encode(), secret_material.encode(), hashlib.sha256
    ).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# --- Identifier handling -----------------------------------------------------

def classify_identifier(identifier: str) -> tuple[str, str] | None:
    """Normalize an email or E.164 phone. Returns (channel, normalized) or None."""
    ident = (identifier or "").strip()
    if EMAIL_RE.match(ident):
        return "email", ident.lower()
    digits = re.sub(r"[\s().-]", "", ident)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if re.match(r"^\+[1-9]\d{7,14}$", digits):
        return "phone", digits
    return None


# --- OTP codes ---------------------------------------------------------------

def _latest_otp(identifier: str) -> models.OtpCode | None:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        return s.execute(
            select(models.OtpCode)
            .where(models.OtpCode.identifier == identifier)
            .order_by(models.OtpCode.id.desc())
            .limit(1)
        ).scalars().first()


def request_code(identifier: str) -> dict[str, Any]:
    """Issue a login code for an email/phone. Returns {ok, channel, dev_code?}."""
    if not auth_enabled():
        return {"ok": False, "error": "auth_disabled"}
    classified = classify_identifier(identifier)
    if not classified:
        return {"ok": False, "error": "Format invalide. Utilisez un email ou un numéro (+225...)."}
    channel, ident = classified

    latest = _latest_otp(ident)
    if latest is not None:
        age = (_utcnow() - _as_utc(latest.created_at)).total_seconds()
        if (
            latest.consumed_at is None
            and age < config.OTP_RESEND_COOLDOWN_SECONDS
            and _as_utc(latest.expires_at) > _utcnow()
        ):
            return {"ok": False, "error": "retry_later", "retry_after_seconds": int(config.OTP_RESEND_COOLDOWN_SECONDS - age)}

    code = f"{secrets.randbelow(1_000_000):06d}"
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.add(models.OtpCode(
            identifier=ident,
            channel=channel,
            code_hash=_hash(code),
            purpose=_PURPOSE_LOGIN,
            expires_at=_utcnow() + timedelta(seconds=config.OTP_TTL_SECONDS),
        ))
    sent = _deliver_code(channel, ident, code)
    if not sent:
        return {"ok": False, "error": "delivery_failed"}
    result: dict[str, Any] = {"ok": True, "channel": channel}
    if config.AUTH_PROVIDER == "mock":
        result["dev_code"] = code  # dev/tests only; never set AUTH_PROVIDER=mock in prod
    return result


def _deliver_code(channel: str, ident: str, code: str) -> bool:
    from app.services.otp_delivery import deliver_otp

    try:
        return deliver_otp(channel, ident, code)
    except Exception:
        logger.exception("OTP delivery failed (%s)", channel)
        return False


def verify_code(identifier: str, code: str) -> dict[str, Any]:
    """Validate a login code; on success return {ok, user} and consume the code."""
    if not auth_enabled():
        return {"ok": False, "error": "auth_disabled"}
    classified = classify_identifier(identifier)
    if not classified:
        return {"ok": False, "error": "code_invalid"}
    _, ident = classified

    row = _latest_otp(ident)
    now = _utcnow()
    if (
        row is None
        or row.purpose != _PURPOSE_LOGIN
        or row.consumed_at is not None
        or _as_utc(row.expires_at) <= now
        or row.attempts >= config.OTP_MAX_ATTEMPTS
    ):
        return {"ok": False, "error": "code_invalid"}

    if not hmac.compare_digest(row.code_hash, _hash(code.strip())):
        with db_engine.session_scope() as s:
            s.execute(
                update(models.OtpCode)
                .where(models.OtpCode.id == row.id)
                .values(attempts=models.OtpCode.attempts + 1)
            )
        return {"ok": False, "error": "code_invalid"}

    with db_engine.session_scope() as s:
        s.execute(
            update(models.OtpCode)
            .where(models.OtpCode.id == row.id)
            .values(consumed_at=now)
        )
    user = get_or_create_app_user(**{row.channel: ident})
    if user is None:
        return {"ok": False, "error": "user_error"}
    return {"ok": True, "user": user}


# --- App users ---------------------------------------------------------------

def _new_principal_id() -> int:
    """Synthetic negative id; Telegram ids are always positive so no collision."""
    db_migrate.ensure_schema()
    for _ in range(20):
        candidate = -(10**12) - secrets.randbelow(9 * 10**12)
        with db_engine.session_scope() as s:
            clash = s.execute(
                select(models.AppUser.principal_id).where(
                    models.AppUser.principal_id == candidate
                )
            ).first()
            clash_legacy = s.execute(
                select(models.User.telegram_id).where(models.User.telegram_id == candidate)
            ).first()
        if clash is None and clash_legacy is None:
            return candidate
    raise RuntimeError("Could not allocate a principal id")


def _fetch_app_user(email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
    db_migrate.ensure_schema()
    stmt = select(models.AppUser).where(
        models.AppUser.is_active == 1,
        models.AppUser.email == email if email else models.AppUser.phone == phone,
    )
    with db_engine.session_scope() as s:
        row = s.execute(stmt).scalars().first()
        return _user_dict(row) if row else None


def _user_dict(row: models.AppUser) -> dict[str, Any]:
    return {
        "id": row.id,
        "principal_id": row.principal_id,
        "email": row.email,
        "phone": row.phone,
        "telegram_id": row.telegram_id,
        # Boolean only — the hash itself must never leave this module.
        "has_password": row.password_hash is not None,
    }


def get_or_create_app_user(email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
    """Find (or create) the app user for an email/phone.

    Account merging (linking an app account to an existing Telegram identity by
    phone/email) is a post-v1 flow; app users today always get a fresh synthetic
    principal id, so bot and app data stay separate until linked.
    """
    existing = _fetch_app_user(email=email, phone=phone)
    if existing:
        return existing

    db_migrate.ensure_schema()
    user = models.AppUser(
        id=uuid.uuid4(),
        principal_id=_new_principal_id(),
        email=email,
        phone=phone,
        telegram_id=None,
    )
    with db_engine.session_scope() as s:
        s.add(user)
        try:
            s.commit()
        except Exception:
            s.rollback()
            # Lost a create race: re-fetch the winner.
            return _fetch_app_user(email=email, phone=phone)
    return _user_dict(user)


def get_app_user_by_id(user_id: uuid.UUID) -> dict[str, Any] | None:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        row = s.execute(
            select(models.AppUser).where(models.AppUser.id == user_id)
        ).scalars().first()
        return _user_dict(row) if row else None


def delete_app_user(user: dict[str, Any], password: str | None = None) -> dict[str, Any]:
    """Delete an app account and every row it owns, in one transaction.

    Accounts with a password must confirm it (``wrong_password`` otherwise);
    passwordless accounts (demo/mock) delete without one. LangGraph
    checkpoints live outside this DB and are purged best-effort afterwards —
    their failure never rolls the account deletion back. DB purge errors may
    propagate.
    """
    db_migrate.ensure_schema()
    thread_ids: list[str] = []
    with db_engine.session_scope() as s:
        row = s.execute(
            select(models.AppUser).where(models.AppUser.id == user["id"])
        ).scalars().first()
        if row is None:
            return {"ok": True}  # already gone: deletion is idempotent
        if row.password_hash is not None and (
            not password or not verify_password(password, row.password_hash)
        ):
            return {"ok": False, "error": "wrong_password"}

        user_id = row.id
        principal_id = row.principal_id
        identifiers = [v for v in (row.email, row.phone) if v]
        prefix = f"app:{user_id}"
        thread_match = (models.ThreadActivity.thread_id == prefix) | (
            models.ThreadActivity.thread_id.like(prefix + ":%")
        )
        thread_ids = list(
            s.execute(
                select(models.ThreadActivity.thread_id).where(thread_match)
            ).scalars().all()
        )
        # FK-referenced children first, the app_users row last.
        s.execute(delete(models.RefreshToken).where(models.RefreshToken.user_id == user_id))
        s.execute(delete(models.Device).where(models.Device.user_id == user_id))
        for model in (
            models.Portfolio,
            models.Tracking,
            models.TargetAlert,
            models.DigestSubscription,
            models.User,
        ):
            s.execute(delete(model).where(model.telegram_id == principal_id))
        s.execute(delete(models.UsageDaily).where(models.UsageDaily.user_id == prefix))
        s.execute(delete(models.ThreadActivity).where(thread_match))
        if identifiers:
            s.execute(delete(models.OtpCode).where(models.OtpCode.identifier.in_(identifiers)))
        s.execute(delete(models.AppUser).where(models.AppUser.id == user_id))

    if thread_ids:
        try:
            from app.api.chat import _get_checkpointer  # lazy: avoid circulars

            checkpointer = _get_checkpointer()
            for tid in thread_ids:
                try:
                    checkpointer.delete_thread(tid)
                except Exception:
                    logger.warning("checkpoint purge failed for thread %s", tid, exc_info=True)
        except Exception:
            logger.warning("checkpointer unavailable during account deletion", exc_info=True)
    return {"ok": True}


# --- JWT access/refresh tokens ------------------------------------------------

def _encode_token(claims: dict[str, Any], ttl: int) -> str:
    now = _utcnow()
    payload = {**claims, "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=ttl)).timestamp()), "jti": secrets.token_hex(16)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGO)


def _decode_token(token: str, expected_type: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload


def issue_tokens(user: dict[str, Any]) -> dict[str, Any]:
    """Fresh access+refresh token pair for an app user (refresh is persisted,
    hashed, so it can be revoked by rotating/replacing it)."""
    access = _encode_token(
        {"sub": str(user["id"]), "pid": user["principal_id"], "typ": "access"},
        config.JWT_ACCESS_TTL_SECONDS,
    )
    refresh_plain = secrets.token_urlsafe(48)
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.add(models.RefreshToken(
            user_id=user["id"],
            token_hash=_hash(refresh_plain),
            expires_at=_utcnow() + timedelta(seconds=config.JWT_REFRESH_TTL_SECONDS),
        ))
        # Housekeeping: drop expired/revoked tokens for this user.
        s.execute(
            delete(models.RefreshToken).where(
                models.RefreshToken.user_id == user["id"],
                (models.RefreshToken.revoked == 1)
                | (models.RefreshToken.expires_at <= _utcnow()),
            )
        )
    return {
        "access_token": access,
        "access_expires_in": config.JWT_ACCESS_TTL_SECONDS,
        "refresh_token": refresh_plain,
        "refresh_expires_in": config.JWT_REFRESH_TTL_SECONDS,
        "token_type": "bearer",
    }


def refresh_tokens(refresh_token: str) -> dict[str, Any] | None:
    """Validate a refresh token, rotate it, and return a new pair (or None)."""
    if not auth_enabled():
        return None
    token_hash = _hash(refresh_token.strip())
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        row = s.execute(
            select(models.RefreshToken).where(
                models.RefreshToken.token_hash == token_hash
            )
        ).scalars().first()
        if (
            row is None
            or row.revoked
            or _as_utc(row.expires_at) <= _utcnow()
        ):
            return None
        s.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.id == row.id)
            .values(revoked=1)
        )
    user = get_app_user_by_id(row.user_id)
    if user is None or not user.get("principal_id"):
        return None
    return issue_tokens(user)


def revoke_refresh_token(refresh_token: str) -> None:
    token_hash = _hash(refresh_token.strip())
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.token_hash == token_hash)
            .values(revoked=1)
        )


def authenticate_access_token(token: str) -> dict[str, Any] | None:
    """Resolve a bearer access token to an app user (None when invalid)."""
    payload = _decode_token(token.strip(), "access")
    if payload is None:
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = get_app_user_by_id(user_id)
    if user is None or user.get("principal_id") != payload.get("pid"):
        return None
    return user


# --- Password auth (scrypt, stdlib) -------------------------------------------

PASSWORD_MIN_LENGTH = config.PASSWORD_MIN_LENGTH

_SCRYPT_N = 2 ** 14


def hash_password(password: str) -> str:
    """scrypt salted hash, stored as 'salt$hash'."""
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=_SCRYPT_N, r=8, p=1
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    try:
        candidate = hashlib.scrypt(
            password.encode(), salt=salt.encode(), n=_SCRYPT_N, r=8, p=1
        ).hex()
    except Exception:
        return False
    return hmac.compare_digest(candidate, digest)


def set_user_password(user_id: uuid.UUID, password: str) -> None:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.execute(
            update(models.AppUser)
            .where(models.AppUser.id == user_id)
            .values(password_hash=hash_password(password))
        )


def find_user_by_identifier(identifier: str) -> dict[str, Any] | None:
    """Look up an app user by email or phone (normalized)."""
    classified = classify_identifier(identifier)
    if not classified:
        return None
    channel, ident = classified
    return _fetch_app_user(email=ident if channel == "email" else None,
                           phone=ident if channel == "phone" else None)


def register_user(identifier: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
    """Create a local account (email or phone + password). Returns (user, None)
    or (None, error_code) with 'exists' | 'invalid_identifier' | 'weak_password'."""
    if len(password or "") < PASSWORD_MIN_LENGTH:
        return None, "weak_password"
    existing = find_user_by_identifier(identifier)
    if existing is not None:
        return None, "exists"
    classified = classify_identifier(identifier)
    if not classified:
        return None, "invalid_identifier"
    channel, ident = classified
    user = get_or_create_app_user(email=ident if channel == "email" else None,
                                  phone=ident if channel == "phone" else None)
    if user is None:
        return None, "invalid_identifier"
    set_user_password(user["id"], password)
    # The dict above was built before the password was set; keep it accurate.
    user["has_password"] = True
    return user, None


def authenticate_user(identifier: str, password: str) -> dict[str, Any] | None:
    """Login: find the user, check the password (constant-time)."""
    user = find_user_by_identifier(identifier)
    if user is None:
        # Burn comparable time against the scrypt cost to blunt user probing.
        hashlib.scrypt(password.encode(), salt=b"0" * 32, n=_SCRYPT_N, r=8, p=1)
        return None
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        stored = s.execute(
            select(models.AppUser.password_hash).where(models.AppUser.id == user["id"])
        ).scalar()
    if not verify_password(password, stored):
        return None
    return user


# --- Devices (FCM push tokens) -------------------------------------------------

def register_device(user_id: uuid.UUID, fcm_token: str, platform: str) -> None:
    """Upsert a device token; a token is reassigned when it moves between users."""
    db_migrate.ensure_schema()
    platform = platform if platform in ("android", "ios") else "android"
    with db_engine.session_scope() as s:
        existing = s.execute(
            select(models.Device).where(models.Device.fcm_token == fcm_token)
        ).scalars().first()
        if existing is not None:
            existing.user_id = user_id
            existing.platform = platform
            existing.updated_at = _utcnow()
            return
        s.add(models.Device(user_id=user_id, fcm_token=fcm_token, platform=platform))


def remove_device(fcm_token: str) -> bool:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        res = s.execute(delete(models.Device).where(models.Device.fcm_token == fcm_token))
        return bool(res.rowcount)


def devices_for_principal(principal_id: int) -> list[dict[str, Any]]:
    """FCM tokens of every app user linked to this principal id (usually one)."""
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(models.Device.fcm_token, models.Device.platform)
            .join(models.AppUser, models.AppUser.id == models.Device.user_id)
            .where(models.AppUser.principal_id == principal_id)
        ).mappings().all()
        return [dict(r) for r in rows]

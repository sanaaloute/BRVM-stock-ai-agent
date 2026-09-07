"""Declarative models for the user database (BRVM bot).

Schema matches the legacy hand-rolled DDL exactly (table/column names, uniques,
FKs, partial index) so existing SQLite/PostgreSQL databases are adopted as-is
by migration 0001. String columns are Text (legacy PostgreSQL used TEXT).

Mobile app identity: every app user (see AppUser) owns a *principal id* — an
integer used as the ``telegram_id`` key across the legacy tables. When the
account is linked to a real Telegram account the principal id IS the Telegram
id; app-only users get a synthetic negative id (real Telegram ids are always
positive, so the namespaces never collide). Legacy helpers in
app.utils.user_db therefore work unchanged for mobile users.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Rowid-alias PK on SQLite (INTEGER PRIMARY KEY), BIGSERIAL on PostgreSQL.
_pk_int = BigInteger().with_variant(Integer, "sqlite")
# Legacy users.telegram_id: INTEGER on SQLite, BIGINT on PostgreSQL.
_telegram_id_type = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    """Mobile app user. ``principal_id`` is the integer identity key used across
    the legacy user tables (telegram_id column): the real Telegram id when
    linked, a synthetic negative id for app-only users."""

    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    principal_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    # Real linked Telegram id (== principal_id when linked); NULL for app-only.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    # Password auth (scrypt, "salt$hash"); NULL until the user sets one. OTP
    # codes remain available as an alternative once delivery is configured.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OtpCode(Base):
    """One-time login codes (email or SMS). Codes are stored hashed."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)  # normalized email/phone
    channel: Mapped[str] = mapped_column(Text, nullable=False)  # 'email' | 'phone'
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="login")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RefreshToken(Base):
    """Hashed refresh tokens for the mobile app (revocable)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Device(Base):
    """FCM-registered mobile devices (push notifications)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_users.id"), nullable=False
    )
    fcm_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)  # 'android' | 'ios'
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(_telegram_id_type, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Added by a later ALTER in the legacy code: TEXT on both backends.
    help_sent_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class Portfolio(Base):
    """Portfolio buy lots: one row per purchase. The same symbol may appear
    many times (each buy at its own price/date/quantity); positions are
    aggregated per symbol (weighted average buy price) by the user_db helpers."""

    __tablename__ = "portfolio"
    __table_args__ = (
        Index("idx_portfolio_telegram", "telegram_id"),
    )

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    buy_date: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Tracking(Base):
    __tablename__ = "tracking"
    __table_args__ = (
        UniqueConstraint("telegram_id", "symbol"),
        Index("idx_tracking_telegram", "telegram_id"),
    )

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TargetAlert(Base):
    __tablename__ = "target_alerts"
    __table_args__ = (
        CheckConstraint("direction IN ('above', 'below')"),
        Index("idx_targets_telegram", "telegram_id"),
        Index(
            "idx_targets_pending",
            "notified",
            sqlite_where=text("notified = 0"),
            postgresql_where=text("notified = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    notified: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ThreadActivity(Base):
    """Last-activity bookkeeping per conversation thread (ephemeral TTL data).

    Lives in the shared user DB (brvm_bot.db / DATABASE_URL) — moved out of the
    checkpoint DB; no data migration needed for this bookkeeping table.
    """

    __tablename__ = "thread_activity"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen: Mapped[float] = mapped_column(Float)


class DigestSubscription(Base):
    __tablename__ = "digest_subscriptions"

    telegram_id: Mapped[int] = mapped_column(
        _telegram_id_type, ForeignKey("users.telegram_id"), primary_key=True
    )
    frequency: Mapped[str] = mapped_column(Text, nullable=False)  # 'daily' | 'weekly'
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MarketSnapshot(Base):
    """Daily post-close snapshot of the full BRVM palmarès (one row per symbol
    per day). Refreshed by the scheduled job after market close; the mobile API
    serves this instead of scraping on every request."""

    __tablename__ = "market_snapshots"
    __table_args__ = (Index("idx_market_snapshots_day", "day"),)

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD (UTC)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    variation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_fcfa: Mapped[float | None] = mapped_column(Float, nullable=True)
    capitalisation: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SgiBroker(Base):
    """SGI (courtier) profile stored locally: the app shows details in-app
    instead of sending users to external sites. Refreshed weekly."""

    __tablename__ = "sgi_brokers"

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    info: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_amount: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_countries: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # enriched conditions page
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (Index("idx_snapshots_symbol_day", "symbol", "day"),)

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    signal: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AiPrediction(Base):
    """Daily post-close AI prediction per symbol (direction, confidence,
    targets). Computed by app.services.predictions after market close; the
    mobile API serves the latest day."""

    __tablename__ = "ai_predictions"
    __table_args__ = (Index("idx_predictions_symbol_day", "symbol", "day"),)

    id: Mapped[int] = mapped_column(_pk_int, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD (UTC)
    direction: Mapped[str] = mapped_column(Text, nullable=False, server_default="")  # hausse|baisse|neutre
    confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_move_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

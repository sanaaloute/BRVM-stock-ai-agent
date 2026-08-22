"""Declarative models for the user database (BRVM bot).

Schema matches the legacy hand-rolled DDL exactly (table/column names, uniques,
FKs, partial index) so existing SQLite/PostgreSQL databases are adopted as-is
by migration 0001. String columns are Text (legacy PostgreSQL used TEXT).
"""
from __future__ import annotations

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


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(_telegram_id_type, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Added by a later ALTER in the legacy code: TEXT on both backends.
    help_sent_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class Portfolio(Base):
    __tablename__ = "portfolio"
    __table_args__ = (
        UniqueConstraint("telegram_id", "symbol"),
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

"""Initial schema: adopt legacy databases, create new tables.

Revision ID: 0001
Revises:
Create Date: 2026-08-22

For every table: create it only when missing, so `alembic upgrade head` is a
no-op on current production databases and a full create on fresh ones. Also
ensures users.help_sent_at (a later ALTER in the legacy code) and creates the
new tables (thread_activity in its new home, digest_subscriptions,
score_snapshots).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        # `alembic upgrade --sql`: no live inspection, emit a plain full create.
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
            for index in sorted(table.indexes, key=lambda i: i.name):
                op.execute(str(sa.schema.CreateIndex(index).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())

    # Adopt legacy databases: create only what is missing (no-op when current).
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind=conn)

    if "users" in existing:
        # help_sent_at post-dates the original schema (new-user welcome flag).
        if conn.dialect.name == "postgresql":
            op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS help_sent_at TEXT")
        else:
            cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(users)")}
            if "help_sent_at" not in cols:
                op.execute("ALTER TABLE users ADD COLUMN help_sent_at TEXT")

    # Indexes predate Alembic on legacy DBs; keep creation idempotent.
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_portfolio_telegram ON portfolio(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_tracking_telegram ON tracking(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_targets_telegram ON target_alerts(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_targets_pending ON target_alerts(notified) WHERE notified = 0",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_day ON score_snapshots(symbol, day)",
    ):
        op.execute(stmt)


def downgrade() -> None:
    # Drop only the tables introduced with this migration; the legacy tables
    # (users/portfolio/tracking/target_alerts/usage_daily) may predate Alembic
    # and are left untouched on purpose.
    if context.is_offline_mode():
        existing = {"score_snapshots", "digest_subscriptions", "thread_activity"}
    else:
        existing = set(sa.inspect(op.get_bind()).get_table_names())
    for name in ("score_snapshots", "digest_subscriptions", "thread_activity"):
        if name in existing:
            op.drop_table(name)

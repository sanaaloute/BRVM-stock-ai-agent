"""Mobile app identity: app_users, otp_codes, refresh_tokens, devices.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

Adds the mobile-app auth/identity tables. Existing tables are untouched: app
users are identified across the legacy user tables by their ``principal_id``
(see app.db.models.AppUser), so no column changes are needed on
portfolio/tracking/target_alerts/digest_subscriptions. Existing Telegram users
are backfilled into app_users (linked accounts: principal_id == telegram_id)
so both surfaces share one identity.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NEW_TABLES = ("app_users", "otp_codes", "refresh_tokens", "devices")


def upgrade() -> None:
    if context.is_offline_mode():
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            if table.name not in _NEW_TABLES:
                continue
            op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
            for index in sorted(table.indexes, key=lambda i: i.name):
                op.execute(str(sa.schema.CreateIndex(index).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name in _NEW_TABLES and table.name not in existing:
            table.create(bind=conn)

    # Backfill: one linked app_users row per existing Telegram user (idempotent).
    if "users" in existing and "app_users" in existing:
        op.execute(
            """
            INSERT INTO app_users (id, principal_id, telegram_id, is_active, created_at)
            SELECT gen_random_uuid(), u.telegram_id, u.telegram_id, 1, u.created_at
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM app_users a WHERE a.telegram_id = u.telegram_id
            )
            """
            if conn.dialect.name == "postgresql"
            else
            # SQLite has no gen_random_uuid(): UUIDs are stored as CHAR(32)
            # by SQLAlchemy's Uuid type — hex without dashes.
            """
            INSERT INTO app_users (id, principal_id, telegram_id, is_active, created_at)
            SELECT lower(hex(randomblob(16))), u.telegram_id, u.telegram_id, 1, u.created_at
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM app_users a WHERE a.telegram_id = u.telegram_id
            )
            """
        )


def downgrade() -> None:
    if context.is_offline_mode():
        existing = set(_NEW_TABLES)
    else:
        existing = set(sa.inspect(op.get_bind()).get_table_names())
    for name in reversed(_NEW_TABLES):
        if name in existing:
            op.drop_table(name)

"""Password auth for app users: add app_users.password_hash.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("ALTER TABLE app_users ADD COLUMN password_hash TEXT")
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    else:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_users)")}
        if "password_hash" not in cols:
            op.execute("ALTER TABLE app_users ADD COLUMN password_hash TEXT")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE app_users DROP COLUMN IF EXISTS password_hash")
    else:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_users)")}
        if "password_hash" in cols:
            # SQLite cannot drop a column pre-3.35 without a table rebuild;
            # harmless to leave in place on downgrade.
            pass

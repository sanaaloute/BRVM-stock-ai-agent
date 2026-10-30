"""User profile: add app_users.display_name and app_users.photo_path.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_COLUMNS = ("display_name", "photo_path")


def upgrade() -> None:
    if context.is_offline_mode():
        for col in _COLUMNS:
            op.execute(f"ALTER TABLE app_users ADD COLUMN {col} TEXT")
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        for col in _COLUMNS:
            op.execute(f"ALTER TABLE app_users ADD COLUMN IF NOT EXISTS {col} TEXT")
    else:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_users)")}
        for col in _COLUMNS:
            if col not in cols:
                op.execute(f"ALTER TABLE app_users ADD COLUMN {col} TEXT")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        for col in _COLUMNS:
            op.execute(f"ALTER TABLE app_users DROP COLUMN IF EXISTS {col}")
    else:
        # SQLite cannot drop a column pre-3.35 without a table rebuild;
        # harmless to leave in place on downgrade.
        pass

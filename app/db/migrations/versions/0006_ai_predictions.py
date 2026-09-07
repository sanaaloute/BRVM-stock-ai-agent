"""AI predictions table: daily post-close per-symbol predictions.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            if table.name == "ai_predictions":
                op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        exists = "ai_predictions" in set(sa.inspect(conn).get_table_names())
    else:
        exists = bool(conn.exec_driver_sql("PRAGMA table_info(ai_predictions)").fetchall())
    if not exists:
        Base.metadata.tables["ai_predictions"].create(bind=conn)


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("ai_predictions")
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        exists = "ai_predictions" in set(sa.inspect(conn).get_table_names())
    else:
        exists = bool(conn.exec_driver_sql("PRAGMA table_info(ai_predictions)").fetchall())
    if exists:
        op.drop_table("ai_predictions")

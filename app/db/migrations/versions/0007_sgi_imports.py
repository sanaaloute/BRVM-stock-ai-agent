"""Portfolio SGI document imports.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            if table.name == "portfolio_imports":
                op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        exists = "portfolio_imports" in set(sa.inspect(conn).get_table_names())
    else:
        exists = bool(conn.exec_driver_sql("PRAGMA table_info(portfolio_imports)").fetchall())
    if not exists:
        Base.metadata.tables["portfolio_imports"].create(bind=conn)


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("portfolio_imports")
        return

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        exists = "portfolio_imports" in set(sa.inspect(conn).get_table_names())
    else:
        exists = bool(conn.exec_driver_sql("PRAGMA table_info(portfolio_imports)").fetchall())
    if exists:
        op.drop_table("portfolio_imports")

"""SGI identity on portfolio lots and dividend payments.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column("portfolio", sa.Column("sgi", sa.Text, nullable=True))
        for table in Base.metadata.sorted_tables:
            if table.name == "portfolio_dividends":
                op.execute(str(sa.schema.CreateTable(table).compile(dialect=context.get_context().dialect)).strip())
        return

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if conn.dialect.name == "postgresql":
        columns = {column["name"] for column in inspector.get_columns("portfolio")}
        table_exists = "portfolio_dividends" in set(inspector.get_table_names())
    else:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(portfolio)").fetchall()}
        table_exists = bool(conn.exec_driver_sql("PRAGMA table_info(portfolio_dividends)").fetchall())
    if "sgi" not in columns:
        op.add_column("portfolio", sa.Column("sgi", sa.Text, nullable=True))
    if not table_exists:
        Base.metadata.tables["portfolio_dividends"].create(bind=conn)


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("portfolio_dividends")
        op.drop_column("portfolio", "sgi")
        return

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if conn.dialect.name == "postgresql":
        table_exists = "portfolio_dividends" in set(inspector.get_table_names())
        columns = {column["name"] for column in inspector.get_columns("portfolio")}
    else:
        table_exists = bool(conn.exec_driver_sql("PRAGMA table_info(portfolio_dividends)").fetchall())
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(portfolio)").fetchall()}
    if table_exists:
        op.drop_table("portfolio_dividends")
    if "sgi" in columns:
        op.drop_column("portfolio", "sgi")

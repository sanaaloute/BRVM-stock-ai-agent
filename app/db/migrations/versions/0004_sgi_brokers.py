"""SGI (brokers) table: store broker profiles locally.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            if table.name == "sgi_brokers":
                op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name == "sgi_brokers" and table.name not in existing:
            table.create(bind=conn)


def downgrade() -> None:
    existing = {"sgi_brokers"} if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())
    if "sgi_brokers" in existing:
        op.drop_table("sgi_brokers")

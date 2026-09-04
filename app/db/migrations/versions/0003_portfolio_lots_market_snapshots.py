"""Portfolio lots + market snapshots.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

1. portfolio: drop UNIQUE(telegram_id, symbol) so one user can hold several
   buy lots of the same symbol (each purchase = one row). Positions are
   aggregated per symbol by the app layer (weighted average buy price).
   SQLite cannot drop a constraint in place: the table is rebuilt via the
   Alembic batch API (data preserved).
2. market_snapshots: new table — daily post-close palmarès snapshot served by
   the mobile API instead of live scraping.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from app.db.models import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        dialect = context.get_context().dialect
        for table in Base.metadata.sorted_tables:
            if table.name == "market_snapshots":
                op.execute(str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip())
                for index in sorted(table.indexes, key=lambda i: i.name):
                    op.execute(str(sa.schema.CreateIndex(index).compile(dialect=dialect)).strip())
        return

    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())

    # --- 1. portfolio: drop the (telegram_id, symbol) unique constraint -----
    if "portfolio" in existing:
        if conn.dialect.name == "postgresql":
            # Constraint name is dialect-defaulted (portfolio_telegram_id_symbol_key);
            # resolve it dynamically in case a legacy DB named it differently.
            row = conn.execute(sa.text(
                """
                SELECT c.conname FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE t.relname = 'portfolio' AND n.nspname = current_schema()
                  AND c.contype = 'u'
                  AND (SELECT count(*) FROM pg_attribute a
                       WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                         AND a.attname IN ('telegram_id', 'symbol')) = 2
                """
            )).first()
            if row:
                op.execute(sa.text(f'ALTER TABLE portfolio DROP CONSTRAINT "{row[0]}"'))
        else:
            # SQLite cannot drop a constraint in place: rebuild the table
            # without the unique constraint (data preserved).
            has_new = "portfolio_new" in existing
            if not has_new:
                op.create_table(
                    "portfolio_new",
                    sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
                    sa.Column("telegram_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), nullable=False),
                    sa.Column("symbol", sa.Text, nullable=False),
                    sa.Column("buy_price", sa.Float, nullable=False),
                    sa.Column("buy_date", sa.Text, nullable=False),
                    sa.Column("quantity", sa.Float, nullable=False, server_default="1"),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                )
                op.execute(
                    "INSERT INTO portfolio_new (id, telegram_id, symbol, buy_price, buy_date, quantity, created_at) "
                    "SELECT id, telegram_id, symbol, buy_price, buy_date, quantity, created_at FROM portfolio"
                )
                op.drop_table("portfolio")
                op.rename_table("portfolio_new", "portfolio")
                op.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_telegram ON portfolio(telegram_id)")

    # --- 2. market_snapshots --------------------------------------------------
    for table in Base.metadata.sorted_tables:
        if table.name == "market_snapshots" and table.name not in existing:
            table.create(bind=conn)


def downgrade() -> None:
    if context.is_offline_mode():
        existing = {"market_snapshots"}
    else:
        existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "market_snapshots" in existing:
        op.drop_table("market_snapshots")
    # The portfolio unique constraint is not restored (data may violate it).

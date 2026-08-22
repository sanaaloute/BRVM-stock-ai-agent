"""Alembic environment: online (default) and offline modes.

The database URL is never stored in alembic.ini: it is resolved at runtime —
`sqlalchemy.url` when set programmatically (app.db.migrate / tests), otherwise
from config.DATABASE_URL (PostgreSQL) or app.utils.user_db.DB_PATH (SQLite).
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Repo root on sys.path so `alembic` CLI works from any cwd.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import engine as db_engine  # noqa: E402
from app.db.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or db_engine.make_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_name=_url().split(":", 1)[0].split("+", 1)[0],
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

#!/usr/bin/env python3
"""Apply database migrations (Alembic) for the configured target.

Local -> cloud story:
1. Set DATABASE_URL=postgresql://user:password@host:5432/dbname (env or .env).
2. Run `python run_migrations.py` — creates/adopts the schema in PostgreSQL.
3. If you are migrating existing data, restore your pg_dump afterwards; the
   initial migration adopts legacy tables in place and never drops them.

With no DATABASE_URL set, migrates the local SQLite file (app/data/brvm_bot.db).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect  # noqa: E402

from app.db.engine import get_engine  # noqa: E402
from app.db.migrate import upgrade_to_head  # noqa: E402


def main() -> None:
    upgrade_to_head()
    tables = sorted(inspect(get_engine()).get_table_names())
    print("Migrated. Tables:", ", ".join(tables))


if __name__ == "__main__":
    main()

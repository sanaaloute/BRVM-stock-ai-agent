#!/usr/bin/env python3
"""Import user-owned rows from the local SQLite database into PostgreSQL.

Run a dry run first. The import preserves primary keys and account password
hashes, skips ephemeral auth state and refuses to overwrite conflicting rows.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.sqltypes import Uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import Base  # noqa: E402

# Intentionally exclude OTPs, refresh sessions, device tokens, transient chat
# activity, derived market caches, and LangGraph checkpoints.
USER_DATA_TABLES = (
    "users",
    "app_users",
    "portfolio",
    "portfolio_imports",
    "portfolio_dividends",
    "tracking",
    "target_alerts",
    "usage_daily",
    "digest_subscriptions",
)


def _normalized(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value


def _source_table(engine: Engine, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=engine)


def _readonly_sqlite_engine(path: Path) -> Engine:
    return create_engine(
        f"sqlite:///file:{path.resolve()}?mode=ro&immutable=1&uri=true"
    )


def _target_values(table: Table, source_row: Any) -> dict[str, Any]:
    source_values = dict(source_row)
    values = {
        column.name: source_values[column.name]
        for column in table.columns
        if column.name in source_values
    }
    for column in table.columns:
        if column.name in values or column.nullable:
            continue
        if column.default is None and column.server_default is None and not column.autoincrement:
            raise ValueError(
                f"Source row for {table.name} lacks required column {column.name!r}."
            )
    for column in table.columns:
        if isinstance(column.type, Uuid) and isinstance(values.get(column.name), str):
            values[column.name] = uuid.UUID(values[column.name])
    return values


def _existing_row(
    connection: Connection, table: Table, values: dict[str, Any]
) -> dict[str, Any] | None:
    primary_key = list(table.primary_key.columns)
    if not primary_key:
        raise ValueError(f"Cannot safely import {table.name}: table has no primary key.")
    criteria = [column == values[column.name] for column in primary_key]
    row = connection.execute(select(table).where(*criteria)).mappings().one_or_none()
    return dict(row) if row is not None else None


def _sync_postgres_sequence(connection: Connection, table: Table) -> None:
    if connection.dialect.name != "postgresql":
        return
    primary_key = list(table.primary_key.columns)
    if len(primary_key) != 1:
        return
    column = primary_key[0]
    if not column.autoincrement or not str(column.type).upper().startswith(("INTEGER", "BIGINT")):
        return

    preparer = connection.dialect.identifier_preparer
    table_name = preparer.quote(table.name)
    column_name = preparer.quote(column.name)
    connection.execute(
        text(
            "SELECT setval("
            "pg_get_serial_sequence(:table_name, :column_name), "
            f"GREATEST(COALESCE(MAX({column_name}), 1), 1), "
            f"COALESCE(MAX({column_name}), 0) >= 1) FROM {table_name}"
        ),
        {"table_name": table.name, "column_name": column.name},
    )


def import_user_data(
    source_engine: Engine,
    target_connection: Connection,
    *,
    sync_sequences: bool = True,
) -> dict[str, int]:
    """Import source rows transactionally; return inserted and unchanged counts."""
    source_names = set(inspect(source_engine).get_table_names())
    results: dict[str, int] = {}

    with source_engine.connect() as source_connection:
        for name in USER_DATA_TABLES:
            if name not in source_names:
                results[name] = 0
                continue

            target_table = Base.metadata.tables[name]
            source_table = _source_table(source_engine, name)
            if not set(column.name for column in target_table.columns).intersection(
                column.name for column in source_table.columns
            ):
                raise ValueError(f"No compatible columns found for {name}.")

            inserted = 0
            unchanged = 0
            for source_row in source_connection.execute(select(source_table)).mappings():
                values = _target_values(target_table, source_row)
                existing = _existing_row(target_connection, target_table, values)
                if existing is not None:
                    shared_columns = set(values).intersection(existing)
                    if all(
                        _normalized(existing[column]) == _normalized(values[column])
                        for column in shared_columns
                    ):
                        unchanged += 1
                        continue
                    key_columns = ", ".join(
                        f"{column.name}={values[column.name]!r}"
                        for column in target_table.primary_key.columns
                    )
                    raise ValueError(
                        f"Conflicting target row in {name} ({key_columns}); "
                        "no changes were committed."
                    )
                target_connection.execute(target_table.insert().values(**values))
                inserted += 1

            if sync_sequences:
                _sync_postgres_sequence(target_connection, target_table)
            results[name] = inserted
            results[f"{name} (already identical)"] = unchanged

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="SQLite backup file")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit the import (default is a rollback-only dry run)",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error(f"SQLite source file does not exist: {args.source}")

    from config import DATABASE_URL

    database_url = (DATABASE_URL or "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        parser.error("DATABASE_URL must point to the PostgreSQL target database.")

    source_engine = _readonly_sqlite_engine(args.source)
    target_engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with target_engine.connect() as target_connection:
            transaction = target_connection.begin()
            result = import_user_data(
                source_engine, target_connection, sync_sequences=args.apply
            )
            if args.apply:
                transaction.commit()
                print("Import committed.")
            else:
                transaction.rollback()
                print("Dry run only; no PostgreSQL changes were committed.")
            for table, count in result.items():
                print(f"{table}: {count}")
    except (IntegrityError, ValueError) as exc:
        raise SystemExit(f"Import stopped safely: {exc}") from exc
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    main()

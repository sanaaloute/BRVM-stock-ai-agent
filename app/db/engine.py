"""SQLAlchemy engine factory for the user database.

Target: PostgreSQL (psycopg3 driver) when config.DATABASE_URL is set, else the
SQLite file at app.utils.user_db.DB_PATH. Engines and session factories are
cached per target key, so rebinding user_db.DB_PATH (tests) transparently
builds a fresh engine for the new file.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import config


def db_target() -> str:
    """Current persistence target key: DATABASE_URL or the SQLite file path."""
    url = (getattr(config, "DATABASE_URL", "") or "").strip()
    if url:
        return url
    # Late import on purpose: tests rebind user_db.DB_PATH per module.
    from app.utils.user_db import DB_PATH

    return str(DB_PATH)


def make_url(target: str | None = None) -> str:
    """SQLAlchemy URL for a target key (default: current target)."""
    target = target or db_target()
    if "://" in target:
        # config carries the bare postgresql:// scheme; we ride psycopg3.
        if target.startswith("postgresql://"):
            return "postgresql+psycopg://" + target[len("postgresql://"):]
        return target
    return f"sqlite:///{target}"


def _build_engine(url: str, target: str) -> Engine:
    if url.startswith("sqlite"):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 30}
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            # The bot process (alert job) and the API process (portfolio tools)
            # share this DB: WAL + busy_timeout avoid cross-process lock errors.
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

        return engine
    return create_engine(url)  # PostgreSQL: default pool is fine.


_engines: dict[str, tuple[Engine, sessionmaker]] = {}
_engines_lock = threading.Lock()


def _entry(target: str | None = None) -> tuple[Engine, sessionmaker]:
    target = target or db_target()
    with _engines_lock:
        entry = _engines.get(target)
        if entry is None:
            engine = _build_engine(make_url(target), target)
            entry = (engine, sessionmaker(bind=engine, expire_on_commit=False))
            _engines[target] = entry
    return entry


def get_engine(target: str | None = None) -> Engine:
    """Shared engine for a target (default: current), created on first use."""
    return _entry(target)[0]


def get_session_factory(target: str | None = None) -> sessionmaker:
    """sessionmaker bound to the target's shared engine."""
    return _entry(target)[1]


def dialect_insert(table, target: str | None = None):
    """Dialect-specific INSERT for the target (enables ON CONFLICT clauses)."""
    if get_engine(target).dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.insert(table)
    from sqlalchemy.dialects import sqlite

    return sqlite.insert(table)


@contextmanager
def session_scope(target: str | None = None):
    """Session scope: commit on success, rollback on error, always close."""
    session: Session = _entry(target)[1]()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engines() -> None:
    """Dispose and forget all cached engines (tests)."""
    with _engines_lock:
        entries = list(_engines.values())
        _engines.clear()
    for engine, _factory in entries:
        engine.dispose()

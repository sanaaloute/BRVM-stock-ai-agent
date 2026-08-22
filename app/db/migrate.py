"""Programmatic Alembic runner: upgrade the current DB target to head.

ensure_schema() applies migrations lazily, once per DB target (DATABASE_URL or
SQLite path), so rebinding app.utils.user_db.DB_PATH (tests) re-migrates the
new target on first use.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

_migrated_targets: set[str] = set()
_migrate_lock = threading.Lock()


def upgrade_to_head(url: str | None = None) -> None:
    """Apply all migrations up to head against `url` (default: current target)."""
    from alembic import command
    from alembic.config import Config

    from app.db.engine import make_url

    logging.getLogger("alembic").setLevel(logging.WARNING)  # keep runs quiet
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url or make_url())
    command.upgrade(cfg, "head")


def ensure_schema(target: str | None = None) -> None:
    """Migrate once per DB target (lazy; safe when tests rebind DB_PATH)."""
    from app.db.engine import db_target, make_url

    target = target or db_target()
    if target in _migrated_targets:
        return
    with _migrate_lock:
        if target in _migrated_targets:
            return
        upgrade_to_head(make_url(target))
        _migrated_targets.add(target)


def reset_cache() -> None:
    """Forget migrated targets (tests)."""
    _migrated_targets.clear()

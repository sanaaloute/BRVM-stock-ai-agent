"""PostgreSQL backend tests (Track: PG migration).

1. Always runs: SQLAlchemy models create the full schema on SQLite, and the
   dialect-specific usage upsert compiles for BOTH SQLite and PostgreSQL
   (offline compilation, no server needed).
2. When TEST_DATABASE_URL is set (e.g. postgresql://brvm:brvm@localhost:5432/brvm):
   full integration — upgrade_to_head + user_db CRUD + quota on Postgres,
   PostgresSaver setup, an end-to-end agent run checkpointed in Postgres,
   and the memory wipe.

Spin up a throwaway server with: docker compose up -d db
Run:
    .venv/Scripts/python tests/test_postgres_backend.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import config  # noqa: E402
config.DATABASE_URL = ""  # always-run tests use SQLite regardless of local .env

import app.utils.user_db as user_db  # noqa: E402
from app.db import engine as db_engine  # noqa: E402

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS {name}")
    except Exception as e:
        RESULTS.append((name, False, repr(e)))
        print(f"FAIL {name}: {e!r}")


def test_models_create_on_sqlite():
    """Fresh SQLite target: the Alembic migration creates the full schema."""
    from sqlalchemy import inspect

    saved_path = user_db.DB_PATH
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "models_test.db"
    try:
        user_db.init_db()
        engine = db_engine.get_engine()
        tables = set(inspect(engine).get_table_names())
        expected = {
            "users", "portfolio", "tracking", "target_alerts", "usage_daily",
            "thread_activity", "digest_subscriptions", "score_snapshots",
        }
        assert expected <= tables, tables
        # The legacy partial index must exist on the new schema too.
        indexes = {i["name"] for i in inspect(engine).get_indexes("target_alerts")}
        assert "idx_targets_pending" in indexes, indexes
    finally:
        user_db.DB_PATH = saved_path


def test_upsert_sql_compiles_for_both_dialects():
    """The usage-counter upsert must render ON CONFLICT ... DO UPDATE with
    RETURNING on both backends (compiled offline, no live DB)."""
    from sqlalchemy.dialects import postgresql, sqlite

    pg_sql = str(
        user_db._usage_increment_stmt("postgresql", "u1", "2026-01-01").compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "ON CONFLICT" in pg_sql and "DO UPDATE" in pg_sql, pg_sql
    assert "RETURNING" in pg_sql, pg_sql
    # Table-qualified form: bare `count` is ambiguous in Postgres upserts
    # (table vs EXCLUDED).
    assert "usage_daily.count + 1" in pg_sql, pg_sql

    lite_sql = str(
        user_db._usage_increment_stmt("sqlite", "u1", "2026-01-01").compile(
            dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "ON CONFLICT" in lite_sql and "DO UPDATE" in lite_sql, lite_sql
    assert "RETURNING" in lite_sql, lite_sql
    assert "usage_daily.count + 1" in lite_sql, lite_sql


def test_usage_counter_sqlite():
    """Always runs: quota counter round-trip on SQLite.

    Regression guard for the upsert in increment_daily_usage: the DO UPDATE
    clause must use the table-qualified form (`usage_daily.count + 1`) — bare
    `count` is ambiguous on Postgres. This verifies the behavior on SQLite;
    the integration test covers the Postgres side.
    """
    assert db_engine.get_engine().dialect.name == "sqlite"
    saved_path = user_db.DB_PATH
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "counter_test.db"
    try:
        assert user_db.get_daily_usage("counter-user") == 0
        assert user_db.increment_daily_usage("counter-user") == 1
        assert user_db.increment_daily_usage("counter-user") == 2
        user_db.decrement_daily_usage("counter-user")
        assert user_db.get_daily_usage("counter-user") == 1
        user_db.decrement_daily_usage("counter-user")
        user_db.decrement_daily_usage("counter-user")  # floor at 0
        assert user_db.get_daily_usage("counter-user") == 0
    finally:
        user_db.DB_PATH = saved_path


def _pg_user_db_flow():
    uid = 424242
    user_db.init_db()
    user_db.get_or_create_user(uid)
    assert user_db.has_sent_help(uid) is False
    user_db.mark_help_sent(uid)
    assert user_db.has_sent_help(uid) is True
    r = user_db.portfolio_add(uid, "NTLC", 50000, "2025-01-15")
    assert r.get("ok"), r
    pos = user_db.portfolio_list(uid)
    assert len(pos) == 1 and pos[0]["symbol"] == "NTLC", pos
    # upsert same symbol -> still one row, updated price
    user_db.portfolio_add(uid, "NTLC", 51000, "2025-02-01")
    pos = user_db.portfolio_list(uid)
    assert len(pos) == 1 and pos[0]["buy_price"] == 51000, pos
    assert user_db.tracking_add(uid, "SLBC").get("ok")
    assert [t["symbol"] for t in user_db.tracking_list(uid)] == ["SLBC"]
    assert user_db.target_add(uid, "NTLC", 60000, "above").get("ok")
    assert len(user_db.target_list(uid)) == 1
    assert len(user_db.get_pending_alerts()) == 1
    # quota counters
    assert user_db.get_daily_usage("pg-user") == 0
    assert user_db.increment_daily_usage("pg-user") == 1
    assert user_db.increment_daily_usage("pg-user") == 2
    user_db.decrement_daily_usage("pg-user")
    assert user_db.get_daily_usage("pg-user") == 1
    # removals
    assert user_db.portfolio_remove(uid, "NTLC").get("ok")
    assert user_db.tracking_remove(uid, "SLBC").get("ok")
    assert user_db.target_remove(uid, "NTLC").get("ok")


def _pg_checkpointer_flow(url):
    import test_graph_e2e as e2e  # noqa: sets config.DATABASE_URL = "" on import
    from langchain_core.messages import AIMessage

    config.DATABASE_URL = url  # restore after the import side effect above
    saved_path = user_db.DB_PATH
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "ignored.db"  # must NOT be used
    e2e._patch_llm(e2e._make_fake())

    import app.api.chat as chat_mod
    chat_mod._checkpointer = None  # force fresh saver against the pg URL
    cp = chat_mod._get_checkpointer()
    assert "Postgres" in type(cp).__name__, type(cp).__name__

    from app.agents.graph import run_agent
    result = run_agent(
        "I bought NTLC at 50000 on 2025-01-15",
        model="fake",
        thread_id="pg-e2e",
        telegram_user_id=e2e.USER_ID,
        checkpointer=cp,
    )
    last = result["messages"][-1].content
    assert isinstance(last, str) and last, last
    positions = user_db.portfolio_list(e2e.USER_ID)
    assert len(positions) == 1 and positions[0]["symbol"] == "NTLC", positions

    # /clear-memory path + full wipe must work on postgres
    cp.delete_thread("pg-e2e")
    chat_mod.clear_all_chat_memory()
    user_db.DB_PATH = saved_path


def test_postgres_integration():
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not url:
        print("SKIP test_postgres_integration (set TEST_DATABASE_URL to run; "
              "e.g. docker compose up -d db)")
        return
    import psycopg  # noqa: F401 — must be importable

    from app.db.migrate import upgrade_to_head

    saved_url = config.DATABASE_URL
    config.DATABASE_URL = url
    try:
        assert db_engine.db_target() == url
        assert db_engine.get_engine().dialect.name == "postgresql"
        upgrade_to_head()  # adopts/creates the real schema
        _pg_user_db_flow()
        _pg_checkpointer_flow(url)
    finally:
        config.DATABASE_URL = saved_url


if __name__ == "__main__":
    check("test_models_create_on_sqlite", test_models_create_on_sqlite)
    check("test_upsert_sql_compiles_for_both_dialects", test_upsert_sql_compiles_for_both_dialects)
    check("test_usage_counter_sqlite", test_usage_counter_sqlite)
    check("test_postgres_integration", test_postgres_integration)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)

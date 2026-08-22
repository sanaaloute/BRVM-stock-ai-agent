"""Daily free-quota tests for the Chat API (Track D).

Verifies: limit enforcement, per-user isolation, exempt ids, refund on agent
error, day rollover, and 0 = unlimited. The agent run is faked (no LLM), and
usage is stored in a throwaway SQLite DB. Requires .venv deps (fastapi, httpx).
Run:
    .venv/Scripts/python tests/test_daily_quota.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env
config.API_SECRET_KEY = "k"  # pin secret so a real .env cannot break the suite

import app.api.chat as chat_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

# Throwaway usage DB
_tmp = Path(tempfile.mkdtemp()) / "quota_test.db"
user_db.DB_PATH = _tmp

QUOTA_MSG = "limite de"


def _ok_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    # run_agent's contract: the reply of THIS invocation travels in _fresh_reply.
    reply = f"fake reply to: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _ok_agent
client = TestClient(chat_mod.app)


def _post(user, key="k"):
    return client.post(
        "/chat",
        json={"query": "cours NTLC ?", "thread_id": str(user), "telegram_user_id": user},
        headers={"X-API-Key": key},
    )


def _restore(quota, exempt):
    config.DAILY_FREE_QUOTA = quota
    config.QUOTA_EXEMPT_IDS = exempt


def test_quota_allows_up_to_limit():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 3
    config.QUOTA_EXEMPT_IDS = set()
    try:
        user = 5001
        for i in range(3):
            r = _post(user)
            assert r.status_code == 200 and "fake reply" in r.json().get("reply", ""), r.json()
        r = _post(user)
        assert QUOTA_MSG in r.json().get("error", ""), r.json()
        assert "3" in r.json()["error"], r.json()
        # still blocked on the next attempt too
        assert QUOTA_MSG in _post(user).json().get("error", "")
        assert user_db.get_daily_usage("5001") == 3
    finally:
        _restore(*saved)


def test_quota_isolation_between_users():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 1
    config.QUOTA_EXEMPT_IDS = set()
    try:
        assert "fake reply" in _post(5002).json().get("reply", "")
        assert QUOTA_MSG in _post(5002).json().get("error", "")
        # another user is unaffected
        assert "fake reply" in _post(5003).json().get("reply", "")
    finally:
        _restore(*saved)


def test_quota_exempt_ids():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 1
    config.QUOTA_EXEMPT_IDS = {"5004"}
    try:
        for _ in range(6):
            assert "fake reply" in _post(5004).json().get("reply", "")
        assert user_db.get_daily_usage("5004") == 0  # exempt users are not metered
    finally:
        _restore(*saved)


def test_quota_refund_on_agent_error():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 2
    config.QUOTA_EXEMPT_IDS = set()

    def _boom(*a, **k):
        raise RuntimeError("LLM backend down")

    chat_mod.run_agent = _boom
    try:
        user = 5005
        for _ in range(4):  # more than the quota, all fail
            r = _post(user)
            assert "error" in r.json() and QUOTA_MSG not in r.json()["error"], r.json()
        assert user_db.get_daily_usage("5005") == 0  # all refunded
        # a working agent is still fully available
        chat_mod.run_agent = _ok_agent
        assert "fake reply" in _post(user).json().get("reply", "")
    finally:
        chat_mod.run_agent = _ok_agent
        _restore(*saved)


def test_new_day_resets_quota():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 1
    config.QUOTA_EXEMPT_IDS = set()
    try:
        user = 5006
        assert "fake reply" in _post(user).json().get("reply", "")
        assert QUOTA_MSG in _post(user).json().get("error", "")
        # simulate tomorrow: move today's row to an old date
        conn = sqlite3.connect(str(_tmp))
        conn.execute("UPDATE usage_daily SET day = '2000-01-01' WHERE user_id = '5006'")
        conn.commit()
        conn.close()
        assert "fake reply" in _post(user).json().get("reply", "")
    finally:
        _restore(*saved)


def test_quota_disabled_when_zero():
    saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 0
    config.QUOTA_EXEMPT_IDS = set()
    try:
        for _ in range(5):
            assert "fake reply" in _post(5007).json().get("reply", "")
    finally:
        _restore(*saved)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

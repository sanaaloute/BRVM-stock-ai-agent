"""Security tests for the Chat API: API-key auth + per-user rate limiting.

The agent run is faked, so no LLM is needed. Requires .venv deps (fastapi, httpx).
Run:
    .venv/Scripts/python tests/test_api_security.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

import app.api.chat as chat_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

SECRET = "test-secret-123"

# Throwaway usage DB: the repo dev DB may be locked by a running server.
_tmp_db = Path(tempfile.mkdtemp()) / "security_test.db"
user_db.DB_PATH = _tmp_db


def _fake_run_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    # run_agent's contract: the reply of THIS invocation travels in _fresh_reply.
    reply = f"fake reply to: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _fake_run_agent
client = TestClient(chat_mod.app)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_fake_agent():
    """Under pytest, each test gets THIS module's fake agent regardless of the
    import/run order (other test modules patch chat_mod.run_agent too)."""
    old = chat_mod.run_agent
    old_db_path = user_db.DB_PATH
    chat_mod.run_agent = _fake_run_agent
    user_db.DB_PATH = _tmp_db
    try:
        yield
    finally:
        chat_mod.run_agent = old
        user_db.DB_PATH = old_db_path


def _post(query="price of NTLC?", key=None, user=42):
    headers = {"X-API-Key": key} if key else {}
    return client.post(
        "/chat",
        json={"query": query, "thread_id": str(user), "telegram_user_id": user},
        headers=headers,
    )


def test_health_is_public():
    assert client.get("/health").status_code == 200


def test_missing_key_rejected():
    config.API_SECRET_KEY = SECRET
    r = _post(key=None)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_wrong_key_rejected():
    config.API_SECRET_KEY = SECRET
    r = _post(key="wrong-key")
    assert r.status_code == 401


def test_correct_key_accepted():
    config.API_SECRET_KEY = SECRET
    r = _post(key=SECRET, user=1001)
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert reply.startswith("fake reply to: price of NTLC?"), reply
    assert chat_mod.SOURCE_FOOTER.strip() in reply, "AI disclaimer footer must be appended"


def test_rate_limit_per_user():
    config.API_SECRET_KEY = SECRET
    config.RATE_LIMIT_PER_MINUTE = 2
    user = 2002
    assert _post(key=SECRET, user=user).status_code == 200
    assert _post(key=SECRET, user=user).status_code == 200
    r = _post(key=SECRET, user=user)
    assert r.status_code == 200 and "Trop de requêtes" in r.json().get("error", "")
    # a different user is unaffected
    assert _post(key=SECRET, user=3003).status_code == 200
    config.RATE_LIMIT_PER_MINUTE = 30  # restore


def test_dev_mode_when_no_key():
    config.API_SECRET_KEY = ""
    r = _post(key=None, user=4004)
    assert r.status_code == 200
    config.API_SECRET_KEY = SECRET  # restore


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

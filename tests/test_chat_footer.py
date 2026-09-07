"""AI disclaimer footer tests (app/api/chat.py SOURCE_FOOTER).

The footer marks AI-generated financial content. Greetings/chitchat (NLU
intent "general") and clarification questions must NOT carry it; substantive
answers must. The agent run is faked, so no LLM is needed.
Run:
    .venv/bin/python -m pytest tests/test_chat_footer.py
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

# Throwaway usage DB: the repo dev DB may be held by a running server.
_tmp_db = Path(tempfile.mkdtemp()) / "footer_test.db"
user_db.DB_PATH = _tmp_db

SECRET = "test-secret-footer"
FOOTER = chat_mod.SOURCE_FOOTER.strip()

client = TestClient(chat_mod.app)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_state():
    """Per test: pin the API key and the throwaway usage DB (other test
    modules patch config.API_SECRET_KEY / user_db.DB_PATH too)."""
    old_db_path = user_db.DB_PATH
    config.API_SECRET_KEY = SECRET
    user_db.DB_PATH = _tmp_db
    try:
        yield
    finally:
        user_db.DB_PATH = old_db_path


def _fake_result(intent: str | None = None, clarification: str | None = None,
                 reply: str = "Réponse factice.") -> dict:
    if clarification is not None:
        return {"messages": [AIMessage(content=clarification)], "clarification": clarification}
    result: dict = {
        "messages": [AIMessage(content=reply)],
        "_fresh_reply": reply,
        "clarification": None,
    }
    if intent is not None:
        result["structured_data"] = {"intent": intent, "entities": {}, "suggested_worker": ""}
    return result


class _patch_agent:
    """Swap chat_mod.run_agent with a fake returning `result` (mirrors the
    context-manager patching style used across tests/)."""

    def __init__(self, result: dict):
        self._result = result

    def __enter__(self):
        self._old = chat_mod.run_agent

        def _fake(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
            return self._result

        chat_mod.run_agent = _fake

    def __exit__(self, *exc):
        chat_mod.run_agent = self._old


def _post(query: str, user: int):
    return client.post(
        "/chat",
        json={"query": query, "thread_id": str(user), "telegram_user_id": user},
        headers={"X-API-Key": SECRET},
    )


def test_greeting_general_intent_has_no_footer():
    config.API_SECRET_KEY = SECRET
    with _patch_agent(_fake_result(intent="general", reply="Bonjour ! Que voulez-vous savoir ?")):
        r = _post("Hi", user=9101)
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert reply.startswith("Bonjour"), reply
    assert FOOTER not in reply, "greeting must not carry the AI disclaimer"


def test_clarification_has_no_footer():
    config.API_SECRET_KEY = SECRET
    with _patch_agent(_fake_result(clarification="Quel symbole voulez-vous suivre ?")):
        r = _post("je veux suivre une action", user=9102)
    assert r.status_code == 200
    body = r.json()
    assert body["clarification"] is True
    assert FOOTER not in body["reply"], "clarification question must not carry the AI disclaimer"


def test_financial_answer_keeps_footer():
    config.API_SECRET_KEY = SECRET
    with _patch_agent(_fake_result(intent="advice", reply="NTLC affiche un score de 72/100.")):
        r = _post("faut-il acheter NTLC ?", user=9103)
    assert r.status_code == 200
    assert FOOTER in r.json()["reply"], "substantive answer must keep the AI disclaimer"


def test_unknown_intent_keeps_footer():
    # No structured_data (legacy/failed NLU): safe default = footer appended.
    config.API_SECRET_KEY = SECRET
    with _patch_agent(_fake_result(reply="Réponse sans NLU.")):
        r = _post("question quelconque", user=9104)
    assert r.status_code == 200
    assert FOOTER in r.json()["reply"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print("ok")

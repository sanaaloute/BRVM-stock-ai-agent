"""WhatsApp channel tests: webhook verification, inbound message handling,
dedup, quota integration, chunking, and channel-disabled behavior.

The agent run and the Meta Graph API sends are stubbed (no network, no LLM).
Requires .venv deps (fastapi, httpx).
Run:
    .venv/Scripts/python tests/test_whatsapp_webhook.py
"""
import hashlib
import hmac
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env
config.WHATSAPP_APP_SECRET = "test-app-secret"  # pin so POSTs can be signed deterministically

import app.api.chat as chat_mod  # noqa: E402
import app.api.whatsapp as wa_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

user_db.DB_PATH = Path(tempfile.mkdtemp()) / "wa_test.db"

PHONE = "2250700000001"


def _ok_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    # run_agent contract: the reply of THIS invocation travels in _fresh_reply.
    reply = f"réponse à: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _ok_agent
client = TestClient(chat_mod.app)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_fake_agent():
    """Under pytest, each test gets THIS module's fake agent regardless of the
    import/run order (other test modules patch chat_mod.run_agent too)."""
    old = chat_mod.run_agent
    chat_mod.run_agent = _ok_agent
    try:
        yield
    finally:
        chat_mod.run_agent = old


def _post(payload):
    """POST a webhook payload the way Meta does: raw bytes + HMAC-SHA256 signature."""
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(config.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )

_sent: list[tuple[str, str]] = []
_images: list[tuple[str, bytes]] = []


def _rec_send(to, text):
    _sent.append((to, text))


def _rec_image(to, png, caption=""):
    _images.append((to, png))


wa_mod.send_message = _rec_send
wa_mod.send_image = _rec_image


def _msg_payload(phone=PHONE, wamid="wamid.1", mtype="text", body="cours NTLC ?"):
    msg = {"from": phone, "id": wamid, "timestamp": "1700000000", "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": body}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"value": {"messaging_product": "whatsapp", "messages": [msg]}, "field": "messages"}]}],
    }


def _statuses_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"value": {"statuses": [{"id": "wamid.x", "status": "delivered"}]}, "field": "messages"}]}],
    }


def _reset():
    _sent.clear()
    _images.clear()


def test_webhook_verification_ok():
    saved = config.WHATSAPP_VERIFY_TOKEN
    config.WHATSAPP_VERIFY_TOKEN = "verify-me"
    try:
        r = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
        assert r.status_code == 200 and r.text == "12345", (r.status_code, r.text)
    finally:
        config.WHATSAPP_VERIFY_TOKEN = saved


def test_webhook_verification_rejected():
    saved = config.WHATSAPP_VERIFY_TOKEN
    config.WHATSAPP_VERIFY_TOKEN = "verify-me"
    try:
        r = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "12345"})
        assert r.status_code == 403, r.status_code
    finally:
        config.WHATSAPP_VERIFY_TOKEN = saved


def test_text_message_answered_and_metered():
    saved = (config.WHATSAPP_ENABLED, config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.WHATSAPP_ENABLED = True
    config.DAILY_FREE_QUOTA = 30
    config.QUOTA_EXEMPT_IDS = set()
    _reset()
    phone = "2250700000099"  # dedicated: quota rows persist across tests in this file
    try:
        r = _post(_msg_payload(phone=phone, wamid="wamid.t1"))
        assert r.status_code == 200, r.status_code
        assert len(_sent) == 1 and _sent[0][0] == phone, _sent
        assert "réponse à: cours NTLC ?" in _sent[0][1], _sent
        assert user_db.get_daily_usage(f"wa:{phone}") == 1
    finally:
        config.WHATSAPP_ENABLED, config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS = saved


def test_duplicate_delivery_processed_once():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    _reset()
    try:
        payload = _msg_payload(wamid="wamid.dup")
        _post(payload)
        _post(payload)
        assert len(_sent) == 1, _sent
    finally:
        config.WHATSAPP_ENABLED = saved


def test_statuses_ignored():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    _reset()
    try:
        r = _post(_statuses_payload())
        assert r.status_code == 200
        assert _sent == [], _sent
    finally:
        config.WHATSAPP_ENABLED = saved


def test_unsupported_type_gets_hint():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    _reset()
    try:
        r = _post(_msg_payload(wamid="wamid.img", mtype="image"))
        assert r.status_code == 200
        assert len(_sent) == 1 and "texte" in _sent[0][1], _sent
    finally:
        config.WHATSAPP_ENABLED = saved


def test_long_reply_is_chunked():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    big = "ligne\n" * 2000  # ~12k chars

    def _big_agent(*a, **k):
        return {"messages": [AIMessage(content=big)], "_fresh_reply": big}

    chat_mod.run_agent = _big_agent
    _reset()
    try:
        r = _post(_msg_payload(wamid="wamid.big"))
        assert r.status_code == 200
        assert len(_sent) >= 3, len(_sent)
        assert all(len(t) <= 4000 for _, t in _sent)
    finally:
        chat_mod.run_agent = _ok_agent
        config.WHATSAPP_ENABLED = saved


def test_chart_image_forwarded():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    png = Path(tempfile.mkdtemp()) / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def _img_agent(*a, **k):
        return {"messages": [AIMessage(content="voici le graphique")], "image_path": str(png), "_fresh_reply": "voici le graphique"}

    chat_mod.run_agent = _img_agent
    _reset()
    try:
        r = _post(_msg_payload(wamid="wamid.chart"))
        assert r.status_code == 200
        assert len(_sent) == 1 and "graphique" in _sent[0][1], _sent
        assert len(_images) == 1 and _images[0][0] == PHONE, _images
    finally:
        chat_mod.run_agent = _ok_agent
        config.WHATSAPP_ENABLED = saved


def test_unsigned_or_bad_signature_rejected():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = True
    _reset()
    body = json.dumps(_msg_payload(wamid="wamid.sec")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    try:
        # no signature header at all
        r = client.post("/whatsapp/webhook", content=body, headers=headers)
        assert r.status_code == 401, r.status_code
        # garbage signature
        r = client.post(
            "/whatsapp/webhook", content=body,
            headers={**headers, "X-Hub-Signature-256": "sha256=" + "0" * 64},
        )
        assert r.status_code == 401, r.status_code
        # well-formed HMAC but computed over different bytes
        sig = hmac.new(config.WHATSAPP_APP_SECRET.encode(), b"{}", hashlib.sha256).hexdigest()
        r = client.post(
            "/whatsapp/webhook", content=body,
            headers={**headers, "X-Hub-Signature-256": f"sha256={sig}"},
        )
        assert r.status_code == 401, r.status_code
        assert _sent == [], _sent  # nothing was processed
    finally:
        config.WHATSAPP_ENABLED = saved


def test_channel_disabled_drops_silently():
    saved = config.WHATSAPP_ENABLED
    config.WHATSAPP_ENABLED = False
    _reset()
    try:
        r = _post(_msg_payload(wamid="wamid.off"))
        assert r.status_code == 200  # still acked, so Meta doesn't retry forever
        assert _sent == [], _sent
    finally:
        config.WHATSAPP_ENABLED = saved


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

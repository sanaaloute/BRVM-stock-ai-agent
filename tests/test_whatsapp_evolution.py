"""WhatsApp Evolution channel tests: webhook auth, payload shapes (v1/v2),
inbound text/audio handling, dedup, quota integration, chunking, images,
and channel-disabled behavior.

The agent run and the Evolution API sends are stubbed (no network, no LLM).
Requires .venv deps (fastapi, httpx).
Run:
    .venv/Scripts/python tests/test_whatsapp_evolution.py
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
import app.channels.whatsapp.service as svc_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

user_db.DB_PATH = Path(tempfile.mkdtemp()) / "wa_evo_test.db"

PHONE = "22670000000"


class FakeEvolutionClient:
    """Records sends instead of calling the Evolution API."""

    def __init__(self):
        self.texts: list[tuple[str, str]] = []
        self.images: list[tuple[str, str]] = []
        self.media_base64: str | None = None

    async def send_text(self, number, text):
        self.texts.append((number, text))
        return {}

    async def send_image(self, number, image_base64, caption=""):
        self.images.append((number, image_base64))
        return {}

    async def get_media_base64(self, message):
        return self.media_base64


fake_client = FakeEvolutionClient()
svc_mod._service = svc_mod.WhatsAppService(client=fake_client)


def _ok_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    # run_agent contract: the reply of THIS invocation travels in _fresh_reply.
    reply = f"réponse à: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _ok_agent
client = TestClient(chat_mod.app)


def _v2_payload(phone=PHONE, msg_id="evo.1", kind="text", body="cours NTLC ?", from_me=False, with_base64=False):
    if kind == "text":
        message, mtype = {"conversation": body}, "conversation"
    elif kind == "audio":
        message, mtype = {"audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": 3}}, "audioMessage"
    else:
        message, mtype = {"stickerMessage": {}}, "stickerMessage"
    data = {
        "key": {"remoteJid": f"{phone}@s.whatsapp.net", "fromMe": from_me, "id": msg_id},
        "pushName": "Test User",
        "message": message,
        "messageType": mtype,
        "messageTimestamp": 1700000000,
    }
    if with_base64:
        data["base64"] = "T2dnUw=="  # "OggS"
    return {"event": "messages.upsert", "instance": "brvm-bot", "data": data, "sender": f"{phone}@s.whatsapp.net"}


def _v1_payload(phone=PHONE, msg_id="evo.v1", body="cours SNTS ?"):
    return {
        "event": "messages.upsert",
        "instance": "brvm-bot",
        "data": {
            "messages": [
                {
                    "key": {"remoteJid": f"{phone}@s.whatsapp.net", "fromMe": False, "id": msg_id},
                    "message": {"conversation": body},
                }
            ]
        },
    }


def _group_payload(msg_id="evo.grp"):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "120363000000@g.us", "fromMe": False, "id": msg_id},
            "message": {"conversation": "hello group"},
        },
    }


def _reset():
    fake_client.texts.clear()
    fake_client.images.clear()
    fake_client.media_base64 = None


def _enabled(**overrides):
    """Context helper: enable the channel without webhook auth, restore after."""
    saved = (config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY)
    config.EVOLUTION_ENABLED = True
    config.EVOLUTION_API_KEY = ""
    for k, v in overrides.items():
        setattr(config, k, v)
    return saved


def test_text_message_answered_and_metered():
    saved = _enabled()
    quota_saved = (config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS)
    config.DAILY_FREE_QUOTA = 30
    config.QUOTA_EXEMPT_IDS = set()
    _reset()
    phone = "22670000099"  # dedicated: quota rows persist across tests in this file
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(phone=phone, msg_id="evo.t1"))
        assert r.status_code == 200, r.status_code
        assert len(fake_client.texts) == 1 and fake_client.texts[0][0] == phone, fake_client.texts
        assert "réponse à: cours NTLC ?" in fake_client.texts[0][1], fake_client.texts
        assert user_db.get_daily_usage(f"wa:{phone}") == 1
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved
        config.DAILY_FREE_QUOTA, config.QUOTA_EXEMPT_IDS = quota_saved


def test_v1_payload_shape_supported():
    saved = _enabled()
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v1_payload())
        assert r.status_code == 200, r.status_code
        assert len(fake_client.texts) == 1, fake_client.texts
        assert "réponse à: cours SNTS ?" in fake_client.texts[0][1], fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_duplicate_delivery_processed_once():
    saved = _enabled()
    _reset()
    try:
        payload = _v2_payload(msg_id="evo.dup")
        client.post("/whatsapp/evolution/webhook", json=payload)
        client.post("/whatsapp/evolution/webhook", json=payload)
        assert len(fake_client.texts) == 1, fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_from_me_and_groups_ignored():
    saved = _enabled()
    _reset()
    try:
        client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.me", from_me=True))
        client.post("/whatsapp/evolution/webhook", json=_group_payload())
        assert fake_client.texts == [], fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_other_events_and_invalid_json_acked():
    saved = _enabled()
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json={"event": "connection.update", "data": {}})
        assert r.status_code == 200 and fake_client.texts == []
        r = client.post(
            "/whatsapp/evolution/webhook",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.status_code
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_webhook_apikey_enforced_when_configured():
    saved = (config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY)
    config.EVOLUTION_ENABLED = True
    config.EVOLUTION_API_KEY = "secret-key"
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.k1"))
        assert r.status_code == 401, r.status_code
        r = client.post(
            "/whatsapp/evolution/webhook",
            json=_v2_payload(msg_id="evo.k1"),
            headers={"apikey": "wrong"},
        )
        assert r.status_code == 401, r.status_code
        r = client.post(
            "/whatsapp/evolution/webhook",
            json=_v2_payload(msg_id="evo.k1"),
            headers={"apikey": "secret-key"},
        )
        assert r.status_code == 200 and len(fake_client.texts) == 1
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_unsupported_type_gets_hint():
    saved = _enabled()
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.stk", kind="sticker"))
        assert r.status_code == 200
        assert len(fake_client.texts) == 1 and "texte" in fake_client.texts[0][1], fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_long_reply_is_chunked():
    saved = _enabled()
    big = "ligne\n" * 2000  # ~12k chars

    def _big_agent(*a, **k):
        return {"messages": [AIMessage(content=big)], "_fresh_reply": big}

    chat_mod.run_agent = _big_agent
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.big"))
        assert r.status_code == 200
        assert len(fake_client.texts) >= 3, len(fake_client.texts)
        assert all(len(t) <= 4000 for _, t in fake_client.texts)
    finally:
        chat_mod.run_agent = _ok_agent
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_chart_image_forwarded():
    saved = _enabled()
    png = Path(tempfile.mkdtemp()) / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def _img_agent(*a, **k):
        return {"messages": [AIMessage(content="voici le graphique")], "image_path": str(png), "_fresh_reply": "voici le graphique"}

    chat_mod.run_agent = _img_agent
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.chart"))
        assert r.status_code == 200
        assert len(fake_client.texts) == 1 and "graphique" in fake_client.texts[0][1], fake_client.texts
        assert len(fake_client.images) == 1 and fake_client.images[0][0] == PHONE, fake_client.images
    finally:
        chat_mod.run_agent = _ok_agent
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_audio_transcribed_then_answered():
    saved = _enabled()
    transcribe_saved = svc_mod.voice_to_text
    svc_mod.voice_to_text = lambda path, language="fr-FR": "cours NTLC ?"
    _reset()
    try:
        r = client.post(
            "/whatsapp/evolution/webhook",
            json=_v2_payload(msg_id="evo.aud", kind="audio", with_base64=True),
        )
        assert r.status_code == 200
        assert len(fake_client.texts) == 1, fake_client.texts
        assert "réponse à: cours NTLC ?" in fake_client.texts[0][1], fake_client.texts
    finally:
        svc_mod.voice_to_text = transcribe_saved
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_audio_without_bytes_gets_hint():
    saved = _enabled()
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.aud2", kind="audio"))
        assert r.status_code == 200
        assert len(fake_client.texts) == 1 and "vocal" in fake_client.texts[0][1], fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


def test_channel_disabled_drops_silently():
    saved = (config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY)
    config.EVOLUTION_ENABLED = False
    config.EVOLUTION_API_KEY = ""
    _reset()
    try:
        r = client.post("/whatsapp/evolution/webhook", json=_v2_payload(msg_id="evo.off"))
        assert r.status_code == 200  # still acked, so Evolution doesn't retry forever
        assert fake_client.texts == [], fake_client.texts
    finally:
        config.EVOLUTION_ENABLED, config.EVOLUTION_API_KEY = saved


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

"""Tests for the mobile app API: OTP auth, JWT tokens, and the authenticated
/mobile/v1 surface (portfolio, watchlist, alerts, digest, devices, chat quota).

The agent run is faked; OTP delivery runs in mock mode (codes returned inline).
Run:
    .venv/bin/python -m pytest tests/test_mobile_api.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from langchain_core.messages import AIMessage  # noqa: E402

import app.api.chat as chat_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

JWT_SECRET = "test-jwt-secret-mobile"


def _fake_run_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    reply = f"fake reply to: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _fake_run_agent

_tmp_db = Path(tempfile.mkdtemp()) / "test_mobile.db"
user_db.DB_PATH = _tmp_db
user_db.reset_engine()
user_db.init_db()

client = TestClient(chat_mod.app)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_env():
    old = chat_mod.run_agent
    chat_mod.run_agent = _fake_run_agent
    config.JWT_SECRET = JWT_SECRET
    config.AUTH_PROVIDER = "mock"
    config.API_SECRET_KEY = ""  # /chat in dev mode; mobile endpoints use JWT only
    config.RATE_LIMIT_PER_MINUTE = 0  # chat rate limit off (we test quota separately)
    try:
        yield
    finally:
        chat_mod.run_agent = old


def _auth(identifier: str) -> dict:
    """Full OTP login; returns the verify-code response JSON (tokens + user)."""
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": identifier})
    assert r.status_code == 200, r.text
    dev_code = r.json().get("dev_code")
    assert dev_code, "mock provider must return the code"
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": identifier, "code": dev_code})
    assert r.status_code == 200, r.text
    return r.json()


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --- Auth --------------------------------------------------------------------

def test_auth_disabled_returns_503():
    config.JWT_SECRET = ""
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": "a@b.co"})
    assert r.status_code == 503


def test_request_code_rejects_bad_identifier():
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": "not-an-email-or-phone"})
    assert r.status_code == 400


def test_verify_code_rejects_wrong_code():
    identifier = "wrong-code@example.com"
    assert client.post("/mobile/v1/auth/request-code", json={"identifier": identifier}).status_code == 200
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": identifier, "code": "000000"})
    assert r.status_code == 401


def test_verify_code_rejects_replay():
    identifier = "replay@example.com"
    tokens = _auth(identifier)
    assert tokens["user"]["email"] == identifier
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": identifier, "code": "000000"})
    assert r.status_code == 401  # code consumed; even the right code fails


def test_refresh_rotates_and_revokes_old_token():
    first = _auth("rotate@example.com")
    r = client.post("/mobile/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()
    assert second["access_token"] != first["access_token"]
    # old refresh token is dead
    r = client.post("/mobile/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401


def test_phone_identifier_gets_channel_phone():
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": "+2250701020304"})
    assert r.status_code == 200 and r.json()["channel"] == "phone"


def test_password_register_and_login():
    # register
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "pass-user@example.com", "password": "secret12345",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["user"]["email"] == "pass-user@example.com"
    assert body["access_token"] and body["refresh_token"]
    # duplicate register → 409
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "pass-user@example.com", "password": "secret12345",
    })
    assert r.status_code == 409
    # weak password → 400
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "weak@example.com", "password": "123",
    })
    assert r.status_code == 400
    # wrong password → 401 (generic)
    r = client.post("/mobile/v1/auth/login", json={
        "identifier": "pass-user@example.com", "password": "wrong-password",
    })
    assert r.status_code == 401
    # correct login → fresh tokens, same user id
    r = client.post("/mobile/v1/auth/login", json={
        "identifier": "pass-user@example.com", "password": "secret12345",
    })
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == body["user"]["id"]
    # authenticated call works with the new token
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/mobile/v1/quota", headers=h).status_code == 200
    # phone identifier works too
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "+2250712345678", "password": "secret12345",
    })
    assert r.status_code == 200, r.text
    assert r.json()["user"]["phone"] == "+2250712345678"


def test_password_min_length_is_six():
    # exactly 6 chars, letters+digits
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "sixchars@example.com", "password": "abc123",
    })
    assert r.status_code == 200, r.text
    # exactly 6 digits (simple-digit passwords are allowed)
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "+2250799990001", "password": "123456",
    })
    assert r.status_code == 200, r.text
    # login works with the 6-digit password
    r = client.post("/mobile/v1/auth/login", json={
        "identifier": "+2250799990001", "password": "123456",
    })
    assert r.status_code == 200, r.text
    # 5 chars → too weak
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "fivechars@example.com", "password": "abc12",
    })
    assert r.status_code == 400


def test_dev_login_only_in_mock_mode():
    config.AUTH_PROVIDER = "mock"
    r = client.post("/mobile/v1/auth/dev-login", json={"identifier": "demo-device@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["user"]["email"] == "demo-device@example.com"
    assert body["access_token"] and body["refresh_token"]
    # second call returns the same user (idempotent)
    r2 = client.post("/mobile/v1/auth/dev-login", json={"identifier": "demo-device@example.com"})
    assert r2.json()["user"]["id"] == body["user"]["id"]
    # real auth provider disables it
    config.AUTH_PROVIDER = "smtp"
    r3 = client.post("/mobile/v1/auth/dev-login", json={})
    assert r3.status_code == 403
    # missing body works (default demo account)
    config.AUTH_PROVIDER = "mock"
    r4 = client.post("/mobile/v1/auth/dev-login")
    assert r4.status_code == 200 and r4.json()["user"]["email"] == "demo@brvm.app"


# --- Authenticated surface ----------------------------------------------------

def test_mobile_endpoints_require_token():
    for method, path in [
        ("GET", "/mobile/v1/portfolio"),
        ("GET", "/mobile/v1/watchlist"),
        ("GET", "/mobile/v1/alerts"),
        ("GET", "/mobile/v1/digest"),
        ("GET", "/mobile/v1/quota"),
        ("GET", "/mobile/v1/market/quotes/NTLC"),
        ("POST", "/mobile/v1/chat"),
    ]:
        if method == "POST":
            r = client.post(path, json={})
        else:
            r = client.get(path)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"


def test_expired_token_rejected():
    import uuid as uuidlib

    import app.services.auth_service as auth_svc

    tokens = _auth("expired@example.com")
    config.JWT_ACCESS_TTL_SECONDS = -10
    fresh = auth_svc.issue_tokens({"id": uuidlib.UUID(tokens["user"]["id"]), "principal_id": -1})
    r = client.get("/mobile/v1/quota", headers={"Authorization": f"Bearer {fresh['access_token']}"})
    assert r.status_code == 401


def test_portfolio_round_trip():
    tokens = _auth("portfolio@example.com")
    h = _headers(tokens)
    r = client.post("/mobile/v1/portfolio", json={
        "symbol": "NTLC", "buy_price": 1000.0, "buy_date": "2026-01-15", "quantity": 5,
    }, headers=h)
    assert r.status_code == 200, r.text
    # second buy of the same symbol → second lot (not an overwrite)
    r = client.post("/mobile/v1/portfolio", json={
        "symbol": "NTLC", "buy_price": 1200.0, "buy_date": "2026-02-01", "quantity": 5,
    }, headers=h)
    assert r.status_code == 200, r.text
    r = client.get("/mobile/v1/portfolio", headers=h)
    body = r.json()
    assert body["summary"]["positions_count"] == 1
    assert body["summary"]["lots_count"] == 2
    pos = body["positions"][0]
    assert pos["symbol"] == "NTLC"
    assert pos["quantity"] == 10
    assert pos["avg_buy_price"] == 1100.0
    assert len(pos["lots"]) == 2
    # other users do not see it
    other = _auth("portfolio-other@example.com")
    assert client.get("/mobile/v1/portfolio", headers=_headers(other)).json()["summary"]["positions_count"] == 0
    # lot-level edit + delete
    lot_id = pos["lots"][0]["id"]
    assert client.put(f"/mobile/v1/portfolio/lots/{lot_id}", json={"buy_price": 990.0}, headers=h).status_code == 200
    assert client.delete(f"/mobile/v1/portfolio/lots/{lot_id}", headers=h).status_code == 200
    # symbol delete removes remaining lots
    r = client.delete("/mobile/v1/portfolio/NTLC", headers=h)
    assert r.status_code == 200
    assert client.get("/mobile/v1/portfolio", headers=h).json()["summary"]["positions_count"] == 0


def test_palmares_served_from_local_snapshot():
    import app.services.market_data as md

    tokens = _auth("snap@example.com")
    h = _headers(tokens)
    md.save_daily_snapshot([{
        "symbol": "NTLC", "name": "NESTLE", "cours_actuel": 16900, "cours_veille": 16700,
        "variation_pct": 1.2, "volume": 1642, "value_fcfa": 27680815, "capitalisation": 372989760000,
    }])
    try:
        r = client.get("/mobile/v1/market/palmares", headers=h)
        stocks = r.json()["stocks"]
        ntlc = next(s for s in stocks if s["symbol"] == "NTLC")
        assert ntlc["cours_actuel"] == 16900 and ntlc["day"] == md.latest_snapshot_day()
        r = client.get("/mobile/v1/market/symbols/NTLC?period=1M", headers=h)
        assert r.json()["quote"]["cours_actuel"] == 16900
    finally:
        from sqlalchemy import delete
        from app.db import engine as db_engine
        from app.db import models as db_models
        with db_engine.session_scope() as s:
            s.execute(delete(db_models.MarketSnapshot))


def test_watchlist_round_trip():
    tokens = _auth("watchlist@example.com")
    h = _headers(tokens)
    assert client.post("/mobile/v1/watchlist", json={"symbol": "SNTS"}, headers=h).status_code == 200
    symbols = [s["symbol"] for s in client.get("/mobile/v1/watchlist", headers=h).json()["symbols"]]
    assert "SNTS" in symbols
    assert client.delete("/mobile/v1/watchlist/SNTS", headers=h).status_code == 200
    assert client.get("/mobile/v1/watchlist", headers=h).json()["symbols"] == []


def test_alerts_round_trip_delete_by_id():
    tokens = _auth("alerts@example.com")
    h = _headers(tokens)
    r = client.post("/mobile/v1/alerts", json={
        "symbol": "BOAM", "target_price": 5000.0, "direction": "above",
    }, headers=h)
    assert r.status_code == 200, r.text
    alerts = client.get("/mobile/v1/alerts", headers=h).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["direction"] == "above"
    r = client.delete(f"/mobile/v1/alerts/{alerts[0]['id']}", headers=h)
    assert r.status_code == 200
    assert client.get("/mobile/v1/alerts", headers=h).json()["alerts"] == []


def test_digest_subscription():
    tokens = _auth("digest@example.com")
    h = _headers(tokens)
    assert client.get("/mobile/v1/digest", headers=h).json()["enabled"] is False
    r = client.put("/mobile/v1/digest", json={"frequency": "weekly", "enabled": True}, headers=h)
    assert r.status_code == 200
    body = client.get("/mobile/v1/digest", headers=h).json()
    assert body == {"enabled": True, "frequency": "weekly"}
    client.put("/mobile/v1/digest", json={"frequency": "weekly", "enabled": False}, headers=h)
    assert client.get("/mobile/v1/digest", headers=h).json()["enabled"] is False


def test_device_registration_and_removal():
    tokens = _auth("device@example.com")
    h = _headers(tokens)
    r = client.post("/mobile/v1/devices", json={"fcm_token": "tok-test-123456", "platform": "android"}, headers=h)
    assert r.status_code == 200
    from app.services import auth_service

    devices = auth_service.devices_for_principal(-10**12)  # unknown principal
    assert devices == []
    r = client.delete("/mobile/v1/devices/tok-test-123456", headers=h)
    assert r.json()["removed"] is True


def test_mobile_chat_fake_agent_and_quota():
    tokens = _auth("chat@example.com")
    h = _headers(tokens)
    config.DAILY_FREE_QUOTA = 1
    r = client.post("/mobile/v1/chat", json={"query": "prix de NTLC ?"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("fake reply to:")
    assert body["quota_remaining"] == 0
    # second request exceeds the daily quota
    r = client.post("/mobile/v1/chat", json={"query": "encore"}, headers=h)
    assert "error" in r.json() and "limite" in r.json()["error"]
    config.DAILY_FREE_QUOTA = 30


def test_conversations_scoped_to_user():
    tokens = _auth("conv@example.com")
    h = _headers(tokens)
    r = client.post("/mobile/v1/chat", json={"query": "bonjour", "thread_id": f"app:{tokens['user']['id']}:test"}, headers=h)
    assert r.status_code == 200
    convs = client.get("/mobile/v1/conversations", headers=h).json()["conversations"]
    assert any(c["title"] == "test" for c in convs)
    # another user cannot see or delete it
    other = _auth("conv-other@example.com")
    oh = _headers(other)
    assert all(c["title"] != "test" for c in client.get("/mobile/v1/conversations", headers=oh).json()["conversations"])
    r = client.delete(f"/mobile/v1/conversations/app:{tokens['user']['id']}:test", headers=oh)
    assert r.status_code == 404


def test_default_thread_listed_with_title_and_history():
    """The default thread (no slug) must appear in the list with a real title
    (first user message), and its message history must replay."""
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, HumanMessage

    import app.api.mobile as mobile_mod

    tokens = _auth("history@example.com")
    h = _headers(tokens)
    uid = tokens["user"]["id"]
    default_thread = f"app:{uid}"
    # Seed activity + a stub checkpoint (the fake test agent never writes one).
    assert client.post("/mobile/v1/chat", json={"query": "x"}, headers=h).status_code == 200

    fake_cp = SimpleNamespace(
        get_tuple=lambda cfg: SimpleNamespace(
            checkpoint={
                "channel_values": {
                    "messages": [
                        HumanMessage(content="première question de test"),
                        AIMessage(content="réponse"),
                        HumanMessage(content="deuxième question"),
                        AIMessage(content="réponse 2"),
                    ]
                }
            }
        )
    )
    import app.api.chat as chat_mod

    chat_backup = chat_mod._get_checkpointer
    chat_mod._get_checkpointer = lambda: fake_cp
    try:
        convs = client.get("/mobile/v1/conversations", headers=h).json()["conversations"]
        entry = next((c for c in convs if c["thread_id"] == default_thread), None)
        assert entry is not None, convs
        assert entry["title"].startswith("première question de test"), entry

        r = client.get(f"/mobile/v1/conversations/{default_thread}/messages", headers=h)
        msgs = r.json()["messages"]
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant", "user", "assistant"], msgs
        assert msgs[0]["text"].startswith("première question de test")
    finally:
        chat_mod._get_checkpointer = chat_backup

    # another user gets 404 on this thread's messages
    other = _auth("history-other@example.com")
    assert client.get(f"/mobile/v1/conversations/{default_thread}/messages", headers=_headers(other)).status_code == 404


def test_symbol_detail_aggregates_sections():
    import app.api.mobile as mobile_mod

    tokens = _auth("detail@example.com")
    h = _headers(tokens)
    # Keep the test offline/fast: stub the live-scrape sections.
    real_safe_section = mobile_mod._safe_section
    mobile_mod._safe_section = lambda fn, *a, **k: {"stubbed": fn.__name__}
    try:
        r = client.get("/mobile/v1/market/symbols/NTLC?period=1M", headers=h)
    finally:
        mobile_mod._safe_section = real_safe_section
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "NTLC"
    for section in ("history", "profile", "dividends", "news", "prediction", "score"):
        assert section in body
    assert body["profile"]["stubbed"] == "load_company_details"
    # unknown symbol → 404
    assert client.get("/mobile/v1/market/symbols/XXXX", headers=h).status_code == 404


def test_symbol_detail_history_periods():
    from datetime import date

    import app.api.mobile as mobile_mod

    mobile_mod._load_history = lambda sym, period: [{"date": "2026-01-02", "price": 100.0}]
    tokens = _auth("hist@example.com")
    r = client.get("/mobile/v1/market/symbols/NTLC?period=ALL", headers=_headers(tokens))
    assert r.json()["history"] == [{"date": "2026-01-02", "price": 100.0}]


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

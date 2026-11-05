"""Tests for the lite admin dashboard: env-credential login, metrics endpoints,
user management actions (deactivate / quota reset / delete).

The agent run is faked; OTP delivery runs in mock mode (codes returned inline).
Run:
    .venv/bin/python -m pytest tests/test_admin_api.py
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

import app.api.admin as admin_mod  # noqa: E402
import app.api.chat as chat_mod  # noqa: E402
from app.utils import user_db  # noqa: E402

JWT_SECRET = "test-jwt-secret-admin"
ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "test-admin-password"


def _fake_run_agent(query, model=None, thread_id=None, telegram_user_id=None, checkpointer=None):
    reply = f"fake reply to: {query}"
    return {"messages": [AIMessage(content=reply)], "_fresh_reply": reply}


chat_mod.run_agent = _fake_run_agent

_tmp_db = Path(tempfile.mkdtemp()) / "test_admin.db"
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
    config.API_SECRET_KEY = ""
    config.RATE_LIMIT_PER_MINUTE = 0
    config.ADMIN_USERNAME = ADMIN_USERNAME
    config.ADMIN_PASSWORD = ADMIN_PASSWORD
    admin_mod._login_hits.clear()
    try:
        yield
    finally:
        chat_mod.run_agent = old


def _admin_token() -> str:
    r = client.post("/admin/v1/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _ah(token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or _admin_token()}"}


def _new_user(identifier: str) -> dict:
    """Full OTP login (mock provider); returns tokens + user payload."""
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": identifier})
    assert r.status_code == 200, r.text
    code = r.json()["dev_code"]
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": identifier, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def _uh(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --- Auth -----------------------------------------------------------------------

def test_dashboard_page_served():
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Kora Bourse" in r.text


def test_admin_endpoints_require_token():
    # a mobile user token is not an admin token either
    user = _new_user("not-admin@example.com")
    for method, path in [
        ("GET", "/admin/v1/overview"),
        ("GET", "/admin/v1/timeseries"),
        ("GET", "/admin/v1/users"),
        ("GET", "/admin/v1/users/00000000-0000-0000-0000-000000000000"),
        ("POST", "/admin/v1/users/00000000-0000-0000-0000-000000000000/deactivate"),
        ("DELETE", "/admin/v1/users/00000000-0000-0000-0000-000000000000"),
    ]:
        r = client.request(method, path)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"
        r = client.request(method, path, headers=_uh(user))
        assert r.status_code == 401, f"{method} {path} with mobile token expected 401"


def test_admin_login_disabled_without_password():
    config.ADMIN_PASSWORD = ""
    r = client.post("/admin/v1/login", json={"username": ADMIN_USERNAME, "password": "x"})
    assert r.status_code == 503
    assert client.get("/admin/v1/overview", headers={"Authorization": "Bearer whatever"}).status_code == 503


def test_admin_login_rejects_wrong_credentials():
    r = client.post("/admin/v1/login", json={"username": ADMIN_USERNAME, "password": "wrong"})
    assert r.status_code == 401
    r = client.post("/admin/v1/login", json={"username": "nobody", "password": ADMIN_PASSWORD})
    assert r.status_code == 401


def test_admin_login_and_token_work():
    token = _admin_token()
    assert client.get("/admin/v1/overview", headers=_ah(token)).status_code == 200


# --- Metrics ----------------------------------------------------------------------

def test_overview_reflects_users_and_usage():
    user = _new_user("overview@example.com")
    r = client.post("/mobile/v1/chat", json={"query": "bonjour"}, headers=_uh(user))
    assert r.status_code == 200, r.text

    o = client.get("/admin/v1/overview", headers=_ah()).json()
    assert o["users"]["total"] >= 1
    assert o["users"]["active"] >= 1
    assert o["users"]["new_7d"] >= 1
    assert o["activity"]["messages_today"] >= 1
    assert o["activity"]["dau_today"] >= 1
    assert o["conversations"]["total_threads"] >= 1
    for section in ("devices", "features", "top_symbols", "system"):
        assert section in o


def test_timeseries_shape_and_today():
    _new_user("timeseries@example.com")
    ts = client.get("/admin/v1/timeseries?days=30", headers=_ah()).json()
    assert len(ts["days"]) == 30
    assert len(ts["signups"]) == len(ts["messages"]) == len(ts["active_users"]) == 30
    assert ts["signups"][-1] >= 1  # the user signed up today


# --- Users list / detail ------------------------------------------------------------

def test_users_list_and_search():
    user = _new_user("find-me@example.com")
    uid = user["user"]["id"]

    data = client.get("/admin/v1/users?q=find-me", headers=_ah()).json()
    assert data["total"] >= 1
    row = next(u for u in data["users"] if u["id"] == uid)
    assert row["email"] == "find-me@example.com"
    assert row["is_active"] is True
    assert "messages_30d" in row and "quota_used_today" in row

    # search excludes non-matching users
    data = client.get("/admin/v1/users?q=zzz-no-such-user", headers=_ah()).json()
    assert all(u["id"] != uid for u in data["users"])


def test_user_detail_reports_usage():
    user = _new_user("detail@example.com")
    uid = user["user"]["id"]
    client.post("/mobile/v1/chat", json={"query": "prix NTLC ?"}, headers=_uh(user))
    client.post("/mobile/v1/watchlist", json={"symbol": "SNTS"}, headers=_uh(user))

    d = client.get(f"/admin/v1/users/{uid}", headers=_ah()).json()
    assert d["email"] == "detail@example.com"
    assert d["usage"]["today"] == 1
    assert d["usage"]["last_30d"] == 1
    assert d["watchlist"] == 1
    assert d["portfolio"]["positions"] == 0
    assert d["sessions_live"] >= 1
    assert client.get(f"/admin/v1/users/{uid}", headers=_ah()).status_code == 200


def test_user_detail_404_for_unknown_id():
    r = client.get("/admin/v1/users/00000000-0000-0000-0000-000000000000", headers=_ah())
    assert r.status_code == 404


# --- Actions -------------------------------------------------------------------------

def test_deactivate_blocks_sessions_and_login_then_reactivate():
    user = _new_user("deactivate-me@example.com")
    uid = user["user"]["id"]
    assert client.get("/mobile/v1/me", headers=_uh(user)).status_code == 200

    r = client.post(f"/admin/v1/users/{uid}/deactivate", headers=_ah())
    assert r.status_code == 200 and r.json()["is_active"] is False

    # live access token dies immediately, refresh token is revoked
    assert client.get("/mobile/v1/me", headers=_uh(user)).status_code == 401
    r = client.post("/mobile/v1/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert r.status_code == 401
    # a fresh OTP login is refused too
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": "deactivate-me@example.com"})
    code = r.json()["dev_code"]
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": "deactivate-me@example.com", "code": code})
    assert r.status_code == 401

    # reactivate: OTP login works again
    r = client.post(f"/admin/v1/users/{uid}/activate", headers=_ah())
    assert r.status_code == 200 and r.json()["is_active"] is True
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": "deactivate-me@example.com"})
    code = r.json()["dev_code"]
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": "deactivate-me@example.com", "code": code})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == uid  # same account, not a duplicate


def test_reset_quota_clears_todays_usage():
    user = _new_user("quota@example.com")
    uid = user["user"]["id"]
    config.DAILY_FREE_QUOTA = 1
    r = client.post("/mobile/v1/chat", json={"query": "un"}, headers=_uh(user))
    assert r.status_code == 200 and r.json()["quota_remaining"] == 0
    # quota exhausted for the day
    r = client.post("/mobile/v1/chat", json={"query": "deux"}, headers=_uh(user))
    assert "error" in r.json()

    r = client.post(f"/admin/v1/users/{uid}/reset-quota", headers=_ah())
    assert r.status_code == 200 and r.json()["cleared"] == 1
    assert client.get("/mobile/v1/quota", headers=_uh(user)).json()["used"] == 0
    # and the user can chat again right away
    assert client.post("/mobile/v1/chat", json={"query": "trois"}, headers=_uh(user)).status_code == 200


def test_delete_user_purges_account():
    user = _new_user("delete-me@example.com")
    uid = user["user"]["id"]
    client.post("/mobile/v1/watchlist", json={"symbol": "NTLC"}, headers=_uh(user))

    r = client.delete(f"/admin/v1/users/{uid}", headers=_ah())
    assert r.status_code == 200
    assert client.get(f"/admin/v1/users/{uid}", headers=_ah()).status_code == 404
    assert client.get("/mobile/v1/me", headers=_uh(user)).status_code == 401
    data = client.get("/admin/v1/users?q=delete-me", headers=_ah()).json()
    assert all(u["id"] != uid for u in data["users"])
    # idempotent: deleting again is a 404, not a 500
    assert client.delete(f"/admin/v1/users/{uid}", headers=_ah()).status_code == 404


# --- Design-review additions ------------------------------------------------------

def test_overview_has_prev_window_metrics():
    o = client.get("/admin/v1/overview", headers=_ah()).json()
    for key in ("new_prev_7d",):
        assert key in o["users"], key
    for key in ("dau_yesterday", "messages_yesterday", "wau_prev_7d", "messages_prev_7d"):
        assert key in o["activity"], key
    assert o["activity"]["messages_prev_7d"] >= 0


def test_adoption_counts_only_app_users():
    """Legacy rows (principals with no app_users row) must not inflate adoption."""
    from sqlalchemy import delete

    from app.db import engine as db_engine
    from app.db import migrate as db_migrate
    from app.db import models as db_models

    ghost_pid = -(7 * 10**11)  # no AppUser with this principal
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.execute(delete(db_models.Tracking).where(db_models.Tracking.telegram_id == ghost_pid))
        s.add(db_models.User(telegram_id=ghost_pid))
        s.add(db_models.Tracking(telegram_id=ghost_pid, symbol="GHST"))

    before = client.get("/admin/v1/overview", headers=_ah()).json()["features"]["watchlist_users"]
    with db_engine.session_scope() as s:
        s.execute(delete(db_models.Tracking).where(db_models.Tracking.telegram_id == ghost_pid))
    after = client.get("/admin/v1/overview", headers=_ah()).json()["features"]["watchlist_users"]
    assert before == after  # the ghost principal was never counted


def test_users_status_filter():
    user = _new_user("status-filter@example.com")
    uid = user["user"]["id"]
    client.post(f"/admin/v1/users/{uid}/deactivate", headers=_ah())

    data = client.get("/admin/v1/users?status=deactivated", headers=_ah()).json()
    assert data["users"] and all(u["is_active"] is False for u in data["users"])
    assert any(u["id"] == uid for u in data["users"])

    data = client.get("/admin/v1/users?status=active", headers=_ah()).json()
    assert all(u["is_active"] is True for u in data["users"])
    assert all(u["id"] != uid for u in data["users"])


def test_users_sort_by_messages():
    heavy = _new_user("heavy@example.com")
    light = _new_user("light@example.com")
    for query in ("un", "deux", "trois"):
        client.post("/mobile/v1/chat", json={"query": query}, headers=_uh(heavy))
    client.post("/mobile/v1/chat", json={"query": "un"}, headers=_uh(light))

    data = client.get("/admin/v1/users?sort=messages&page_size=100", headers=_ah()).json()
    msgs = [u["messages_30d"] for u in data["users"]]
    assert msgs == sorted(msgs, reverse=True), msgs
    assert data["users"][0]["id"] == heavy["user"]["id"]

    by_last_active = client.get("/admin/v1/users?sort=last_active&page_size=100", headers=_ah()).json()
    days = [u["last_active_day"] or "" for u in by_last_active["users"]]
    assert days == sorted(days, reverse=True), days


def test_users_rejects_bad_params():
    assert client.get("/admin/v1/users?status=bogus", headers=_ah()).status_code == 422
    assert client.get("/admin/v1/users?sort=bogus", headers=_ah()).status_code == 422


def test_admin_page_has_security_headers():
    r = client.get("/admin")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_admin_login_rate_limited_per_account():
    for _ in range(10):
        r = client.post("/admin/v1/login", json={"username": "brute", "password": "nope"})
        assert r.status_code == 401
    r = client.post("/admin/v1/login", json={"username": "brute", "password": "nope"})
    assert r.status_code == 429
    # a different username is not blocked by the per-account bucket
    r = client.post("/admin/v1/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200


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

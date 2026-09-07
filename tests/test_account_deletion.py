"""Account deletion tests (Google Play in-app account deletion requirement).

DELETE /mobile/v1/me must purge every row owned by the app user — refresh
tokens and devices (by user UUID), portfolio/tracking/alerts/digest/users (by
principal id), daily usage, conversation threads (+ LangGraph checkpoints,
best-effort), OTP codes, and finally the app_users row. Password-protected
accounts must confirm their password; demo accounts delete without one.
Run:
    .venv/bin/python -m pytest tests/test_account_deletion.py
"""
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

import app.api.chat as chat_mod  # noqa: E402
from app.db import engine as db_engine  # noqa: E402
from app.db import models  # noqa: E402
from app.services import auth_service  # noqa: E402
from app.utils import user_db  # noqa: E402

JWT_SECRET = "test-jwt-secret-deletion"

# Throwaway DB: the dev DB (app/data/brvm_bot.db) is held by a running server.
_tmp_db = Path(tempfile.mkdtemp()) / "test_deletion.db"
user_db.DB_PATH = _tmp_db
user_db.reset_engine()
user_db.init_db()

client = TestClient(chat_mod.app)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_env():
    """Other test modules rebind config / user_db.DB_PATH too; pin per test."""
    old_db_path = user_db.DB_PATH
    user_db.DB_PATH = _tmp_db
    config.JWT_SECRET = JWT_SECRET
    config.AUTH_PROVIDER = "mock"
    config.API_SECRET_KEY = ""
    config.RATE_LIMIT_PER_MINUTE = 0
    try:
        yield
    finally:
        user_db.DB_PATH = old_db_path


class _FakeCheckpointer:
    """Records checkpoint deletions without touching a real checkpoint DB."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


@pytest.fixture
def fake_checkpointer(monkeypatch):
    cp = _FakeCheckpointer()
    monkeypatch.setattr(chat_mod, "_get_checkpointer", lambda: cp)
    return cp


def _make_user(email: str, password: str | None = None):
    if password is not None:
        user, err = auth_service.register_user(email, password)
        assert err is None
    else:
        user = auth_service.get_or_create_app_user(email=email)
    return user, auth_service.issue_tokens(user)


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _delete_me(tokens: dict, body: dict | None = None):
    kwargs: dict = {"headers": _headers(tokens)}
    if body is not None:
        kwargs["json"] = body
    return client.request("DELETE", "/mobile/v1/me", **kwargs)


def _seed_all(user: dict) -> list[str]:
    """Insert one row per user-owned table; returns the seeded thread ids."""
    pid, uid = user["principal_id"], user["id"]
    assert user_db.portfolio_add(pid, "NTLC", 1000.0, "2026-01-15", 5)["ok"]
    assert user_db.tracking_add(pid, "SNTS")["ok"]
    assert user_db.target_add(pid, "BOAM", 5000.0, "above")["ok"]
    assert user_db.digest_set(pid, "daily")["ok"]
    auth_service.register_device(uid, f"fcm-token-{uid}", "android")
    auth_service.issue_tokens(user)  # second refresh token row
    user_db.increment_daily_usage(f"app:{uid}")
    thread_ids = [f"app:{uid}", f"app:{uid}:conv-1"]
    with db_engine.session_scope() as s:
        for tid in thread_ids:
            s.add(models.ThreadActivity(thread_id=tid, last_seen=123.0))
        s.add(models.OtpCode(
            identifier=user["email"],
            channel="email",
            code_hash="x" * 64,
            purpose="login",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
    return thread_ids


def _counts(user: dict) -> dict[str, int]:
    """Row counts owned by this user in every table a deletion must purge."""
    pid, uid = user["principal_id"], user["id"]
    prefix = f"app:{uid}"
    with db_engine.session_scope() as s:
        def n(model, *conds) -> int:
            return int(s.execute(
                select(func.count()).select_from(model).where(*conds)
            ).scalar_one())

        return {
            "app_users": n(models.AppUser, models.AppUser.id == uid),
            "refresh_tokens": n(models.RefreshToken, models.RefreshToken.user_id == uid),
            "devices": n(models.Device, models.Device.user_id == uid),
            "portfolio": n(models.Portfolio, models.Portfolio.telegram_id == pid),
            "tracking": n(models.Tracking, models.Tracking.telegram_id == pid),
            "target_alerts": n(models.TargetAlert, models.TargetAlert.telegram_id == pid),
            "digest_subscriptions": n(models.DigestSubscription, models.DigestSubscription.telegram_id == pid),
            "users": n(models.User, models.User.telegram_id == pid),
            "usage_daily": n(models.UsageDaily, models.UsageDaily.user_id == prefix),
            "thread_activity": n(
                models.ThreadActivity,
                (models.ThreadActivity.thread_id == prefix)
                | models.ThreadActivity.thread_id.like(prefix + ":%"),
            ),
            "otp_codes": n(models.OtpCode, models.OtpCode.identifier == user["email"]),
        }


# --- Password-protected accounts --------------------------------------------

def test_delete_wrong_password_keeps_everything(fake_checkpointer):
    user, tokens = _make_user("del-wrong@example.com", password="secret12345")
    _seed_all(user)
    before = _counts(user)
    assert all(v >= 1 for v in before.values()), before  # seeding sanity
    r = _delete_me(tokens, {"password": "not-the-password"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Mot de passe incorrect."
    assert _counts(user) == before
    assert fake_checkpointer.deleted == []
    # the session is still valid
    assert client.get("/mobile/v1/me", headers=_headers(tokens)).status_code == 200


def test_delete_missing_password_rejected_for_password_account(fake_checkpointer):
    user, tokens = _make_user("del-nopw@example.com", password="secret12345")
    assert _delete_me(tokens).status_code == 401    # no body at all
    assert _delete_me(tokens, {}).status_code == 401  # empty body
    assert _counts(user)["app_users"] == 1
    assert fake_checkpointer.deleted == []


def test_delete_with_password_purges_everything(fake_checkpointer):
    user, tokens = _make_user("del-full@example.com", password="secret12345")
    thread_ids = _seed_all(user)
    r = _delete_me(tokens, {"password": "secret12345"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    counts = _counts(user)
    assert counts == {k: 0 for k in counts}, counts
    assert sorted(fake_checkpointer.deleted) == sorted(thread_ids)
    # the old access token is dead (the account row is gone)
    assert client.get("/mobile/v1/me", headers=_headers(tokens)).status_code == 401
    # the refresh token is gone too: no rotation possible
    r = client.post("/mobile/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
    # the e-mail is free again: re-registering creates a NEW account id
    user2, err = auth_service.register_user("del-full@example.com", "secret12345")
    assert err is None and user2["id"] != user["id"]


# --- Passwordless (demo/mock) accounts ----------------------------------------

def test_delete_demo_user_without_password(fake_checkpointer):
    user, tokens = _make_user("del-demo@example.com")  # no password set
    _seed_all(user)
    r = _delete_me(tokens, {})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    counts = _counts(user)
    assert counts == {k: 0 for k in counts}, counts


# --- has_password flag --------------------------------------------------------

def test_me_exposes_has_password():
    _, tokens_pw = _make_user("me-pw@example.com", password="secret12345")
    body = client.get("/mobile/v1/me", headers=_headers(tokens_pw)).json()
    assert body["has_password"] is True
    _, tokens_demo = _make_user("me-demo@example.com")
    body = client.get("/mobile/v1/me", headers=_headers(tokens_demo)).json()
    assert body["has_password"] is False
    # the auth payloads expose the boolean too (never the hash itself)
    r = client.post("/mobile/v1/auth/register", json={
        "identifier": "me-reg@example.com", "password": "secret12345",
    })
    assert r.status_code == 200 and r.json()["user"]["has_password"] is True
    assert "password_hash" not in r.text
    r = client.post("/mobile/v1/auth/dev-login", json={"identifier": "me-dev@example.com"})
    assert r.json()["user"]["has_password"] is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        cp = _FakeCheckpointer()
        chat_mod._get_checkpointer = lambda: cp
        try:
            if "fake_checkpointer" in t.__code__.co_varnames:
                t(cp)
            else:
                t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

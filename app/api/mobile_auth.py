"""Mobile app auth endpoints: OTP request/verify, token refresh, logout.

Mounted under /mobile/v1. The Flutter app authenticates with JWT bearer
tokens; it never sees the bot's shared API_SECRET_KEY.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import config
from app.services import auth_service

router = APIRouter(prefix="/mobile/v1/auth", tags=["mobile-auth"])

# --- Coarse brute-force protection on auth endpoints (in-memory, per-process) --
_AUTH_WINDOW_SEC = 60.0
_AUTH_LIMIT = 10  # attempts per identifier per minute
_auth_hits: dict[str, list[float]] = {}
_auth_lock = threading.Lock()


def _auth_throttled(key: str) -> bool:
    now = time.monotonic()
    with _auth_lock:
        hits = [t for t in _auth_hits.get(key, []) if now - t < _AUTH_WINDOW_SEC]
        if len(hits) >= _AUTH_LIMIT:
            _auth_hits[key] = hits
            return True
        hits.append(now)
        _auth_hits[key] = hits
        return False


def _require_auth_enabled() -> None:
    if not auth_service.auth_enabled():
        raise HTTPException(status_code=503, detail="Mobile auth is not enabled.")


class RequestCodeBody(BaseModel):
    identifier: str = Field(min_length=3, max_length=120)


class VerifyCodeBody(BaseModel):
    identifier: str = Field(min_length=3, max_length=120)
    code: str = Field(min_length=4, max_length=12)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=20)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["id"]),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "has_telegram": user.get("telegram_id") is not None,
    }


@router.post("/request-code")
def request_code(body: RequestCodeBody, request: Request) -> dict[str, Any]:
    _require_auth_enabled()
    client = request.client.host if request.client else "unknown"
    if _auth_throttled(f"{client}:{body.identifier}"):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez plus tard.")
    result = auth_service.request_code(body.identifier)
    if not result.get("ok"):
        error = result.get("error", "error")
        if error == "retry_later":
            raise HTTPException(
                status_code=429,
                detail={"message": "Un code a déjà été envoyé. Patientez avant de réessayer.", "retry_after_seconds": result.get("retry_after_seconds", 60)},
            )
        if error == "delivery_failed":
            raise HTTPException(status_code=502, detail="L'envoi du code a échoué. Réessayez plus tard.")
        if error == "auth_disabled":
            raise HTTPException(status_code=503, detail="Mobile auth is not enabled.")
        raise HTTPException(status_code=400, detail=result.get("error"))
    response: dict[str, Any] = {"ok": True, "channel": result["channel"]}
    if "dev_code" in result:  # AUTH_PROVIDER=mock only
        response["dev_code"] = result["dev_code"]
    return response


@router.post("/verify-code")
def verify_code(body: VerifyCodeBody, request: Request) -> dict[str, Any]:
    _require_auth_enabled()
    client = request.client.host if request.client else "unknown"
    if _auth_throttled(f"{client}:{body.identifier}"):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez plus tard.")
    result = auth_service.verify_code(body.identifier, body.code)
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail="Code invalide ou expiré.")
    user = result["user"]
    tokens = auth_service.issue_tokens(user)
    return {"ok": True, "user": _public_user(user), **tokens}


@router.post("/refresh")
def refresh(body: RefreshBody) -> dict[str, Any]:
    _require_auth_enabled()
    tokens = auth_service.refresh_tokens(body.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Session expirée. Reconnectez-vous.")
    return {"ok": True, **tokens}


@router.post("/logout")
def logout(body: RefreshBody) -> dict[str, Any]:
    auth_service.revoke_refresh_token(body.refresh_token)
    return {"ok": True}


class DevLoginBody(BaseModel):
    """Optional label so several demo devices don't share one account."""
    identifier: str | None = Field(default=None, max_length=120)


@router.post("/dev-login")
def dev_login(body: DevLoginBody | None = None) -> dict[str, Any]:
    """DEV ONLY: obtain a session without OTP. Enabled exclusively when
    AUTH_PROVIDER=mock; any real provider (smtp/twilio) disables it (503),
    so it can never exist in production."""
    _require_auth_enabled()
    if config.AUTH_PROVIDER != "mock":
        raise HTTPException(status_code=403, detail="Dev login is only available in mock auth mode.")
    identifier = (body.identifier if body else None) or "demo@brvm.app"
    classified = auth_service.classify_identifier(identifier)
    email = classified[1] if classified and classified[0] == "email" else None
    phone = classified[1] if classified and classified[0] == "phone" else None
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Identifiant invalide.")
    user = auth_service.get_or_create_app_user(email=email, phone=phone)
    if user is None:
        raise HTTPException(status_code=500, detail="user_error")
    tokens = auth_service.issue_tokens(user)
    return {"ok": True, "user": _public_user(user), **tokens}


# --- Shared bearer-auth dependency (used by the mobile API router) ------------

def require_app_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: resolve the Authorization bearer token to an app user."""
    _require_auth_enabled()
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = auth_service.authenticate_access_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré.")
    return user


AppUserDep = Depends(require_app_user)

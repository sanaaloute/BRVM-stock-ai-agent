"""FCM push notifications (Android + iOS via firebase-admin).

Disabled until FIREBASE_CREDENTIALS is set (service-account JSON path or inline
JSON document). Importing this module never requires Firebase — the SDK loads
lazily on first send.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

_app_initialized = False


def push_enabled() -> bool:
    return bool(config.FIREBASE_CREDENTIALS)


def _ensure_app() -> None:
    global _app_initialized
    if _app_initialized:
        return
    import firebase_admin
    from firebase_admin import credentials

    creds = config.FIREBASE_CREDENTIALS
    if creds.strip().startswith("{"):
        info = json.loads(creds)
        credential = credentials.Certificate(info)
    else:
        credential = credentials.Certificate(str(Path(creds).expanduser()))
    firebase_admin.initialize_app(credential)
    _app_initialized = True


def send_push(tokens: list[str], title: str, body: str, data: dict[str, str] | None = None) -> int:
    """Multicast one notification; returns the number of successfully sent pushes."""
    if not tokens or not push_enabled():
        return 0
    try:
        _ensure_app()
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(headers={"apns-priority": "10"}),
        )
        result = messaging.send_each_for_multicast(message)
        stale = [tokens[i] for i, r in enumerate(result.responses) if not r.success and _is_invalid_token(r)]
        for token in stale:
            from app.services import auth_service

            auth_service.remove_device(token)
        sent = result.success_count
        if result.failure_count:
            logger.warning("FCM multicast: %d failed", result.failure_count)
        return sent
    except Exception:
        logger.exception("FCM push failed")
        return 0


def _is_invalid_token(response: Any) -> bool:
    code = getattr(getattr(response, "exception", None), "code", "") or ""
    return code in ("messaging/registration-token-not-registered", "messaging/invalid-registration-token")

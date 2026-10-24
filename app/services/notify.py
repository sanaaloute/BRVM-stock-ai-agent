"""User notification dispatch: FCM push to the user's registered app devices.
Alert/digest jobs call notify_user() so app users get pushes."""
from __future__ import annotations

import logging

from app.services import auth_service
from app.services.push import push_enabled, send_push

logger = logging.getLogger(__name__)

_PUSH_BODY_MAX = 350  # keep push payloads small; full text stays in the app


def notify_user(principal_id: int, text: str, *, push_title: str = "BRVM") -> None:
    """Deliver `text` to every app device the user has registered (FCM)."""
    devices = auth_service.devices_for_principal(principal_id)
    if devices and push_enabled():
        body = text if len(text) <= _PUSH_BODY_MAX else text[: _PUSH_BODY_MAX - 1].rstrip() + "…"
        sent = send_push([d["fcm_token"] for d in devices], push_title, body)
        if sent:
            logger.info("Push sent to principal %s (%d device(s))", principal_id, sent)
    elif devices:
        logger.info("Devices registered for %s but FCM is not configured; skipping push.", principal_id)

"""User notification dispatch: FCM push to app devices + Telegram message when
the principal id is a real linked Telegram account. Alert/digest jobs call
notify_user() so app users get pushes without any Telegram coupling.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services import auth_service
from app.services.push import push_enabled, send_push

logger = logging.getLogger(__name__)

_PUSH_BODY_MAX = 350  # keep push payloads small; full text stays in the app


def notify_user(
    principal_id: int,
    text: str,
    *,
    bot: Any = None,
    application: Any = None,
    push_title: str = "BRVM",
) -> None:
    """Deliver `text` to every channel the user has: FCM push (app devices) and
    Telegram (when principal_id is a real, positive Telegram id)."""
    devices = auth_service.devices_for_principal(principal_id)
    if devices and push_enabled():
        body = text if len(text) <= _PUSH_BODY_MAX else text[: _PUSH_BODY_MAX - 1].rstrip() + "…"
        sent = send_push([d["fcm_token"] for d in devices], push_title, body)
        if sent:
            logger.info("Push sent to principal %s (%d device(s))", principal_id, sent)
    elif devices:
        logger.info("Devices registered for %s but FCM is not configured; skipping push.", principal_id)

    if principal_id > 0 and bot is not None and application is not None:
        try:
            from app.bot.telegram_bot import split_text

            for chunk in split_text(text):
                application.create_task(bot.send_message(chat_id=principal_id, text=chunk))
        except Exception as e:
            logger.warning("Telegram dispatch to %s failed: %s", principal_id, e)

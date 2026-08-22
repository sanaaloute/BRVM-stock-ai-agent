"""Evolution API webhook for the WhatsApp channel.

Exposes on the Chat API app:
  POST /whatsapp/evolution/webhook — inbound messages from Evolution

Deliveries are authenticated with the instance API key (Evolution sends it as
the `apikey` header), acked immediately, and processed in the background so
Evolution never retries a slow agent answer. Text and voice notes are answered
through the same AI pipeline as Telegram; each user is identified as
"wa:<phone>" so quota and conversation memory work per person.

Setup: set EVOLUTION_URL / EVOLUTION_API_KEY / EVOLUTION_INSTANCE in .env,
then point the instance webhook (event MESSAGES_UPSERT, base64 enabled for
voice notes) at https://<your-api-host>/whatsapp/evolution/webhook.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

import config

from .schemas import parse_inbound_messages
from .service import WhatsAppService, get_whatsapp_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Dedup of delivered message ids (Evolution retries delivery until we ack).
_seen_ids: dict[str, float] = {}
_seen_lock = threading.Lock()


def _is_duplicate(message_id: str) -> bool:
    now = time.monotonic()
    with _seen_lock:
        for k, t in [kv for kv in _seen_ids.items() if now - kv[1] > config.WHATSAPP_DEDUP_TTL_SECONDS]:
            _seen_ids.pop(k, None)
        if message_id in _seen_ids:
            return True
        _seen_ids[message_id] = now
    return False


def _verify_apikey(apikey: str | None) -> None:
    """Authenticate the delivery with the instance API key (constant-time compare).

    When EVOLUTION_API_KEY is empty the channel is disabled anyway; verification
    is skipped so local dev payloads still flow.
    """
    expected = config.EVOLUTION_API_KEY
    if not expected:
        return
    if not apikey or not secrets.compare_digest(apikey.strip(), expected):
        logger.warning("Evolution webhook rejected: invalid or missing apikey header.")
        raise HTTPException(status_code=401, detail="Invalid or missing apikey.")


@router.post("/whatsapp/evolution/webhook")
async def receive_evolution_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    apikey: str | None = Header(default=None),
    service: WhatsAppService = Depends(get_whatsapp_service),
):
    _verify_apikey(apikey)
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}  # ack anyway so Evolution stops retrying
    if not isinstance(payload, dict):
        logger.debug("Evolution webhook: non-object payload dropped.")
        return {"status": "ok"}
    if not config.EVOLUTION_ENABLED:
        logger.debug("Evolution payload received but channel is disabled; dropping.")
        return {"status": "ok"}
    for msg in parse_inbound_messages(payload):
        if msg.message_id and _is_duplicate(msg.message_id):
            logger.info("Duplicate Evolution delivery skipped: %s", msg.message_id)
            continue
        background_tasks.add_task(service.handle_message, msg)
    return {"status": "ok"}

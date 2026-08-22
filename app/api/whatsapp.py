"""WhatsApp Business Cloud API channel.

Exposes the Meta webhook on the Chat API app:
  GET  /whatsapp/webhook  — verification handshake (hub.mode/hub.verify_token/hub.challenge)
  POST /whatsapp/webhook  — inbound messages

Inbound text is answered through the same chat pipeline as Telegram (quota,
rate limits, agent, memory): each WhatsApp user is identified as "wa:<phone>"
so usage metering works per person. Replies are sent back via the Graph API.

Setup: create a Meta app with the WhatsApp product, set WHATSAPP_VERIFY_TOKEN,
WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env, then point the
Meta webhook at https://<your-api-host>/whatsapp/webhook.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

import config

logger = logging.getLogger(__name__)

router = APIRouter()

GRAPH_API_VERSION = "v21.0"
MAX_MESSAGE_LENGTH = 4000  # WhatsApp text limit is 4096; keep margin
UNSUPPORTED_TYPE_MSG = (
    "Pour l'instant, seuls les messages texte sont supportés. "
    "Envoyez votre question en texte (ex: « cours NTLC ? »)."
)
GENERIC_ERROR_MSG = "Une erreur est survenue. Réessayez dans un instant."

# Dedup of delivered message ids (Meta retries delivery until we ack).
_seen_ids: dict[str, float] = {}
_seen_lock = threading.Lock()


def _is_duplicate(wamid: str) -> bool:
    now = time.monotonic()
    ttl = config.WHATSAPP_DEDUP_TTL_SECONDS  # Meta can retry long after 10 min
    with _seen_lock:
        for k, t in [kv for kv in _seen_ids.items() if now - kv[1] > ttl]:
            _seen_ids.pop(k, None)
        if wamid in _seen_ids:
            return True
        _seen_ids[wamid] = now
    return False


def _graph_post(path: str, *, json_body: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            url,
            headers={"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"},
            json=json_body,
            files=files,
            data=data,
        )
        resp.raise_for_status()
        return resp.json()


def send_message(to: str, text: str) -> None:
    """Send a single text message (caller chunks long text)."""
    if not text:
        return
    _graph_post(
        "/messages",
        json_body={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
    )


def send_image(to: str, png_bytes: bytes, caption: str = "") -> None:
    """Upload a PNG to Meta then send it as an image message."""
    uploaded = _graph_post(
        "/media",
        data={"messaging_product": "whatsapp", "type": "image/png"},
        files={"file": ("chart.png", png_bytes, "image/png")},
    )
    media_id = uploaded.get("id")
    if not media_id:
        logger.warning("Media upload returned no id: %s", uploaded)
        return
    image: dict[str, Any] = {"id": media_id}
    if caption:
        image["caption"] = caption[:1024]
    _graph_post(
        "/messages",
        json_body={"messaging_product": "whatsapp", "to": to, "type": "image", "image": image},
    )


def _split_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    chunks: list[str] = []
    text = text or ""
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


# Bound concurrent background processing of webhook deliveries.
_process_semaphore = asyncio.Semaphore(8)


async def _process_text(phone: str, body: str) -> None:
    """Run one WhatsApp text message through the shared chat pipeline and reply."""
    # Lazy import: app.api.chat includes this router, so importing it at module
    # load would be circular.
    from app.api.chat import ChatError, ChatRequest, run_chat

    user_id = f"wa:{phone}"
    async with _process_semaphore:
        try:
            result = await run_chat(ChatRequest(query=body, thread_id=f"wa-{phone}", user_id=user_id))
            if isinstance(result, ChatError):
                await asyncio.to_thread(send_message, phone, result.error)
                return
            for chunk in _split_text(result.reply):
                await asyncio.to_thread(send_message, phone, chunk)
            if result.image_base64:
                try:
                    await asyncio.to_thread(
                        send_image, phone, base64.b64decode(result.image_base64), caption="📊"
                    )
                except Exception as e:
                    logger.warning("WhatsApp image send failed for %s: %s", phone, e)
        except Exception:
            logger.exception("WhatsApp processing failed for %s", phone)
            try:
                await asyncio.to_thread(send_message, phone, GENERIC_ERROR_MSG)
            except Exception:
                pass


def _iter_messages(payload: dict):
    """Yield (phone, wamid, msg_type, text_body) for each inbound message."""
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                phone = msg.get("from")
                wamid = msg.get("id") or ""
                mtype = msg.get("type") or ""
                body = ((msg.get("text") or {}).get("body") or "").strip() if mtype == "text" else ""
                if phone:
                    yield phone, wamid, mtype, body


@router.get("/whatsapp/webhook")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected = config.WHATSAPP_VERIFY_TOKEN
    if (
        hub_mode == "subscribe"
        and expected
        and hub_verify_token is not None
        and secrets.compare_digest(hub_verify_token, expected)
        and hub_challenge is not None
    ):
        logger.info("WhatsApp webhook verified.")
        return PlainTextResponse(hub_challenge)
    logger.warning("WhatsApp webhook verification rejected (mode=%r).", hub_mode)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_bytes = await request.body()
    if not config.WHATSAPP_ENABLED:
        logger.debug("WhatsApp payload received but channel is disabled; dropping.")
        return {"status": "ok"}
    # Authenticate the delivery: Meta signs the raw body with the app secret.
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        config.WHATSAPP_APP_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    if not secrets.compare_digest(signature, expected):
        logger.warning("WhatsApp webhook rejected: invalid X-Hub-Signature-256.")
        raise HTTPException(status_code=401, detail="Invalid signature.")
    try:
        payload = json.loads(payload_bytes)
    except Exception:
        return {"status": "ok"}  # ack anyway so Meta stops retrying
    for phone, wamid, mtype, body in _iter_messages(payload):
        if wamid and _is_duplicate(wamid):
            logger.info("Duplicate WhatsApp delivery skipped: %s", wamid)
            continue
        if mtype == "text" and body:
            background_tasks.add_task(_process_text, phone, body)
        elif mtype in ("image", "audio", "video", "document"):
            background_tasks.add_task(send_message, phone, UNSUPPORTED_TYPE_MSG)
        else:
            logger.debug("Ignoring WhatsApp message type %r from %s", mtype, phone)
    return {"status": "ok"}

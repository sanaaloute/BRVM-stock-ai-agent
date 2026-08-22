"""WhatsApp channel service: inbound message -> ChatService -> Evolution reply.

Flow (identical AI backend as Telegram — the agent never sees the platform):

    inbound message
        -> extract user id (WhatsApp phone number, e.g. "22670000000")
        -> ChatService.chat("wa:<phone>", message)      # shared AI pipeline
        -> EvolutionClient.send_text(...)               # reply (+ chart image)

Supported inbound types: text and audio (voice notes transcribed like the
Telegram channel). Everything else gets a short "unsupported" hint.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
from pathlib import Path

from app.bot.voice_to_text import voice_to_text
from app.services.chat_service import ChatService, ChatServiceResult, chat_service

from .evolution_client import EvolutionClient, EvolutionError
from .schemas import InboundMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000  # WhatsApp text limit is 4096; keep margin
VOICE_LANGUAGE = "fr-FR"

UNSUPPORTED_TYPE_MSG = (
    "Pour l'instant, seuls les messages texte et vocaux sont supportés. "
    "Envoyez votre question en texte (ex: « cours NTLC ? »)."
)
AUDIO_FAILED_MSG = (
    "Votre message vocal n'a pas pu être transcrit. "
    "Envoyez votre question en texte (ex: « cours NTLC ? »)."
)
GENERIC_ERROR_MSG = "Une erreur est survenue. Réessayez dans un instant."

_MIMETYPE_SUFFIX = {
    "mpeg": ".mp3",
    "mp3": ".mp3",
    "mp4": ".m4a",
    "m4a": ".m4a",
    "wav": ".wav",
    "ogg": ".ogg",
    "opus": ".ogg",
}


def _split_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long reply on line boundaries so each chunk fits WhatsApp."""
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


def _audio_suffix(mimetype: str | None) -> str:
    mime = (mimetype or "").split(";")[0].strip().lower()
    return _MIMETYPE_SUFFIX.get(mime.split("/")[-1], ".ogg") if mime else ".ogg"


# Bound concurrent background processing of webhook deliveries.
_handle_semaphore = asyncio.Semaphore(8)


class WhatsAppService:
    """Orchestrates one inbound WhatsApp message end to end."""

    def __init__(
        self,
        client: EvolutionClient | None = None,
        chat: ChatService | None = None,
    ) -> None:
        self._client = client or EvolutionClient()
        self._chat = chat or chat_service

    async def handle_message(self, msg: InboundMessage) -> None:
        """Dispatch one inbound message. Never raises (webhook must not crash)."""
        async with _handle_semaphore:
            try:
                if msg.kind == "text":
                    await self._process_text(msg.phone, msg.text)
                elif msg.kind == "audio":
                    await self._process_audio(msg)
                else:
                    await self._send_safe(msg.phone, UNSUPPORTED_TYPE_MSG)
            except Exception:
                logger.exception("WhatsApp processing failed for %s", msg.phone)
                await self._send_safe(msg.phone, GENERIC_ERROR_MSG)

    # --- Inbound processing -------------------------------------------------

    async def _process_text(self, phone: str, text: str) -> None:
        """Run a text message through the shared pipeline and send the reply."""
        if not text:
            return
        user_id = f"wa:{phone}"
        result = await self._chat.chat(user_id, text, thread_id=f"wa-{phone}")
        await self._send_result(phone, result)

    async def _process_audio(self, msg: InboundMessage) -> None:
        """Transcribe a voice note (like the Telegram channel) then treat as text."""
        audio_b64 = msg.audio_base64 or await self._client.get_media_base64(msg.raw_message)
        if not audio_b64:
            logger.info("No audio bytes available for %s", msg.phone)
            await self._send_safe(msg.phone, AUDIO_FAILED_MSG)
            return
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=_audio_suffix(msg.audio_mimetype), delete=False
            ) as f:
                f.write(base64.b64decode(audio_b64))
                tmp_path = Path(f.name)
            text = await asyncio.to_thread(voice_to_text, tmp_path, VOICE_LANGUAGE)
        except Exception as e:
            logger.warning("Audio decode/transcription failed for %s: %s", msg.phone, e)
            text = None
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        if not text:
            await self._send_safe(msg.phone, AUDIO_FAILED_MSG)
            return
        logger.info("Transcribed voice note from %s (%d chars)", msg.phone, len(text))
        await self._process_text(msg.phone, text)

    # --- Outbound -------------------------------------------------------------

    async def _send_result(self, phone: str, result: ChatServiceResult) -> None:
        """Send the pipeline outcome: error text, chunked reply, then chart image."""
        if not result.ok:
            await self._send_safe(phone, result.error or GENERIC_ERROR_MSG)
            return
        for chunk in _split_text(result.reply or ""):
            await self._send_safe(phone, chunk)
        if result.image_base64:
            try:
                await self._client.send_image(phone, result.image_base64, caption="📊")
            except EvolutionError as e:
                logger.warning("WhatsApp image send failed for %s: %s", phone, e)

    async def _send_safe(self, phone: str, text: str) -> None:
        """Send text, swallowing delivery errors (user messages must not crash the flow)."""
        try:
            await self._client.send_text(phone, text)
        except EvolutionError as e:
            logger.warning("WhatsApp text send failed for %s: %s", phone, e)


# Process-wide singleton, resolved through dependency injection in the router.
_service: WhatsAppService | None = None


def get_whatsapp_service() -> WhatsAppService:
    """FastAPI dependency: the shared WhatsAppService instance."""
    global _service
    if _service is None:
        _service = WhatsAppService()
    return _service

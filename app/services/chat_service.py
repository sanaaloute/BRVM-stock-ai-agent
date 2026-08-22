"""Channel-agnostic chat service.

Single entry point every messaging channel (Telegram, WhatsApp, ...) uses to
talk to the AI backend. It reuses the existing Chat API pipeline *in-process*
(quota, rate limit, agent run, memory, reply sanitization) so no AI logic is
duplicated and the agent never knows which platform a message came from.

Identity: `user_id` is a channel-prefixed key (e.g. "wa:22670000000") used for
rate limiting and the daily quota; `thread_id` keys the conversation memory.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)

GENERIC_ERROR_MSG = "Une erreur est survenue. Réessayez dans un instant."


class ChatServiceResult(BaseModel):
    """Outcome of one user message through the AI pipeline."""

    reply: str | None = None
    image_base64: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ChatService:
    """Runs one user message through the shared chat pipeline."""

    async def chat(
        self, user_id: str, message: str, thread_id: str | None = None
    ) -> ChatServiceResult:
        """Send `message` as `user_id` and return the AI reply (never raises).

        `thread_id` defaults to `user_id` so conversation memory is per user.
        """
        # Lazy import: app.api.chat includes the channel routers, so importing
        # it at module load would be circular.
        from app.api.chat import ChatError, ChatRequest, run_chat

        try:
            result = await run_chat(
                ChatRequest(
                    query=message,
                    thread_id=thread_id or user_id,
                    user_id=user_id,
                )
            )
        except Exception:
            logger.exception("ChatService call failed for user %s", user_id)
            return ChatServiceResult(error=GENERIC_ERROR_MSG)
        if isinstance(result, ChatError):
            logger.info("ChatService error for user %s: %s", user_id, result.error)
            return ChatServiceResult(error=result.error)
        return ChatServiceResult(reply=result.reply, image_base64=result.image_base64)


# Process-wide singleton: channels share one service instance.
chat_service = ChatService()

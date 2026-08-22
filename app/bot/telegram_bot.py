"""Telegram bot: forwards to Chat API. Open to all users; chat and memory are keyed by Telegram user ID."""
from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

import config
from .help import get_help_message
from .voice_to_text import voice_to_text
from app.utils.user_db import (
    digest_get,
    digest_set,
    digest_unsubscribe,
    get_or_create_user,
    has_sent_help,
    mark_help_sent,
)

logger = logging.getLogger(__name__)

# Network/connection errors that are often transient (proxy, TLS, timeout)
RETRYABLE_ERRORS = (NetworkError, TimedOut, httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, OSError)

MAX_MESSAGE_LENGTH = 4096  # Telegram limit
MAX_CAPTION_LENGTH = 1024  # Telegram photo caption limit
VOICE_LANGUAGE = "fr-FR"  # BRVM / West Africa; use "en-US" for English
API_TIMEOUT = 300.0  # Agent + LLM can take several minutes (NLU, supervisor, workers)
STATUS_UPDATE_INTERVAL_SEC = 5  # Update "please wait" message every N seconds
WAIT_SPINNER = ("◐", "◓", "◑", "◒")
WAIT_MESSAGE = "Veuillez patienter — je récupère les données BRVM. Cela peut prendre jusqu'à une minute."


def _is_local_api() -> bool:
    u = config.BRVM_API_URL.lower()
    return "localhost" in u or "127.0.0.1" in u


async def _call_chat_api(query: str, thread_id: str, telegram_user_id: int) -> dict[str, Any]:
    url = f"{config.BRVM_API_URL}/chat"
    payload = {"query": query, "thread_id": thread_id, "telegram_user_id": telegram_user_id}
    headers = {"X-API-Key": config.API_SECRET_KEY} if config.API_SECRET_KEY else None
    client_kwargs = {"timeout": API_TIMEOUT}
    if _is_local_api():
        client_kwargs["trust_env"] = False
    async with httpx.AsyncClient(**client_kwargs) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            logger.error("Chat API rejected our API key (401). Check API_SECRET_KEY on both bot and API.")
            return {"error": "Le bot n'est pas autorisé à appeler le service IA (clé API rejetée). Contactez l'administrateur."}
        if resp.status_code != 200:
            try:
                data = resp.json()
                if "error" in data:
                    return data
            except Exception as e:
                logger.debug("Chat API response not JSON: %s", e)
            return {"error": "Le service IA est temporairement indisponible. Réessayez dans un instant."}
        return resp.json()


async def _call_clear_memory(thread_id: str) -> dict[str, Any]:
    """Call API to clear conversation checkpoint for this thread."""
    url = f"{config.BRVM_API_URL.rstrip('/')}/clear-memory"
    headers = {"X-API-Key": config.API_SECRET_KEY} if config.API_SECRET_KEY else None
    client_kwargs = {"timeout": 10.0}
    if _is_local_api():
        client_kwargs["trust_env"] = False
    async with httpx.AsyncClient(**client_kwargs) as client:
        resp = await client.post(url, json={"thread_id": thread_id}, headers=headers)
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {"ok": True, "message": "Mémoire de conversation effacée."}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"ok": False, "error": "Échec de l'effacement de la mémoire."}
        except Exception:
            return {"ok": False, "error": "L'API n'a pas pu effacer la mémoire. Réessayez."}


async def _status_updater(
    status_msg: Any,
    interval: float = STATUS_UPDATE_INTERVAL_SEC,
    max_updates: int = 60,
) -> None:
    """Update the status message every interval with spinner and elapsed time. Stops when cancelled."""
    start = time.monotonic()
    for i in range(1, max_updates + 1):
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
        elapsed = int(time.monotonic() - start)
        spinner = WAIT_SPINNER[(i - 1) % len(WAIT_SPINNER)]
        text = f"{spinner} {WAIT_MESSAGE}\n\n⏱ {elapsed}s"
        try:
            await status_msg.edit_text(text)
        except Exception:
            return


async def _get_query_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    msg = update.message
    if not msg:
        return None
    # Text
    if msg.text:
        return msg.text.strip() or None
    voice = getattr(msg, "voice", None)
    audio = getattr(msg, "audio", None)
    file_id = None
    suffix = ".ogg"
    if voice:
        file_id = voice.file_id
    elif audio:
        file_id = audio.file_id
        suffix = ".m4a"  # Telegram audio often m4a
    if not file_id:
        return None
    try:
        tg_file = await context.bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            await tg_file.download_to_drive(f.name)
            path = Path(f.name)
        try:
            text = await asyncio.to_thread(voice_to_text, path, VOICE_LANGUAGE)
            return (text or "").strip() or None
        finally:
            path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Voice/audio download or transcription failed: %s", e)
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    # Chat and memory are keyed by Telegram user ID so each user has their own conversation
    thread_id = str(user_id)

    query = await _get_query_from_message(update, context)
    if not query:
        await update.message.reply_text(
            "Envoyez un message texte ou un message vocal avec votre question (ex. cours de NTLC, comparer deux actions). "
            "Si vous avez envoyé un vocal et que ce message s'affiche, l'audio n'a pas pu être transcrit."
        )
        return

    query_lower = query.strip().lower()
    if query_lower in ("help", "/help", "aide", "?", "aide moi", "comment utiliser", "how to use"):
        await update.message.reply_text(get_help_message())
        return

    # Sync SQLite/Postgres calls: keep them off the PTB event loop.
    await asyncio.to_thread(get_or_create_user, user_id)
    if not await asyncio.to_thread(has_sent_help, user_id):
        await update.message.reply_text(get_help_message())
        await asyncio.to_thread(mark_help_sent, user_id)

    status = await update.message.reply_text(f"{WAIT_SPINNER[0]} {WAIT_MESSAGE}\n\n⏱ 0s")
    updater_task: asyncio.Task | None = None
    try:
        updater_task = asyncio.create_task(_status_updater(status))
        result = await _call_chat_api(query, thread_id, user_id)
    except httpx.ReadTimeout:
        if updater_task and not updater_task.done():
            updater_task.cancel()
            try:
                await updater_task
            except asyncio.CancelledError:
                pass
        logger.warning("API call timed out for user %s", user_id)
        await status.edit_text("L'assistant a mis trop de temps à répondre. Réessayez.")
        return
    except Exception as e:
        if updater_task and not updater_task.done():
            updater_task.cancel()
            try:
                await updater_task
            except asyncio.CancelledError:
                pass
        logger.exception("API call failed for user %s: %s", user_id, e)
        await status.edit_text("Impossible de joindre le service IA. Réessayez dans un instant.")
        return
    finally:
        if updater_task and not updater_task.done():
            updater_task.cancel()
            try:
                await updater_task
            except asyncio.CancelledError:
                pass

    if "error" in result:
        await status.edit_text(result["error"])
        return

    reply = result.get("reply", "")
    if len(reply) > MAX_MESSAGE_LENGTH:
        reply = reply[: MAX_MESSAGE_LENGTH - 20] + "\n\n… (tronqué)"

    image_base64 = result.get("image_base64")
    if not reply and not image_base64:
        # Telegram rejects an empty edit_text (BadRequest): use a fallback.
        reply = "Je n'ai pas pu générer de réponse. Réessayez dans un instant."
    if image_base64:
        caption = reply[:MAX_CAPTION_LENGTH] if len(reply) <= MAX_CAPTION_LENGTH else reply[: MAX_CAPTION_LENGTH - 20] + "\n… (tronqué)"
        await status.delete()
        try:
            img_bytes = base64.b64decode(image_base64)
            await update.message.reply_photo(photo=img_bytes, caption=caption or None)
        except Exception as e:
            logger.warning("Failed to send image: %s", e)
            await update.message.reply_text(reply)
    else:
        await status.edit_text(reply)


TELEGRAM_CONNECT_TIMEOUT = 30.0
TELEGRAM_READ_TIMEOUT = 30.0
TELEGRAM_WRITE_TIMEOUT = 30.0


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(get_help_message())


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.effective_user:
        await update.message.reply_text(get_help_message())


async def cmd_clearmemory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation memory for this user (keyed by Telegram user ID)."""
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    thread_id = str(user_id)
    try:
        result = await _call_clear_memory(thread_id)
        if result.get("ok"):
            await update.message.reply_text("Mémoire de conversation effacée. Vous pouvez reprendre une nouvelle conversation.")
        else:
            await update.message.reply_text(result.get("error", "Échec de l'effacement de la mémoire. Réessayez."))
    except Exception as e:
        logger.warning("Clear memory failed for user %s: %s", user_id, e)
        await update.message.reply_text("Impossible d'effacer la mémoire. Vérifiez que l'API tourne et réessayez.")


DIGEST_USAGE = (
    "Résumé automatique du marché BRVM (scores et signaux du jour).\n"
    "• /digest jour — résumé chaque jour de bourse, 18h GMT\n"
    "• /digest semaine — résumé hebdomadaire, le vendredi\n"
    "• /digest off — désactiver le résumé"
)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manage the scheduled market digest subscription (direct command, no LLM)."""
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    arg = context.args[0].strip().lower() if context.args else ""
    try:
        if arg in ("jour", "daily"):
            result = await asyncio.to_thread(digest_set, user_id, "daily")
        elif arg in ("semaine", "weekly"):
            result = await asyncio.to_thread(digest_set, user_id, "weekly")
        elif arg in ("off", "stop"):
            result = await asyncio.to_thread(digest_unsubscribe, user_id)
        else:
            sub = await asyncio.to_thread(digest_get, user_id)
            if sub and sub.get("enabled"):
                freq_fr = "quotidien" if sub.get("frequency") == "daily" else "hebdomadaire"
                await update.message.reply_text(f"Votre abonnement digest actuel : {freq_fr}.\n\n{DIGEST_USAGE}")
            else:
                await update.message.reply_text(f"Aucun abonnement digest actif.\n\n{DIGEST_USAGE}")
            return
        await update.message.reply_text(result.get("message") or result.get("error") or "Erreur inattendue, réessayez.")
    except Exception as e:
        logger.warning("Digest command failed for user %s: %s", user_id, e)
        await update.message.reply_text("Impossible de mettre à jour l'abonnement digest. Réessayez dans un instant.")


async def _global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and, for user-facing updates, reply on network/transient errors. Prevents unhandled exception logging."""
    err = context.error
    if err is None:
        return
    is_retryable = isinstance(err, RETRYABLE_ERRORS) or (
        isinstance(getattr(err, "__cause__", None), RETRYABLE_ERRORS)
    )
    if is_retryable:
        logger.warning(
            "Telegram network/connection error (transient): %s: %s",
            type(err).__name__,
            err,
        )
    else:
        logger.exception("Telegram bot error: %s", err)

    # If we have a user chat (update from a message), optionally reply on retryable errors
    if isinstance(update, Update) and update.effective_chat and update.effective_message and is_retryable:
        try:
            await update.effective_message.reply_text(
                "Problème de connexion. Veuillez réessayer dans un instant."
            )
        except Exception:
            pass


# How often to poll Telegram for new updates (getUpdates). 1 second for responsive replies.
POLL_INTERVAL_SEC = 1


def build_application() -> Application:
    request = HTTPXRequest(
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
    )
    builder = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .request(request)
    )
    app = builder.build()
    app.add_error_handler(_global_error_handler)
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clearmemory", cmd_clearmemory))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.VOICE | filters.AUDIO,
            handle_message,
        )
    )
    return app


def run_polling_with_retry(
    app: Application,
    *,
    allowed_updates: list[str] | None = None,
    bootstrap_retries: int = 5,
    poll_interval: float = POLL_INTERVAL_SEC,
    poll_retry_max: int = 0,
    poll_retry_delay: float = 30.0,
    poll_retry_backoff: float = 1.5,
) -> None:
    """
    Run polling with optional retry on network errors.
    poll_interval: seconds between getUpdates calls (default 1 second).
    poll_retry_max: 0 = infinite retries; N = up to N restarts after the first run.
    """
    allowed_updates = allowed_updates or ["message"]
    attempt = 0
    while True:
        try:
            app.run_polling(
                allowed_updates=allowed_updates,
                bootstrap_retries=bootstrap_retries,
                poll_interval=poll_interval,
                # Don't replay the stale update backlog after a downtime.
                drop_pending_updates=True,
            )
            break
        except RETRYABLE_ERRORS as e:
            attempt += 1
            if poll_retry_max and attempt > poll_retry_max:
                logger.exception("Polling failed after %s attempts (network error). Giving up.", attempt)
                raise
            # Cap the backoff so a long outage can't push retries to hours.
            delay = min(poll_retry_delay * (poll_retry_backoff ** (attempt - 1)), 300.0)
            logger.warning(
                "Polling stopped due to network error (%s). Restarting in %.1fs (attempt %s).",
                e,
                delay,
                attempt,
            )
            time.sleep(delay)
        except Exception:
            raise

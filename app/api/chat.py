"""FastAPI chat endpoint. Bot calls this; API runs agents and returns sanitized response."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

import config
from app.agents import run_agent
from app.agents.graph import CHAT_MEMORY_DB
from app.bot.redact import redact_for_telegram
from app.models.llm import get_default_model
from app.utils.user_db import decrement_daily_usage, increment_daily_usage

logger = logging.getLogger(__name__)

router = APIRouter()

# Conversation memory: per-user threads are kept until /clear-memory is called
# or they have been inactive for config.MEMORY_TTL_HOURS (0 = never auto-wipe).

# Message appended to every bot reply so users know the content is AI-generated
SOURCE_FOOTER = "\n\n⚠️ Attention : ce texte est généré par IA. Vérifiez les informations avant toute décision ou action."


if not config.API_SECRET_KEY:
    logger.warning(
        "API_SECRET_KEY is not set: /chat accepts UNAUTHENTICATED requests. "
        "Set API_SECRET_KEY in .env before exposing this API."
    )


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require the shared secret when API_SECRET_KEY is configured (constant-time compare)."""
    secret = config.API_SECRET_KEY
    if not secret:
        return  # dev mode: no key configured
    if not x_api_key or not secrets.compare_digest(x_api_key.strip(), secret):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# --- Coarse per-user rate limiting (in-memory, per-process) ---
_RATE_WINDOW_SEC = 60.0
_rate_hits: dict[str, list[float]] = {}
_rate_lock = threading.Lock()
_rate_last_cleanup = 0.0


def _rate_limited(key: str) -> bool:
    """True if `key` exceeded RATE_LIMIT_PER_MINUTE within the last 60 seconds."""
    limit = config.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False
    global _rate_last_cleanup
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(key, []) if now - t < _RATE_WINDOW_SEC]
        if len(hits) >= limit:
            _rate_hits[key] = hits
            return True
        hits.append(now)
        _rate_hits[key] = hits
        if now - _rate_last_cleanup > 600:  # keep dict bounded
            _rate_last_cleanup = now
            for k in [k for k, v in _rate_hits.items() if not v or now - v[-1] >= _RATE_WINDOW_SEC]:
                _rate_hits.pop(k, None)
    return False


# One persistent checkpointer for the process: created once (not per request).
# PostgreSQL when DATABASE_URL is set, else a local SQLite file (WAL mode,
# check_same_thread=False so uvicorn's worker threads can share it).
_checkpointer = None
_checkpointer_lock = threading.Lock()


def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        with _checkpointer_lock:
            if _checkpointer is None:
                if config.DATABASE_URL:
                    import psycopg
                    from langgraph.checkpoint.postgres import PostgresSaver

                    # psycopg3 connections are thread-safe; checkpoint ops just
                    # serialize behind the connection lock (fine at our scale).
                    # autocommit=True is required: setup() migrations include
                    # CREATE INDEX CONCURRENTLY, which can't run inside the
                    # implicit transaction psycopg opens by default.
                    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
                    saver = PostgresSaver(conn)
                    saver.setup()  # creates checkpoint tables if missing
                    _checkpointer = saver
                else:
                    from langgraph.checkpoint.sqlite import SqliteSaver

                    CHAT_MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(
                        str(CHAT_MEMORY_DB), check_same_thread=False, timeout=30.0
                    )
                    try:
                        conn.execute("PRAGMA journal_mode=WAL")
                        conn.execute("PRAGMA busy_timeout=30000")
                    except sqlite3.Error as e:
                        logger.warning("SQLite pragmas skipped: %s", e)
                    _checkpointer = SqliteSaver(conn)
    return _checkpointer


# Cap concurrent agent runs so a burst of users can't melt the LLM backend.
_agent_semaphore = threading.Semaphore(max(1, config.MAX_CONCURRENT_AGENTS))


def _extract_reply(messages: list) -> str:
    for m in reversed(messages):
        if not getattr(m, "content", None):
            continue
        content = str(m.content).strip()
        if "[NLU]" in content:
            continue
        kind = getattr(m, "type", None) or type(m).__name__
        if kind == "ai" or "AI" in str(kind):
            return content
    for m in reversed(messages):
        if getattr(m, "content", None) and "Human" not in type(m).__name__:
            content = str(m.content).strip()
            if "[NLU]" not in content:
                return content
    return "Aucune réponse de l'assistant."


def _user_friendly_error(exc: Exception) -> str:
    err_str = str(exc).lower()
    if "recursion" in err_str:
        return "La question est trop complexe. Essayez une question plus simple."
    if "404" in err_str:
        return "Modèle introuvable. Téléchargez-le d'abord : ollama pull <model>"
    if "503" in err_str:
        return "Le service IA est occupé ou charge encore le modèle. Attendez quelques secondes et réessayez."
    if "ssl" in err_str or "eof" in err_str or "connect" in err_str:
        return "Le service IA est temporairement indisponible. Réessayez dans un instant."
    if "timeout" in err_str:
        return "La requête a pris trop de temps. Réessayez."
    return "Une erreur s'est produite. Veuillez réessayer."


class ChatRequest(BaseModel):
    query: str
    thread_id: str = "default"
    telegram_user_id: int | None = None
    # Channel-agnostic identity (e.g. "wa:22507000000"). When set, it is the
    # key used for rate limiting and the daily quota. Telegram callers keep
    # sending telegram_user_id (their key stays the raw id for back-compat).
    user_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    image_base64: str | None = None
    clarification: bool = False


class ChatError(BaseModel):
    error: str


class ClearMemoryRequest(BaseModel):
    thread_id: str = "default"


def clear_all_chat_memory() -> None:
    """Erase all conversation checkpoints. Safe to call if DB/tables do not exist."""
    if config.DATABASE_URL:
        try:
            import psycopg

            with psycopg.connect(config.DATABASE_URL) as conn:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints", "thread_activity"):
                    try:
                        conn.execute(f"DELETE FROM {table}")
                    except psycopg.Error:
                        pass  # table may not exist yet
                conn.commit()
            logger.info("Chat memory wiped (all threads, PostgreSQL).")
        except Exception as e:
            logger.warning("Chat memory wipe failed: %s", e)
        return
    if not CHAT_MEMORY_DB.exists():
        return
    try:
        with sqlite3.connect(str(CHAT_MEMORY_DB)) as conn:
            conn.execute("DELETE FROM writes")
            conn.execute("DELETE FROM checkpoints")
            try:
                conn.execute("DELETE FROM thread_activity")
            except sqlite3.OperationalError:
                pass  # table may not exist yet
            conn.commit()
        logger.info("Chat memory wiped (all threads).")
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return
        logger.warning("Chat memory wipe failed (tables may not exist yet): %s", e)
    except Exception as e:
        logger.warning("Chat memory wipe failed: %s", e)


# --- Per-thread activity tracking + TTL-based cleanup -----------------------
# A tiny table in the checkpoint DB records the last activity per thread_id.
# cleanup_stale_threads() wipes threads inactive for > MEMORY_TTL_HOURS.

def _activity_connect():
    """Raw connection to the checkpoint DB, in autocommit mode (SQLite or Postgres)."""
    if config.DATABASE_URL:
        import psycopg

        return psycopg.connect(config.DATABASE_URL, autocommit=True)
    CHAT_MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(CHAT_MEMORY_DB), timeout=30.0, isolation_level=None)


def _placeholder() -> str:
    """SQL parameter placeholder for the active backend (psycopg vs sqlite3)."""
    return "%s" if config.DATABASE_URL else "?"


def _ensure_activity_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thread_activity "
        "(thread_id TEXT PRIMARY KEY, last_seen DOUBLE PRECISION)"
    )


def touch_thread_activity(thread_id: str | None) -> None:
    """Record activity for a conversation thread (best-effort, never raises)."""
    if not thread_id:
        return
    try:
        with contextlib.closing(_activity_connect()) as conn:
            _ensure_activity_table(conn)
            ph = _placeholder()
            conn.execute(
                f"INSERT INTO thread_activity (thread_id, last_seen) VALUES ({ph}, {ph}) "
                "ON CONFLICT(thread_id) DO UPDATE SET last_seen = excluded.last_seen",
                (thread_id, time.time()),
            )
    except Exception as e:
        logger.warning("touch_thread_activity failed: %s", e)


def cleanup_stale_threads() -> None:
    """Delete conversation threads inactive for more than MEMORY_TTL_HOURS.

    No-op when MEMORY_TTL_HOURS <= 0 (memory kept until manual /clear-memory).
    """
    ttl = config.MEMORY_TTL_HOURS
    if ttl <= 0:
        return
    cutoff = time.time() - ttl * 3600
    try:
        with contextlib.closing(_activity_connect()) as conn:
            _ensure_activity_table(conn)
            ph = _placeholder()
            rows = conn.execute(
                f"SELECT thread_id FROM thread_activity WHERE last_seen < {ph}", (cutoff,)
            ).fetchall()
            stale = [r[0] for r in rows]
            for tid in stale:
                try:
                    _get_checkpointer().delete_thread(tid)
                except Exception as e:
                    logger.warning("delete_thread(%s) failed: %s", tid, e)
            if stale:
                conn.execute(
                    f"DELETE FROM thread_activity WHERE last_seen < {ph}", (cutoff,)
                )
                logger.info(
                    "Cleaned up %d stale conversation(s) (TTL %.1fh).", len(stale), ttl
                )
    except Exception as e:
        logger.warning("cleanup_stale_threads failed: %s", e)


def _quota_active(user_key: str) -> bool:
    return config.DAILY_FREE_QUOTA > 0 and user_key not in config.QUOTA_EXEMPT_IDS


@router.post("/chat", dependencies=[Depends(verify_api_key)])
def chat(req: ChatRequest) -> ChatResponse | ChatError:
    if req.user_id:
        user_key = req.user_id
    elif req.telegram_user_id is not None:
        user_key = str(req.telegram_user_id)
    else:
        user_key = f"thread:{req.thread_id}"
    if _rate_limited(user_key):
        logger.info("Rate limited: %s", user_key)
        return ChatError(error="Trop de requêtes. Patientez un instant et réessayez.")
    acquired = _agent_semaphore.acquire(timeout=config.AGENT_QUEUE_TIMEOUT)
    if not acquired:
        logger.warning("Agent pool saturated; rejecting request for thread %s", req.thread_id)
        return ChatError(
            error="L'assistant est très sollicité en ce moment. Réessayez dans un instant."
        )
    counted = False
    try:
        touch_thread_activity(req.thread_id)
        # Daily free quota: count the request once it has a worker slot, so
        # rate-limited/"busy" rejections never consume quota. Atomic
        # increment-then-check keeps concurrent requests from overshooting.
        if _quota_active(user_key):
            used = increment_daily_usage(user_key)
            if used > config.DAILY_FREE_QUOTA:
                decrement_daily_usage(user_key)
                logger.info("Daily quota exhausted: %s (limit %d)", user_key, config.DAILY_FREE_QUOTA)
                return ChatError(
                    error=(
                        f"⏳ Vous avez atteint la limite de {config.DAILY_FREE_QUOTA} "
                        "requêtes gratuites par jour. Revenez demain pour continuer !"
                    )
                )
            counted = True
        result = run_agent(
            query=req.query,
            model=get_default_model(),
            thread_id=req.thread_id,
            telegram_user_id=req.telegram_user_id,
            checkpointer=_get_checkpointer(),
        )

        clarification = result.get("clarification")
        if clarification:
            reply = redact_for_telegram(clarification)
            return ChatResponse(reply=reply + SOURCE_FOOTER, clarification=True)

        messages = result.get("messages") or []
        raw_reply = _extract_reply(messages)
        reply = redact_for_telegram(raw_reply)
        reply = (reply + SOURCE_FOOTER) if reply else SOURCE_FOOTER.strip()

        image_base64 = None
        image_path = result.get("image_path")
        if image_path and Path(image_path).exists():
            try:
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("ascii")
            finally:
                Path(image_path).unlink(missing_ok=True)

        return ChatResponse(reply=reply, image_base64=image_base64)
    except Exception as e:
        if counted:
            decrement_daily_usage(user_key)  # refund: failed requests are free
        logger.exception("Chat API error: %s", e)
        return ChatError(error=_user_friendly_error(e))
    finally:
        _agent_semaphore.release()


@router.post("/clear-memory", dependencies=[Depends(verify_api_key)])
def clear_memory(req: ClearMemoryRequest) -> dict:
    """Clear conversation checkpoint for the given thread_id. Bot can call this for /clearmemory."""
    try:
        # Works on both backends (SqliteSaver / PostgresSaver share this API).
        _get_checkpointer().delete_thread(req.thread_id)
        return {"ok": True, "message": "Mémoire de conversation effacée."}
    except Exception as e:
        logger.exception("Clear memory error: %s", e)
        return {"ok": False, "error": _user_friendly_error(e)}


@router.get("/health")
def health():
    return {"status": "ok"}


async def _memory_cleanup_loop() -> None:
    """Background task: periodically wipe threads inactive for > MEMORY_TTL_HOURS."""
    while True:
        await asyncio.sleep(max(60, config.MEMORY_CLEANUP_INTERVAL_SEC))
        try:
            await asyncio.to_thread(cleanup_stale_threads)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Memory cleanup loop error: %s", e)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = (
        asyncio.create_task(_memory_cleanup_loop())
        if config.MEMORY_TTL_HOURS > 0
        else None
    )
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="BRVM Chat API", version="1.0", lifespan=_lifespan)
app.include_router(router)

# WhatsApp Business Cloud API webhook (no-op unless WHATSAPP_* env vars are set).
from app.api.whatsapp import router as whatsapp_router  # noqa: E402

app.include_router(whatsapp_router)

# WhatsApp via Evolution API webhook (no-op unless EVOLUTION_* env vars are set).
from app.channels.whatsapp import router as whatsapp_evolution_router  # noqa: E402

app.include_router(whatsapp_evolution_router)

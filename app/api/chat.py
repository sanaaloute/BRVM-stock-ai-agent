"""FastAPI chat endpoint. Bot calls this; API runs agents and returns sanitized response."""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select

import config
from app.agents import run_agent
from app.agents.graph import CHAT_MEMORY_DB
from app.bot.redact import redact_for_telegram
from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models as db_models
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

# Dedicated executor for agent runs: keeps /chat off Starlette's shared anyio
# threadpool, so queued requests (each holding a pool thread while it waits on
# the agent semaphore) can't stall unrelated endpoints like /health.
_chat_executor = ThreadPoolExecutor(
    max_workers=max(2, config.MAX_CONCURRENT_AGENTS + 2),
    thread_name_prefix="chat-agent",
)

# One agent run at a time per conversation thread: concurrent runs on the same
# thread_id would interleave checkpoint writes (lost history, duplicated effects).
_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()
_THREAD_LOCKS_MAX = 10_000


def _thread_lock(thread_id: str) -> threading.Lock:
    """Per-thread lock registry, bounded (locks are cheap to recreate)."""
    with _thread_locks_guard:
        if len(_thread_locks) > _THREAD_LOCKS_MAX:
            _thread_locks.clear()
        lock = _thread_locks.get(thread_id)
        if lock is None:
            lock = _thread_locks[thread_id] = threading.Lock()
        return lock


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
    images_base64: list[str] | None = None
    """All charts of this run (image_base64 mirrors the first, for older clients)."""
    image_caption: str | None = None
    """Short (≤ 50 chars) chart caption; the full reply is sent as text."""
    clarification: bool = False


class ChatError(BaseModel):
    error: str


class ClearMemoryRequest(BaseModel):
    thread_id: str = "default"


def clear_all_chat_memory() -> None:
    """Erase all conversation checkpoints + thread activity. Safe if tables do not exist."""
    try:
        if config.DATABASE_URL:
            import psycopg

            with psycopg.connect(config.DATABASE_URL) as conn:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    try:
                        conn.execute(f"DELETE FROM {table}")
                    except psycopg.Error:
                        pass  # table may not exist yet
                conn.commit()
            logger.info("Chat memory wiped (all threads, PostgreSQL).")
        elif CHAT_MEMORY_DB.exists():
            with sqlite3.connect(str(CHAT_MEMORY_DB)) as conn:
                conn.execute("DELETE FROM writes")
                conn.execute("DELETE FROM checkpoints")
                conn.commit()
            logger.info("Chat memory wiped (all threads).")
        _clear_thread_activity()
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            logger.warning("Chat memory wipe failed (tables may not exist yet): %s", e)
    except Exception as e:
        logger.warning("Chat memory wipe failed: %s", e)


def _clear_thread_activity() -> None:
    """Wipe the thread_activity table (shared user DB) — best effort."""
    try:
        db_migrate.ensure_schema()
        with db_engine.session_scope() as s:
            s.execute(delete(db_models.ThreadActivity))
    except Exception as e:
        logger.warning("Thread activity wipe failed: %s", e)


# --- Per-thread activity tracking + TTL-based cleanup -----------------------
# thread_activity lives in the shared user DB (app/db): last activity per
# thread_id. cleanup_stale_threads() wipes threads inactive > MEMORY_TTL_HOURS.

def touch_thread_activity(thread_id: str | None) -> None:
    """Record activity for a conversation thread (best-effort, never raises)."""
    if not thread_id:
        return
    try:
        db_migrate.ensure_schema()
        t = db_models.ThreadActivity.__table__
        stmt = db_engine.dialect_insert(t).values(
            thread_id=thread_id, last_seen=time.time()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["thread_id"],
            set_={"last_seen": stmt.excluded.last_seen},
        )
        with db_engine.session_scope() as s:
            s.execute(stmt)
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
        db_migrate.ensure_schema()
        with db_engine.session_scope() as s:
            stale = [
                r[0]
                for r in s.execute(
                    select(db_models.ThreadActivity.thread_id).where(
                        db_models.ThreadActivity.last_seen < cutoff
                    )
                )
            ]
            deleted: list[str] = []
            for tid in stale:
                try:
                    _get_checkpointer().delete_thread(tid)
                    deleted.append(tid)
                except Exception as e:
                    logger.warning("delete_thread(%s) failed: %s", tid, e)
            if deleted:
                # Only forget threads whose checkpoints were actually deleted;
                # failures stay in thread_activity so the next pass retries them.
                s.execute(
                    delete(db_models.ThreadActivity).where(
                        db_models.ThreadActivity.thread_id.in_(deleted)
                    )
                )
                logger.info(
                    "Cleaned up %d stale conversation(s) (TTL %.1fh).", len(deleted), ttl
                )
    except Exception as e:
        logger.warning("cleanup_stale_threads failed: %s", e)


def _quota_active(user_key: str) -> bool:
    return config.DAILY_FREE_QUOTA > 0 and user_key not in config.QUOTA_EXEMPT_IDS


def _chat_impl(req: ChatRequest) -> ChatResponse | ChatError:
    """Sync chat pipeline: rate limit, quota, agent run, reply sanitization.

    Runs on _chat_executor (via run_chat) — never call from the event loop.
    """
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
        # One run at a time per conversation thread, inside the semaphore-
        # protected section (concurrent runs would corrupt the checkpoint).
        with _thread_lock(req.thread_id):
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

        raw_reply = result.get("_fresh_reply")
        if raw_reply is None:
            # This run produced no fresh AI reply (e.g. all workers failed).
            # Never fall back to older checkpoint messages: that could serve a
            # stale previous-turn answer (or raw ToolMessage JSON) as the reply.
            logger.warning("No fresh reply produced for thread %s", req.thread_id)
            return ChatError(error="Une erreur s'est produite. Veuillez réessayer.")
        reply = redact_for_telegram(raw_reply)
        reply = (reply + SOURCE_FOOTER) if reply else SOURCE_FOOTER.strip()

        image_paths = result.get("image_paths") or []
        if not image_paths and result.get("image_path"):
            image_paths = [result["image_path"]]
        images_base64: list[str] = []
        for image_path in image_paths:
            if not image_path or not Path(image_path).exists():
                continue
            try:
                with open(image_path, "rb") as f:
                    images_base64.append(base64.b64encode(f.read()).decode("ascii"))
            finally:
                Path(image_path).unlink(missing_ok=True)

        return ChatResponse(
            reply=reply,
            image_base64=images_base64[0] if images_base64 else None,
            images_base64=images_base64 or None,
            image_caption=result.get("image_caption") if images_base64 else None,
        )
    except Exception as e:
        if counted:
            try:
                decrement_daily_usage(user_key)  # refund: failed requests are free
            except Exception:
                logger.warning("Quota refund failed for %s", user_key, exc_info=True)
        logger.exception("Chat API error: %s", e)
        return ChatError(error=_user_friendly_error(e))
    finally:
        _agent_semaphore.release()


async def run_chat(req: ChatRequest) -> ChatResponse | ChatError:
    """Run one chat request on the dedicated executor (awaitable from channels)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_chat_executor, _chat_impl, req)


@router.post("/chat", dependencies=[Depends(verify_api_key)])
async def chat(req: ChatRequest) -> ChatResponse | ChatError:
    return await run_chat(req)


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
    tasks = []
    if config.MEMORY_TTL_HOURS > 0:
        tasks.append(asyncio.create_task(_memory_cleanup_loop()))
    # Daily post-close market snapshot (weekdays ~16:30 GMT).
    from app.services.market_data import scheduled_refresh_loop

    tasks.append(asyncio.create_task(scheduled_refresh_loop()))
    yield
    for task in tasks:
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

# Mobile app (Flutter) API: JWT auth + market/portfolio/chat endpoints.
from app.api.mobile_auth import router as mobile_auth_router  # noqa: E402
from app.api.mobile import router as mobile_router  # noqa: E402
from app.api.privacy import router as privacy_router  # noqa: E402

app.include_router(mobile_auth_router)
app.include_router(mobile_router)
app.include_router(privacy_router)

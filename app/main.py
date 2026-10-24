"""Single entry point: FastAPI app. Run with: python main.py or uvicorn app.main:app."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import config
from app.api.chat import cleanup_stale_threads, router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background jobs: stale-thread memory cleanup, market snapshot refresh,
    digest, price-target alerts and the daily timeseries update."""

    async def memory_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(max(60, config.MEMORY_CLEANUP_INTERVAL_SEC))
            try:
                await asyncio.to_thread(cleanup_stale_threads)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Memory cleanup loop error: %s", e)

    tasks = []
    if config.MEMORY_TTL_HOURS > 0:
        tasks.append(asyncio.create_task(memory_cleanup_loop()))

    from app.services import scheduler
    from app.services.market_data import scheduled_refresh_loop

    tasks.append(asyncio.create_task(scheduled_refresh_loop()))
    tasks.append(asyncio.create_task(scheduler.target_alerts_loop()))
    if config.DIGEST_ENABLED:
        tasks.append(asyncio.create_task(scheduler.digest_loop()))
    tasks.append(asyncio.create_task(scheduler.timeseries_loop()))
    yield
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="BRVM Chat API", version="1.0", lifespan=lifespan)
app.include_router(chat_router)

from app.api.mobile_auth import router as mobile_auth_router  # noqa: E402
from app.api.mobile import router as mobile_router  # noqa: E402
from app.api.privacy import router as privacy_router  # noqa: E402

app.include_router(mobile_auth_router)
app.include_router(mobile_router)
app.include_router(privacy_router)

"""Single entry point: FastAPI + Telegram bot. Run with: python main.py or uvicorn app.main:app."""

from __future__ import annotations



import asyncio

import logging

import multiprocessing

import time

from contextlib import asynccontextmanager



from fastapi import FastAPI



import config

from app.api.chat import cleanup_stale_threads, router as chat_router

from app.channels.whatsapp import router as whatsapp_evolution_router

from app.utils.log_redact import install_log_redaction



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S",

)

install_log_redaction()  # keep the bot token out of httpx request logs

logger = logging.getLogger(__name__)



DAILY_INTERVAL_SEC = 24 * 3600

TARGET_CHECK_INTERVAL_SEC = 300





def _daily_timeseries_job() -> None:

    """Run once per day: update CSVs for all configured symbols."""

    while True:

        try:

            from app.utils._data import run_daily_timeseries_update

            logger.info("Daily timeseries update: %s", config.TIMESERIES_SYMBOLS)

            for r in run_daily_timeseries_update(config.TIMESERIES_SYMBOLS):

                logger.info("Timeseries %s: %s", r.get("symbol"), r.get("action", r))

        except Exception as e:

            logger.exception("Daily timeseries update failed: %s", e)

        time.sleep(DAILY_INTERVAL_SEC)





async def _check_target_alerts(context) -> None:

    """Job: check price targets and send Telegram notifications to users whose target was reached."""

    try:

        from app.utils.user_db import check_targets_and_notify

        for telegram_id, text in check_targets_and_notify():

            try:

                await context.bot.send_message(chat_id=telegram_id, text=text)

                logger.info("Target alert sent to user %s", telegram_id)

            except Exception as e:

                logger.warning("Failed to send target alert to %s: %s", telegram_id, e)

    except Exception as e:

        logger.exception("Target check job failed: %s", e)





def _run_telegram_bot() -> None:

    """Run Telegram bot (blocking). Must run in main thread for signal handlers; use Process."""

    time.sleep(2)  # Let uvicorn finish starting

    if not config.TELEGRAM_BOT_TOKEN:

        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot disabled.")

        return



    import threading

    thread = threading.Thread(target=_daily_timeseries_job, daemon=True)

    thread.start()



    from app.bot import build_application

    from app.bot.telegram_bot import run_polling_with_retry

    app = build_application()

    if app.job_queue is not None:

        app.job_queue.run_repeating(_check_target_alerts, interval=TARGET_CHECK_INTERVAL_SEC, first=60)

        logger.info(

            "Telegram bot starting (open to all users). API: %s. Daily timeseries + target alerts (every %s s).",

            config.BRVM_API_URL,

            TARGET_CHECK_INTERVAL_SEC,

        )

    else:

        logger.info(

            "Telegram bot starting (open to all users). API: %s. Target alerts disabled (install python-telegram-bot[job-queue]).",

            config.BRVM_API_URL,

        )

    run_polling_with_retry(

        app,

        allowed_updates=["message"],

        bootstrap_retries=5,

        poll_retry_max=0,

        poll_retry_delay=30.0,

        poll_retry_backoff=1.5,

    )





@asynccontextmanager

async def lifespan(app: FastAPI):

    """Start Telegram bot in background process (needs main thread for signal handlers). Start stale-thread memory cleanup."""

    async def memory_cleanup_loop() -> None:

        while True:

            await asyncio.sleep(max(60, config.MEMORY_CLEANUP_INTERVAL_SEC))

            try:

                await asyncio.to_thread(cleanup_stale_threads)

            except asyncio.CancelledError:

                break

            except Exception as e:

                logger.warning("Memory cleanup loop error: %s", e)



    cleanup_task = (

        asyncio.create_task(memory_cleanup_loop())

        if config.MEMORY_TTL_HOURS > 0

        else None

    )

    if config.TELEGRAM_BOT_TOKEN:

        p = multiprocessing.Process(target=_run_telegram_bot, daemon=True)

        p.start()

        logger.info("Telegram bot process started.")

    else:

        logger.info("API-only mode (no Telegram bot). Set TELEGRAM_BOT_TOKEN for full mode.")

    yield

    if cleanup_task is not None:

        cleanup_task.cancel()

        try:

            await cleanup_task

        except asyncio.CancelledError:

            pass





app = FastAPI(title="BRVM Chat API", version="1.0", lifespan=lifespan)

app.include_router(chat_router)

app.include_router(whatsapp_evolution_router)


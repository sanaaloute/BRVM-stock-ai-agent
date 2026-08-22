"""Run Telegram bot only (requires API). For API + bot together, use: python main.py"""

import asyncio

import datetime

import logging

import sys

import threading

import time



import httpx



import config

from app.bot import build_application

from app.bot.telegram_bot import run_polling_with_retry

from app.utils._data import run_daily_timeseries_update

from app.utils.log_redact import install_log_redaction



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S",

)

install_log_redaction()  # keep the bot token out of httpx request logs

logger = logging.getLogger(__name__)



DAILY_INTERVAL_SEC = 24 * 3600

TARGET_CHECK_INTERVAL_SEC = 300  # 5 minutes

DIGEST_ENABLED = getattr(config, "DIGEST_ENABLED", True)

DIGEST_HOUR_GMT = int(getattr(config, "DIGEST_HOUR_GMT", 18))  # weekdays, post-close (GMT == Abidjan)

# The API container can take ~15-30s to boot (font cache, model warmup). Wait

# for it instead of crashing and relying on the restart loop.

API_STARTUP_RETRIES = 20

API_STARTUP_RETRY_DELAY = 3  # seconds





def _daily_timeseries_job() -> None:

    """Run once per day: update CSVs for all configured symbols."""

    while True:

        try:

            logger.info("Daily timeseries update: %s", config.TIMESERIES_SYMBOLS)

            results = run_daily_timeseries_update(config.TIMESERIES_SYMBOLS)

            for r in results:

                logger.info("Timeseries %s: %s", r.get("symbol"), r.get("action", r))

        except Exception as e:

            logger.exception("Daily timeseries update failed: %s", e)

        time.sleep(DAILY_INTERVAL_SEC)





async def _check_target_alerts(context) -> None:

    """Job: check price targets and send Telegram notifications to users whose target was reached."""

    try:

        from app.utils.user_db import check_targets_and_notify

        # Blocking (sleeps + HTTP with retries): keep it off the event loop.

        results = await asyncio.to_thread(check_targets_and_notify)

        for telegram_id, text in results:

            try:

                await context.bot.send_message(chat_id=telegram_id, text=text)

                logger.info("Target alert sent to user %s", telegram_id)

            except Exception as e:

                logger.warning("Failed to send target alert to %s: %s", telegram_id, e)

    except Exception as e:

        logger.exception("Target check job failed: %s", e)





async def _digest_job(context) -> None:

    """Job: score the market, persist score snapshots and push the digest to /digest subscribers."""

    try:

        from app.bot.telegram_bot import MAX_MESSAGE_LENGTH

        from app.services.digest import run_digest

        # Blocking (scores every symbol from the local caches + DB): off the event loop.

        pairs = await asyncio.to_thread(run_digest, "daily")

        if datetime.datetime.now(datetime.timezone.utc).weekday() == 4:

            # Friday: weekly subscribers get their edition too.

            pairs += await asyncio.to_thread(run_digest, "weekly")

        for telegram_id, text in pairs:

            try:

                if len(text) > MAX_MESSAGE_LENGTH:

                    text = text[: MAX_MESSAGE_LENGTH - 20] + "\n\n… (tronqué)"

                await context.bot.send_message(chat_id=telegram_id, text=text)

                logger.info("Digest sent to user %s", telegram_id)

            except Exception as e:

                logger.warning("Failed to send digest to %s: %s", telegram_id, e)

    except Exception as e:

        logger.exception("Digest job failed: %s", e)





def main() -> int:

    if not config.TELEGRAM_BOT_TOKEN:

        logger.error("TELEGRAM_BOT_TOKEN is not set. Add it to .env (from @BotFather).")

        return 1

    if config.OLLAMA_CLOUD and not config.OLLAMA_API_KEY:

        logger.error("OLLAMA_API_KEY is required when OLLAMA_CLOUD=true. Create one at https://ollama.com/settings/keys")

        return 1



    api_url = config.BRVM_API_URL

    health_url = f"{api_url}/health"

    client_kwargs = {"timeout": 5.0}

    if "localhost" in api_url.lower() or "127.0.0.1" in api_url:

        client_kwargs["trust_env"] = False

    last_err: str | None = "not attempted"

    for attempt in range(1, API_STARTUP_RETRIES + 1):

        try:

            with httpx.Client(**client_kwargs) as client:

                r = client.get(health_url)

            if r.status_code == 200:

                last_err = None

                break

            last_err = f"HTTP {r.status_code}"

        except Exception as e:

            last_err = str(e)

        if attempt < API_STARTUP_RETRIES:

            logger.warning(

                "Chat API not ready at %s (%s) - retry %s/%s in %ss",

                api_url, last_err, attempt, API_STARTUP_RETRIES, API_STARTUP_RETRY_DELAY,

            )

            time.sleep(API_STARTUP_RETRY_DELAY)

    if last_err is not None:

        logger.error(

            "Cannot reach Chat API at %s after %s attempts. Is it running? Start it with: python main.py or python run_api.py\n"

            "If bot and API run on different machines, set BRVM_API_URL in .env to the API URL (e.g. http://your-server:8000).\n"

            "Last error: %s",

            api_url,

            API_STARTUP_RETRIES,

            last_err,

        )

        return 1



    thread = threading.Thread(target=_daily_timeseries_job, daemon=True)

    thread.start()



    app = build_application()

    if app.job_queue is not None:

        app.job_queue.run_repeating(_check_target_alerts, interval=TARGET_CHECK_INTERVAL_SEC, first=60)

        if DIGEST_ENABLED:

            app.job_queue.run_daily(

                _digest_job,

                time=datetime.time(hour=DIGEST_HOUR_GMT, tzinfo=datetime.timezone.utc),

                days=(0, 1, 2, 3, 4),

            )

            logger.info("Digest scheduled: weekdays at %s:00 GMT (weekly edition on Friday).", DIGEST_HOUR_GMT)

        logger.info(

            "Bot starting (open to all users). Chat API: %s. Daily timeseries + target alerts (every %s s) scheduled.",

            config.BRVM_API_URL,

            TARGET_CHECK_INTERVAL_SEC,

        )

    else:

        logger.warning(

            "JobQueue not available. Install with: pip install \"python-telegram-bot[job-queue]\" for price target alerts."

        )

        logger.info(

            "Bot starting (open to all users). Chat API: %s. Daily timeseries scheduled; target alerts disabled.",

            config.BRVM_API_URL,

        )

    # Polling runs until interrupted (exception/signal)

    run_polling_with_retry(

        app,

        allowed_updates=["message"],

        bootstrap_retries=5,

        poll_retry_max=0,

        poll_retry_delay=30.0,

        poll_retry_backoff=1.5,

    )





if __name__ == "__main__":

    sys.exit(main())


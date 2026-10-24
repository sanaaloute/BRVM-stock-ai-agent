"""Background scheduled jobs, started from the API lifespan.

These jobs used to run inside the Telegram bot process; they are channel-
agnostic (delivery via FCM push through notify_user) and now live in the API
process:
- price-target alerts (every TARGET_CHECK_INTERVAL_SEC)
- market digest for subscribers (weekdays at DIGEST_HOUR_GMT; weekly edition on
  Friday too)
- daily timeseries CSV refresh
"""
from __future__ import annotations

import asyncio
import datetime
import logging

import config

logger = logging.getLogger(__name__)

DAILY_INTERVAL_SEC = 24 * 3600
TARGET_CHECK_INTERVAL_SEC = 300


async def target_alerts_loop() -> None:
    """Every 5 minutes: check users' price targets and push alerts (FCM)."""
    from app.services.notify import notify_user
    from app.utils.user_db import check_targets_and_notify

    while True:
        await asyncio.sleep(TARGET_CHECK_INTERVAL_SEC)
        try:
            # Blocking (sleeps + HTTP with retries): keep it off the event loop.
            results = await asyncio.to_thread(check_targets_and_notify)
            for principal_id, text in results:
                try:
                    notify_user(principal_id, text, push_title="Kora Bourse — Alerte prix")
                    logger.info("Target alert dispatched to user %s", principal_id)
                except Exception as e:
                    logger.warning("Failed to dispatch target alert to %s: %s", principal_id, e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Target check job failed: %s", e)


async def digest_loop() -> None:
    """Weekdays at DIGEST_HOUR_GMT (post-close; GMT == Abidjan): score the market,
    persist score snapshots and push the digest to subscribers. Friday adds the
    weekly edition."""
    from app.services.digest import run_digest
    from app.services.notify import notify_user

    last_sent: datetime.date | None = None
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            # Same hour only: a process restart later in the day must not resend.
            if now.weekday() > 4 or now.hour != config.DIGEST_HOUR_GMT:
                continue
            if last_sent == now.date():
                continue
            last_sent = now.date()
            # Blocking (scores every symbol from the local caches + DB): off the loop.
            pairs = await asyncio.to_thread(run_digest, "daily")
            if now.weekday() == 4:
                pairs += await asyncio.to_thread(run_digest, "weekly")
            for principal_id, text in pairs:
                try:
                    notify_user(principal_id, text, push_title="Kora Bourse — Digest")
                    logger.info("Digest dispatched to user %s", principal_id)
                except Exception as e:
                    logger.warning("Failed to dispatch digest to %s: %s", principal_id, e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Digest job failed: %s", e)


async def timeseries_loop() -> None:
    """Once at startup, then every 24h: update CSVs for all configured symbols."""
    from app.utils._data import run_daily_timeseries_update

    while True:
        try:
            logger.info("Daily timeseries update: %s", config.TIMESERIES_SYMBOLS)
            # Consume the generator inside the thread — iterating it on the event
            # loop would block it.
            results = await asyncio.to_thread(
                lambda: list(run_daily_timeseries_update(config.TIMESERIES_SYMBOLS))
            )
            for r in results:
                logger.info("Timeseries %s: %s", r.get("symbol"), r.get("action", r))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Daily timeseries update failed: %s", e)
        await asyncio.sleep(DAILY_INTERVAL_SEC)

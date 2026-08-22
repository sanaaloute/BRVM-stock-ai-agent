"""Run BRVM Chat API only (no Telegram bot). For API + bot together, use: python main.py"""
import logging
import sys

import uvicorn

from config import API_BIND, API_PORT
from app.utils.log_redact import install_log_redaction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
install_log_redaction()  # keep the bot token out of httpx request logs

if __name__ == "__main__":
    # host: API_BIND (default 127.0.0.1 = local only). docker compose overrides
    # API_BIND=0.0.0.0 inside the container; host exposure is then limited by
    # the ports mapping (default 127.0.0.1) — see docker-compose.yml.
    uvicorn.run(
        "app.api.chat:app",
        host=API_BIND,
        port=API_PORT,
        reload=False,
    )
    sys.exit(0)

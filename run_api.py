"""Run BRVM Chat API only (no Telegram bot). For API + bot together, use: python main.py"""
import logging
import sys

import uvicorn

from config import API_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    uvicorn.run(
        "app.api.chat:app",
        host="0.0.0.0",
        port=API_PORT,
        reload=False,
    )
    sys.exit(0)

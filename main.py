"""Single entry point: runs API + Telegram bot. Usage: python main.py"""
import sys
import uvicorn

from config import API_BIND, API_PORT

if __name__ == "__main__":
    # host: API_BIND (default 127.0.0.1 = local only; see .env.example).
    uvicorn.run(
        "app.main:app",
        host=API_BIND,
        port=API_PORT,
        reload=False,
    )
    sys.exit(0)

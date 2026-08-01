"""Single entry point: runs API + Telegram bot. Usage: python main.py"""
import sys
import uvicorn

from config import API_PORT

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=API_PORT,
        reload=False,
    )
    sys.exit(0)

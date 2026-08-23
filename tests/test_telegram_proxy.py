"""Tests for the Telegram Bot API base-URL override (Cloudflare Worker proxy path).

Run: python tests/test_telegram_proxy.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from app.bot.telegram_bot import _telegram_base_urls  # noqa: E402

_passed = _failed = 0


def check(name: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"PASS {name}")
    else:
        _failed += 1
        print(f"FAIL {name}")


def main() -> int:
    original = getattr(config, "TELEGRAM_BASE_URL", "")
    try:
        # Default: no override -> PTB defaults (None, None)
        config.TELEGRAM_BASE_URL = ""
        check("empty knob -> defaults", _telegram_base_urls() == (None, None))

        # Worker URL -> both API and file URLs point at it (PTB appends
        # <token>/<method> — so the /bot and /file/bot suffixes are included)
        config.TELEGRAM_BASE_URL = "https://telegram-api-proxy.example.workers.dev"
        check(
            "worker URL -> both base urls",
            _telegram_base_urls()
            == (
                "https://telegram-api-proxy.example.workers.dev/bot",
                "https://telegram-api-proxy.example.workers.dev/file/bot",
            ),
        )

        # Trailing slash is stripped (PTB appends <token>/<method>)
        config.TELEGRAM_BASE_URL = "https://telegram-api-proxy.example.workers.dev/"
        check(
            "trailing slash stripped",
            _telegram_base_urls()[0] == "https://telegram-api-proxy.example.workers.dev/bot",
        )

        # Whitespace tolerated
        config.TELEGRAM_BASE_URL = "  https://w.example.workers.dev  "
        check("whitespace tolerated", _telegram_base_urls()[0] == "https://w.example.workers.dev/bot")
    finally:
        config.TELEGRAM_BASE_URL = original

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())

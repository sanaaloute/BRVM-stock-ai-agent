"""Log redaction tests: the Telegram bot token must never reach log output.

httpx logs full request URLs at INFO level, and Bot API URLs embed the token.
Run:
    .venv/Scripts/python tests/test_log_redact.py
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils.log_redact import RedactSecretsFilter, install_log_redaction  # noqa: E402

# Realistic Bot API shape (bot<digits>:<secret>) — the redaction regex targets real tokens.
TOKEN_URL = "https://api.telegram.org/bot123456789:REDACTED_SECRET_TOKEN/sendMessage"


def _record(msg, args=()):
    return logging.LogRecord("httpx", logging.INFO, __file__, 1, msg, args, None)


def test_token_in_url_is_redacted():
    rec = _record(f'HTTP Request: POST {TOKEN_URL} "HTTP/1.1 200 OK"')
    RedactSecretsFilter().filter(rec)
    assert "REDACTED_SECRET" not in rec.getMessage(), rec.getMessage()
    assert "bot<redacted>" in rec.getMessage(), rec.getMessage()


def test_token_with_printf_args_is_redacted():
    rec = _record("HTTP Request: POST %s \"HTTP/1.1 200 OK\"", (TOKEN_URL,))
    RedactSecretsFilter().filter(rec)
    assert "REDACTED_SECRET" not in rec.getMessage(), rec.getMessage()


def test_plain_message_untouched():
    rec = _record('HTTP Request: GET http://api:8000/health "HTTP/1.1 200 OK"')
    RedactSecretsFilter().filter(rec)
    assert rec.getMessage() == 'HTTP Request: GET http://api:8000/health "HTTP/1.1 200 OK"'


def test_filter_always_passes_record():
    assert RedactSecretsFilter().filter(_record("anything")) is True


def test_install_attaches_to_handlers_and_httpx():
    root = logging.getLogger()
    handler = logging.StreamHandler()
    root.addHandler(handler)
    try:
        install_log_redaction()
        assert any(isinstance(f, RedactSecretsFilter) for f in handler.filters)
        assert any(isinstance(f, RedactSecretsFilter) for f in logging.getLogger("httpx").filters)
    finally:
        root.removeHandler(handler)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

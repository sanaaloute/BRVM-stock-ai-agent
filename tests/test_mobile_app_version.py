"""GET /mobile/v1/app-version: public store-release metadata driving the
mobile app's update prompt. Run:
    .venv/bin/python -m pytest tests/test_mobile_app_version.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

import app.api.chat as chat_mod  # noqa: E402

client = TestClient(chat_mod.app)


def test_app_version_is_public():
    """No JWT required: release metadata is not user data."""
    r = client.get("/mobile/v1/app-version")
    assert r.status_code == 200, r.text


def test_empty_config_means_no_update_prompt():
    config.MOBILE_APP_LATEST_VERSION = ""
    config.MOBILE_APP_WHATS_NEW = ""
    r = client.get("/mobile/v1/app-version")
    assert r.status_code == 200
    assert r.json() == {"latest_version": None, "whats_new": None}


def test_configured_release_served_with_real_newlines():
    config.MOBILE_APP_LATEST_VERSION = "1.6.0"
    config.MOBILE_APP_WHATS_NEW = "Nouveautés :\\n- Point A\\n- Point B"
    r = client.get("/mobile/v1/app-version")
    assert r.status_code == 200
    assert r.json() == {
        "latest_version": "1.6.0",
        "whats_new": "Nouveautés :\n- Point A\n- Point B",
    }


if __name__ == "__main__":
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
    sys.exit(1 if failed else 0)

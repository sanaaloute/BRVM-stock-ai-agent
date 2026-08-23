"""Shared pytest fixtures for the suite.

Many test modules drive the app through module-level singletons (`config`,
`app.api.chat.run_agent`, ...). Historically they patched those at import time
and "restored" to their own local value, so the result depended on pytest's
collection/run order and tests failed only when the whole suite ran.

This autouse fixture snapshots every public UPPERCASE config attribute before
each test and restores it afterwards, making config mutations test-local.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import config  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_config_after_test():
    snapshot = {}
    for key in dir(config):
        if not key.isupper():
            continue
        value = getattr(config, key)
        if isinstance(value, (set, list, dict)):
            value = value.copy()
        snapshot[key] = value
    try:
        yield
    finally:
        for key, value in snapshot.items():
            setattr(config, key, value)

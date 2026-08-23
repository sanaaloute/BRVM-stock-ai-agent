"""Integration test: fetch_palmares TTL caching + stale-if-error fallback.

Heavy third-party deps (requests, bs4, tavily, dotenv) are stubbed and the
scraper is monkeypatched, so this runs with a bare Python install.

Run:  python tests/test_palmares_cache.py
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub(name, **attrs):
    """Stub a third-party module ONLY when it is genuinely missing.

    Under pytest the venv provides bs4/requests/etc.: installing a bare stub
    into sys.modules at collection time leaks into every other test module
    (e.g. test_scraper_fixtures getting 'cannot import name ResultSet').
    Standalone runs on a bare Python install still get the stubs.
    """
    try:
        return __import__(name)
    except ImportError:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        return mod


# Stub third-party modules needed by the import chain (never really called).
_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("requests", get=lambda *a, **k: None)
_stub("bs4", BeautifulSoup=object)
_stub("tavily", TavilyClient=object)

import app.utils.cache as cache_mod  # noqa: E402
import app.utils._data as data_mod  # noqa: E402

FAIL = {"flag": False}
CALLS = {"n": 0}
DATE = {"value": None}


class FakeScraper:
    def __init__(self, *args, **kwargs):
        pass

    def scrape(self):
        CALLS["n"] += 1
        if FAIL["flag"]:
            return {"error": "boom", "stocks": []}
        return {"stocks": [{"symbol": "NTLC", "cours_actuel": 53000}], "date": DATE["value"]}


data_mod.RichBourseScraper = FakeScraper


class _LogCapture:
    """Capture records emitted by the app.utils._data logger."""

    def __init__(self):
        import logging

        self.records = []
        self.logger = logging.getLogger("app.utils._data")

    def __enter__(self):
        import logging

        self._handler = logging.Handler()
        self._handler.emit = lambda r: self.records.append(r)
        self.logger.addHandler(self._handler)
        self.logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *a):
        self.logger.removeHandler(self._handler)

    def messages(self, level):
        import logging

        return [r.getMessage() for r in self.records if r.levelno >= level]


def _fresh_cache(ttl=60):
    cache_mod._palmares_cache = cache_mod.MarketDataCache(ttl_seconds=ttl, persist_path=None)


def test_first_call_scrapes_then_cache_hit():
    _fresh_cache(ttl=60)
    CALLS["n"] = 0
    FAIL["flag"] = False
    r1 = data_mod.fetch_palmares(period="veille")
    assert CALLS["n"] == 1 and r1[0]["symbol"] == "NTLC"
    r2 = data_mod.fetch_palmares(period="veille")
    assert CALLS["n"] == 1, "second call within TTL must not re-scrape"
    assert r2 == r1


def test_force_refresh_bypasses_cache():
    _fresh_cache(ttl=60)
    FAIL["flag"] = False
    CALLS["n"] = 0
    data_mod.fetch_palmares(period="veille")
    assert CALLS["n"] == 1
    data_mod.fetch_palmares(period="veille", force_refresh=True)
    assert CALLS["n"] == 2


def test_stale_fallback_when_refresh_fails():
    _fresh_cache(ttl=0.0)  # everything expires instantly
    CALLS["n"] = 0
    FAIL["flag"] = False
    # Pin "today" to a Wednesday: on Sat/Sun fetch_palmares serves the stale
    # snapshot WITHOUT scraping (BRVM closed), which is not what this test
    # exercises — it must verify the failed-refresh stale fallback.
    real_datetime = data_mod.datetime

    class _WednesdayDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 8, 19, 12, 0, tzinfo=tz)  # a Wednesday

    data_mod.datetime = _WednesdayDateTime
    try:
        r1 = data_mod.fetch_palmares(period="1_mois")
        assert r1[0]["symbol"] == "NTLC"
        FAIL["flag"] = True  # source goes down
        import logging

        with _LogCapture() as cap:
            r2 = data_mod.fetch_palmares(period="1_mois")
        assert r2 and r2[0]["symbol"] == "NTLC", "must serve last good snapshot on failure"
        assert CALLS["n"] == 2
        # ... and the stale serving must be surfaced in the logs
        assert any("Serving stale" in m for m in cap.messages(logging.INFO)), cap.records
    finally:
        data_mod.datetime = real_datetime


def test_empty_result_with_no_history_returns_empty():
    _fresh_cache(ttl=60)
    FAIL["flag"] = True
    assert data_mod.fetch_palmares(period="2_ans") == []
    FAIL["flag"] = False


def test_french_date_parse():
    from datetime import date as _date

    assert data_mod._parse_french_date("Vendredi 20 Février 2026") == _date(2026, 2, 20)
    assert data_mod._parse_french_date("Lundi 5 Août 2025") == _date(2025, 8, 5)
    assert data_mod._parse_french_date("no date here") is None
    assert data_mod._parse_french_date("") is None


def test_stale_data_date_warns():
    _fresh_cache(ttl=60)
    FAIL["flag"] = False
    DATE["value"] = "Vendredi 20 Février 2020"  # ancient
    with _LogCapture() as cap:
        data_mod.fetch_palmares(period="3_mois")
    import logging

    assert any("days old" in m for m in cap.messages(logging.WARNING))
    DATE["value"] = None


def test_consecutive_failures_escalate_to_error():
    _fresh_cache(ttl=0.0)  # every call re-scrapes
    FAIL["flag"] = True
    import logging

    with _LogCapture() as cap:
        for _ in range(3):
            data_mod.fetch_palmares(period="6_mois")
    errors = cap.messages(logging.ERROR)
    assert errors and "3 times in a row" in errors[-1], errors
    FAIL["flag"] = False


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

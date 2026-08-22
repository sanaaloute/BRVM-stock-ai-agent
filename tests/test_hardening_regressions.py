"""Regression tests for the hardening round (2026-08).

Covers, fully offline (network and LLM calls stubbed):
  a. Sikafinance raw-text fallback parser: column group order with French
     thousand separators (app/scrapers/sikafinance.py).
  b. Rich Bourse timeseries: Highcharts ms timestamps convert as UTC (host-TZ
     independent) and the CSV write is atomic (app/scrapers/richbourse_timeseries.py).
  c. fetch_sgi_url SSRF allowlist (app/tools/stock_tools.py).
  d. Strict supervisor label parsing (app/agents/graph.py::_parse_next).
  e. Per-thread lock serialization in the chat pipeline (app/api/chat.py).

Run:
    .venv/bin/python tests/test_hardening_regressions.py
"""
import csv
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env


# --- a. Sikafinance raw-text fallback: group order ---------------------------
def test_sikafinance_fallback_group_order():
    from app.scrapers.sikafinance import SikaFinanceScraper

    # Raw text as the Tavily pipeline delivers it: thousand separators are
    # non-breaking spaces, which scrape() strips before the regex fallback
    # runs (plain spaces inside numbers would make the numeric groups
    # ambiguous — the regex relies on the strip).
    content = (
        "Palmarès BRVM — séance du vendredi\n"
        "SOLIBRA CI 35 540 35 000 35 500 1 234 +2,50 % +5,10 %\n"
        "NTLC 53 000 52 500 53 000 742 -0,50 % +1,20 %"
    )
    scraper = SikaFinanceScraper(period="veille", sleep_seconds=0)
    scraper.extract_content = lambda: content  # offline: skip Tavily
    out = scraper.scrape()
    rows = out["brvm_stocks"]
    assert len(rows) == 2, rows
    # symbol is None: proof these rows came from the raw-text fallback (no href)
    assert all(r["symbol"] is None for r in rows), rows
    row = next(r for r in rows if "SOLIBRA" in r["name"])
    assert row["haut"] == 35540, row
    assert row["bas"] == 35000, row
    assert row["dernier"] == 35500, row
    assert row["volume"] == 1234, row
    assert row["variation_jour_pct"] == 2.5, row
    assert row["variation_period_pct"] == 5.1, row


# --- b. Timeseries: UTC conversion + atomic write ----------------------------
def test_timeseries_utc_dates_and_atomic_write():
    import app.scrapers.richbourse_timeseries as ts_mod

    # 1756857600000 ms = 2025-09-03T00:00:00Z exactly; a naive local-time
    # conversion in America/New_York (UTC-4) would yield 2025-09-02 20:00.
    html = (
        "<html><body><script>var chart = new Highcharts.StockChart('c', {"
        " series: [{ data ? [[1756857600000,53000],[1756944000000,53100]]: [] }] });"
        "</script></body></html>"
    )

    class _Resp:
        text = html

        def raise_for_status(self):
            pass

    real_get = ts_mod.http_get
    ts_mod.http_get = lambda *a, **k: _Resp()
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        with tempfile.TemporaryDirectory() as d:
            out_dir = Path(d)
            old_csv = out_dir / "TEST_1999-01-01_1999-01-02.csv"
            old_csv.write_text("Date,Price\n1999-01-01 00:00:00,1\n", encoding="utf-8")
            scraper = ts_mod.RichBourseTimeseriesScraper(
                symbol="TEST", output_dir=out_dir, sleep_seconds=0
            )
            result = scraper.scrape()
            assert result["error"] is None, result
            assert result["rows"] == 2, result
            csv_path = Path(result["csv_path"])
            assert csv_path.name == "TEST_2025-09-03_2025-09-04.csv", csv_path.name
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            assert rows[0] == ["Date", "Price", "Open", "High", "Low", "Volume"], rows
            # UTC midnight must stay 2025-09-03 even with the host TZ behind UTC
            assert rows[1][0] == "2025-09-03 00:00:00", rows
            # atomic replace: old CSV gone, only the new one remains, no .tmp
            assert not old_csv.exists()
            assert [p.name for p in out_dir.glob("TEST_*.csv")] == [csv_path.name]
            assert list(out_dir.glob("*.tmp")) == []
    finally:
        ts_mod.http_get = real_get
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


# --- c. fetch_sgi_url SSRF allowlist -----------------------------------------
def test_fetch_sgi_url_ssrf_allowlist():
    import app.utils.http_client as http_client
    from app.tools.stock_tools import fetch_sgi_url_tool

    calls: list[str] = []

    class _Resp:
        text = "<html><body>Liste des SGI de la BRVM</body></html>"

        def raise_for_status(self):
            pass

    def _fake_get(url, **kwargs):
        calls.append(url)
        return _Resp()

    real_get = http_client.http_get
    http_client.http_get = _fake_get  # _fetch_sgi_url imports it lazily per call
    try:
        rejected = [
            "http://169.254.169.254/latest/meta-data",  # cloud metadata IP literal
            "http://localhost:8000/chat",               # loopback service
            "https://evil.com/x",                       # arbitrary host
            "https://richbourse.com@evil.com/",         # userinfo trick: host is evil.com
        ]
        for url in rejected:
            out = json.loads(fetch_sgi_url_tool.invoke({"url": url}))
            assert "error" in out, (url, out)
        assert calls == [], calls  # rejected URLs must never hit the network
        out = json.loads(fetch_sgi_url_tool.invoke({"url": "https://www.richbourse.com/common/sgi"}))
        assert "error" not in out and "SGI" in out["text_preview"], out
        assert calls == ["https://www.richbourse.com/common/sgi"], calls
    finally:
        http_client.http_get = real_get


# --- d. Strict supervisor label parsing --------------------------------------
def test_supervisor_exact_labels_route():
    from app.agents.graph import _label_to_worker, _parse_next

    assert _parse_next("SCRAPER") == ("scraper", [], False)
    assert _parse_next("FINISH") == ("FINISH", [], False)
    assert _label_to_worker("company details") == "company_details"  # spaces normalize
    assert _label_to_worker("SCRAPER.") is None  # exact match only


def test_supervisor_multi_mode():
    from app.agents.graph import _parse_next

    # comma = parallel, pipe = sequential
    assert _parse_next("ANALYTICS,NEWS") == ("FINISH", ["analytics", "news"], True)
    assert _parse_next("SCRAPER|CHARTS") == ("FINISH", ["scraper", "charts"], False)
    # multi is capped at the first 2 workers
    nxt, workers, parallel = _parse_next("ANALYTICS,NEWS,SCRAPER")
    assert nxt == "FINISH" and workers == ["analytics", "news"] and parallel
    # TIMESERIES is never auto-chained into a multi
    _, workers, _ = _parse_next("TIMESERIES,NEWS")
    assert workers == ["news"], workers
    _, workers, _ = _parse_next("SCRAPER|TIMESERIES")
    assert workers == ["scraper"], workers


def test_supervisor_verbose_output_rejected():
    from app.agents.graph import _parse_next

    # verbose garbage must NOT fan out into multi mode: fall back to FINISH
    assert _parse_next("NEWS, because the user asked for actualités") == ("FINISH", [], False)
    nxt, workers, parallel = _parse_next("One of SCRAPER | ANALYTICS | NEWS")
    assert (nxt, workers, parallel) == ("FINISH", [], False)
    assert _parse_next("I think ANALYTICS is the right worker") == ("FINISH", [], False)


# --- e. Per-thread lock serialization in /chat --------------------------------
def test_thread_lock_identity():
    import app.api.chat as chat_mod

    assert chat_mod._thread_lock("thr-x") is chat_mod._thread_lock("thr-x")
    assert chat_mod._thread_lock("thr-x") is not chat_mod._thread_lock("thr-y")


def test_chat_serializes_per_thread():
    import app.api.chat as chat_mod

    saved_cfg = (config.RATE_LIMIT_PER_MINUTE, config.DAILY_FREE_QUOTA)
    config.RATE_LIMIT_PER_MINUTE = 0  # 0 = disabled
    config.DAILY_FREE_QUOTA = 0       # 0 = unlimited
    real_agent = chat_mod.run_agent
    real_semaphore = chat_mod._agent_semaphore
    chat_mod._agent_semaphore = threading.Semaphore(4)  # never the bottleneck here

    state = {"cur": 0, "max": 0}
    state_lock = threading.Lock()

    def _slow_agent(*a, **k):
        with state_lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        try:
            time.sleep(0.2)
        finally:
            with state_lock:
                state["cur"] -= 1
        return {"messages": [], "_fresh_reply": "ok"}

    def _run(tid, errors):
        try:
            r = chat_mod._chat_impl(chat_mod.ChatRequest(query="q", thread_id=tid))
            if isinstance(r, chat_mod.ChatError):
                errors.append(r)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    chat_mod.run_agent = _slow_agent
    try:
        # Same thread_id: the two runs must serialize -> max concurrency 1.
        state["cur"] = state["max"] = 0
        errors: list = []
        threads = [threading.Thread(target=_run, args=("thr-same", errors)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert state["max"] == 1, state

        # Different thread_ids: the two runs overlap -> max concurrency 2.
        state["cur"] = state["max"] = 0
        errors = []
        threads = [threading.Thread(target=_run, args=(f"thr-diff-{i}", errors)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert state["max"] == 2, state
    finally:
        chat_mod.run_agent = real_agent
        chat_mod._agent_semaphore = real_semaphore
        config.RATE_LIMIT_PER_MINUTE, config.DAILY_FREE_QUOTA = saved_cfg


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

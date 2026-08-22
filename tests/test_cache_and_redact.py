"""Unit tests for the market-data cache and the deterministic redact formatter.

Run:  python tests/test_cache_and_redact.py   (or: pytest tests/)
Modules are loaded by file path so these tests need no third-party deps.
"""
import importlib.util
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cache_mod = _load("cache_mod", "app/utils/cache.py")
redact_mod = _load("redact_mod", "app/bot/redact.py")


# ---------------- MarketDataCache ----------------
def test_cache_set_get():
    c = cache_mod.MarketDataCache(ttl_seconds=60)
    c.set("k", [1, 2, 3])
    assert c.get("k") == [1, 2, 3]
    assert c.get("missing") is None


def test_cache_ttl_expiry():
    c = cache_mod.MarketDataCache(ttl_seconds=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(0.07)
    assert c.get("k") is None
    # stale fallback still returns the value
    assert c.get_stale("k") == "v"


def test_cache_disk_persistence():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cache.json"
        c1 = cache_mod.MarketDataCache(ttl_seconds=60, persist_path=p)
        c1.set("veille|tout", [{"symbol": "NTLC", "cours_actuel": 53000}])
        assert p.exists()
        c2 = cache_mod.MarketDataCache(ttl_seconds=60, persist_path=p)
        assert c2.get("veille|tout") == [{"symbol": "NTLC", "cours_actuel": 53000}]


def test_cache_corrupt_disk_file_ignored():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cache.json"
        p.write_text("not json{{{", encoding="utf-8")
        c = cache_mod.MarketDataCache(ttl_seconds=60, persist_path=p)  # must not raise
        assert c.get("k") is None


# ---------------- redact_for_telegram ----------------
def test_redact_strips_markdown():
    out = redact_mod.redact_for_telegram("## Price\n**NTLC** is at *53 000* F CFA (`last close`)")
    assert "##" not in out and "**" not in out and "`" not in out
    assert "NTLC" in out
    assert "last close" in out


def test_redact_removes_internal_lines():
    raw = (
        "Here is your chart for NTLC.\n"
        "Send image at /tmp/chart_abc123.png with your explanation.\n"
        "I used the plot_company_chart tool to make it.\n"
        "Price went up 2%."
    )
    out = redact_mod.redact_for_telegram(raw)
    assert "/tmp/" not in out
    assert "plot_company_chart" not in out
    assert "Price went up 2%." in out


def test_redact_table_to_lines():
    raw = "| Symbol | Price |\n| --- | --- |\n| NTLC | 53 000 |\n| SLBC | 35 540 |"
    out = redact_mod.redact_for_telegram(raw)
    assert "|" not in out
    assert "NTLC · 53 000" in out
    assert "SLBC · 35 540" in out


def test_redact_empty():
    assert redact_mod.redact_for_telegram("") == "No answer."
    assert redact_mod.redact_for_telegram("   ") == "No answer."


def test_redact_keeps_content():
    out = redact_mod.redact_for_telegram("NTLC: 53 000 F CFA (+1,2%)")
    assert out == "NTLC: 53 000 F CFA (+1,2%)"


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

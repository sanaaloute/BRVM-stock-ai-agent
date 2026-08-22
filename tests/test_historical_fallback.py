"""Historical price lookup must fall back to the last trading day on
weekends/holidays (BRVM is closed Sat/Sun).

Uses a fixture CSV in a temp series dir — no network. Run:
    .venv/Scripts/python tests/test_historical_fallback.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.utils._data as data_mod  # noqa: E402
import app.utils.stock_metrics as sm  # noqa: E402
import app.utils.comparison as cmp_mod  # noqa: E402

# Fixture: only Thu 2026-02-19 and Fri 2026-02-20 exist (Sat 21 / Sun 22 missing).
CSV = """Date,Price
2026-02-19 00:00:00,52500
2026-02-20 00:00:00,53000
"""


def _setup():
    d = Path(tempfile.mkdtemp())
    (d / "NTLC_2026-02-19_2026-02-20.csv").write_text(CSV, encoding="utf-8")
    data_mod.DATA_SERIES_DIR = d
    # Hermetic: no palmares scrape, no series fetch for missing symbols.
    sm.fetch_palmares = lambda *a, **k: []
    data_mod.ensure_series_csv = lambda symbol: None
    data_mod.ensure_timeseries_up_to_date = lambda symbol: None


def test_exact_trading_day():
    _setup()
    out = sm.get_stock_metrics("NTLC", at_time="2026-02-20")
    assert out["price"] == 53000
    assert out["price_date"] == "2026-02-20"


def test_sunday_falls_back_to_friday():
    _setup()
    out = sm.get_stock_metrics("NTLC", at_time="2026-02-22")  # Sunday
    assert out["price"] == 53000, out
    assert out["price_date"] == "2026-02-20"


def test_compare_on_weekend():
    _setup()
    out = cmp_mod.compare_stocks("NTLC", "SLBC", period_price_date="2026-02-21")  # Saturday
    assert out["a_period_price"] == 53000
    # SLBC has no CSV here -> None (no crash)
    assert out["b_period_price"] is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

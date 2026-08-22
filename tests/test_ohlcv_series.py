"""OHLCV series tests (app/scrapers/richbourse_timeseries.py, app/utils/_data.py).

Fully offline: synthetic Highcharts HTML, http_get stubbed, tmp output dirs.
Covers: OHLC+volume extraction (5-element points preferred over 2-element),
the 6-column CSV write, and load_series on both modern and legacy 2-column
CSVs (legacy rows get open/high/low/volume=None).

Run:
    .venv/bin/python tests/test_ohlcv_series.py
"""
import csv
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.scrapers.richbourse_timeseries as ts_mod  # noqa: E402
import app.utils._data as data_mod  # noqa: E402
from app.scrapers.richbourse_timeseries import extract_highcharts_ohlcv  # noqa: E402

# UTC-midnight millisecond timestamps (2025-09-03 .. 2025-09-09, weekend skipped).
OHLC = [
    [1756857600000, 100, 105, 99, 103],   # 2025-09-03
    [1756944000000, 103, 107, 102, 106],  # 2025-09-04
    [1757030400000, 106, 108, 104, 105],  # 2025-09-05
    [1757289600000, 105, 109, 104, 108],  # 2025-09-08
    [1757376000000, 108, 110, 106, 109],  # 2025-09-09
]
VOLUMES = [
    [1756857600000, 1200],
    [1756944000000, 1500],
    [1757030400000, 900],
    [1757289600000, 2000],
    [1757376000000, 1800],
]
CLOSE_ONLY = [[1756857600000, 103], [1756944000000, 106]]


def _block(data) -> str:
    return "{ data ? " + json.dumps(data) + " : [] }"


def _volume_block(data) -> str:
    # The extractor flags a series as volume via 'name: "Volume"' in the ~300
    # chars preceding the data array — same shape as the real mouvements page.
    return '{ name: "Volume", data ? ' + json.dumps(data) + " : [] }"


def _html(*blocks) -> str:
    series = ",".join(blocks)
    return (
        "<html><body><script>var chart = new Highcharts.StockChart('c', { series: ["
        + series + "] });</script></body></html>"
    )


def test_extract_prefers_ohlc_and_aligns_volume():
    # 2-element series first on the page: the OHLC series must still win.
    html = _html(_block(CLOSE_ONLY), _block(OHLC), _volume_block(VOLUMES))
    out = extract_highcharts_ohlcv(html)
    assert out is not None
    assert out["points"] == OHLC, out["points"]
    assert out["volumes"] == VOLUMES, out["volumes"]


def test_extract_drops_misaligned_volume_and_falls_back_to_close():
    # Volume series with a different point count: dropped rather than misaligned.
    html = _html(_block(OHLC), _volume_block(VOLUMES[:2]))
    out = extract_highcharts_ohlcv(html)
    assert out is not None
    assert out["points"] == OHLC
    assert out["volumes"] is None
    # Close-only page: 2-element series used, no volume.
    out2 = extract_highcharts_ohlcv(_html(_block(CLOSE_ONLY)))
    assert out2 is not None
    assert out2["points"] == CLOSE_ONLY
    assert out2["volumes"] is None


def test_scrape_writes_six_column_csv():
    html = _html(_block(OHLC), _volume_block(VOLUMES))

    class _Resp:
        text = html

        def raise_for_status(self):
            pass

    real_get = ts_mod.http_get
    ts_mod.http_get = lambda *a, **k: _Resp()
    try:
        with tempfile.TemporaryDirectory() as d:
            scraper = ts_mod.RichBourseTimeseriesScraper(
                symbol="TEST", output_dir=Path(d), sleep_seconds=0
            )
            result = scraper.scrape()
            assert result["error"] is None, result
            assert result["rows"] == 5, result
            assert result["date_range"] == ["2025-09-03", "2025-09-09"], result
            with open(result["csv_path"], newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            assert rows[0] == ["Date", "Price", "Open", "High", "Low", "Volume"], rows[0]
            assert rows[1] == ["2025-09-03 00:00:00", "103", "100", "105", "99", "1200"], rows[1]
            assert rows[5] == ["2025-09-09 00:00:00", "109", "108", "110", "106", "1800"], rows[5]
    finally:
        ts_mod.http_get = real_get


def test_load_series_modern_and_legacy_csv():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Modern 6-column file.
        (tmp / "NEW_2025-09-03_2025-09-04.csv").write_text(
            "Date,Price,Open,High,Low,Volume\n"
            "2025-09-03 00:00:00,103,100,105,99,1200\n"
            "2025-09-04 00:00:00,106,103,107,102,1500\n",
            encoding="utf-8",
        )
        # Legacy 2-column file (pre-OHLCV format).
        (tmp / "LEG_2025-01-02_2025-01-03.csv").write_text(
            "Date,Price\n"
            "2025-01-02 00:00:00,100\n"
            "2025-01-03 00:00:00,101\n",
            encoding="utf-8",
        )
        real_dir = data_mod.DATA_SERIES_DIR
        data_mod.DATA_SERIES_DIR = tmp
        try:
            modern = data_mod.load_series("NEW", fetch_if_missing=False)
            assert len(modern) == 2, modern
            first = modern[0]
            assert first["date"] == date(2025, 9, 3) and first["price"] == 103.0
            assert first["open"] == 100.0 and first["high"] == 105.0
            assert first["low"] == 99.0 and first["volume"] == 1200.0

            legacy = data_mod.load_series("LEG", fetch_if_missing=False)
            assert len(legacy) == 2, legacy
            assert legacy[0]["date"] == date(2025, 1, 2) and legacy[0]["price"] == 100.0
            assert legacy[1]["price"] == 101.0
            for row in legacy:
                assert row["open"] is None and row["high"] is None
                assert row["low"] is None and row["volume"] is None
        finally:
            data_mod.DATA_SERIES_DIR = real_dir


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

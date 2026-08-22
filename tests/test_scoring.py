"""Unit tests for the deterministic scoring engine (app/services/scoring.py).

Run:  python tests/test_scoring.py
Data loaders are monkeypatched on the scoring module (no network, no CSV I/O).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import scoring  # noqa: E402


# ---------------- Fakes & patch helper ----------------
def make_rows(prices, volumes=None, start=date(2024, 1, 2)):
    """Build load_series-style rows (ascending dates, price = close)."""
    rows = []
    for i, p in enumerate(prices):
        rows.append({
            "date": start + timedelta(days=i),
            "price": float(p),
            "open": None,
            "high": None,
            "low": None,
            "volume": (float(volumes[i]) if volumes else None),
        })
    return rows


UP_PRICES = [100.0 + 0.5 * i for i in range(300)]    # steady rise 100 -> 249.5
DOWN_PRICES = [250.0 - 0.5 * i for i in range(300)]  # steady fall 250 -> 100.5
FLAT_PRICES = [100.0] * 300

# Real BRVM symbols (validated against BRVM_Companies.xlsx).
SYM_UP = "SNTS"
SYM_DOWN = "NTLC"
SYM_SHORT = "SGBC"


class patch_loaders:
    """Context manager monkeypatching scoring.load_series / load_company_details
    / fetch_palmares, restoring originals afterwards."""

    def __init__(self, series_by_symbol=None, rows=None, details=None, palmares=None):
        self._series_by_symbol = series_by_symbol
        self._rows = rows
        self._details = details  # callable(symbol) -> dict | None
        self._palmares = palmares if palmares is not None else []
        self._saved = {}

    def __enter__(self):
        def fake_load_series(symbol, *args, **kwargs):
            if self._series_by_symbol is not None:
                return self._series_by_symbol.get(symbol, [])
            return self._rows or []

        def fake_details(symbol, *args, **kwargs):
            if callable(self._details):
                return self._details(symbol)
            return self._details

        def fake_palmares(*args, **kwargs):
            return self._palmares

        for name, fake in (("load_series", fake_load_series),
                           ("load_company_details", fake_details),
                           ("fetch_palmares", fake_palmares)):
            self._saved[name] = getattr(scoring, name)
            setattr(scoring, name, fake)
        return self

    def __exit__(self, *exc):
        for name, original in self._saved.items():
            setattr(scoring, name, original)


# ---------------- Tests ----------------
def test_uptrend_beats_downtrend():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        up = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows(DOWN_PRICES), details=None):
        down = scoring.score_symbol(SYM_DOWN)
    assert up["error"] is None and down["error"] is None
    assert up["score"] is not None and down["score"] is not None
    assert up["score"] > down["score"], (up["score"], down["score"])
    assert up["signal"] in (scoring.SIGNAL_BUY, scoring.SIGNAL_ACCUMULATE), up["signal"]
    assert down["signal"] in (scoring.SIGNAL_NEUTRAL, scoring.SIGNAL_REDUCE), down["signal"]


def test_flat_series_is_neutral():
    with patch_loaders(rows=make_rows(FLAT_PRICES), details=None):
        res = scoring.score_symbol(SYM_UP)
    assert res["error"] is None
    assert 35 <= res["score"] <= 65, res["score"]
    assert res["signal"] == scoring.SIGNAL_NEUTRAL, res["signal"]


def test_rsi_helper():
    up15 = [float(i) for i in range(1, 16)]  # monotonic up
    assert scoring._rsi(up15) == 100.0
    # Alternating +2 / -5 (down-heavy), 15 closes
    down_heavy = [100, 102, 97, 99, 94, 96, 91, 93, 88, 90, 85, 87, 82, 84, 79]
    r = scoring._rsi([float(x) for x in down_heavy])
    assert r is not None and r < 35, r
    assert scoring._rsi([100.0] * 20) == 50.0  # flat -> neutral
    assert scoring._rsi([1.0, 2.0]) is None    # not enough data


def test_parse_fr_number():
    assert scoring._parse_fr_number("32 348") == 32348.0
    assert scoring._parse_fr_number("1 234,56") == 1234.56
    assert scoring._parse_fr_number("1 234,56") == 1234.56  # NBSP
    assert scoring._parse_fr_number("16,08") == 16.08
    assert scoring._parse_fr_number("") is None
    assert scoring._parse_fr_number("abc") is None
    assert scoring._parse_fr_number(None) is None


def test_missing_company_details_still_scores():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        res = scoring.score_symbol(SYM_UP)
    assert res["error"] is None and res["score"] is not None
    # All fundamental components neutral -> block at its mid value 50.
    assert abs(res["fundamentals"]["block"] - 50.0) < 0.01, res["fundamentals"]
    assert len(res["data_warnings"]) > 0
    assert any("Résultat net" in w for w in res["data_warnings"])


def test_insufficient_history_errors():
    with patch_loaders(rows=make_rows(UP_PRICES[:50]), details=None):
        res = scoring.score_symbol(SYM_UP)
    assert res["score"] is None
    assert res["error"] and "insuffisantes" in res["error"]
    with patch_loaders(rows=[], details=None):
        res = scoring.score_symbol(SYM_UP)
    assert res["score"] is None and res["error"]


def test_full_fundamentals_scored():
    details = {
        "performance": {
            "croissance_rn": {"2023": "16,0"},
            "croissance_ca": {"2023": "-5,0"},
            "per": {"2023": "10"},
            "dividende": {"2023": "500"},
        }
    }

    def fake_details(symbol):
        # One symbol without cached details: median must tolerate it.
        return None if symbol == "BOAC" else details

    # Flat at 10 000 so dividend yield = 500 / 10 000 = 5 %.
    with patch_loaders(rows=make_rows([10000.0] * 300), details=fake_details):
        res = scoring.score_symbol(SYM_UP)
    assert res["error"] is None
    fund = res["fundamentals"]
    assert abs(fund["growth"] - 24.0) < 0.01, fund        # 20 (RN >= +15%) + 4 (CA -5%)
    assert abs(fund["valuation"] - 23.33) < 0.01, fund    # PER == median -> 35*(2-1)/1.5
    assert abs(fund["dividend"] - 21.67) < 0.01, fund     # 5 + (5%/6%)*20
    assert abs(fund["block"] - 69.0) < 0.01, fund
    assert fund["per_median"] == 10.0
    assert not any("PER indisponible" in w for w in res["data_warnings"])
    assert any("Rendement du dividende" in r for r in res["reasons"])


def test_score_all_ranks_and_separates_insufficient():
    series = {
        SYM_UP: make_rows(UP_PRICES),
        SYM_DOWN: make_rows(DOWN_PRICES),
        SYM_SHORT: make_rows(UP_PRICES[:50]),
    }
    with patch_loaders(series_by_symbol=series, details=None):
        res = scoring.score_all([SYM_DOWN, SYM_SHORT, SYM_UP])
    ranked_symbols = [r["symbol"] for r in res["ranked"]]
    assert ranked_symbols == [SYM_UP, SYM_DOWN], ranked_symbols
    assert res["ranked"][0]["score"] >= res["ranked"][1]["score"]
    insufficient_symbols = [r["symbol"] for r in res["insufficient"]]
    assert insufficient_symbols == [SYM_SHORT], insufficient_symbols
    assert res["insufficient"][0]["error"]
    assert res["as_of"]


def test_invalid_symbol():
    res = scoring.score_symbol("XXXX")
    assert res["score"] is None
    assert res["error"] and "BRVM" in res["error"]


def test_volume_absent_vs_present():
    # Same uptrend prices; one series with rising volume, one with no volume.
    volumes = [1000.0] * 280 + [2000.0] * 20  # ratio recent/prior = 2.0
    with patch_loaders(rows=make_rows(UP_PRICES, volumes=volumes), details=None):
        with_vol = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        without_vol = scoring.score_symbol(SYM_UP)
    assert with_vol["error"] is None and without_vol["error"] is None
    for res in (with_vol, without_vol):
        assert 0.0 <= res["technicals"]["block"] <= 100.0, res["technicals"]["block"]
    assert with_vol["technicals"]["volume"] == 10.0
    assert with_vol["technicals"]["volume_ratio"] == 2.0
    assert without_vol["technicals"]["volume"] is None
    assert any("Volumes indisponibles" in w for w in without_vol["data_warnings"])
    assert not any("Volumes indisponibles" in w for w in with_vol["data_warnings"])
    assert with_vol["technicals"]["block"] > without_vol["technicals"]["block"]


def test_signal_bands():
    assert scoring.signal_for_score(70) == scoring.SIGNAL_BUY
    assert scoring.signal_for_score(55) == scoring.SIGNAL_ACCUMULATE
    assert scoring.signal_for_score(40) == scoring.SIGNAL_NEUTRAL
    assert scoring.signal_for_score(39.9) == scoring.SIGNAL_REDUCE


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

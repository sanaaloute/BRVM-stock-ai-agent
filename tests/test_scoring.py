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


# ---------------- Sika Finance enriched-data tests ----------------
def make_dividend_history(montants, yields):
    return [{"year": 2020 + i, "montant": float(m), "rendement_pct": float(y)}
            for i, (m, y) in enumerate(zip(montants, yields))]


def make_technical_analysis(up, down, neutral=0, signals_count=None):
    n = signals_count if signals_count is not None else up + down + neutral
    return {
        "signals": [{"group": "tendance", "direction": "up", "text": "x"}
                    for _ in range(n)],
        "up": up,
        "down": down,
        "neutral": neutral,
        "fetched_at": "2024-06-01T00:00:00",
    }


def make_sector(symbol, self_ytd, peer_ytds, name="BRVM - TELECOMMUNICATIONS"):
    peers = [{"symbol": symbol, "name": "Self", "dernier": None,
              "variation_jour_pct": None, "variation_ytd_pct": self_ytd}]
    for i, y in enumerate(peer_ytds):
        peers.append({"symbol": f"P{i}", "name": f"Peer {i}", "dernier": None,
                      "variation_jour_pct": None, "variation_ytd_pct": y})
    return {"sector": {"name": name, "peers": peers, "fetched_at": "2024-06-01"}}


def test_dividend_history_5y_upgrades_dividend_subscore():
    perf = {"dividende": {"2023": "500"}}
    rising = {
        "performance": perf,
        "market": {"dividend_history": make_dividend_history(
            [100, 110, 120, 130, 140], [8.0] * 5)},
    }
    with patch_loaders(rows=make_rows([10000.0] * 300), details=rising):
        res = scoring.score_symbol(SYM_UP)
    fund = res["fundamentals"]
    # avg yield 8 % -> base 25, +3 consistency (never cut) -> clamped to 25.
    assert fund["dividend"] == 25.0, fund
    assert fund["dividend_yield_avg_5y"] == 0.08, fund
    assert fund["dividend_history_years"] == 5, fund
    assert fund["dividend_never_cut"] is True, fund
    assert any("Rendement moyen du dividende sur 5 ans : 8,0 %" in r
               for r in res["reasons"]), res["reasons"]
    assert any("dividende jamais baissé depuis 5 ans" in r
               for r in res["reasons"]), res["reasons"]

    # Two montant cuts -> base - 3 (avg yield 4 % -> base 18.33).
    cut = {
        "performance": perf,
        "market": {"dividend_history": make_dividend_history(
            [100, 90, 95, 80, 85], [4.0] * 5)},
    }
    with patch_loaders(rows=make_rows([10000.0] * 300), details=cut):
        res2 = scoring.score_symbol(SYM_UP)
    base = 5.0 + (0.04 / 0.06) * 20.0
    assert abs(res2["fundamentals"]["dividend"] - (base - 3.0)) < 0.01, res2["fundamentals"]
    assert res2["fundamentals"]["dividend_never_cut"] is False
    assert not any("jamais baissé" in r for r in res2["reasons"])


def test_dividend_history_under_3_entries_keeps_legacy_path():
    perf = {"dividende": {"2023": "500"}}
    two = {
        "performance": perf,
        "market": {"dividend_history": make_dividend_history([100, 110], [9.0, 9.0])},
    }
    legacy = {"performance": perf}
    with patch_loaders(rows=make_rows([10000.0] * 300), details=two):
        with_two = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows([10000.0] * 300), details=legacy):
        without = scoring.score_symbol(SYM_UP)
    assert with_two["fundamentals"] == without["fundamentals"]
    assert "dividend_yield_avg_5y" not in with_two["fundamentals"]
    # Legacy single-year yield: 500 / 10 000 = 5 % -> 5 + (5/6)*20.
    assert abs(with_two["fundamentals"]["dividend"] - 21.67) < 0.01
    assert with_two["score"] == without["score"]
    assert with_two["reasons"] == without["reasons"]


def test_beta_rebalances_risk_subscore():
    with patch_loaders(rows=make_rows(UP_PRICES), details={"market": {"beta_1an": 0.7}}):
        low = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows(UP_PRICES), details={"market": {"beta_1an": 1.31}}):
        high = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows(UP_PRICES), details={"market": {"beta_1an": 1.0}}):
        mid = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        baseline = scoring.score_symbol(SYM_UP)

    assert low["technicals"]["beta_1an"] == 0.7
    assert high["technicals"]["beta_1an"] == 1.31
    assert low["technicals"]["risk"] > high["technicals"]["risk"]
    # UP_PRICES: near-zero volatility, no drawdown -> vol 7 + dd 6 + beta pts.
    assert abs(low["technicals"]["risk"] - 15.0) < 0.01, low["technicals"]
    expected_high = 13.0 + 2.0 * (1.5 - 1.31) / 0.7
    assert abs(high["technicals"]["risk"] - expected_high) < 0.01, high["technicals"]
    assert abs(mid["technicals"]["risk"] - (13.0 + 2.0 * 0.5 / 0.7)) < 0.01, mid["technicals"]
    assert any("Bêta 1 an : 0,70 (faible sensibilité au marché)" in r
               for r in low["reasons"]), low["reasons"]
    assert any("Bêta 1 an : 1,31 (sensibilité élevée au marché)" in r
               for r in high["reasons"]), high["reasons"]
    assert any("Bêta 1 an : 1,00 (sensibilité moyenne au marché)" in r
               for r in mid["reasons"]), mid["reasons"]

    # Beta None -> byte-identical to the no-details baseline.
    with patch_loaders(rows=make_rows(UP_PRICES), details={"market": {"beta_1an": None}}):
        none_beta = scoring.score_symbol(SYM_UP)
    assert none_beta["technicals"] == baseline["technicals"]
    assert none_beta["fundamentals"] == baseline["fundamentals"]
    assert none_beta["score"] == baseline["score"]
    assert none_beta["reasons"] == baseline["reasons"]
    assert none_beta["data_warnings"] == baseline["data_warnings"]


def test_sika_consensus_adjusts_technicals_block():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        base = scoring.score_symbol(SYM_UP)
    base_block = base["technicals"]["block"]

    details_up = {"technical_analysis": make_technical_analysis(6, 2)}
    with patch_loaders(rows=make_rows(UP_PRICES), details=details_up):
        bullish = scoring.score_symbol(SYM_UP)
    assert abs(bullish["technicals"]["block"] - (base_block + 4.0)) < 0.01, bullish["technicals"]
    assert bullish["technicals"]["sika_consensus_up"] == 6
    assert bullish["technicals"]["sika_consensus_down"] == 2
    assert bullish["technicals"]["sika_consensus_neutral"] == 0
    assert any("Analyse technique Sika Finance : 6 signaux haussiers, 2 baissiers" in r
               for r in bullish["reasons"]), bullish["reasons"]

    details_down = {"technical_analysis": make_technical_analysis(1, 5)}
    with patch_loaders(rows=make_rows(UP_PRICES), details=details_down):
        bearish = scoring.score_symbol(SYM_UP)
    assert abs(bearish["technicals"]["block"] - (base_block - 4.0)) < 0.01, bearish["technicals"]
    assert any("Analyse technique Sika Finance : 1 signaux haussiers, 5 baissiers" in r
               for r in bearish["reasons"]), bearish["reasons"]

    # Fewer than 3 signals -> no adjustment, no reason, counts still exposed.
    few = {"technical_analysis": make_technical_analysis(2, 0, signals_count=2)}
    with patch_loaders(rows=make_rows(UP_PRICES), details=few):
        res = scoring.score_symbol(SYM_UP)
    assert res["technicals"]["block"] == base_block
    assert res["technicals"]["sika_consensus_up"] == 2
    assert not any("Sika Finance" in r for r in res["reasons"])

    # Balanced consensus (adj == 0) -> no reason either.
    balanced = {"technical_analysis": make_technical_analysis(2, 2)}
    with patch_loaders(rows=make_rows(UP_PRICES), details=balanced):
        res = scoring.score_symbol(SYM_UP)
    assert res["technicals"]["block"] == base_block
    assert not any("Sika Finance" in r for r in res["reasons"])


def test_sector_context_reason():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        baseline = scoring.score_symbol(SYM_UP)

    top = make_sector(SYM_UP, 41.6, [10.0, 20.0])
    with patch_loaders(rows=make_rows(UP_PRICES), details=top):
        res = scoring.score_symbol(SYM_UP)
    sector_reasons = [r for r in res["reasons"] if r.startswith("Secteur ")]
    assert sector_reasons == [
        "Secteur TELECOMMUNICATIONS : +41,6 % depuis janvier — 1er du secteur"
    ], res["reasons"]
    assert res["reasons"][-1] == sector_reasons[0]  # appended last
    assert len(res["reasons"]) <= 7
    assert res["score"] == baseline["score"]  # informational only

    bottom = make_sector(SYM_UP, 5.0, [10.0, 20.0, 30.0, 41.6])
    with patch_loaders(rows=make_rows(UP_PRICES), details=bottom):
        res = scoring.score_symbol(SYM_UP)
    assert any(r.startswith("Secteur TELECOMMUNICATIONS : +5,0 % depuis janvier")
               and "à la traîne du secteur" in r for r in res["reasons"]), res["reasons"]

    mid = make_sector(SYM_UP, 20.0, [10.0, 41.6])
    with patch_loaders(rows=make_rows(UP_PRICES), details=mid):
        res = scoring.score_symbol(SYM_UP)
    assert any("2e du secteur" in r for r in res["reasons"]), res["reasons"]

    # Sector key absent, or symbol missing from the peer table -> no reason.
    assert not any(r.startswith("Secteur ") for r in baseline["reasons"])
    other = make_sector("OTHER", 41.6, [10.0])
    with patch_loaders(rows=make_rows(UP_PRICES), details=other):
        res = scoring.score_symbol(SYM_UP)
    assert not any(r.startswith("Secteur ") for r in res["reasons"])


def test_empty_new_containers_are_noop():
    legacy = {
        "performance": {
            "croissance_rn": {"2023": "16,0"},
            "per": {"2023": "10"},
            "dividende": {"2023": "500"},
        }
    }
    enriched_empty = dict(legacy, market={}, technical_analysis={}, sector={})
    with patch_loaders(rows=make_rows([10000.0] * 300), details=legacy):
        a = scoring.score_symbol(SYM_UP)
    with patch_loaders(rows=make_rows([10000.0] * 300), details=enriched_empty):
        b = scoring.score_symbol(SYM_UP)
    assert a == b


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

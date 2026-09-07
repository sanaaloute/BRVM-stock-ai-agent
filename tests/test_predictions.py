"""Tests for the daily AI predictions (app/services/predictions.py):
computation on synthetic series, persistence + idempotency, scheduling gate,
and the /mobile/v1/market/predictions API.

Offline: throwaway SQLite DBs (DB_PATH rebound per test), the data loaders
monkeypatched in BOTH the scoring and predictions module namespaces (each
reads its own module attrs), LLM disabled unless a test re-enables it.

Run:
    .venv/bin/python -m pytest tests/test_predictions.py
"""
import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import mobile as mobile_mod  # noqa: E402
from app.api import mobile_auth  # noqa: E402
from app.services import predictions, scoring  # noqa: E402
from app.utils import user_db  # noqa: E402

TODAY_ISO = datetime.now(timezone.utc).date().isoformat()
JWT_SECRET = "test-jwt-secret-predictions"


def _fresh_db():
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "predictions_test.db"
    user_db.init_db()


# ---------------- Fakes & patch helpers ----------------
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


# Steady trends with a small wiggle, so the 20d volatility is non-degenerate.
UP_PRICES = [100.0 * (1.004 ** i) * (1 + 0.008 * ((i % 5) - 2)) for i in range(300)]
DOWN_PRICES = [250.0 * (0.996 ** i) * (1 + 0.008 * ((i % 5) - 2)) for i in range(300)]

# Real BRVM symbols (validated against the local companies registry).
SYM_UP = "SNTS"
SYM_DOWN = "NTLC"


class patch_loaders:
    """Context manager monkeypatching load_series / fetch_palmares in both the
    scoring and predictions namespaces, plus scoring.load_company_details;
    restores originals afterwards."""

    def __init__(self, series_by_symbol=None, rows=None, details=None, palmares=None):
        self._series_by_symbol = series_by_symbol
        self._rows = rows
        self._details = details
        self._palmares = palmares if palmares is not None else []
        self._saved = []

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

        for mod, name, fake in (
            (scoring, "load_series", fake_load_series),
            (scoring, "load_company_details", fake_details),
            (scoring, "fetch_palmares", fake_palmares),
            (predictions, "load_series", fake_load_series),
            (predictions, "fetch_palmares", fake_palmares),
        ):
            self._saved.append((mod, name, getattr(mod, name)))
            setattr(mod, name, fake)
        return self

    def __exit__(self, *exc):
        for mod, name, original in self._saved:
            setattr(mod, name, original)


class patch_valid_symbols:
    """Restrict predictions.get_valid_symbols (the run's symbol universe)."""

    def __init__(self, symbols):
        self._symbols = set(symbols)

    def __enter__(self):
        self._saved = predictions.get_valid_symbols
        predictions.get_valid_symbols = lambda: set(self._symbols)
        return self

    def __exit__(self, *exc):
        predictions.get_valid_symbols = self._saved


# ---------------- compute_prediction ----------------
def test_compute_prediction_rising_series():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        pred = predictions.compute_prediction(SYM_UP)
    assert pred.get("error") is None, pred
    assert pred["direction"] == "hausse", pred["votes"]
    assert 50 <= pred["confidence_pct"] <= 95, pred["confidence_pct"]
    assert pred["expected_move_pct"] > 0
    assert pred["target_low"] < pred["price"] < pred["target_high"]
    assert pred["price"] == round(UP_PRICES[-1], 2)
    assert pred["score"] is not None and pred["signal"]


def test_compute_prediction_falling_series():
    with patch_loaders(rows=make_rows(DOWN_PRICES), details=None):
        pred = predictions.compute_prediction(SYM_DOWN)
    assert pred.get("error") is None, pred
    assert pred["direction"] == "baisse", pred["votes"]
    assert 50 <= pred["confidence_pct"] <= 95
    assert pred["target_low"] < pred["price"] < pred["target_high"]


def test_compute_prediction_insufficient_data():
    with patch_loaders(rows=make_rows(UP_PRICES[:50]), details=None):
        pred = predictions.compute_prediction(SYM_UP)
    assert pred.get("error") and "insuffisantes" in pred["error"]
    with patch_loaders(rows=[], details=None):
        pred = predictions.compute_prediction(SYM_UP)
    assert pred.get("error")


def test_fallback_explanation_is_french_and_grounded():
    with patch_loaders(rows=make_rows(UP_PRICES), details=None):
        pred = predictions.compute_prediction(SYM_UP)
    text = predictions._fallback_explanation(pred)
    assert SYM_UP in text and "haussière" in text
    assert "conseil en investissement" in text


# ---------------- run_daily_predictions ----------------
def test_run_daily_predictions_persists_and_is_idempotent():
    _fresh_db()
    config.PREDICTIONS_LLM_ENABLED = False  # deterministic fallback text
    series = {SYM_UP: make_rows(UP_PRICES), SYM_DOWN: make_rows(DOWN_PRICES)}
    symbols = {SYM_UP, SYM_DOWN}
    with patch_loaders(series_by_symbol=series, details=None), patch_valid_symbols(symbols):
        res1 = predictions.run_daily_predictions()
        rows1 = user_db.get_latest_predictions()
        res2 = predictions.run_daily_predictions()  # same day: replaces rows
        rows2 = user_db.get_latest_predictions()
    assert res1["count"] == 2 and res1["errors"] == 0, res1
    assert res1["day"] == TODAY_ISO
    assert len(rows1) == 2
    assert len(rows2) == 2, "re-run the same day must not duplicate rows"
    assert user_db.get_latest_prediction_day() == TODAY_ISO
    by_sym = {r["symbol"]: r for r in rows2}
    assert by_sym[SYM_UP]["direction"] == "hausse"
    assert by_sym[SYM_DOWN]["direction"] == "baisse"
    assert by_sym[SYM_UP]["explanation"]  # fallback text persisted
    details = json.loads(by_sym[SYM_UP]["details_json"])
    assert details["votes"] and details["technicals"] and details["fundamentals"]
    assert user_db.get_prediction(SYM_UP)["symbol"] == SYM_UP
    assert user_db.get_prediction("BOAC") is None


def test_run_daily_predictions_uses_llm_explanation():
    _fresh_db()
    config.PREDICTIONS_LLM_ENABLED = True
    series = {SYM_UP: make_rows(UP_PRICES)}
    calls = []
    real_explain = predictions.explain_with_llm

    def fake_explain(pred):
        calls.append(pred["symbol"])
        return f"Analyse LLM pour {pred['symbol']}."

    predictions.explain_with_llm = fake_explain
    try:
        with patch_loaders(series_by_symbol=series, details=None), patch_valid_symbols({SYM_UP}):
            res = predictions.run_daily_predictions()
    finally:
        predictions.explain_with_llm = real_explain
    assert res["count"] == 1
    assert calls == [SYM_UP]
    assert user_db.get_prediction(SYM_UP)["explanation"] == "Analyse LLM pour SNTS."


def test_explain_with_llm_falls_back_on_error():
    pred = {
        "symbol": SYM_UP, "direction": "hausse", "confidence_pct": 80,
        "score": 70.0, "signal": "Achat",
        "reasons": ["Momentum 3 mois : +5,0 %"],
        "expected_move_pct": 3.0, "target_low": 240.0, "target_high": 260.0,
    }
    real_get_llm = predictions.get_llm

    def dead_llm():
        raise RuntimeError("provider down")

    predictions.get_llm = dead_llm
    try:
        text = predictions.explain_with_llm(pred)
    finally:
        predictions.get_llm = real_get_llm
    assert SYM_UP in text and "haussière" in text  # deterministic fallback


# ---------------- Scheduling gate ----------------
def test_predictions_due_gating():
    _fresh_db()
    saturday = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)
    monday_am = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    monday_pm = datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)
    assert predictions.predictions_due(saturday) is False     # weekend
    assert predictions.predictions_due(monday_am) is False    # before 16:30 GMT
    assert predictions.predictions_due(monday_pm) is True     # weekday post-close
    user_db.save_predictions([
        {"symbol": SYM_UP, "day": "2026-09-07", "direction": "hausse"},
    ])
    assert predictions.predictions_due(monday_pm) is False    # already computed


# ---------------- API ----------------
_app = FastAPI()
_app.include_router(mobile_auth.router)
_app.include_router(mobile_mod.router)
client = TestClient(_app)


def _auth(identifier: str) -> dict:
    """Full OTP login (mock provider); returns tokens + user."""
    config.JWT_SECRET = JWT_SECRET
    config.AUTH_PROVIDER = "mock"
    r = client.post("/mobile/v1/auth/request-code", json={"identifier": identifier})
    assert r.status_code == 200, r.text
    dev_code = r.json().get("dev_code")
    assert dev_code, "mock provider must return the code"
    r = client.post("/mobile/v1/auth/verify-code", json={"identifier": identifier, "code": dev_code})
    assert r.status_code == 200, r.text
    return r.json()


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _seed_predictions():
    user_db.save_predictions([
        {"symbol": SYM_DOWN, "direction": "baisse", "confidence_pct": 62,
         "expected_move_pct": 2.1, "price": 100.0, "target_low": 97.9,
         "target_high": 102.1, "score": 38.0, "signal": "Alléger",
         "explanation": "Tendance baissière attendue.",
         "details": {"votes": [{"label": "Cours vs MM20", "vote": -1}]}},
        {"symbol": SYM_UP, "direction": "hausse", "confidence_pct": 88,
         "expected_move_pct": 3.2, "price": 250.0, "target_low": 242.0,
         "target_high": 258.0, "score": 71.5, "signal": "Achat",
         "explanation": "Tendance haussière attendue.",
         "details": {"votes": [{"label": "Cours vs MM20", "vote": 1}]}},
    ])


def test_api_predictions_require_token():
    _fresh_db()
    config.JWT_SECRET = JWT_SECRET  # auth on, but no token supplied -> 401
    assert client.get("/mobile/v1/market/predictions").status_code == 401
    assert client.get("/mobile/v1/market/predictions/SNTS").status_code == 401


def test_api_predictions_empty_when_never_computed():
    _fresh_db()
    tokens = _auth("pred-empty@example.com")
    r = client.get("/mobile/v1/market/predictions", headers=_headers(tokens))
    assert r.status_code == 200
    assert r.json() == {"day": None, "predictions": []}


def test_api_predictions_list_and_detail():
    _fresh_db()
    _seed_predictions()
    tokens = _auth("pred@example.com")
    h = _headers(tokens)

    r = client.get("/mobile/v1/market/predictions", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["day"] == TODAY_ISO
    items = body["predictions"]
    # Sorted by confidence desc: SNTS (88) before NTLC (62).
    assert [p["symbol"] for p in items] == [SYM_UP, SYM_DOWN]
    assert items[0]["name"] and items[0]["direction"] == "hausse"
    assert items[0]["confidence_pct"] == 88

    r = client.get(f"/mobile/v1/market/predictions/{SYM_UP}", headers=h)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["symbol"] == SYM_UP and detail["day"] == TODAY_ISO
    assert detail["explanation"] == "Tendance haussière attendue."
    assert detail["target_low"] == 242.0 and detail["target_high"] == 258.0
    assert detail["details"]["votes"] == [{"label": "Cours vs MM20", "vote": 1}]
    assert detail["name"]

    # Valid symbol without a prediction -> 404; invalid symbol -> 404.
    r = client.get("/mobile/v1/market/predictions/BOAC", headers=h)
    assert r.status_code == 404 and "prévision" in r.json()["detail"]
    assert client.get("/mobile/v1/market/predictions/XXXX", headers=h).status_code == 404


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

"""Digest tests: subscriptions (app/utils/user_db.py) + composition and job
body (app/services/digest.py).

Offline: throwaway SQLite DBs (DB_PATH rebound per test), the scoring engine
monkeypatched for run_digest. Days are derived from UTC (user_db stores
UTC days); "yesterday" seeds the previous-snapshot comparison.

Run:
    .venv/bin/python tests/test_digest.py
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from app.services import digest, scoring  # noqa: E402
from app.utils import user_db  # noqa: E402

TODAY_ISO = datetime.now(timezone.utc).date().isoformat()
YESTERDAY_ISO = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def _fresh_db():
    user_db.DB_PATH = Path(tempfile.mkdtemp()) / "digest_test.db"
    user_db.init_db()


def _seed_snapshots():
    """Today: NTLC Achat > SNTS Accumuler > BOAC Neutre > SGBC Alléger.
    Yesterday: NTLC Accumuler, SNTS Accumuler, SGBC Neutre."""
    user_db.save_score_snapshots([
        {"symbol": "NTLC", "score": 73.3, "signal": "Achat",
         "details": {"reasons": ["Tendance haussière : cours au-dessus des MM50 et MM200"],
                     "data_warnings": []}},
        {"symbol": "SNTS", "score": 60.1, "signal": "Accumuler",
         "details": {"reasons": ["Momentum 6 mois : +12,3 %"], "data_warnings": []}},
        {"symbol": "BOAC", "score": 45.0, "signal": "Neutre",
         "details": {"reasons": [], "data_warnings": ["Volumes indisponibles"]}},
        {"symbol": "SGBC", "score": 31.5, "signal": "Alléger",
         "details": {"reasons": ["Tendance baissière : cours sous les MM50 et MM200"],
                     "data_warnings": []}},
    ])
    user_db.save_score_snapshots([
        {"symbol": "NTLC", "day": YESTERDAY_ISO, "score": 60.0, "signal": "Accumuler"},
        {"symbol": "SNTS", "day": YESTERDAY_ISO, "score": 60.1, "signal": "Accumuler"},
        {"symbol": "SGBC", "day": YESTERDAY_ISO, "score": 45.0, "signal": "Neutre"},
    ])


class patch_score_all:
    """Monkeypatch scoring.score_all (run_digest reads it off the module)."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        self._saved = scoring.score_all
        scoring.score_all = lambda symbols=None: self._payload
        return self

    def __exit__(self, *exc):
        scoring.score_all = self._saved


# ---------------- Subscriptions ----------------
def test_subscribe_list_unsubscribe():
    _fresh_db()
    assert user_db.digest_set(101, "daily")["ok"]
    assert user_db.digest_set(102, "weekly")["ok"]
    assert user_db.digest_subscribers("daily") == [101]
    assert user_db.digest_subscribers("weekly") == [102]
    assert sorted(user_db.digest_subscribers()) == [101, 102]
    sub = user_db.digest_get(101)
    assert sub and sub["frequency"] == "daily" and sub["enabled"] == 1
    # Re-subscribe switches the frequency.
    assert user_db.digest_set(101, "weekly")["ok"]
    assert user_db.digest_get(101)["frequency"] == "weekly"
    # Invalid frequency rejected.
    bad = user_db.digest_set(103, "monthly")
    assert not bad["ok"] and "error" in bad
    # Unsubscribe removes from the enabled list; unknown user fails cleanly.
    assert user_db.digest_unsubscribe(101)["ok"]
    assert user_db.digest_subscribers() == [102]
    assert not user_db.digest_unsubscribe(999)["ok"]  # never subscribed


# ---------------- Composition ----------------
def test_compose_digest_empty_db_returns_none():
    _fresh_db()
    assert digest.compose_digest(999, "daily") is None
    assert digest.compose_digest(999, "weekly") is None


def test_compose_digest_daily_content():
    _fresh_db()
    _seed_snapshots()
    user_db.digest_set(201, "daily")
    user_db.portfolio_add(201, "NTLC", 50000, "2025-01-15")
    user_db.portfolio_add(201, "SNTS", 3000, "2025-03-10")
    user_db.tracking_add(201, "SGBC")

    text = digest.compose_digest(201, "daily")
    assert text is not None
    header = text.splitlines()[0]
    assert header.startswith("📊 Résumé BRVM du "), header
    french_days = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
    assert any(day in header for day in french_days), header

    # Top picks: buys section first (score order), watch section after.
    assert "🟢 À l'achat" in text
    assert "NTLC — 73,3/100 (Achat) : Tendance haussière : cours au-dessus des MM50 et MM200" in text
    assert "SNTS — 60,1/100 (Accumuler) : Momentum 6 mois : +12,3 %" in text
    assert "🔴 À surveiller / alléger" in text
    assert "SGBC — 31,5/100 (Alléger) : Tendance baissière : cours sous les MM50 et MM200" in text
    assert "BOAC — 45,0/100 (Neutre)" in text
    assert text.index("NTLC — 73,3") < text.index("SGBC — 31,5")

    # Positions: signal change vs yesterday, unchanged otherwise.
    assert "📁 Vos positions" in text
    assert "NTLC : Accumuler → Achat ⬆️" in text
    assert "SNTS : Accumuler — inchangé" in text
    # Tracking list: same compact block.
    assert "👀 Votre liste de suivi" in text
    assert "SGBC : Neutre → Alléger ⬇️" in text
    # Disclaimer footer.
    assert text.rstrip().endswith(digest.DISCLAIMER)


def test_compose_digest_weekly_header_and_empty_sections():
    _fresh_db()
    _seed_snapshots()
    user_db.digest_set(202, "weekly")
    text = digest.compose_digest(202, "weekly")
    assert text is not None
    assert text.splitlines()[0].startswith("📊 Résumé hebdo BRVM — semaine du lundi "), text.splitlines()[0]
    # No portfolio / tracking -> personal sections omitted.
    assert "Vos positions" not in text
    assert "liste de suivi" not in text
    assert text.rstrip().endswith(digest.DISCLAIMER)


# ---------------- Job body ----------------
def test_run_digest_persists_and_returns_pairs():
    _fresh_db()
    user_db.digest_set(301, "daily")
    user_db.digest_set(302, "weekly")
    fake_all = {
        "as_of": TODAY_ISO,
        "ranked": [
            {"symbol": "NTLC", "score": 73.3, "signal": "Achat",
             "reasons": ["Tendance haussière"], "data_warnings": []},
            {"symbol": "SGBC", "score": 31.5, "signal": "Alléger",
             "reasons": [], "data_warnings": ["Volumes indisponibles"]},
        ],
        "insufficient": [{"symbol": "SNTS", "score": None, "signal": None,
                          "error": "Pas de série historique en cache"}],
    }
    with patch_score_all(fake_all):
        pairs = digest.run_digest("daily")
        weekly_pairs = digest.run_digest("weekly")
    assert [tid for tid, _ in pairs] == [301], pairs
    assert [tid for tid, _ in weekly_pairs] == [302], weekly_pairs
    assert "NTLC — 73,3/100 (Achat)" in pairs[0][1]
    assert weekly_pairs[0][1].splitlines()[0].startswith("📊 Résumé hebdo BRVM")

    # Snapshots persisted from the ranked entries only (insufficient skipped).
    snaps = {s["symbol"]: s for s in user_db.get_latest_snapshots(TODAY_ISO)}
    assert set(snaps) == {"NTLC", "SGBC"}, snaps
    assert snaps["NTLC"]["signal"] == "Achat"
    assert abs(snaps["NTLC"]["score"] - 73.3) < 1e-9
    details = json.loads(snaps["SGBC"]["details_json"])
    assert details["data_warnings"] == ["Volumes indisponibles"]


def test_run_digest_disabled_returns_empty():
    _fresh_db()
    user_db.digest_set(401, "daily")
    saved = getattr(config, "DIGEST_ENABLED", True)
    config.DIGEST_ENABLED = False
    try:
        assert digest.run_digest("daily") == []
    finally:
        config.DIGEST_ENABLED = saved


def test_run_digest_skips_failed_subscribers():
    _fresh_db()
    _seed_snapshots()
    user_db.digest_set(501, "daily")
    user_db.digest_set(502, "daily")
    user_db.digest_set(503, "daily")
    empty_all = {"as_of": TODAY_ISO, "ranked": [], "insufficient": []}
    real_compose = digest.compose_digest

    def flaky(telegram_id, frequency):
        if telegram_id == 501:
            raise RuntimeError("boom")  # per-subscriber failure: logged, skipped
        if telegram_id == 503:
            return None  # nothing useful to send: skipped
        return real_compose(telegram_id, frequency)

    digest.compose_digest = flaky
    try:
        with patch_score_all(empty_all):
            pairs = digest.run_digest("daily")
    finally:
        digest.compose_digest = real_compose
    assert [tid for tid, _ in pairs] == [502], pairs


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

"""History graph (GET /mobile/v1/portfolio/history) consistency tests.

The graph must always agree with the summary card (``portfolio_summary``) and
react to every lot edit/delete — the two sources of truth (frozen import
transactions vs live lot rows) used to desync: quantity edits were ignored by
the curve and price/date edits double-counted the position.
"""
from datetime import date, timedelta

import pytest

import config
from app.utils import user_db

USER_ID = 123

IMPORT_BUYS = [
    {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 10, "price": 50000},
    {"symbol": "NTLC", "side": "buy", "date": "2026-02-01", "quantity": 5, "price": 52000},
]


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(user_db, "DB_PATH", tmp_path / "test.db")
    user_db.reset_engine()
    user_db.init_db()
    yield
    user_db.reset_engine()


def _fake_series(today: date):
    return [
        {"date": today - timedelta(days=20), "price": 50000.0},
        {"date": today - timedelta(days=10), "price": 52000.0},
        {"date": today, "price": 60000.0},
    ]


def _series_loader(rows):
    """Range-respecting fake for user_db.load_series (mirrors the real filter)."""

    def load(symbol, start_date=None, end_date=None, **kwargs):
        return [
            row
            for row in rows
            if (start_date is None or row["date"] >= start_date)
            and (end_date is None or row["date"] <= end_date)
        ]

    return load


def _import(temp_db, transactions, digest="a" * 64):
    result = user_db.portfolio_apply_import(USER_ID, digest, transactions)
    assert result["ok"], result
    return result


def test_history_reflects_lot_quantity_edit(temp_db, monkeypatch):
    """Editing an imported lot's quantity must change the curve (it was
    silently ignored because the import snapshot replayed the old quantity)."""
    today = date.today()
    monkeypatch.setattr(user_db, "load_series", _series_loader(_fake_series(today)))
    _import(temp_db, IMPORT_BUYS)

    lot = user_db.portfolio_list(USER_ID)[0]
    assert user_db.portfolio_lot_update(USER_ID, lot["id"], quantity=20)["ok"]

    history = user_db.portfolio_history(USER_ID, 90)
    assert history[-1]["total_cost_fcfa"] == 20 * 50000 + 5 * 52000
    assert history[-1]["total_value_fcfa"] == 25 * 60000
    assert history[-1]["gain_loss_fcfa"] == 25 * 60000 - (20 * 50000 + 5 * 52000)


def test_history_price_edit_does_not_double_count(temp_db, monkeypatch):
    """Editing an imported lot's price/date/SGI must not replay both the frozen
    import transaction AND the edited lot (positions were doubled)."""
    today = date.today()
    monkeypatch.setattr(user_db, "load_series", _series_loader(_fake_series(today)))
    _import(temp_db, IMPORT_BUYS)

    lot = user_db.portfolio_list(USER_ID)[0]
    assert user_db.portfolio_lot_update(USER_ID, lot["id"], buy_price=45000)["ok"]

    history = user_db.portfolio_history(USER_ID, 90)
    assert history[-1]["total_cost_fcfa"] == 10 * 45000 + 5 * 52000
    assert history[-1]["total_value_fcfa"] == 15 * 60000


def test_history_matches_summary_after_delete(temp_db, monkeypatch):
    """Deleting a lot shrinks the curve immediately."""
    today = date.today()
    monkeypatch.setattr(user_db, "load_series", _series_loader(_fake_series(today)))
    _import(temp_db, IMPORT_BUYS)

    lot = user_db.portfolio_list(USER_ID)[0]
    assert user_db.portfolio_lot_remove(USER_ID, lot["id"])["ok"]

    history = user_db.portfolio_history(USER_ID, 90)
    assert history[-1]["total_cost_fcfa"] == 5 * 52000
    assert history[-1]["total_value_fcfa"] == 5 * 60000


def test_history_missing_series_is_neutral_not_a_loss(temp_db, monkeypatch):
    """A symbol with no close in the window must not show an artificial loss of
    its full cost: like the summary card, fall back to cost (flat zero gain)."""
    monkeypatch.setattr(user_db, "load_series", _series_loader([]))
    buy_date = (date.today() - timedelta(days=30)).isoformat()
    assert user_db.portfolio_add(USER_ID, "NTLC", 50000, buy_date, 10)["ok"]

    history = user_db.portfolio_history(USER_ID, 90)
    assert history, "expected history points even without price data"
    assert history[-1]["total_cost_fcfa"] == 500000
    assert history[-1]["total_value_fcfa"] == 500000
    assert history[-1]["gain_loss_fcfa"] == 0


def test_history_seeds_price_before_window(temp_db, monkeypatch):
    """When the last close predates the window, the position must still be
    valued (no dip to zero until the first in-window close)."""
    today = date.today()
    stale_close = today - timedelta(days=120)
    rows = [{"date": stale_close, "price": 55000.0}]
    monkeypatch.setattr(user_db, "load_series", _series_loader(rows))
    buy_date = (today - timedelta(days=150)).isoformat()
    assert user_db.portfolio_add(USER_ID, "NTLC", 50000, buy_date, 10)["ok"]

    history = user_db.portfolio_history(USER_ID, 90)
    assert history
    assert history[0]["total_value_fcfa"] == 10 * 55000
    assert history[-1]["total_value_fcfa"] == 10 * 55000
    assert history[-1]["gain_loss_fcfa"] == 10 * 55000 - 500000

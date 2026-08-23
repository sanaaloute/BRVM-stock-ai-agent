"""Tests for BRVM session-time semantics (app/utils/market_hours.py) and the
last-close price fallback in app/utils/stock_metrics.py.

Run: .venv/bin/python tests/test_market_hours.py
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
config.DATABASE_URL = ""  # force SQLite regardless of local .env

from app.utils import market_hours  # noqa: E402

_passed = _failed = 0


def check(name: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"PASS {name}")
    else:
        _failed += 1
        print(f"FAIL {name}")


def _utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def main() -> int:
    # 2026-08-21 is a Friday; 22/23 Sat/Sun; 24 Monday.
    fri, sat, sun, mon = date(2026, 8, 21), date(2026, 8, 22), date(2026, 8, 23), date(2026, 8, 24)

    check("is_trading_day weekdays", market_hours.is_trading_day(fri) and not market_hours.is_trading_day(sat))
    check("last_trading_day saturday -> friday", market_hours.last_trading_day_on_or_before(sat) == fri)
    check("last_trading_day monday -> monday", market_hours.last_trading_day_on_or_before(mon) == mon)

    # Saturday anytime -> Friday's close is the reference
    check("saturday -> friday data", market_hours.expected_data_date(_utc(2026, 8, 22, 12)) == fri)
    check("sunday -> friday data", market_hours.expected_data_date(_utc(2026, 8, 23, 18)) == fri)
    # Monday before 15:30 UTC publish -> still Friday's close
    check("monday noon -> friday data", market_hours.expected_data_date(_utc(2026, 8, 24, 12)) == fri)
    check("monday 15:00 (fixing) -> friday data (buffer)", market_hours.expected_data_date(_utc(2026, 8, 24, 15, 0)) == fri)
    # Monday after publish -> Monday's close
    check("monday 16:00 -> monday data", market_hours.expected_data_date(_utc(2026, 8, 24, 16)) == mon)
    # Friday morning -> Thursday's close; Friday evening -> Friday's close
    check("friday 10:00 -> thursday data", market_hours.expected_data_date(_utc(2026, 8, 21, 10)) == date(2026, 8, 20))
    check("friday 16:00 -> friday data", market_hours.expected_data_date(_utc(2026, 8, 21, 16)) == fri)

    note_sat = market_hours.market_note(_utc(2026, 8, 22, 12))
    check("weekend note mentions week-end + friday date", "week-end" in note_sat and "21/08/2026" in note_sat)
    note_mon_am = market_hours.market_note(_utc(2026, 8, 24, 11))
    check("pre-close note mentions 15h00 close", "15h00" in note_mon_am and "21/08/2026" in note_mon_am)
    note_mon_pm = market_hours.market_note(_utc(2026, 8, 24, 16))
    check("post-close note gives today's session", "24/08/2026" in note_mon_pm)

    # get_stock_metrics: palmarès price None -> last close from series, with date
    from app.utils import stock_metrics

    real_palmares = stock_metrics.fetch_palmares
    real_load = stock_metrics.load_price_on_or_before
    stock_metrics.fetch_palmares = lambda **kw: [
        {"symbol": "ETIT", "cours_actuel": None, "volume": 1185056, "capitalisation": 66, "variation_pct": 0.0}
    ]
    stock_metrics.load_price_on_or_before = lambda sym, d: {"date": date(2026, 8, 21), "price": 22500.0}
    try:
        out = stock_metrics.get_stock_metrics("ETIT")
        check("null palmarès price -> last close fallback", out["price"] == 22500.0)
        check("fallback carries the close date", out.get("price_date") == "2026-08-21")
        check("fallback source labeled", out.get("source") == "timeseries_last_close")
        check("market note attached", "market_note" in out and "data_as_of" in out)
        check("volume from palmarès kept", out["volume"] == 1185056)
    finally:
        stock_metrics.fetch_palmares = real_palmares
        stock_metrics.load_price_on_or_before = real_load

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())

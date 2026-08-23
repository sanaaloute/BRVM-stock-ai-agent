"""BRVM trading-session calendar helpers (UTC == Abidjan market time).

Official session phases (brvm.org/fr/horaires-de-cotation): pre-open
09:00-09:45 UTC, opening fixing 09:45, continuous trading until 15:00 UTC,
closing fixing ~15:00. Practical consequence for market data:
- on a trading day BEFORE the close is published, sources (Rich Bourse, Sika)
  show the PREVIOUS session's closing price;
- today's close only appears after the ~15:00 UTC closing fixing (we allow a
  publish buffer);
- on weekends the visible price is Friday's close (same for holidays, which we
  don't track — the "last available close" logic stays correct regardless).
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone

# Closing fixing is ~15:00 UTC; sources publish shortly after. Buffer included.
CLOSE_PUBLISH_UTC = dtime(15, 30)


def is_trading_day(d: date) -> bool:
    """BRVM trades Monday-Friday (public holidays not tracked — callers use
    last-available-close logic, which stays correct)."""
    return d.weekday() < 5


def last_trading_day_on_or_before(d: date) -> date:
    """Most recent trading day on or before d (weekend rolls back to Friday)."""
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def expected_data_date(now: datetime | None = None) -> date:
    """The session whose closing price should currently be visible in sources."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    if is_trading_day(today) and now.time() >= CLOSE_PUBLISH_UTC:
        return today
    return last_trading_day_on_or_before(today - timedelta(days=1))


def market_note(now: datetime | None = None) -> str:
    """French phrasing of the price-timing semantics, for tool outputs so the
    LLM words answers correctly ('dernière clôture' vs 'clôture du jour')."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    ref = expected_data_date(now).strftime("%d/%m/%Y")
    if not is_trading_day(today):
        return (
            f"Marché fermé (week-end) : les cours affichés sont les dernières "
            f"clôtures disponibles (séance du {ref})."
        )
    if now.time() < CLOSE_PUBLISH_UTC:
        return (
            f"Séance du jour pas encore clôturée (clôture ~15h00 GMT) : les cours "
            f"affichés sont les dernières clôtures disponibles (séance du {ref})."
        )
    return f"Cours de clôture de la séance du {ref}."

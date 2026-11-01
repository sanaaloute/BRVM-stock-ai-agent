"""Unit tests for app.services.symbol_sections: the daily-refreshed store
behind the mobile fiche's dividends/news/prediction sections.

Run:  python tests/test_symbol_sections.py   (or: pytest tests/)
"""
from pathlib import Path

import app.utils.news as news_utils
from app.services import symbol_sections
from app.utils.cache import MarketDataCache


def _fresh_cache(monkeypatch, ttl=3600.0):
    cache = MarketDataCache(ttl_seconds=ttl, persist_path=None)
    monkeypatch.setattr(symbol_sections, "_cache", cache)
    return cache


def test_news_cache_first_no_refetch(monkeypatch):
    _fresh_cache(monkeypatch)
    calls = []
    monkeypatch.setattr(
        news_utils, "get_company_news",
        lambda sym, limit=15: calls.append(sym) or {"items": [{"title": "T"}]},
    )
    first = symbol_sections.news_for("SNTS")
    second = symbol_sections.news_for("SNTS")
    assert first["items"][0]["title"] == "T"
    assert second["items"][0]["title"] == "T"
    assert calls == ["SNTS"]  # scraped once, then served from cache


def test_expired_entry_refreshes(monkeypatch):
    _fresh_cache(monkeypatch, ttl=0.0)  # everything is immediately stale
    calls = []
    monkeypatch.setattr(
        news_utils, "get_company_news",
        lambda sym, limit=15: calls.append(sym) or {"items": []},
    )
    symbol_sections.news_for("SNTS")
    symbol_sections.news_for("SNTS")
    assert calls == ["SNTS", "SNTS"]


def test_scrape_failure_serves_stale(monkeypatch):
    cache = _fresh_cache(monkeypatch, ttl=0.0)
    cache.set("news:SNTS", {"items": [{"title": "Ancien"}]})
    monkeypatch.setattr(
        news_utils, "get_company_news",
        lambda sym, limit=15: {"items": [], "error": "HTTP 503"},
    )
    out = symbol_sections.news_for("SNTS")
    assert out["items"][0]["title"] == "Ancien"  # last known good, not the error


def test_scrape_exception_without_stale_returns_nothing(monkeypatch):
    _fresh_cache(monkeypatch)

    def boom(sym, limit=15):
        raise RuntimeError("network down")

    monkeypatch.setattr(news_utils, "get_company_news", boom)
    assert symbol_sections.news_for("SNTS") == {}  # degraded section, no crash


def test_dividends_shared_page_cached_once(monkeypatch):
    _fresh_cache(monkeypatch)
    calls = []
    monkeypatch.setattr(
        news_utils, "get_richbourse_dividends",
        lambda limit=50, symbol=None: calls.append(symbol) or {
            "items": [
                {"symbol": "SNTS", "dividende": 1740.0},
                {"symbol": "NTLC", "dividende": 150.0},
            ]
        },
    )
    snts = symbol_sections.dividends_for("SNTS")
    ntlc = symbol_sections.dividends_for("NTLC")
    assert [i["dividende"] for i in snts["items"]] == [1740.0]
    assert [i["dividende"] for i in ntlc["items"]] == [150.0]
    assert calls == [None]  # one scrape for both symbols


def test_refresh_all_caches_sections_and_skips_errors(monkeypatch):
    cache = _fresh_cache(monkeypatch)
    monkeypatch.setattr(
        news_utils, "get_richbourse_dividends",
        lambda limit=50, symbol=None: {"items": []},
    )
    monkeypatch.setattr(
        news_utils, "get_company_news",
        lambda sym, limit=15: {"items": [], "error": "x"} if sym == "BICB" else {"items": [{"title": sym}]},
    )
    monkeypatch.setattr(
        news_utils, "get_richbourse_prediction",
        lambda sym: (_ for _ in ()).throw(RuntimeError("down")) if sym == "BICB" else {"trend": "HAUSSE"},
    )
    stats = symbol_sections.refresh_all(["ABJC", "BICB"])
    assert stats == {"dividends": 1, "news": 1, "prediction": 1}
    assert cache.get("news:ABJC") == {"items": [{"title": "ABJC"}]}
    assert cache.get("prediction:ABJC") == {"trend": "HAUSSE"}
    assert cache.get("news:BICB") is None  # error results are not cached
    assert cache.get("prediction:BICB") is None
    assert cache.get("dividends:ALL") == {"items": []}


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([str(Path(__file__))]))

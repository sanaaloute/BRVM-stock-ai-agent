"""Tests for the Ollama Cloud web_search/web_fetch scraper fallback channel
(app/utils/ollama_web.py, BaseScraper.extract_content fallback).

This is the only remaining Ollama usage in the app: a scraper fallback when
Tavily fails. The chat LLM goes through the Afrikia provider.

Run: .venv/bin/python tests/test_ollama_web_fallback.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

_passed = _failed = 0


def check(name: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"PASS {name}")
    else:
        _failed += 1
        print(f"FAIL {name}")


def main() -> int:
    # ollama_web helpers
    import app.utils.ollama_web as ow

    saved_key = config.OLLAMA_API_KEY
    try:
        config.OLLAMA_API_KEY = ""
        check("web_fetch unavailable without key", ow.web_fetch("https://x.com") is None)

        config.OLLAMA_API_KEY = "k"
        real_post = ow.httpx.post

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"title": "T", "content": "  contenu page  ", "links": []}

        ow.httpx.post = lambda *a, **k: _Resp()
        data = ow.web_fetch("https://example.com")
        check("web_fetch returns content", data is not None and "contenu page" in data["content"])

        class _RespSearch:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [{"title": "a", "url": "u", "content": "c"}]}

        ow.httpx.post = lambda *a, **k: _RespSearch()
        check("web_search returns results", len(ow.web_search("brvm")) == 1)
        ow.httpx.post = real_post
    finally:
        config.OLLAMA_API_KEY = saved_key

    # BaseScraper.extract_content: Tavily failure -> Ollama fallback
    from app.scrapers.base import BaseScraper

    class _Dummy(BaseScraper):
        @property
        def url(self):
            return "https://blocked.example/page"

        def scrape(self):
            return {}

    d = _Dummy(api_key="x", sleep_seconds=0)
    d.fetch_raw = lambda: (_ for _ in ()).throw(RuntimeError("tavily down"))

    import app.utils.ollama_web as ow2
    real_fetch = ow2.web_fetch
    ow2.web_fetch = lambda url: {"title": "T", "content": "contenu-de-secours", "links": []}
    try:
        out = d.extract_content()
        check("extract_content falls back to ollama", "contenu-de-secours" in out)
    finally:
        ow2.web_fetch = real_fetch

    # When Tavily works, no fallback is used
    d2 = _Dummy(api_key="x", sleep_seconds=0)
    d2.fetch_raw = lambda: {"results": [{"raw_content": "tavily content"}]}
    ow2.web_fetch = lambda url: (_ for _ in ()).throw(AssertionError("fallback must not run"))
    try:
        check("tavily content wins, no fallback", d2.extract_content() == "tavily content")
    finally:
        ow2.web_fetch = real_fetch

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for Ollama thinking mode (provider_ollama reasoning kwarg) and the
Ollama Cloud web_search/web_fetch fallback channel (app/utils/ollama_web.py,
BaseScraper.extract_content fallback).

Run: .venv/bin/python tests/test_ollama_features.py
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
    from app.models.provider_ollama import _parse_reasoning

    check("reasoning empty -> None", _parse_reasoning("") is None and _parse_reasoning("off") is None)
    check("reasoning levels", all(_parse_reasoning(v) == v for v in ("low", "medium", "high")))
    check("reasoning bools", _parse_reasoning("true") is True and _parse_reasoning("false") is False)
    check("reasoning bogus -> None", _parse_reasoning("ultra") is None)

    # Provider wires reasoning into ChatOllama kwargs only when configured.
    import langchain_ollama
    from app.models import provider_ollama

    class _Recorder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    real_cls = langchain_ollama.ChatOllama
    langchain_ollama.ChatOllama = _Recorder
    saved_reasoning = getattr(config, "OLLAMA_REASONING", "")
    saved_cloud, saved_key = config.OLLAMA_CLOUD, config.OLLAMA_API_KEY
    try:
        config.OLLAMA_CLOUD = True
        config.OLLAMA_API_KEY = "k"
        config.OLLAMA_REASONING = "high"
        llm = provider_ollama.create_ollama_llm()
        check("reasoning=high wired", llm.kwargs.get("reasoning") == "high")
        check("headers in client_kwargs", llm.kwargs["client_kwargs"]["headers"]["Authorization"] == "Bearer k")
        config.OLLAMA_REASONING = ""
        llm2 = provider_ollama.create_ollama_llm()
        check("reasoning omitted when unset", "reasoning" not in llm2.kwargs)
    finally:
        langchain_ollama.ChatOllama = real_cls
        config.OLLAMA_REASONING = saved_reasoning
        config.OLLAMA_CLOUD, config.OLLAMA_API_KEY = saved_cloud, saved_key

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

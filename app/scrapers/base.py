"""Base scraper using Tavily API with configurable sleep."""
import time
import logging
from abc import ABC, abstractmethod
from typing import Any

from tavily import TavilyClient

import config

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for stock market scrapers using Tavily extract + sleep."""

    def __init__(
        self,
        api_key: str | None = None,
        sleep_seconds: float | None = None,
    ):
        self._api_key = api_key or config.TAVILY_API_KEY
        self._sleep_seconds = sleep_seconds if sleep_seconds is not None else config.SLEEP_SECONDS
        self._client: TavilyClient | None = None

    @property
    def client(self) -> TavilyClient:
        if self._client is None:
            if not self._api_key:
                raise ValueError("TAVILY_API_KEY is not set. Set it in .env or pass api_key=.")
            self._client = TavilyClient(api_key=self._api_key)
        return self._client

    @property
    def url(self) -> str:
        """Override in subclasses."""
        return ""

    def _sleep(self) -> None:
        """Apply configured delay between requests."""
        if self._sleep_seconds > 0:
            logger.debug("Sleeping %.1f s", self._sleep_seconds)
            time.sleep(self._sleep_seconds)

    def fetch_raw(self) -> dict[str, Any]:
        """Fetch page content via Tavily extract. Call _sleep before/after as needed."""
        self._sleep()
        try:
            response = self.client.extract([self.url])
            self._sleep()
            return response
        except Exception as e:
            logger.exception("Tavily extract failed for %s: %s", self.url, e)
            raise

    def extract_content(self) -> str:
        """Get raw text content: Tavily extract first; on failure/empty, fall back
        to Ollama Cloud web_fetch (e.g. sources that block Tavily). Replaces \\xa0
        (non-breaking space) with empty string for clean parsing and JSON output."""
        content = ""
        try:
            raw = self.fetch_raw()
            if not isinstance(raw, dict):
                content = str(raw).strip()
            else:
                results = raw.get("results", [])
                if isinstance(results, list) and results:
                    first = results[0]
                    if isinstance(first, dict):
                        content = (first.get("raw_content") or first.get("content") or "").strip()
        except Exception as e:
            logger.warning("Tavily extract failed for %s: %s — trying Ollama web_fetch.", self.url, e)
        if content:
            return content.replace("\xa0", "")
        from app.utils.ollama_web import web_fetch

        data = web_fetch(self.url)
        if data:
            logger.info("Ollama web_fetch fallback succeeded for %s", self.url)
            return str(data["content"]).strip().replace("\xa0", "")
        return ""

    @abstractmethod
    def scrape(self) -> dict[str, Any]:
        """Fetch and parse stock data. Return structured dict."""
        ...

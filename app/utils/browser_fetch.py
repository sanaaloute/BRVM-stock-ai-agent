"""Render-to-HTML fetching via Playwright/Chromium.

Some market-data sites block plain HTTP clients (403) but serve a real
browser. `fetch_html_browser` renders the page in headless Chromium with a
genuine user agent and returns the parsed DOM. Used as a fallback behind the
lightweight `http_get` (browser launch is ~1s — pay it only when needed).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def browser_available() -> bool:
    try:
        import playwright  # noqa: F401

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def fetch_html_browser(url: str, *, wait_selector: str | None = None, timeout_ms: int = 45000, extra_wait_ms: int = 2500) -> str | None:
    """Render `url` in headless Chromium and return the page HTML (None on failure)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed; browser fetch unavailable.")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            try:
                context = browser.new_context(
                    user_agent=_BROWSER_UA,
                    locale="fr-FR",
                    viewport={"width": 1366, "height": 900},
                    ignore_https_errors=True,
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms // 2)
                    except Exception:
                        pass  # selector may legitimately be absent
                if extra_wait_ms:
                    page.wait_for_timeout(extra_wait_ms)
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Browser fetch failed for %s: %s", url, e)
        return None

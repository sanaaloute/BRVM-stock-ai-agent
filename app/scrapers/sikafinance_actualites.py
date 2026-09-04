"""Fetch BRVM market news from Sika Finance actualités bourse BRVM page."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

ACTUALITES_URL = getattr(
    config, "SIKAFINANCE_ACTUALITES_URL", "https://www.sikafinance.com/marches/actualites_bourse_brvm"
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
BASE = "https://www.sikafinance.com"


def fetch_sikafinance_actualites(limit: int = 20) -> dict[str, Any]:
    """
    Fetch BRVM market news from Sika Finance actualités bourse BRVM.
    Returns {source, url, items: [{date, title, url, snippet}], error?}.
    """
    out: dict[str, Any] = {
        "source": "sikafinance_actualites",
        "url": ACTUALITES_URL,
        "items": [],
        "error": None,
    }

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(ACTUALITES_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning("Direct fetch failed for %s: %s — trying browser render.", ACTUALITES_URL, e)
        # The site blocks plain HTTP clients (403); fall back to a real browser.
        from app.utils.browser_fetch import fetch_html_browser

        html = fetch_html_browser(ACTUALITES_URL, wait_selector="a[href*='/marches/']")
        if not html:
            out["error"] = str(e)
            return out

    soup = BeautifulSoup(html, "html.parser")

    # Parse article links: [Title](url) followed by date (dd/mm/yyyy) and optional snippet
    seen_urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/marches/" not in href or "_" not in href:
            continue
        full_url = href if href.startswith("http") else f"{BASE}{href}" if href.startswith("/") else f"{BASE}/{href}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        title = (a.get_text() or "").strip()
        if not title or len(title) < 5:
            continue

        date_str = ""
        snippet = ""
        parent = a.parent
        if parent:
            # Look for date (dd/mm/yyyy or dd/mm/yyyy hh:mm)
            text = (parent.get_text() or "").strip()
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)", text)
            if date_match:
                date_str = date_match.group(1)
            # Snippet: text after title, before date
            parts = re.split(r"\d{1,2}/\d{1,2}/\d{4}", text, maxsplit=1)
            if len(parts) >= 2:
                snippet = (parts[0].replace(title, "").strip() or "")[:300]
            elif len(parts) == 1 and title in text:
                rest = text.replace(title, "").strip()
                if rest and not re.match(r"^\d", rest):
                    snippet = rest[:300]

        out["items"].append({"date": date_str, "title": title, "url": full_url, "snippet": snippet})
        if len(out["items"]) >= limit:
            break

    return out

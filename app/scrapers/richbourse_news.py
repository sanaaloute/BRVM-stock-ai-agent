"""Fetch company news from Rich Bourse: https://www.richbourse.com/common/news/index/{SYMBOL}."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

BASE_URL = getattr(config, "RICHBOURSE_NEWS_URL", "https://www.richbourse.com/common/news/index")
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"


def fetch_company_news(symbol: str, limit: int = 15) -> dict[str, Any]:
    """
    Fetch news for a BRVM symbol from Rich Bourse. Returns list of {date, title, url, snippet}.
    """
    symbol = (symbol or "").strip().upper()
    out: dict[str, Any] = {"source": "richbourse_news", "symbol": symbol, "url": "", "items": [], "error": None}
    if not symbol:
        out["error"] = "Le symbole est requis."
        return out

    url = f"{BASE_URL}/{symbol}"
    out["url"] = url

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        out["error"] = str(e)
        return out

    # Links to articles: common/apprendre/article/
    # Each article is linked by 3 anchors: image (no text), title, "Lire la suite...".
    # Only the title anchor carries text, so skip empty-title anchors BEFORE dedup.
    seen_urls: set[str] = set()
    date_re = re.compile(r"(\d{1,2}\s+\w+\s+\d{4}\s*-\s*\d{1,2}h:\d{2})")
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/common/apprendre/article/" not in href:
            continue
        title = (a.get_text() or "").strip()
        if not title or title == "Lire la suite...":
            continue
        full_url = href if href.startswith("http") else f"https://www.richbourse.com/{href.lstrip('/')}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        # Find date (e.g. "23 Janvier 2024 - 08h:18") anywhere in the item row/block
        date_str = ""
        row = a.find_parent("div", class_=lambda c: c == "col-xs-12")
        for root in (row, a.parent):
            if root is None:
                continue
            match = date_re.search(root.get_text(" ", strip=True))
            if match:
                date_str = match.group(1)
                break
        if not date_str and a.parent:
            prev = a.parent.find_previous_sibling()
            if prev:
                date_str = (prev.get_text() or "").strip()
        # Snippet: paragraph right after the title paragraph
        snippet = ""
        title_p = a.parent if a.parent and a.parent.name == "p" else None
        next_p = title_p.find_next_sibling("p") if title_p else None
        if next_p:
            candidate = (next_p.get_text(" ", strip=True) or "").strip()
            if candidate and "Lire la suite" not in candidate:
                snippet = candidate[:300]
        if not snippet:
            next_el = a.find_next_sibling()
            if next_el and next_el.name != "a":
                snippet = (next_el.get_text() or "").strip()[:300]
        out["items"].append({"date": date_str, "title": title, "url": full_url, "snippet": snippet})
        if len(out["items"]) >= limit:
            break

    return out

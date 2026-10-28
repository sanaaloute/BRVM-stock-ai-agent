"""Fetch BRVM market news from Sika Finance bourse page (section ACTUALITES DE LA BOURSE)."""
from __future__ import annotations

import logging
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

BOURSE_URL = getattr(config, "SIKAFINANCE_BOURSE_URL", "https://www.sikafinance.com/bourse/")
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
BASE = "https://www.sikafinance.com"


def fetch_bourse_news(limit: int = 20) -> dict[str, Any]:
    """
    Fetch 'ACTUALITES DE LA BOURSE' from Sika Finance. Returns list of {date, title, url}.
    """
    out: dict[str, Any] = {"source": "sikafinance_bourse", "url": BOURSE_URL, "items": [], "error": None}

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(BOURSE_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", BOURSE_URL, e)
        out["error"] = str(e)
        return out

    # Find section ACTUALITES DE LA BOURSE then tables with date + link
    for heading in soup.find_all(["h2", "h3", "strong"]):
        text = (heading.get_text() or "").strip()
        if "ACTUALITES" in text.upper() and "BOURSE" in text.upper():
            table = heading.find_next("table")
            if not table:
                continue
            for row in table.find_all("tr")[:limit]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                date_cell = (cells[0].get_text() or "").strip()
                link = cells[1].find("a", href=True) if cells[1] else None
                if not link:
                    continue
                href = link.get("href", "")
                title = (link.get_text() or "").strip()
                if not title:
                    continue
                full_url = href if href.startswith("http") else f"{BASE}{href}" if href.startswith("/") else f"{BASE}/{href}"
                out["items"].append({"date": date_cell, "title": title, "url": full_url})
            break

    return out

"""Fetch BRVM official communiqués (PDFs) from Sika Finance communiqués page."""
from __future__ import annotations

import logging
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

COMMUNIQUES_URL = getattr(
    config, "SIKAFINANCE_COMMUNIQUES_URL", "https://www.sikafinance.com/marches/communiques_brvm"
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
BASE = "https://www.sikafinance.com"


def fetch_sikafinance_communiques(limit: int = 20, company: str | None = None) -> dict[str, Any]:
    """
    Fetch BRVM official communiqués (PDFs) from Sika Finance.
    Returns {source, url, items: [{date, title, pdf_url, company?}], error?}.
    If company is set (symbol or name), filter to matching rows.
    """
    out: dict[str, Any] = {
        "source": "sikafinance_communiques",
        "url": COMMUNIQUES_URL,
        "items": [],
        "error": None,
    }

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(COMMUNIQUES_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", COMMUNIQUES_URL, e)
        out["error"] = str(e)
        return out

    filter_upper = (company or "").strip().upper()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = rows[0] if rows else None
        header_text = (header.get_text() or "").upper() if header else ""
        if "DATE" not in header_text or "PUBLICATION" not in header_text:
            continue
        for row in rows[1 : limit + 1]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            date_cell = (cells[0].get_text() or "").strip()
            pub_cell = cells[1]
            link = pub_cell.find("a", href=True) if pub_cell else None
            if not link:
                continue
            href = link.get("href", "")
            if ".pdf" not in href.lower():
                continue
            full_url = href if href.startswith("http") else f"{BASE}{href}" if href.startswith("/") else f"{BASE}/{href}"
            title = (link.get_text() or "").strip()
            # Extract company from title (e.g. "SONATEL : Etats financiers 2025" -> SONATEL)
            company_part = ""
            if " : " in title:
                company_part = title.split(" : ", 1)[0].strip()
            if company and filter_upper and filter_upper not in title.upper():
                continue
            out["items"].append({
                "date": date_cell,
                "title": title,
                "pdf_url": full_url,
                "company": company_part or None,
            })
        break

    return out

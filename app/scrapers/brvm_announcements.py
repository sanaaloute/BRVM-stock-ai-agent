"""Fetch BRVM official announcements (convocations AGO, etc.) with PDF links."""
from __future__ import annotations

import logging
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

ANNOUNCEMENTS_URL = getattr(
    config, "BRVM_ANNOUNCEMENTS_URL", "https://www.brvm.org/fr/emetteurs/type-annonces/convocations-assemblees-generales"
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
BRVM_BASE = "https://www.brvm.org"


def fetch_brvm_announcements(limit: int = 20, company_filter: str | None = None) -> dict[str, Any]:
    """
    Fetch BRVM convocations/AG announcements. Returns list of {date, company, title, pdf_url}.
    If company_filter (e.g. symbol or company name) is set, only include matching rows.
    """
    out: dict[str, Any] = {
        "source": "brvm_announcements",
        "url": ANNOUNCEMENTS_URL,
        "items": [],
        "error": None,
    }

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(ANNOUNCEMENTS_URL, timeout=30, headers={"User-Agent": USER_AGENT}, verify=config.BRVM_VERIFY_SSL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", ANNOUNCEMENTS_URL, e)
        out["error"] = str(e)
        return out

    filter_upper = (company_filter or "").strip().upper()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = rows[0] if rows else None
        header_text = (header.get_text() or "").upper() if header else ""
        if "DATE" not in header_text or "SOCIÉTÉ" not in header_text and "SOCIETE" not in header_text:
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            date_cell = (cells[0].get_text() or "").strip()
            company_cell = (cells[1].get_text() or "").strip()
            title_cell = (cells[2].get_text() or "").strip()
            if company_filter and filter_upper not in company_cell.upper():
                continue
            pdf_url = ""
            # The download link lives in its own cell (views-field-field-fichier-annonce)
            # on the current site, so scan the whole row, not just the title cell.
            for a in row.find_all("a", href=True):
                href = a.get("href", "")
                if ".pdf" in href.lower() or "sites/default/files" in href:
                    pdf_url = href if href.startswith("http") else f"{BRVM_BASE}{href}" if href.startswith("/") else f"{BRVM_BASE}/{href}"
                    break
            out["items"].append({
                "date": date_cell,
                "company": company_cell,
                "title": title_cell,
                "pdf_url": pdf_url,
            })
        break

    # Limit applied after the company filter, not before
    out["items"] = out["items"][:limit]
    return out

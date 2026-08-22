"""Fetch announced dividends from Rich Bourse dividende page."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

DIVIDENDE_URL = getattr(
    config, "RICHBOURSE_DIVIDENDE_URL", "https://www.richbourse.com/common/dividende/index"
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
BASE = "https://www.richbourse.com"


def fetch_richbourse_dividends(limit: int = 50, symbol: str | None = None) -> dict[str, Any]:
    """
    Fetch announced dividends from Rich Bourse.
    Returns {source, url, date_page, items: [{company, symbol, dividende, rendement, ex_dividende, date_paiement}], error?}.
    If symbol is set, filter to that company.
    """
    out: dict[str, Any] = {
        "source": "richbourse_dividends",
        "url": DIVIDENDE_URL,
        "date_page": "",
        "items": [],
        "error": None,
    }

    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(DIVIDENDE_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", DIVIDENDE_URL, e)
        out["error"] = str(e)
        return out

    # Page date (e.g. "Vendredi 27 Février 2026")
    months_re = re.compile(
        r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre",
        re.IGNORECASE,
    )
    for p in soup.find_all(["p", "div"]):
        text = (p.get_text() or "").strip()
        if months_re.search(text):
            if re.search(r"\d{4}", text):
                out["date_page"] = text
                break

    filter_upper = (symbol or "").strip().upper()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = rows[0] if rows else None
        header_text = (header.get_text() or "").upper() if header else ""
        if "SOCIÉTÉ" not in header_text and "SOCIETE" not in header_text:
            continue
        if "DIVIDENDE" not in header_text:
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            # Table: # | Société | Dividende | Rendement | Ex-dividende | Date paiement
            if len(cells) < 4:
                continue
            # Col 0 may be #; col 1 is Société (with link)
            company_cell = cells[1] if len(cells) > 1 else cells[0]
            company_link = company_cell.find("a", href=True) if company_cell else None
            company_name = (company_link.get_text() or "").strip() if company_link else (company_cell.get_text() or "").strip()
            sym = ""
            if company_link:
                href = company_link.get("href", "")
                if "/mouvements/index/" in href:
                    sym = href.split("/mouvements/index/")[-1].split("/")[0].split("?")[0].upper()
            dividende = (cells[2].get_text() or "").strip() if len(cells) > 2 else ""
            rendement = (cells[3].get_text() or "").strip() if len(cells) > 3 else ""
            ex_div = (cells[4].get_text() or "").strip() if len(cells) > 4 else ""
            date_paiement = (cells[5].get_text() or "").strip() if len(cells) > 5 else ""
            if symbol and filter_upper and filter_upper not in (company_name.upper() + sym):
                continue
            out["items"].append({
                "company": company_name,
                "symbol": sym or None,
                "dividende": dividende,
                "rendement": rendement,
                "ex_dividende": ex_div,
                "date_paiement": date_paiement,
            })
        break

    # Limit applied after the symbol filter, not before
    out["items"] = out["items"][:limit]
    return out

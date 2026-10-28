"""Fetch BRVM stock trends/predictions table from Rich Bourse prévision boursière index.

URLs:
- All stocks: https://www.richbourse.com/common/prevision-boursiere/index
- By trend:   https://www.richbourse.com/common/prevision-boursiere/index/0/hausse
              (options: hausse, baisse, neutre)
- Detail:    https://www.richbourse.com/common/prevision-boursiere/synthese/{SYMBOL}
"""
from __future__ import annotations

import logging
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

INDEX_BASE = getattr(
    config,
    "RICHBOURSE_TRENDS_INDEX_URL",
    "https://www.richbourse.com/common/prevision-boursiere/index",
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"

TREND_OPTIONS = ("hausse", "baisse", "neutre")


def _symbol_from_synthese_href(href: str) -> str | None:
    """Extract symbol from .../synthese/SYMBOL or .../synthese/SYMBOL."""
    if not href or "/synthese/" not in href:
        return None
    parts = href.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p == "synthese" and i + 1 < len(parts):
            return (parts[i + 1] or "").strip().upper()
    return None


def fetch_richbourse_trends_index(
    trend_option: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch the prévision boursière table from Rich Bourse (all stocks or filtered by trend).

    trend_option: None = all stocks; "hausse" | "baisse" | "neutre" = filter by trend.
    Returns {source, url, date_page, trend_filter, items: [{symbol, company_name, trend, confidence_pct, detail_url}], error?}.
    """
    out: dict[str, Any] = {
        "source": "richbourse_trends",
        "url": "",
        "date_page": "",
        "trend_filter": trend_option,
        "items": [],
        "error": None,
    }
    option = (trend_option or "").strip().lower()
    if option and option not in TREND_OPTIONS:
        out["error"] = f"trend_option doit être l'un de : {', '.join(TREND_OPTIONS)}"
        return out

    # URL: index or index/0/hausse (page 0, then trend)
    if option:
        url = f"{INDEX_BASE}/0/{option}"
    else:
        url = INDEX_BASE
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

    # Page date: "Prévisions boursières du Vendredi 27 Février 2026"
    for h1 in soup.find_all("h1"):
        text = (h1.get_text() or "").strip()
        if "Prévisions" in text or "prévisions" in text:
            out["date_page"] = text
            break

    # Table: Action | Tendance | Indice de confiance | (optional link column)
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = rows[0] if rows else None
        header_text = (header.get_text() or "").upper() if header else ""
        if "TENDANCE" not in header_text or "ACTION" not in header_text:
            continue
        for row in rows[1 : limit + 1]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            company_name = ""
            symbol = None
            detail_url = ""
            # First cell: link to synthese/SYMBOL
            first = cells[0]
            a = first.find("a", href=True)
            if a:
                href = a.get("href", "")
                symbol = _symbol_from_synthese_href(href)
                company_name = (a.get_text() or "").strip()
                if href and not href.startswith("http"):
                    detail_url = f"https://www.richbourse.com{href}" if href.startswith("/") else f"https://www.richbourse.com/{href}"
                else:
                    detail_url = href or ""
            if not company_name:
                company_name = (first.get_text() or "").strip()
            # Second cell: trend (Hausse / Baisse / Neutre)
            trend = (cells[1].get_text() or "").strip() if len(cells) > 1 else ""
            # Third: confidence (e.g. 71.43%)
            confidence_pct = ""
            if len(cells) > 2:
                raw = (cells[2].get_text() or "").strip()
                if "%" in raw:
                    confidence_pct = raw
            out["items"].append({
                "symbol": symbol or "",
                "company_name": company_name,
                "trend": trend,
                "confidence_pct": confidence_pct,
                "detail_url": detail_url,
            })
        break

    return out

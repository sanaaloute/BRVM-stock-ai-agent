"""Fetch stock prediction/technical analysis from Rich Bourse prévision boursière."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

PREDICTION_BASE = getattr(
    config, "RICHBOURSE_PREDICTION_URL", "https://www.richbourse.com/common/prevision-boursiere/synthese"
)
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"


def fetch_richbourse_prediction(symbol: str) -> dict[str, Any]:
    """
    Fetch technical prediction for a BRVM symbol from Rich Bourse.
    URL format: .../synthese/{SYMBOL} (e.g. SOGC, NTLC, ORAC).
    Returns {source, url, symbol, company_name, technical_config: [...], trend, confidence, error?}.
    """
    symbol = (symbol or "").strip().upper()
    out: dict[str, Any] = {
        "source": "richbourse_prediction",
        "url": "",
        "symbol": symbol,
        "company_name": "",
        "technical_config": [],
        "trend": "",
        "confidence": "",
        "error": None,
    }
    if not symbol:
        out["error"] = "Le symbole est requis."
        return out

    url = f"{PREDICTION_BASE}/{symbol}"
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

    # Extract company name from h1 (e.g. "SOGB COTE D'IVOIRE : Prévisions du 27/02/2026")
    h1 = soup.find("h1")
    if h1:
        raw = (h1.get_text() or "").strip()
        if " : " in raw:
            out["company_name"] = raw.split(" : ", 1)[0].strip()

    # Technical config: links like "Les cours évoluent au-dessus de leur moyenne mobile..."
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/ratio-techniques/" not in href or symbol.upper() not in href.upper():
            continue
        text = (a.get_text() or "").strip()
        if text and len(text) > 10:
            out["technical_config"].append(text)

    # Trend: "Tendance à court terme : Hausse, avec un indice de confiance de 71.43%"
    body = soup.get_text() or ""
    trend_match = re.search(
        r"Tendance\s+à\s+court\s+terme\s*:\s*([^,]+)(?:,\s*avec\s+un\s+indice\s+de\s+confiance\s+de\s+([\d,]+)\s*%)?",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if trend_match:
        out["trend"] = trend_match.group(1).strip()
        if trend_match.lastindex >= 2 and trend_match.group(2):
            out["confidence"] = f"{trend_match.group(2)}%"

    return out

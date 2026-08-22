"""Scraper for richbourse.com - BRVM variation/palmarès table.

Target URL: https://www.richbourse.com/common/variation/index
Page: "Palmarès des actions (Variation des cours de clôture)"
Table: class="table table-striped table-bordered t"
Form: div.variation-search contains period and progression filters.

URL pattern: {base}/{period}/{progression}
Example: https://www.richbourse.com/common/variation/index/veille/hausse
"""
import re
import logging
from typing import Any

from bs4 import BeautifulSoup

from app.utils.http_client import http_get
from .base import BaseScraper
import config

logger = logging.getLogger(__name__)

RICHBOURSE_BASE_URL = "https://www.richbourse.com/common/variation/index"

# Period options: CLI key → <option value> from the form
RICHBOURSE_PERIODS = {
    "veille": "veille",
    "1_semaine": "1semaine",
    "2_semaines": "2semaine",
    "1_mois": "1mois",
    "2_mois": "2mois",
    "3_mois": "3mois",
    "6_mois": "6mois",
    "1er_janvier": "janvier",
    "1_an": "1an",
    "2_ans": "2an",
    "3_ans": "3an",
    "4_ans": "4an",
    "5_ans": "5an",
}

# Progression options (path segment)
RICHBOURSE_PROGRESSIONS = {
    "tout": "tout",
    "hausse": "hausse",
    "baisse": "baisse",
    "constante": "constante",
    "hausse_baisse": "hausse_baisse",
}


def _normalize_num(s: str) -> str:
    """Remove spaces and return digits/decimals only for parsing."""
    return re.sub(r"\s", "", str(s).strip()) if s else ""


def _parse_int(s: str) -> int | None:
    n = _normalize_num(s)
    return int(n) if n.isdigit() else None


def _parse_float(s: str) -> float | None:
    s = (s or "").replace(",", ".").replace("%", "").strip()
    s = _normalize_num(s) if s else ""
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_markdown_table_line(line: str) -> dict[str, Any] | None:
    """Parse markdown table row: | SLBC | SOLIBRA | 7.49% | 217 | 7 712 180 | 35 540 | 33 065 | ... |"""
    line = (line or "").replace("\xa0", "").strip()
    if not line.startswith("|") or line.count("|") < 7:
        return None
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) < 6:
        return None
    sym = (cells[0] or "").strip()
    if len(sym) not in (4, 5) or not sym.isalpha():
        return None
    try:
        return {
            "symbol": sym,
            "name": (cells[1] or "").strip(),
            "variation_pct": _parse_float(cells[2]),
            "volume": _parse_int(cells[3]),
            "value_fcfa": _parse_int(cells[4]),
            "cours_actuel": _parse_int(cells[5]),
            "cours_veille": _parse_int(cells[6]) if len(cells) > 6 else None,
            "capitalisation": _parse_int(cells[7]) if len(cells) > 7 else None,
        }
    except (ValueError, TypeError):
        return None


class RichBourseScraper(BaseScraper):
    """Fetch stock variation table from Rich Bourse (palmarès des actions)."""

    def __init__(
        self,
        period: str = "veille",
        progression: str = "tout",
        api_key: str | None = None,
        sleep_seconds: float | None = None,
    ):
        super().__init__(api_key=api_key, sleep_seconds=sleep_seconds)
        self._period_key = period if period in RICHBOURSE_PERIODS else "veille"
        self._progression_key = progression if progression in RICHBOURSE_PROGRESSIONS else "tout"

    @property
    def url(self) -> str:
        period_val = RICHBOURSE_PERIODS[self._period_key]
        prog_val = RICHBOURSE_PROGRESSIONS[self._progression_key]
        return f"{RICHBOURSE_BASE_URL}/{period_val}/{prog_val}"

    def scrape(self) -> dict[str, Any]:
        """Fetch and parse the variation (palmarès) table from Rich Bourse."""
        out: dict[str, Any] = {
            "source": "richbourse",
            "url": self.url,
            "period": self._period_key,
            "progression": self._progression_key,
            "date": None,
            "hausses": None,
            "baisses": None,
            "stocks": [],
        }

        # Fetch raw HTML via httpx + certifi (Tavily markdown breaks table structure)
        try:
            self._sleep()
            resp = http_get(
                self.url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"},
            )
            resp.raise_for_status()
            self._sleep()
            content = resp.text.replace("\xa0", "")
        except Exception as e:
            logger.warning("Direct fetch failed: %s. Falling back to Tavily.", e)
            content = self.extract_content().replace("\xa0", "")

        if not content:
            return out

        soup = BeautifulSoup(content, "html.parser")
        text = soup.get_text(separator="\n")
        # --- Date: "Vendredi 20 Février 2026" ---
        date_match = re.search(
            r"(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche)\s+\d+\s+"
            r"(Janvier|Février|Mars|Avril|Mai|Juin|Juillet|Août|Septembre|Octobre|Novembre|Décembre)\s+\d{4}",
            text,
            re.IGNORECASE,
        )
        if date_match:
            out["date"] = date_match.group(0)

        # --- Summary line: "30 hausse(s) 13 baisse(s)" ---
        hausse_baisse = re.search(r"(\d+)\s+hausse?s?\s*\(\s*s\s*\)\s*(\d+)\s+baisse?s?\s*\(\s*s\s*\)", text, re.IGNORECASE)
        if hausse_baisse:
            out["hausses"] = int(hausse_baisse.group(1))
            out["baisses"] = int(hausse_baisse.group(2))

        # --- Table: class="table table-striped table-bordered t" ---
        tables = soup.select("table.table-striped.table-bordered") or soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for tr in rows:
                cells = tr.find_all(["td", "th"])
                if len(cells) < 5:
                    continue
                texts = [c.get_text(strip=True) for c in cells]
                joined = " ".join(texts)

                # Skip header row (contains "Symbole" or "Variation")
                if re.search(r"symbole|variation|volume|valeur\s*\(?\s*fcfa", joined, re.IGNORECASE):
                    continue

                # Skip TOTAL row
                if "TOTAL" == (texts[1] if len(texts) > 1 else "").strip():
                    continue

                # Data row: symbol (4–5 letters), name, variation %, volume, value_fcfa, cours_actuel, cours_veille, capitalisation
                sym = (texts[0] or "").strip()
                if len(sym) not in (4, 5) or not sym.isalpha():
                    continue
                name = (texts[1] or "").strip()
                var_str = texts[2] if len(texts) > 2 else ""
                vol_str = texts[3] if len(texts) > 3 else ""
                value_str = texts[4] if len(texts) > 4 else ""
                cours_str = texts[5] if len(texts) > 5 else ""
                prev_str = texts[6] if len(texts) > 6 else ""
                cap_str = texts[7] if len(texts) > 7 else ""

                try:
                    out["stocks"].append({
                        "symbol": sym,
                        "name": name,
                        "variation_pct": _parse_float(var_str),
                        "volume": _parse_int(vol_str),
                        "value_fcfa": _parse_int(value_str),
                        "cours_actuel": _parse_int(cours_str),
                        "cours_veille": _parse_int(prev_str),
                        "capitalisation": _parse_int(cap_str),
                    })
                except (ValueError, TypeError):
                    logger.debug("Skip row: %s", texts[:8])

        # Fallback 1: parse from text blocks (soup.get_text gives rows as 8 newline-separated values)
        if not out["stocks"]:
            blocks = re.split(r"\n\s*\n+", text)
            for block in blocks:
                lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
                if len(lines) < 4:
                    continue
                if lines[0] == "TOTAL":
                    continue
                if len(lines) < 8:
                    continue
                sym = (lines[0] or "").strip()
                if len(sym) not in (4, 5) or not sym.isalpha():
                    continue
                if "%" not in (lines[2] or ""):
                    continue
                try:
                    out["stocks"].append({
                        "symbol": sym,
                        "name": (lines[1] or "").strip(),
                        "variation_pct": _parse_float(lines[2]),
                        "volume": _parse_int(lines[3]),
                        "value_fcfa": _parse_int(lines[4]),
                        "cours_actuel": _parse_int(lines[5]),
                        "cours_veille": _parse_int(lines[6]),
                        "capitalisation": _parse_int(lines[7]),
                    })
                except (ValueError, IndexError, TypeError):
                    pass

        # Fallback 2: parse markdown table lines | SLBC | SOLIBRA | 7.49% | ... |
        if not out["stocks"]:
            for line in content.splitlines():
                row = _parse_markdown_table_line(line)
                if row:
                    out["stocks"].append(row)

        # Dedupe by symbol (keep first) — the page can render multiple matching tables
        seen_sym: set[str] = set()
        unique_stocks = []
        for x in out["stocks"]:
            if x["symbol"] not in seen_sym:
                seen_sym.add(x["symbol"])
                unique_stocks.append(x)
        out["stocks"] = unique_stocks

        return out

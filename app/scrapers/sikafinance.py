"""Scraper for sikafinance.com - BRVM palmarès table.

Target URL: https://www.sikafinance.com/marches/palmares
Page: "Palmarès des bourses africaines" – extract BRVM data from the table.
Table columns: Nom | Haut | Bas | Dernier | Volume | Variation jour | Variation

When period != veille, the period switch is client-side (JavaScript). We use Playwright to render
the page with the period selected so the Variation period column is populated.
"""
import re
import logging
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import BaseScraper
import config

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)

SIKAFINANCE_PALMARES_URL = "https://www.sikafinance.com/marches/palmares"

# Period options: map CLI keys to <select id="dlSince"> option values
SIKAFINANCE_PERIODS = {
    "veille": "yesterday",
    "1er_janvier": "varJanuary",
    "une_semaine": "varWeek",
    "un_mois": "varMonth",
    "trois_mois": "var3M",
    "six_mois": "var6M",
    "un_an": "varYear",
}


def _normalize_num(s: str) -> str:
    """Remove spaces and \\xa0 (French thousands separator / non-breaking space)."""
    if not s:
        return ""
    s = str(s).replace("\xa0", "").strip()
    return re.sub(r"\s", "", s)


def _parse_int(s: str) -> int | None:
    n = _normalize_num(s)
    if not n:
        return None
    # Allow decimals like "34,00" -> 34
    if "," in n or "." in n:
        try:
            return int(float(n.replace(",", ".")))
        except ValueError:
            return None
    return int(n) if n.isdigit() else None


def _parse_float(s: str) -> float | None:
    s = (s or "").replace(",", ".").replace("%", "").strip()
    s = _normalize_num(s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _symbol_from_href(href: str | None) -> str | None:
    """Extract ticker from link by splitting. E.g. .../cotation_SICC.ci -> SICC."""
    if not href:
        return None
    href = href.replace("\xa0", "").strip()
    # Split by "/" to get path segments (works for full URL and relative path)
    parts = [p for p in href.split("/") if p]
    for seg in reversed(parts):
        seg_normalized = seg.replace("%5f", "_").replace("%5F", "_")
        if "cotation_" in seg_normalized.lower():
            # Segment is "cotation_SICC.ci" -> split by "_", take part after
            after_underscore = seg_normalized.split("_", 1)[1]
            if "." in after_underscore:
                return after_underscore.split(".", 1)[0].upper()
            return after_underscore.upper() if after_underscore else None
    return None


def _parse_first_cell(cell: str) -> tuple[str, str | None]:
    """Extract name and symbol from first cell. Handles:
    - [Name](cotation_SYM.ci)
    - [Name](https://www.sikafinance.com/marches/cotation_SYM.ci)
    - [Name](relative/cotation_SYM.ci)
    Returns (name, symbol)."""
    cell = cell.replace("\xa0", "").strip()
    # Markdown link: [Name](url_or_path)
    m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", cell)
    if m:
        name = m.group(1).strip()
        href = m.group(2).strip()
        symbol = _symbol_from_href(href)
        return (name, symbol)
    # Plain text (no link)
    return (cell, None)


def _parse_markdown_table_line(line: str) -> dict[str, Any] | None:
    """Parse a markdown table row: | [Name](url) | haut | bas | dernier | volume | var_jour% | var_period% |."""
    line = line.replace("\xa0", "").strip()
    if not line.startswith("|") or line.count("|") < 7:
        return None
    cells = [c.strip() for c in line.split("|")[1:-1]]  # drop empty first/last
    if len(cells) < 7:
        return None
    # First cell: [Name](cotation_SYM.ci) or [Name](https://.../cotation_SYM.ci)
    name, symbol = _parse_first_cell(cells[0])
    haut = _parse_int(cells[1])
    bas = _parse_int(cells[2])
    # Dernier may be **35 540** (bold in markdown)
    dernier_str = re.sub(r"\*+", "", cells[3]).strip()
    dernier = _parse_int(dernier_str)
    volume = _parse_int(cells[4])
    var_jour = _parse_float(cells[5])
    var_period = _parse_float(cells[6])
    if not name or (dernier is None and haut is None):
        return None
    return {
        "name": name,
        "symbol": symbol,
        "haut": haut,
        "bas": bas,
        "dernier": dernier,
        "volume": volume,
        "variation_jour_pct": var_jour,
        "variation_period_pct": var_period,
    }


class SikaFinanceScraper(BaseScraper):
    """Fetch BRVM palmarès table from Sika Finance (marches/palmares)."""

    def __init__(
        self,
        period: str = "veille",
        api_key: str | None = None,
        sleep_seconds: float | None = None,
    ):
        super().__init__(api_key=api_key, sleep_seconds=sleep_seconds)
        self._period_key = period if period in SIKAFINANCE_PERIODS else "veille"
        self._period_value = SIKAFINANCE_PERIODS[self._period_key]

    @property
    def url(self) -> str:
        # <select id="dlSince" name="dlSince"> uses these option values
        params = {"dlSince": self._period_value}
        return f"{SIKAFINANCE_PALMARES_URL}?{urlencode(params)}"

    def _fetch_html_with_period(self) -> str | None:
        """Use Playwright to render page with period selected (JS switches columns)."""
        if not HAS_PLAYWRIGHT:
            logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return None
        browser = None
        try:
            self._sleep()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                # networkidle tends to hit the 30s timeout on ad-heavy pages
                page.goto(SIKAFINANCE_PALMARES_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("table", timeout=15000)
                page.select_option("#dlSince", self._period_value)
                submit = page.locator('button[type="submit"]').first
                if submit.count() > 0:
                    submit.click()
                page.wait_for_timeout(3000)
                html = page.content()
            self._sleep()
            return html
        except Exception as e:
            logger.warning("Playwright fetch failed: %s", e)
            return None
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    def scrape(self) -> dict[str, Any]:
        """Fetch and parse the BRVM palmarès table from Sika Finance."""
        out: dict[str, Any] = {
            "source": "sikafinance",
            "url": self.url,
            "period": self._period_key,
            "brvm_stocks": [],
        }

        use_html_for_period = self._period_key != "veille"

        # When period != veille: period switch is JavaScript. Use Playwright to select period and get rendered HTML.
        if use_html_for_period:
            content = self._fetch_html_with_period()
            if not content:
                logger.warning("Playwright/requests fetch failed for period != veille. Falling back to Tavily.")
                content = self.extract_content().replace("\xa0", "")
                use_html_for_period = False
                # Tavily returns the latest session (veille) table regardless of dlSince:
                # stamp the actual period instead of the requested one.
                out["period"] = "veille"
                out["warning"] = (
                    f"Période '{self._period_key}' indisponible (Playwright a échoué) : "
                    "données de la dernière séance (veille)."
                )
            else:
                content = content.replace("\xa0", "")
        else:
            content = self.extract_content().replace("\xa0", "")

        if not content:
            return out

        soup = BeautifulSoup(content, "html.parser")

        # Parse markdown table only when period == veille (Tavily markdown)
        if not use_html_for_period:
            for line in content.splitlines():
                row = _parse_markdown_table_line(line)
                if row:
                    out["brvm_stocks"].append(row)

        # HTML tables: required when period != veille (raw HTML), fallback when veille
        tables = soup.find_all("table")

        # Table: Nom | Haut | Bas | Dernier | Volume | Variation jour | Variation
        # When period != veille, Variation (period) appears in <td style="display:block" class="quote_down2">-6,89%</td>
        for table in tables:
            rows = table.find_all("tr")
            for tr in rows:
                cells = tr.find_all(["td", "th"])
                if len(cells) < 6:
                    continue
                texts = [c.get_text(strip=True) for c in cells]
                joined = " ".join(texts).upper()

                # Skip header row
                if "NOM" in joined and ("HAUT" in joined or "DERNIER" in joined) and "VARIATION" in joined:
                    continue

                # First cell: name often inside a link; link gives symbol
                first_cell = cells[0] if cells else None
                name = texts[0] if texts else ""
                symbol: str | None = None
                href: str | None = None
                if first_cell:
                    a = first_cell.find("a", href=True)
                    if a:
                        href = a.get("href", "")
                        name = a.get_text(strip=True) or name
                        symbol = _symbol_from_href(href)

                # Columns: Nom(0) | Haut(1) | Bas(2) | Dernier(3) | Volume(4) | Variation jour | Variation period
                haut = texts[1] if len(texts) > 1 else ""
                bas = texts[2] if len(texts) > 2 else ""
                dernier = texts[3] if len(texts) > 3 else ""
                volume = texts[4] if len(texts) > 4 else ""

                # Collect td values that contain "%" AND are visible (not display:none)
                # Hidden cells have 0,00%; visible ones have the real variation
                values_with_pct: list[str] = []
                for cell in cells:
                    if cell.name != "td":
                        continue
                    style = (cell.get("style") or "").lower()
                    if "display:none" in style:
                        continue
                    t = cell.get_text(strip=True)
                    if t and "%" in t:
                        values_with_pct.append(t)
                var_jour = values_with_pct[0] if values_with_pct else ""
                var_period_raw = values_with_pct[-1] if values_with_pct else ""

                # Skip if no numeric content in Dernier (header or empty)
                dernier_clean = _normalize_num(dernier).replace(",", ".")
                if not dernier_clean or not (dernier_clean.replace(".", "").isdigit() or dernier_clean.replace(",", "").replace(".", "").isdigit()):
                    continue

                try:
                    row = {
                        "name": name,
                        "symbol": symbol,
                        "haut": _parse_int(haut),
                        "bas": _parse_int(bas),
                        "dernier": _parse_int(dernier),
                        "volume": _parse_int(volume),
                        "variation_jour_pct": _parse_float(var_jour),
                        "variation_period_pct": _parse_float(var_period_raw),
                    }
                    # Only include if we have at least name and one price
                    if row["name"] and (row["dernier"] is not None or row["haut"] is not None):
                        out["brvm_stocks"].append(row)
                except (ValueError, TypeError):
                    logger.debug("Skip row: %s", texts[:7])

        # Fallback: parse from raw text lines if no markdown/HTML table (e.g. "SOLIBRA CI 35 540 ...")
        if not out["brvm_stocks"]:
            text = soup.get_text(separator="\n")
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            # Pattern: name, haut, bas, dernier, volume, var_jour%, var_period%
            seen_names: set[str] = set()
            for line in lines:
                # Match lines ending with two percentages
                m = re.match(
                    r"(.+?)\s+([\d\s]+)\s+([\d\s]+)\s+([\d\s]+)\s+([\d\s]+)\s+([-+]?\d+[,.]?\d*)\s*%\s+([-+]?\d+[,.]?\d*)\s*%",
                    line,
                )
                if m:
                    name = m.group(1).strip()
                    dernier = _parse_int(m.group(4))
                    # Dedupe by name: the site can render multiple matching tables
                    if name and name not in seen_names and dernier is not None:
                        seen_names.add(name)
                        out["brvm_stocks"].append({
                            "name": name,
                            "symbol": None,
                            "haut": _parse_int(m.group(2)),
                            "bas": _parse_int(m.group(3)),
                            "dernier": dernier,
                            "volume": _parse_int(m.group(5)),
                            "variation_jour_pct": _parse_float(m.group(6)),
                            "variation_period_pct": _parse_float(m.group(7)),
                        })

        return out

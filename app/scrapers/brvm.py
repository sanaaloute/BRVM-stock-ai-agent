"""Scraper for brvm.org - BRVM official site."""
import re
import logging
from typing import Any

from bs4 import BeautifulSoup

from .base import BaseScraper
import config

logger = logging.getLogger(__name__)


class BRVMScraper(BaseScraper):
    """Fetch market data from the official BRVM website."""

    @property
    def url(self) -> str:
        return config.BRVM_URL

    def scrape(self) -> dict[str, Any]:
        """Fetch and parse BRVM homepage for indices and listings."""
        content = self.extract_content()
        out: dict[str, Any] = {
            "source": "brvm",
            "url": self.url,
            "indices": [],
            "stocks": [],
        }
        if not content:
            return out

        soup = BeautifulSoup(content, "html.parser")
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Indices: common patterns "BRVM 10 450.25 1.2%" or "Composite 402.38 2.05%"
        index_pattern = re.compile(
            r"([A-Za-z0-9\s\-]+?)\s+([\d\s,.]+\d)\s+([-+]?\d+[,.]?\d*)\s*%"
        )
        for line in lines:
            m = index_pattern.search(line)
            if m and any(x in line.upper() for x in ("BRVM", "COMPOSITE", "INDICE", "INDEX")):
                name = m.group(1).strip()
                value_str = m.group(2).replace(" ", "").replace(",", ".")
                pct = m.group(3).replace(",", ".")
                try:
                    out["indices"].append({
                        "name": name,
                        "value": float(value_str),
                        "variation_pct": float(pct),
                    })
                except ValueError:
                    pass

        # Stock rows: symbol + numeric columns (price, volume, variation)
        sym_price_pct = re.compile(r"([A-Z]{2,5})\s+(\d[\d\s]*)\s+([-+]?\d+[,.]?\d*)\s*%")
        for line in lines:
            m = sym_price_pct.search(line)
            if m:
                sym, price_str, pct_str = m.group(1), m.group(2).replace(" ", ""), m.group(3).replace(",", ".")
                try:
                    out["stocks"].append({
                        "symbol": sym,
                        "price": int(price_str),
                        "variation_pct": float(pct_str),
                    })
                except ValueError:
                    pass

        # Dedupe by symbol (keep first)
        seen_sym: set[str] = set()
        unique_stocks = []
        for x in out["stocks"]:
            if x["symbol"] not in seen_sym:
                seen_sym.add(x["symbol"])
                unique_stocks.append(x)
        out["stocks"] = unique_stocks
        out["indices"] = out["indices"][:20]

        return out

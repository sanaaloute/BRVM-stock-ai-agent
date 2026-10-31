"""Scraper worker: Sika Finance, Rich Bourse, BRVM."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_agent_llm
from app.agents.utils import get_time_prefix
from app.tools.stock_tools import (
    scrape_brvm,
    scrape_richbourse,
    scrape_richbourse_timeseries,
    scrape_sikafinance,
)


def get_scraper_agent_system() -> str:
    return f"""BRVM scraper. Fetch raw data only. Do not compute. {get_time_prefix()} F CFA.

**Tools:** scrape_sikafinance (palmarès) | scrape_richbourse (variation) | scrape_richbourse_timeseries (symbol, dates) | scrape_brvm (official site)

**Rule:** Call matching tool. Report results. No file paths in reply."""


SCRAPER_TOOLS = [
    scrape_sikafinance,
    scrape_richbourse,
    scrape_richbourse_timeseries,
    scrape_brvm,
]


def create_scraper_agent(model: str | None = None):
    llm = get_agent_llm("scraper", model=model)
    return create_react_agent(llm, SCRAPER_TOOLS)

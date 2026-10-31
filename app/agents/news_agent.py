"""News worker: fetch BRVM news from Rich Bourse, Sika Finance, BRVM."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_agent_llm
from app.tools.news_tools import (
    get_richbourse_dividends_tool,
    get_richbourse_prediction_tool,
    get_sikafinance_actualites_tool,
    get_sikafinance_communiques_tool,
)
from app.tools.stock_tools import (
    get_brvm_announcements_tool,
    get_company_info_tool,
    get_company_news_tool,
    get_market_news_tool,
)

NEWS_TOOLS = [
    get_company_news_tool,
    get_market_news_tool,
    get_brvm_announcements_tool,
    get_company_info_tool,
    get_sikafinance_actualites_tool,
    get_sikafinance_communiques_tool,
    get_richbourse_prediction_tool,
    get_richbourse_dividends_tool,
]

def get_news_agent_system() -> str:
    from app.agents.utils import get_time_prefix
    return f"""BRVM news. Answer from tools only. {get_time_prefix()} F CFA.

**CRITICAL:** Use the symbol from NLU entities when fetching company news. Do NOT use symbols from previous messages.

**Tools:** get_company_news | get_market_news | get_brvm_announcements | get_sikafinance_actualites | get_sikafinance_communiques | get_richbourse_prediction | get_richbourse_dividends | get_company_info (name/sector)

**Rule:** Call tools first. Use get_company_info for names. List: date, title, link. Empty → say "No news found". No tool names in reply."""


def create_news_agent(model: str | None = None):
    llm = get_agent_llm("news", model=model)
    return create_react_agent(llm, NEWS_TOOLS)

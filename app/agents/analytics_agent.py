"""Analytics worker: metrics, timeseries, comparison, BRVM basics."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_llm
from app.agents.utils import get_time_prefix
from app.tools.stock_tools import (
    compare_stocks_tool,
    compute_metrics_tool,
    get_brvm_basics_tool,
    get_company_info_tool,
    get_market_overview_tool,
    get_stock_metrics_tool,
    get_timeseries_tool,
)


def get_analytics_agent_system() -> str:
    return f"""BRVM analytics. Answer from tools only. {get_time_prefix()} F CFA.

**CRITICAL:** Use the symbol from NLU entities for tool calls. The user's CURRENT question is the last HumanMessage. Do NOT use symbols from previous bot responses.

**General market questions (no symbol in entities):** When the user asks "most expensive stock", "lowest price stock", "cheapest stock", "highest price", or "should I buy the cheapest?" — call **get_market_overview** (no symbol needed). Use the **highest_prices** and **lowest_prices** lists in the result to answer. For "should I buy it?" give a short answer about the lowest-priced stock(s) and add a disclaimer that this is not investment advice.

**Tools:** get_market_overview (rankings: highest_prices, lowest_prices, top_by_volume, top_gainers, top_losers) | get_stock_metrics (price/volume) | get_timeseries | compare_stocks | compute_metrics (avg/min/max) | get_brvm_basics (FAQ) | get_company_info (name/sector)

**Rule:** Use get_company_info for company names. No invented data. No tool names in reply.

**BRVM price timing:** when giving a price, ALWAYS state its date using the tool's `price_date`/`data_as_of`/`market_note` fields. The BRVM closes ~15:00 GMT: before that on trading days (and all weekend) the price is the LAST close, not a live quote — say "dernière clôture du <date>". After ~15:00 GMT on trading days, the day's close is available. If the palmarès has no live price, the tool falls back to the last close from the time series (source=timeseries_last_close) — present it with its date, never as "unavailable" when a last close exists."""


ANALYTICS_TOOLS = [
    get_market_overview_tool,
    get_stock_metrics_tool,
    get_timeseries_tool,
    compare_stocks_tool,
    compute_metrics_tool,
    get_brvm_basics_tool,
    get_company_info_tool,
]


def create_analytics_agent(model: str = "glm-5:cloud"):
    llm = get_llm(model=model)
    return create_react_agent(llm, ANALYTICS_TOOLS)

"""Timeseries CSV worker: ensure CSVs exist, daily updates."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_agent_llm
from app.agents.utils import get_time_prefix
from app.tools.stock_tools import (
    ensure_all_timeseries_tool,
    ensure_timeseries_tool,
    list_timeseries_status_tool,
)


def get_timeseries_agent_system() -> str:
    return f"""BRVM timeseries CSV. Check/update CSV files. No price questions. {get_time_prefix()}

**Tools:** list_timeseries_status | ensure_timeseries (one symbol) | ensure_all_timeseries

**Rule:** Call tool. Report: created/updated/up-to-date/error. No file paths in reply."""


TIMESERIES_TOOLS = [
    list_timeseries_status_tool,
    ensure_timeseries_tool,
    ensure_all_timeseries_tool,
]


def create_timeseries_agent(model: str | None = None):
    llm = get_agent_llm("timeseries", model=model)
    return create_react_agent(llm, TIMESERIES_TOOLS)

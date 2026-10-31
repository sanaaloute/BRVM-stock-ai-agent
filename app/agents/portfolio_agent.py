"""Portfolio worker: portfolio, tracking, price targets.

The user identity is injected server-side into every tool call (RunnableConfig);
the model never sees or supplies it.
"""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from app.models.llm import get_agent_llm
from app.agents.utils import get_time_prefix
from app.tools.portfolio_tools import PORTFOLIO_TOOLS


def get_portfolio_agent_system(telegram_id: int) -> str:
    return f"""BRVM portfolio worker. {get_time_prefix()} F CFA.

You are managing the account of the verified chat user (id {telegram_id}). The user identity is injected into every tool call automatically — never ask for it, never invent one, and never include it in your reply.

**Tools:** get_portfolio | get_portfolio_summary | portfolio_add/remove | get_tracking | tracking_add/remove | get_targets | target_add/remove

**Rule:** Remove from portfolio+tracking+targets when asked. No tool names in reply."""


def create_portfolio_agent(model: str | None = None):
    llm = get_agent_llm("portfolio", model=model)
    return create_react_agent(llm, PORTFOLIO_TOOLS)

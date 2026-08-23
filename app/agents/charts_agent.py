"""Charts worker: plot stock price (line/area), returns image path."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt import create_react_agent

from app.models.llm import get_llm
from app.agents.utils import get_time_prefix
from app.tools.stock_tools import get_timeseries_tool, plot_company_chart_tool


def get_charts_agent_system() -> str:
    return f"""BRVM charts. Produce price chart (line/area). {get_time_prefix()} F CFA.

**CRITICAL:** Use the symbol from NLU entities. Do NOT use symbols from previous messages.

**Tools:** get_timeseries (symbol, dates) → plot_company_chart (symbol, start_date, end_date, chart_type=line|area, symbols="S1,S2" optional)

**Comparison:** Comparing 2+ companies? Call plot_company_chart ONCE with symbols="SYM1,SYM2" so all curves appear on the SAME chart. Make one separate call per company ONLY when the user explicitly asks for separate charts.

**Rule:** Call both tools. Do not mention image path. Confirm chart and briefly describe."""


CHARTS_TOOLS = [
    get_timeseries_tool,
    plot_company_chart_tool,
]


MAX_CHART_CAPTION_CHARS = 50  # Telegram chart captions stay short; full text goes in follow-up messages


def _parse_chart_tool_content(content: Any) -> dict | None:
    """Parse a plot_company_chart ToolMessage content into a dict (or None)."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        s = str(content).strip()
        if s.endswith(".png") and "/" in s:
            return {"image_path": s}
    return None


def _extract_image_paths_from_messages(messages: list) -> list[str]:
    """All chart file paths produced by plot_company_chart calls, in call order (deduped)."""
    paths: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "plot_company_chart" and m.content:
            data = _parse_chart_tool_content(m.content)
            path = data.get("image_path") if data else None
            if path and isinstance(path, str) and path not in paths:
                paths.append(path)
    return paths


def _extract_image_path_from_messages(messages: list) -> str | None:
    """Last chart produced (kept for single-image callers)."""
    paths = _extract_image_paths_from_messages(messages)
    return paths[-1] if paths else None


def _extract_chart_caption_from_messages(messages: list) -> str | None:
    """Short caption (≤ 50 chars) describing the chart(s): symbols + date range."""
    symbols: list[str] = []
    starts: list[str] = []
    ends: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "plot_company_chart" and m.content:
            data = _parse_chart_tool_content(m.content)
            if not data or not data.get("image_path"):
                continue
            raw_symbols = data.get("symbols") or ([data["symbol"]] if data.get("symbol") else [])
            for s in raw_symbols:
                s = str(s).strip().upper()
                if s and s not in symbols:
                    symbols.append(s)
            if data.get("start_date"):
                starts.append(str(data["start_date"]))
            if data.get("end_date"):
                ends.append(str(data["end_date"]))
    if not symbols:
        return None

    def _fmt(d: str) -> str:
        try:
            return date.fromisoformat(d[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return d[:10]

    caption = "📊 " + ", ".join(symbols)
    if starts and ends:
        caption += f" · {_fmt(min(starts))}–{_fmt(max(ends))}"
    if len(caption) > MAX_CHART_CAPTION_CHARS:
        caption = caption[: MAX_CHART_CAPTION_CHARS - 1].rstrip() + "…"
    return caption


def create_charts_agent(model: str = "glm-5:cloud"):
    llm = get_llm(model=model)
    return create_react_agent(llm, CHARTS_TOOLS)

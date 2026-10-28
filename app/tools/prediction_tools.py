"""LangChain tools for BRVM stock predictions and trends from Rich Bourse prévision boursière."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from app.scrapers.richbourse_trends import fetch_richbourse_trends_index
from app.utils.news import get_richbourse_prediction

from .schemas import (
    GetAllTrendsInput,
    GetStockPredictionDetailInput,
    GetTrendsByOptionInput,
)


def _get_all_trends(limit: int = 100, **kwargs: Any) -> str:
    """Fetch full trends table (all stocks with trend and confidence)."""
    data = fetch_richbourse_trends_index(trend_option=None, limit=limit)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_trends_by_option(trend_option: str, limit: int = 100, **kwargs: Any) -> str:
    """Fetch trends table filtered by hausse, baisse, or neutre."""
    data = fetch_richbourse_trends_index(trend_option=trend_option.strip().lower(), limit=limit)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_stock_prediction_detail(symbol: str, **kwargs: Any) -> str:
    """Fetch full technical prediction for one stock (trend, confidence, indicators)."""
    data = get_richbourse_prediction(symbol)
    return json.dumps(data, ensure_ascii=False, default=str)


get_all_trends_tool = StructuredTool.from_function(
    func=_get_all_trends,
    name="get_all_trends",
    description="Get the full BRVM stock predictions table from Rich Bourse: all stocks with their trend (Hausse/Baisse/Neutre) and confidence %. Use when the user asks for 'all trends', 'predictions table', 'which stocks are trending', or overview of predictions.",
    args_schema=GetAllTrendsInput,
)

get_trends_by_option_tool = StructuredTool.from_function(
    func=_get_trends_by_option,
    name="get_trends_by_option",
    description="Get BRVM stocks filtered by trend: hausse (up), baisse (down), or neutre (neutral). Use when the user asks for 'stocks in hausse', 'stocks in baisse', 'neutral stocks', or list by trend option.",
    args_schema=GetTrendsByOptionInput,
)

get_stock_prediction_detail_tool = StructuredTool.from_function(
    func=_get_stock_prediction_detail,
    name="get_stock_prediction_detail",
    description="Get detailed technical prediction for one BRVM stock: company name, short-term trend, confidence %, and technical indicators (RSI, Bollinger, MACD, etc.). Use when the user asks for 'prediction for X', 'trend of X', 'details for symbol', or analysis of a specific stock.",
    args_schema=GetStockPredictionDetailInput,
)

PREDICTION_TOOLS = [
    get_all_trends_tool,
    get_trends_by_option_tool,
    get_stock_prediction_detail_tool,
]

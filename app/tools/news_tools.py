"""LangChain tools for BRVM news, communiqués, predictions, and dividends from Sika Finance and Rich Bourse."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from app.utils.news import (
    get_richbourse_dividends,
    get_richbourse_prediction,
    get_sikafinance_actualites_bourse,
    get_sikafinance_communiques,
)

from .schemas import (
    GetRichbourseDividendsInput,
    GetRichboursePredictionInput,
    GetSikafinanceActualitesInput,
    GetSikafinanceCommuniquesInput,
)


def _get_sikafinance_actualites(limit: int = 20, **kwargs: Any) -> str:
    data = get_sikafinance_actualites_bourse(limit=limit)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_sikafinance_communiques(limit: int = 20, company: str | None = None, **kwargs: Any) -> str:
    data = get_sikafinance_communiques(limit=limit, company=company)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_richbourse_prediction(symbol: str, **kwargs: Any) -> str:
    data = get_richbourse_prediction(symbol)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_richbourse_dividends(limit: int = 50, symbol: str | None = None, **kwargs: Any) -> str:
    data = get_richbourse_dividends(limit=limit, symbol=symbol)
    return json.dumps(data, ensure_ascii=False, default=str)


get_sikafinance_actualites_tool = StructuredTool.from_function(
    func=_get_sikafinance_actualites,
    name="get_sikafinance_actualites",
    description="Get BRVM market news from Sika Finance actualités bourse BRVM. Returns items with date, title, url, snippet. Use for general BRVM/West Africa market news.",
    args_schema=GetSikafinanceActualitesInput,
)

get_sikafinance_communiques_tool = StructuredTool.from_function(
    func=_get_sikafinance_communiques,
    name="get_sikafinance_communiques",
    description="Get BRVM official communiqués (PDFs) from Sika Finance: états financiers, convocations AGO, notations, etc. Optionally filter by company symbol or name.",
    args_schema=GetSikafinanceCommuniquesInput,
)

get_richbourse_prediction_tool = StructuredTool.from_function(
    func=_get_richbourse_prediction,
    name="get_richbourse_prediction",
    description="Get technical prediction/analysis for a BRVM stock from Rich Bourse: RSI, Bollinger, MACD, trend, confidence. Use symbol (e.g. SOGC, NTLC, ORAC).",
    args_schema=GetRichboursePredictionInput,
)

get_richbourse_dividends_tool = StructuredTool.from_function(
    func=_get_richbourse_dividends,
    name="get_richbourse_dividends",
    description="Get announced dividends from Rich Bourse: company, amount (F CFA), yield %, ex-dividend date, payment date. Optionally filter by symbol.",
    args_schema=GetRichbourseDividendsInput,
)

NEWS_TOOLS = [
    get_sikafinance_actualites_tool,
    get_sikafinance_communiques_tool,
    get_richbourse_prediction_tool,
    get_richbourse_dividends_tool,
]

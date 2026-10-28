"""BRVM news: company news (Rich Bourse), market news (Sika Finance), official announcements (BRVM), communiqués, predictions, dividends."""
from __future__ import annotations

from typing import Any

from app.scrapers.brvm_announcements import fetch_brvm_announcements
from app.scrapers.richbourse_dividends import fetch_richbourse_dividends
from app.scrapers.richbourse_news import fetch_company_news
from app.scrapers.richbourse_prediction import fetch_richbourse_prediction
from app.scrapers.sikafinance_actualites import fetch_sikafinance_actualites
from app.scrapers.sikafinance_communiques import fetch_sikafinance_communiques
from app.scrapers.sikafinance_news import fetch_bourse_news

from app.utils.brvm_companies import resolve_to_symbol


def get_company_news(symbol: str, limit: int = 15) -> dict[str, Any]:
    """
    Get latest news for a BRVM company from Rich Bourse. Symbol is resolved from brvm_companies list.
    Returns {source, symbol, items: [{date, title, url, snippet}], error?}.
    """
    resolved = resolve_to_symbol(symbol)
    sym = resolved or (symbol or "").strip().upper()
    out = fetch_company_news(sym, limit=limit)
    if not resolved and symbol and out.get("items"):
        out["resolved_symbol"] = sym
    if not out.get("items") and out.get("error") is None and not sym:
        out["error"] = "Société inconnue. Utilisez un symbole ou un nom de société BRVM valide."
    return out


def get_market_news(limit: int = 20) -> dict[str, Any]:
    """
    Get BRVM market news from Sika Finance (ACTUALITES DE LA BOURSE).
    Returns {source, url, items: [{date, title, url}], error?}.
    """
    return fetch_bourse_news(limit=limit)


def get_brvm_official_announcements(limit: int = 20, company: str | None = None) -> dict[str, Any]:
    """
    Get BRVM official announcements (convocations AGO, etc.) with PDF links.
    If company is set (symbol or name), filter to that company.
    """
    return fetch_brvm_announcements(limit=limit, company_filter=company)


def get_sikafinance_actualites_bourse(limit: int = 20) -> dict[str, Any]:
    """
    Get BRVM market news from Sika Finance actualités bourse BRVM page.
    Returns {source, url, items: [{date, title, url, snippet}], error?}.
    """
    return fetch_sikafinance_actualites(limit=limit)


def get_sikafinance_communiques(limit: int = 20, company: str | None = None) -> dict[str, Any]:
    """
    Get BRVM official communiqués (PDFs) from Sika Finance.
    Returns {source, url, items: [{date, title, pdf_url, company?}], error?}.
    If company is set, filter to matching rows.
    """
    return fetch_sikafinance_communiques(limit=limit, company=company)


def get_richbourse_prediction(symbol: str) -> dict[str, Any]:
    """
    Get technical prediction for a BRVM symbol from Rich Bourse.
    Returns {source, url, symbol, company_name, technical_config, trend, confidence, error?}.
    """
    resolved = resolve_to_symbol(symbol)
    sym = resolved or (symbol or "").strip().upper()
    return fetch_richbourse_prediction(sym)


def get_richbourse_dividends(limit: int = 50, symbol: str | None = None) -> dict[str, Any]:
    """
    Get announced dividends from Rich Bourse.
    Returns {source, url, date_page, items: [{company, symbol, dividende, rendement, ex_dividende, date_paiement}], error?}.
    If symbol is set, filter to that company.
    """
    resolved = resolve_to_symbol(symbol) if symbol else None
    sym = resolved or (symbol or "").strip().upper() or None
    return fetch_richbourse_dividends(limit=limit, symbol=sym)

"""LangChain tools for scrapers and services."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool  # pyright: ignore[reportMissingImports]

from app.scrapers import BRVMScraper, RichBourseScraper, RichBourseTimeseriesScraper, SikaFinanceScraper
from app.scrapers.sgi_brvm import fetch_and_save_sgi, load_sgi_local, SGI_JSON_PATH
from app.scrapers.sikafinance_company import (
    fetch_and_save_company_details,
    load_company_details,
)
from app.utils import compare_stocks, compute_metrics, get_stock_metrics, get_timeseries
from app.utils._data import (
    ensure_timeseries_up_to_date,
    list_series_status,
    run_daily_timeseries_update,
)
from app.utils.news import (
    get_brvm_official_announcements,
    get_company_news as get_company_news_svc,
    get_market_news as get_market_news_svc,
)
from app.utils.plots import plot_timeseries as plot_timeseries_service
from app.utils.plots import plot_timeseries_multi as plot_timeseries_multi_service
from app.utils.market_overview import get_brvm_market_overview
from app.utils.brvm_basics import get_brvm_basics
from app.utils.brvm_companies import (
    get_country_code_for_symbol,
    get_symbol_to_name,
    get_symbol_to_sector,
    get_valid_symbols,
)

import config
from .schemas import (
    CompareStocksInput,
    GetCompanyInfoInput,
    ComputeMetricsInput,
    EnsureAllTimeseriesInput,
    EnsureTimeseriesInput,
    GetBrvmAnnouncementsInput,
    GetBrvmBasicsInput,
    GetCompanyNewsInput,
    GetMarketNewsInput,
    GetStockMetricsInput,
    GetTimeseriesInput,
    ListTimeseriesStatusInput,
    GetMarketOverviewInput,
    PlotCompanyChartInput,
    ScrapeBrvmInput,
    ScrapeRichbourseInput,
    ScrapeRichbourseTimeseriesInput,
    ScrapeSikafinanceInput,
    GetSgiDataInput,
    FetchSgiDataInput,
    FetchSgiUrlInput,
    GetCompanyDetailsInput,
    FetchCompanyDetailsInput,
)

SLEEP = config.SLEEP_SECONDS


def _scrape_sikafinance(period: str = "veille", **kwargs: Any) -> str:
    scraper = SikaFinanceScraper(period=period, sleep_seconds=SLEEP)
    data = scraper.scrape()
    return json.dumps(data, ensure_ascii=False, default=str)


def _scrape_richbourse(period: str = "veille", progression: str = "tout", **kwargs: Any) -> str:
    scraper = RichBourseScraper(period=period, progression=progression, sleep_seconds=SLEEP)
    data = scraper.scrape()
    return json.dumps(data, ensure_ascii=False, default=str)


def _scrape_richbourse_timeseries(symbol: str, **kwargs: Any) -> str:
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data" / "series"
    scraper = RichBourseTimeseriesScraper(symbol=symbol, output_dir=str(data_dir), sleep_seconds=SLEEP)
    data = scraper.scrape()
    return json.dumps(data, ensure_ascii=False, default=str)


def _scrape_brvm(_: Any = None) -> str:
    scraper = BRVMScraper(sleep_seconds=SLEEP)
    data = scraper.scrape()
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_stock_metrics(symbol: str, at_time: str | None = None, period: str = "veille", **kwargs: Any) -> str:
    data = get_stock_metrics(symbol, at_time=at_time, period=period)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_timeseries(symbol: str, start_date: str, end_date: str, **kwargs: Any) -> str:
    data = get_timeseries(symbol, start_date, end_date)
    return json.dumps(data, ensure_ascii=False, default=str)


def _compare_stocks(
    symbol_a: str,
    symbol_b: str,
    period: str = "veille",
    period_price_date: str | None = None,
    **kwargs: Any,
) -> str:
    data = compare_stocks(symbol_a, symbol_b, period=period, period_price_date=period_price_date)
    return json.dumps(data, ensure_ascii=False, default=str)


def _compute_metrics(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    **kwargs: Any,
) -> str:
    data = compute_metrics(symbol, start_date=start_date, end_date=end_date)
    return json.dumps(data, ensure_ascii=False, default=str)


def _ensure_timeseries(symbol: str, **kwargs: Any) -> str:
    data = ensure_timeseries_up_to_date(symbol)
    return json.dumps(data, ensure_ascii=False, default=str)


def _list_timeseries_status(symbols: str | None = None, **kwargs: Any) -> str:
    sym_list = [s.strip() for s in (symbols or "").split(",") if s.strip()] or None
    data = list_series_status(sym_list)
    return json.dumps(data, ensure_ascii=False, default=str)


def _ensure_all_timeseries(**kwargs: Any) -> str:
    data = run_daily_timeseries_update(config.TIMESERIES_SYMBOLS)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_company_news(symbol: str, limit: int = 10, **kwargs: Any) -> str:
    data = get_company_news_svc(symbol, limit=limit)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_market_news(limit: int = 15, **kwargs: Any) -> str:
    data = get_market_news_svc(limit=limit)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_brvm_announcements(limit: int = 15, company: str | None = None, **kwargs: Any) -> str:
    data = get_brvm_official_announcements(limit=limit, company=company)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_market_overview(top_n: int = 10, **kwargs: Any) -> str:
    data = get_brvm_market_overview(top_n=top_n)
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_brvm_basics(**kwargs: Any) -> str:
    return get_brvm_basics()


def _get_sgi_data(name_filter: str | None = None, country_filter: str | None = None, **kwargs: Any) -> str:
    """Read SGI data from app/data/sgi_brvm.json. If file missing, tell caller to use fetch_sgi_data."""
    from pathlib import Path
    if not Path(SGI_JSON_PATH).exists():
        return json.dumps({
            "error": "no_local_data",
            "message": "Aucune donnée SGI locale. Utilisez fetch_sgi_data pour télécharger depuis Rich Bourse (enregistré dans app/data/sgi_brvm.json).",
        }, ensure_ascii=False)
    data = load_sgi_local()
    sgi_list = data.get("sgi") or []
    if name_filter and (name_filter := str(name_filter).strip()):
        name_lower = name_filter.lower()
        sgi_list = [s for s in sgi_list if name_lower in (s.get("name") or "").lower()]
    if country_filter and (country_filter := str(country_filter).strip()):
        country_lower = country_filter.lower()
        sgi_list = [
            s for s in sgi_list
            if country_lower in (s.get("country") or "").lower()
            or country_lower in (s.get("other_countries") or "").lower()
        ]
    return json.dumps({
        "source": data.get("source_name"),
        "updated_at": data.get("updated_at"),
        "count": len(sgi_list),
        "sgi": sgi_list,
    }, ensure_ascii=False, default=str)


def _fetch_sgi_data(**kwargs: Any) -> str:
    """Fetch SGI list from Rich Bourse (list + detail pages) and save to app/data/sgi_brvm.json."""
    result = fetch_and_save_sgi()
    return json.dumps(result, ensure_ascii=False, default=str)


# fetch_sgi_url SSRF guard: the URL comes from the LLM, so only known BRVM-data
# hosts may be fetched — the static set below plus any host referenced by the
# local SGI data file (websites and detail/tarifs/documents links).
_SGI_URL_ALLOWED_HOSTS = {
    "richbourse.com",
    "www.richbourse.com",
    "sikafinance.com",
    "www.sikafinance.com",
    "brvm.org",
    "www.brvm.org",
}
_SGI_URL_FIELDS = ("website", "detail_url", "tarifs_url", "documents_url")
_IP_LITERAL_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def _sgi_url_host(url: str) -> str:
    """Lowercased host without credentials or port ("" when unparseable)."""
    netloc = (urlparse(url).netloc or "").lower()
    return netloc.split("@")[-1].split(":")[0]


def _sgi_allowed_hosts() -> set[str]:
    hosts = set(_SGI_URL_ALLOWED_HOSTS)
    try:
        data = load_sgi_local()
        for entry in data.get("sgi") or []:
            if not isinstance(entry, dict):
                continue
            for field in _SGI_URL_FIELDS:
                host = _sgi_url_host(str(entry.get(field) or "").strip())
                if host:
                    hosts.add(host)
    except Exception:
        pass  # missing/corrupt SGI file: the static allowlist still applies
    return hosts


def _fetch_sgi_url(url: str, **kwargs: Any) -> str:
    """Fetch content from a URL (e.g. SGI detail page, tarifs, or website). Returns text summary or error."""
    from app.utils.http_client import http_get
    url = (url or "").strip()
    parsed = urlparse(url)
    host = _sgi_url_host(url)
    if parsed.scheme not in ("http", "https") or not host:
        return json.dumps({"error": "URL invalide."}, ensure_ascii=False)
    if _IP_LITERAL_RE.match(host) or "localhost" in host:
        return json.dumps({"error": f"Hôte non autorisé : {host}."}, ensure_ascii=False)
    if host not in _sgi_allowed_hosts():
        return json.dumps({
            "error": f"Hôte non autorisé : {host}. Seuls les sites de données BRVM connus (Rich Bourse, Sika Finance, BRVM, sites SGI) peuvent être consultés.",
        }, ensure_ascii=False)
    try:
        resp = http_get(url, timeout=15, verify=True)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        return json.dumps({
            "url": url,
            "text_preview": text[:4000] if len(text) > 4000 else text,
            "length": len(text),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"url": url, "error": str(e)}, ensure_ascii=False)


def _get_company_details(symbol: str, **kwargs: Any) -> str:
    """Read cached company profile for one BRVM symbol (presentation, shareholders, performance).

    Loads from app/data/company_details/{SYMBOL}.json. Returns JSON with company_name, code,
    presentation, phone, address, dirigeants, nombre_titres, flottant, valorisation,
    shareholders (list of {name, pct}), and performance (metrics by year: chiffre_affaires,
    resultat_net, croissance_ca, croissance_rn, bnpa, per, dividende).

    Returns error "no_local_data" when the file does not exist; the caller should then
    use fetch_company_details(symbol) and call get_company_details again.
    """
    sym = (symbol or "").strip().upper()
    if sym not in get_valid_symbols():
        return json.dumps({"error": f"Symbole inconnu : {symbol}. Utilisez un symbole BRVM valide."}, ensure_ascii=False)
    data = load_company_details(sym)
    if not data:
        return json.dumps({
            "error": "no_local_data",
            "message": "Aucune fiche société locale. Utilisez fetch_company_details pour télécharger depuis Sika Finance (enregistré dans app/data/company_details).",
        }, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False, default=str)


def _fetch_company_details(symbol: str, **kwargs: Any) -> str:
    """Fetch company fiche société from Sika Finance and save to local cache.

    Downloads the Sika Finance page for the given BRVM symbol (e.g. BOAM.ml, NTLC.ci),
    parses presentation, management, shareholders, and performance table, then saves
    to app/data/company_details/{SYMBOL}.json. Country code is derived from BRVM data.
    Call this when get_company_details returns no_local_data or when the user asks
    to refresh company details. Returns the same structure as get_company_details
    (or an error dict if the fetch failed).
    """
    sym = (symbol or "").strip().upper()
    if sym not in get_valid_symbols():
        return json.dumps({"error": f"Symbole inconnu : {symbol}. Utilisez un symbole BRVM valide."}, ensure_ascii=False)
    country_code = get_country_code_for_symbol(sym)
    result = fetch_and_save_company_details(sym, country_code)
    return json.dumps(result, ensure_ascii=False, default=str)


def _get_company_info(symbol: str, **kwargs: Any) -> str:
    sym = (symbol or "").strip().upper()
    valid = get_valid_symbols()
    if sym not in valid:
        return json.dumps({"error": f"Symbole inconnu : {symbol}. Utilisez un symbole BRVM valide."}, ensure_ascii=False)
    name = get_symbol_to_name().get(sym, sym)
    sector = get_symbol_to_sector().get(sym, "")
    return json.dumps(
        {"symbol": sym, "company_name": name, "sector": sector or "Non spécifié"},
        ensure_ascii=False,
    )


def _plot_company_chart(
    symbol: str,
    start_date: str,
    end_date: str,
    chart_type: str = "line",
    symbols: str | None = None,
    **kwargs: Any,
) -> str:
    ct = "area" if (chart_type or "").strip().lower() == "area" else "line"
    # Comparison mode: several symbols on ONE chart. The primary `symbol` is
    # always part of the list even if the model omitted it from `symbols`.
    syms: list[str] = []
    for s in (symbols or "").split(","):
        s = s.strip().upper()
        if s and s not in syms:
            syms.append(s)
    primary = (symbol or "").strip().upper()
    if primary and primary not in syms:
        syms.insert(0, primary)
    if len(syms) >= 2:
        data = plot_timeseries_multi_service(syms, start_date, end_date, chart_type=ct)
        if not data.get("image_path"):
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps(
            {
                "image_path": data.get("image_path"),
                "symbols": data.get("symbols"),
                "missing_symbols": data.get("missing_symbols"),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "points_count": data.get("points_count"),
                "message": f"Graphique comparatif enregistré. Envoyez l'image à {data.get('image_path')} avec votre explication.",
            },
            ensure_ascii=False,
            default=str,
        )
    data = plot_timeseries_service(symbol, start_date, end_date, chart_type=ct)
    if data.get("error") and not data.get("image_path"):
        return json.dumps(data, ensure_ascii=False, default=str)
    return json.dumps(
        {
            "image_path": data.get("image_path"),
            "symbol": data.get("symbol"),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "points_count": data.get("points_count"),
            "message": f"Graphique enregistré. Envoyez l'image à {data.get('image_path')} avec votre explication.",
        },
        ensure_ascii=False,
        default=str,
    )


scrape_sikafinance = StructuredTool.from_function(
    func=_scrape_sikafinance,
    name="scrape_sikafinance",
    description="Scrape Sika Finance palmarès (BRVM stocks: indices, gains, losses, volume). Returns JSON.",
    args_schema=ScrapeSikafinanceInput,
)

scrape_richbourse = StructuredTool.from_function(
    func=_scrape_richbourse,
    name="scrape_richbourse",
    description="Scrape Rich Bourse variation table (stocks with price, volume, variation %, capitalisation). Returns JSON.",
    args_schema=ScrapeRichbourseInput,
)

scrape_richbourse_timeseries = StructuredTool.from_function(
    func=_scrape_richbourse_timeseries,
    name="scrape_richbourse_timeseries",
    description="Fetch and save Rich Bourse time series for a stock symbol to data/series (CSV). Returns JSON with csv_path and row count.",
    args_schema=ScrapeRichbourseTimeseriesInput,
)

scrape_brvm = StructuredTool.from_function(
    func=_scrape_brvm,
    name="scrape_brvm",
    description="Scrape BRVM official site (indices and stocks). Returns JSON.",
    args_schema=ScrapeBrvmInput,
)

get_stock_metrics_tool = StructuredTool.from_function(
    func=_get_stock_metrics,
    name="get_stock_metrics",
    description="Get current or historical price, volume, growth %, loss % and capitalisation for a stock. Use at_time (YYYY-MM-DD) for historical price.",
    args_schema=GetStockMetricsInput,
)

get_timeseries_tool = StructuredTool.from_function(
    func=_get_timeseries,
    name="get_timeseries",
    description="Get time series (date, price) for a stock over a date range. Use for charts. Returns points list.",
    args_schema=GetTimeseriesInput,
)

compare_stocks_tool = StructuredTool.from_function(
    func=_compare_stocks,
    name="compare_stocks",
    description="Compare two stocks: price, volume, growth %, loss %, market cap. Optionally compare price at a given date (period_price_date).",
    args_schema=CompareStocksInput,
)

compute_metrics_tool = StructuredTool.from_function(
    func=_compute_metrics,
    name="compute_metrics",
    description="Compute average, median, min, max, stdev and count for a stock over a date range. Omit dates for full series.",
    args_schema=ComputeMetricsInput,
)

ensure_timeseries_tool = StructuredTool.from_function(
    func=_ensure_timeseries,
    name="ensure_timeseries",
    description="Check if company CSV exists and is up to date; fetch/refresh if missing or stale (older than 1 day).",
    args_schema=EnsureTimeseriesInput,
)

list_timeseries_status_tool = StructuredTool.from_function(
    func=_list_timeseries_status,
    name="list_timeseries_status",
    description="List status of company CSVs: path, last_date, up_to_date. Optionally pass comma-separated symbols.",
    args_schema=ListTimeseriesStatusInput,
)

ensure_all_timeseries_tool = StructuredTool.from_function(
    func=_ensure_all_timeseries,
    name="ensure_all_timeseries",
    description="Update CSVs for all configured target companies (daily job). Call once per day.",
    args_schema=EnsureAllTimeseriesInput,
)

plot_company_chart_tool = StructuredTool.from_function(
    func=_plot_company_chart,
    name="plot_company_chart",
    description="Plot price chart for a company over a date range. Uses most up-to-date CSV. Returns image_path (temp file) and summary. Chart types: line, area. To compare several companies on ONE chart, pass symbols='S1,S2'.",
    args_schema=PlotCompanyChartInput,
)

get_company_news_tool = StructuredTool.from_function(
    func=_get_company_news,
    name="get_company_news",
    description="Get latest news for a BRVM company from Rich Bourse (ground truth). Returns items with date, title, url, snippet. Use valid BRVM symbol or company name.",
    args_schema=GetCompanyNewsInput,
)

get_market_news_tool = StructuredTool.from_function(
    func=_get_market_news,
    name="get_market_news",
    description="Get BRVM market news from Sika Finance (ACTUALITES DE LA BOURSE). General finance news that can influence BRVM. No symbol required.",
    args_schema=GetMarketNewsInput,
)

get_brvm_announcements_tool = StructuredTool.from_function(
    func=_get_brvm_announcements,
    name="get_brvm_announcements",
    description="Get BRVM official announcements (convocations AGO, etc.) with PDF download links. Optionally filter by company symbol or name.",
    args_schema=GetBrvmAnnouncementsInput,
)

get_market_overview_tool = StructuredTool.from_function(
    func=_get_market_overview,
    name="get_market_overview",
    description="Get BRVM market overview: most expensive stocks (highest_prices), cheapest stocks (lowest_prices), most traded (top_by_volume), top gainers, top losers. Use this for: 'most expensive stock', 'lowest price stock', 'cheapest stock', 'highest price', 'top 5 by price', 'should I buy the cheapest?'. No symbol required. Returns only BRVM-listed symbols. All amounts in F CFA.",
    args_schema=GetMarketOverviewInput,
)

get_brvm_basics_tool = StructuredTool.from_function(
    func=_get_brvm_basics,
    name="get_brvm_basics",
    description="Get short text about BRVM (what it is, how to invest on BRVM). Use for questions like 'what is BRVM', 'how to invest in BRVM', 'how does the BRVM work'.",
    args_schema=GetBrvmBasicsInput,
)

get_company_info_tool = StructuredTool.from_function(
    func=_get_company_info,
    name="get_company_info",
    description="Get full company name and sector for a BRVM symbol. Use when you need to explain what a company does or its sector of activity.",
    args_schema=GetCompanyInfoInput,
)

get_sgi_data_tool = StructuredTool.from_function(
    func=_get_sgi_data,
    name="get_sgi_data",
    description="Read SGI (brokers) data from local file app/data/sgi_brvm.json. Use name_filter or country_filter to narrow results. If file is missing, use fetch_sgi_data first.",
    args_schema=GetSgiDataInput,
)

fetch_sgi_data_tool = StructuredTool.from_function(
    func=_fetch_sgi_data,
    name="fetch_sgi_data",
    description="Fetch full SGI list from Rich Bourse and save to app/data/sgi_brvm.json. Call this when local data is missing or user asks to refresh SGI data.",
    args_schema=FetchSgiDataInput,
)

fetch_sgi_url_tool = StructuredTool.from_function(
    func=_fetch_sgi_url,
    name="fetch_sgi_url",
    description="Fetch content from a URL (e.g. SGI detail_url, tarifs_url, documents_url, or website). Use when user needs details from a specific SGI link.",
    args_schema=FetchSgiUrlInput,
)

get_company_details_tool = StructuredTool.from_function(
    func=_get_company_details,
    name="get_company_details",
    description="Read cached BRVM company profile for one symbol: presentation, dirigeants, shareholders, performance (CA, résultat net, dividendes, croissance, BNPA, PER). Call this first. If it returns no_local_data, call fetch_company_details(symbol) then get_company_details(symbol) again.",
    args_schema=GetCompanyDetailsInput,
)

fetch_company_details_tool = StructuredTool.from_function(
    func=_fetch_company_details,
    name="fetch_company_details",
    description="Download company fiche société from Sika Finance for one BRVM symbol and save to app/data/company_details. Use when get_company_details returned no_local_data or when the user asks to refresh/update company data.",
    args_schema=FetchCompanyDetailsInput,
)

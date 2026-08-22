"""Pydantic schemas for agent tools."""
from pydantic import BaseModel, Field


class ScrapeSikafinanceInput(BaseModel):
    period: str = Field(
        default="veille",
        description="Period: veille, une_semaine, un_mois, 3_mois, 6_mois, 1_an, etc.",
    )


class ScrapeRichbourseInput(BaseModel):
    period: str = Field(
        default="veille",
        description="Period: veille, 1_semaine, 1_mois, 3_mois, 6_mois, 1_an, etc.",
    )
    progression: str = Field(
        default="tout",
        description="Filter: tout, hausse, baisse, constante, hausse_baisse",
    )


class ScrapeRichbourseTimeseriesInput(BaseModel):
    symbol: str = Field(description="Stock symbol (e.g. NTLC, SLBC).")


class ScrapeBrvmInput(BaseModel):
    pass


class GetStockMetricsInput(BaseModel):
    symbol: str = Field(description="Stock symbol (e.g. NTLC).")
    at_time: str | None = Field(
        default=None,
        description="Optional date (YYYY-MM-DD) for historical price; omit for current.",
    )
    period: str = Field(default="veille", description="Palmarès period when at_time is omitted.")


class GetTimeseriesInput(BaseModel):
    symbol: str = Field(description="Stock symbol.")
    start_date: str = Field(description="Start date YYYY-MM-DD.")
    end_date: str = Field(description="End date YYYY-MM-DD.")


class CompareStocksInput(BaseModel):
    symbol_a: str = Field(description="First stock symbol.")
    symbol_b: str = Field(description="Second stock symbol.")
    period: str = Field(default="veille", description="Palmarès period.")
    period_price_date: str | None = Field(
        default=None,
        description="Optional date (YYYY-MM-DD) to compare price at that date.",
    )


class ComputeMetricsInput(BaseModel):
    symbol: str = Field(description="Stock symbol.")
    start_date: str | None = Field(default=None, description="Start date YYYY-MM-DD; omit for full series.")
    end_date: str | None = Field(default=None, description="End date YYYY-MM-DD; omit for full series.")


class EnsureTimeseriesInput(BaseModel):
    symbol: str = Field(description="Stock symbol (e.g. NTLC, SLBC).")


class ListTimeseriesStatusInput(BaseModel):
    symbols: str | None = Field(
        default=None,
        description="Comma-separated symbols to check; omit to list all CSVs in data/series.",
    )


class EnsureAllTimeseriesInput(BaseModel):
    pass


class PlotCompanyChartInput(BaseModel):
    symbol: str = Field(description="Stock symbol.")
    start_date: str = Field(description="Start date YYYY-MM-DD.")
    end_date: str = Field(description="End date YYYY-MM-DD.")
    chart_type: str = Field(
        default="line",
        description="Chart type: line or area.",
    )


class GetCompanyNewsInput(BaseModel):
    symbol: str = Field(description="Stock symbol or company name (e.g. PALC, Palm CI).")
    limit: int = Field(default=10, le=50, description="Max number of news items to return.")


class GetMarketNewsInput(BaseModel):
    limit: int = Field(default=15, le=50, description="Max number of news items to return.")


class GetBrvmAnnouncementsInput(BaseModel):
    limit: int = Field(default=15, le=50, description="Max number of announcements to return.")
    company: str | None = Field(default=None, description="Optional: filter by symbol or company name.")


class GetMarketOverviewInput(BaseModel):
    top_n: int = Field(default=10, le=50, description="Number of stocks to return per category (default 10).")


class GetBrvmBasicsInput(BaseModel):
    pass


class GetCompanyInfoInput(BaseModel):
    symbol: str = Field(description="BRVM symbol (e.g. NTLC, SLBC) to get full name and sector.")


class PortfolioAddInput(BaseModel):
    symbol: str = Field(description="BRVM symbol (e.g. NTLC, SLBC).")
    buy_price: float = Field(description="Buy price in F CFA.")
    buy_date: str = Field(description="Buy date YYYY-MM-DD.")
    quantity: float = Field(default=1.0, description="Number of shares.")


class PortfolioRemoveInput(BaseModel):
    symbol: str = Field(description="BRVM symbol to remove.")


class GetPortfolioInput(BaseModel):
    pass


class GetPortfolioSummaryInput(BaseModel):
    pass


class TrackingAddInput(BaseModel):
    symbol: str = Field(description="BRVM symbol to track.")


class TrackingRemoveInput(BaseModel):
    symbol: str = Field(description="BRVM symbol to remove.")


class GetTrackingInput(BaseModel):
    pass


class TargetAddInput(BaseModel):
    symbol: str = Field(description="BRVM symbol.")
    target_price: float = Field(description="Target price in F CFA.")
    direction: str = Field(default="above", description="Notify when price goes 'above' or 'below' target.")


class TargetRemoveInput(BaseModel):
    symbol: str = Field(description="BRVM symbol.")


class GetTargetsInput(BaseModel):
    pass


# News tools (news_tools.py)
class GetSikafinanceActualitesInput(BaseModel):
    limit: int = Field(default=20, le=50, description="Max number of news items to return.")


class GetSikafinanceCommuniquesInput(BaseModel):
    limit: int = Field(default=20, le=50, description="Max number of communiqués to return.")
    company: str | None = Field(default=None, description="Optional: filter by symbol or company name.")


class GetRichboursePredictionInput(BaseModel):
    symbol: str = Field(description="BRVM symbol (e.g. SOGC, NTLC, ORAC) for technical prediction.")


class GetRichbourseDividendsInput(BaseModel):
    limit: int = Field(default=50, le=50, description="Max number of dividend entries to return.")
    symbol: str | None = Field(default=None, description="Optional: filter by symbol or company name.")


# Prediction/trends tools (prediction_tools.py)
class GetAllTrendsInput(BaseModel):
    limit: int = Field(default=100, le=200, description="Max number of stocks to return from the full trends table.")


class GetTrendsByOptionInput(BaseModel):
    trend_option: str = Field(
        description="Filter by trend: hausse (up), baisse (down), or neutre (neutral).",
    )
    limit: int = Field(default=100, le=200, description="Max number of stocks to return.")


class GetStockPredictionDetailInput(BaseModel):
    symbol: str = Field(description="BRVM symbol (e.g. SPHC, SOGC, NTLC) for full technical prediction details.")


# SGI (brokers) tools
class GetSgiDataInput(BaseModel):
    name_filter: str | None = Field(
        default=None,
        description="Optional: filter SGIs by name (partial match). Omit to return all.",
    )
    country_filter: str | None = Field(
        default=None,
        description="Optional: filter by country (e.g. Côte d'Ivoire, Sénégal). Omit to return all.",
    )


class FetchSgiDataInput(BaseModel):
    pass


class FetchSgiUrlInput(BaseModel):
    url: str = Field(description="Full URL to fetch (e.g. SGI detail_url, tarifs_url, website).")


# Company details (Sika Finance société page: presentation, shareholders, performance)
class GetCompanyDetailsInput(BaseModel):
    symbol: str = Field(
        description="Single BRVM symbol (e.g. BOAM, NTLC, SLBC). Required. Use for any question about this company's profile, actionnaires, dividends, net result, growth, or performance table.",
    )


class FetchCompanyDetailsInput(BaseModel):
    symbol: str = Field(
        description="BRVM symbol to fetch from Sika Finance and save to cache (e.g. BOAM, NTLC). Call only when get_company_details returned no_local_data or the user explicitly asks to refresh company details.",
    )


# Advisor tools (advisor_tools.py)
class GetStockAdviceInput(BaseModel):
    symbol: str = Field(description="BRVM symbol (e.g. NTLC, SLBC) to score for a buy/hold/sell signal.")


class GetMarketRecommendationsInput(BaseModel):
    top_n: int = Field(default=5, le=10, description="Number of top buy and top sell candidates to return (max 10).")


class GetPortfolioAdviceInput(BaseModel):
    pass

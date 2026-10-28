"""Stock market scrapers (Tavily API and requests + BeautifulSoup for news)."""
from .base import BaseScraper
from .brvm import BRVMScraper
from .brvm_announcements import fetch_brvm_announcements
from .richbourse import RichBourseScraper
from .richbourse_dividends import fetch_richbourse_dividends
from .richbourse_news import fetch_company_news
from .richbourse_prediction import fetch_richbourse_prediction
from .richbourse_trends import fetch_richbourse_trends_index
from .richbourse_timeseries import RichBourseTimeseriesScraper
from .sikafinance import SikaFinanceScraper
from .sikafinance_actualites import fetch_sikafinance_actualites
from .sikafinance_communiques import fetch_sikafinance_communiques
from .sikafinance_news import fetch_bourse_news
from .sgi_brvm import fetch_and_save_sgi, load_sgi_local

__all__ = [
    "BaseScraper",
    "BRVMScraper",
    "fetch_brvm_announcements",
    "fetch_bourse_news",
    "fetch_company_news",
    "fetch_richbourse_dividends",
    "fetch_richbourse_prediction",
    "fetch_richbourse_trends_index",
    "fetch_sikafinance_actualites",
    "fetch_sikafinance_communiques",
    "RichBourseScraper",
    "RichBourseTimeseriesScraper",
    "SikaFinanceScraper",
    "fetch_and_save_sgi",
    "load_sgi_local",
]

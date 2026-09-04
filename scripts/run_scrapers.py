"""
Run all stock market scrapers with sleep between each request.

Usage:
  Set TAVILY_API_KEY in .env (see .env.example).
  python run_scrapers.py
  python run_scrapers.py --site richbourse
  python run_scrapers.py --sleep 3
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import argparse
import json
import logging
import sys
from typing import Any

import config
from app.scrapers import (
    BRVMScraper,
    RichBourseScraper,
    RichBourseTimeseriesScraper,
    SikaFinanceScraper,
    fetch_and_save_sgi,
)
from app.scrapers.richbourse import RICHBOURSE_PERIODS
from app.scrapers.sikafinance import SIKAFINANCE_PERIODS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SCRAPERS = {
    "sikafinance": (SikaFinanceScraper, config.SIKAFINANCE_PALMARES_URL),
    "richbourse": (RichBourseScraper, config.RICHBOURSE_URL),
    "richbourse_timeseries": (RichBourseTimeseriesScraper, "https://www.richbourse.com/common/mouvements/index"),
    "brvm": (BRVMScraper, config.BRVM_URL),
    "sgi": (None, "https://www.richbourse.com/common/apprendre/liste-sgi"),  # worker: fetch_and_save_sgi (Rich Bourse only)
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch stock data via Tavily from Sika Finance, Rich Bourse, BRVM.")
    parser.add_argument(
        "--site",
        choices=list(SCRAPERS) + ["all"],
        default="all",
        help="Which site to scrape (default: all)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help=f"Override sleep seconds between requests (default: env SCRAPER_SLEEP_SECONDS or {config.SLEEP_SECONDS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON to stdout",
    )
    parser.add_argument(
        "--period",
        choices=["veille", "1er_janvier", "une_semaine", "un_mois", "1_semaine", "2_semaines", "2_mois", "3_mois", "6_mois", "1_an", "2_ans", "3_ans", "4_ans", "5_ans"],
        default="veille",
        help="Period: Sika Finance (une_semaine, un_mois...) or Rich Bourse (1_semaine, 1_mois...) (default: veille)",
    )
    parser.add_argument(
        "--progression",
        choices=["tout", "hausse", "baisse", "constante", "hausse_baisse"],
        default="tout",
        help="Rich Bourse: progression filter (default: tout)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Rich Bourse timeseries: stock symbol (e.g. NTLC). Required when --site richbourse_timeseries",
    )
    args = parser.parse_args()

    if args.site != "sgi" and not config.TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY is not set. Create a .env file from .env.example.")
        return 1

    sleep = args.sleep if args.sleep is not None else config.SLEEP_SECONDS
    results = {}

    if args.site == "richbourse_timeseries" and not args.symbol:
        logger.error("--symbol is required when --site richbourse_timeseries (e.g. --symbol NTLC)")
        return 1

    sites = list(SCRAPERS) if args.site == "all" else [args.site]
    for name in sites:
        if name == "richbourse_timeseries" and not args.symbol:
            continue
        ScraperCls, url = SCRAPERS[name]
        if name == "sgi":
            logger.info("Fetching SGI (BRVM brokers) from Rich Bourse (list + detail pages)")
            try:
                data = fetch_and_save_sgi()
                results[name] = _to_json_safe(data)
                if not args.json:
                    logger.info("  -> %s", _summary(data, name))
            except Exception as e:
                logger.exception("SGI fetch failed: %s", e)
                results[name] = {"error": str(e), "source": name, "url": url}
            continue
        display_url = f"{url}/{args.symbol}" if name == "richbourse_timeseries" and args.symbol else url
        extra = f", period={args.period}" if name == "sikafinance" else (
            f", period={args.period}, progression={args.progression}" if name == "richbourse" else (
                f", symbol={args.symbol}" if name == "richbourse_timeseries" else ""
            )
        )
        logger.info("Scraping %s (%s) (sleep=%.1fs%s)", name, display_url, sleep, extra)
        try:
            kwargs: dict[str, Any] = {"sleep_seconds": sleep}
            if name == "sikafinance":
                if args.period not in SIKAFINANCE_PERIODS:
                    logger.warning(
                        "Period %r is not valid for sikafinance — it will silently fall back to 'veille'. "
                        "Valid periods: %s",
                        args.period, ", ".join(SIKAFINANCE_PERIODS),
                    )
                kwargs["period"] = args.period
            elif name == "richbourse":
                if args.period not in RICHBOURSE_PERIODS:
                    logger.warning(
                        "Period %r is not valid for richbourse — it will silently fall back to 'veille'. "
                        "Valid periods: %s",
                        args.period, ", ".join(RICHBOURSE_PERIODS),
                    )
                kwargs["period"] = args.period
                kwargs["progression"] = args.progression
            elif name == "richbourse_timeseries":
                kwargs["symbol"] = args.symbol or "NTLC"
            scraper = ScraperCls(**kwargs)
            data = scraper.scrape()
            results[name] = _to_json_safe(data)
            if not args.json:
                logger.info("  -> %s", _summary(data, name))
        except Exception as e:
            logger.exception("Scraper %s failed: %s", name, e)
            results[name] = {"error": str(e), "source": name, "url": url}

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _to_json_safe(obj: Any) -> Any:
    """Recursively replace \\xa0 with empty string so JSON output is clean."""
    if isinstance(obj, str):
        return obj.replace("\xa0", "")
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(v) for v in obj]
    return obj


def _summary(data: dict, site: str) -> str:
    """Custom summary per site."""
    if site == "sikafinance":
        n = len(data.get("brvm_stocks") or [])
        period = data.get("period", "veille")
        return f"brvm_stocks={n} (period={period})" if n else f"no structured data (period={period})"
    if site == "richbourse":
        parts = []
        if data.get("stocks"):
            parts.append(f"stocks={len(data['stocks'])}")
        if data.get("date"):
            parts.append(f"date={data['date']}")
        if data.get("period"):
            parts.append(f"period={data['period']}")
        if data.get("progression"):
            parts.append(f"progression={data['progression']}")
        return ", ".join(parts) if parts else "no structured data"
    if site == "richbourse_timeseries":
        if data.get("error"):
            return f"error={data['error']}"
        parts = []
        if data.get("csv_path"):
            parts.append(f"csv={data['csv_path']}")
        if data.get("date_range"):
            parts.append(f"range={' to '.join(data['date_range'])}")
        if data.get("rows") is not None:
            parts.append(f"rows={data['rows']}")
        return ", ".join(parts) if parts else "no data"
    if site == "brvm":
        parts = []
        if data.get("indices"):
            parts.append(f"indices={len(data['indices'])}")
        if data.get("stocks"):
            parts.append(f"stocks={len(data['stocks'])}")
        return ", ".join(parts) if parts else "no structured data"
    if site == "sgi":
        return f"path={data.get('path', '')}, count={data.get('count', 0)} SGI"
    # Generic fallback
    parts = []
    for key in ("indices", "stocks", "brvm_stocks", "top_gains", "top_losses"):
        if data.get(key):
            parts.append(f"{key}={len(data[key])}")
    return ", ".join(parts) or "no structured data"


if __name__ == "__main__":
    sys.exit(main())
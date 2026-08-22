"""
Fetch BRVM company details from Sika Finance for all valid symbols and save locally.

Usage:
  python run_company_details_fetch.py
  python run_company_details_fetch.py --force
  python run_company_details_fetch.py --symbol BOAM --symbol NTLC
  python run_company_details_fetch.py --no-tabs   # societe page only, no COURS/ANALYSE/SECTEUR tabs

Data is written to app/data/company_details/{SYMBOL}.json. A symbol is skipped
when its cached JSON is fresher than COMPANY_DETAILS_REFRESH_DAYS (default 7),
unless --force is passed. Run periodically (e.g. weekly); company fundamentals
do not change frequently. Unless --no-tabs (or SIKA_TABS_ENABLED=false), each fetch
also pulls the Sika COURS/ANALYSE/SECTEUR tabs via Tavily; the SECTEUR tab is fetched
once per Excel sector (its grouping matches Sika's "BRVM - X" sectors) and reused
for the other symbols of that sector.

Source: https://www.sikafinance.com/marches/societe/{SYMBOL}.{country_code}
"""
import argparse
import importlib.util
import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_company = _load_module("sikafinance_company", _ROOT / "app" / "scrapers" / "sikafinance_company.py")
_brvm = _load_module("brvm_companies", _ROOT / "app" / "utils" / "brvm_companies.py")
fetch_and_save_company_details = _company.fetch_and_save_company_details
COMPANY_DETAILS_DIR = _company.DATA_DIR
get_valid_symbols = _brvm.get_valid_symbols
get_country_code_for_symbol = _brvm.get_country_code_for_symbol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _is_fresh(path: Path, refresh_days: float) -> bool:
    """True when the cached JSON exists and is younger than refresh_days."""
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds < refresh_days * 86400


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and save BRVM company details from Sika Finance.")
    parser.add_argument(
        "--symbol", action="append", default=None,
        help="Fetch only this symbol (repeatable). Default: all valid BRVM symbols.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh even when the cached JSON is still fresh.")
    parser.add_argument(
        "--no-tabs", action="store_true",
        help="Skip the COURS/ANALYSE/SECTEUR tab enrichment (fetch the societe page only).",
    )
    args = parser.parse_args()

    refresh_days = getattr(config, "COMPANY_DETAILS_REFRESH_DAYS", 7)
    sleep_seconds = getattr(config, "SLEEP_SECONDS", 2)
    include_tabs = not args.no_tabs
    # Per-run SECTEUR dedupe: sector name -> fetched block (see _merge_tab_data).
    sector_cache: dict = {}

    if args.symbol:
        symbols = sorted({(s or "").strip().upper() for s in args.symbol if (s or "").strip()})
    else:
        symbols = sorted(get_valid_symbols())
    if not symbols:
        logger.error("No symbols to fetch.")
        return 1

    refreshed = skipped = failed = fetched = tab_blocks = 0
    for symbol in symbols:
        path = COMPANY_DETAILS_DIR / f"{symbol}.json"
        if not args.force and _is_fresh(path, refresh_days):
            skipped += 1
            logger.info("%s: skipped (cached data < %s days old)", symbol, refresh_days)
            continue
        if fetched:
            time.sleep(sleep_seconds)  # pause between fetches
        fetched += 1
        country_code = get_country_code_for_symbol(symbol)
        try:
            data = fetch_and_save_company_details(
                symbol, country_code, include_tabs=include_tabs, sector_cache=sector_cache,
            )
        except Exception as e:
            logger.warning("%s: fetch failed: %s", symbol, e)
            failed += 1
            continue
        if data.get("error"):
            logger.warning("%s: fetch failed: %s", symbol, data["error"])
            failed += 1
            continue
        refreshed += 1
        tab_blocks += sum(1 for k in ("market", "technical_analysis", "sector") if k in data)
        logger.info("%s: saved (%s)", symbol, data.get("company_name") or "ok")

    logger.info(
        "Summary: %d refreshed, %d skipped, %d failed, %d tab blocks fetched (of %d symbols)",
        refreshed, skipped, failed, tab_blocks, len(symbols),
    )
    # Non-zero only when every attempted fetch failed.
    return 1 if failed and not refreshed else 0


if __name__ == "__main__":
    sys.exit(main())

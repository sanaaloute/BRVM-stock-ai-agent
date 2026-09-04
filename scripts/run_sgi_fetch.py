"""
Fetch BRVM SGI (broker) data from Rich Bourse (list + detail pages) and save locally.

Usage:
  python run_sgi_fetch.py
  python run_sgi_fetch.py --json

Data is written to app/data/sgi_brvm.json. Run periodically (e.g. monthly);
SGI information does not change frequently.

Source: https://www.richbourse.com/common/apprendre/liste-sgi
"""
import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location("sgi_brvm", _ROOT / "app" / "scrapers" / "sgi_brvm.py")
_sgi_brvm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sgi_brvm)
fetch_and_save_sgi = _sgi_brvm.fetch_and_save_sgi
load_sgi_local = _sgi_brvm.load_sgi_local
SGI_JSON_PATH = _sgi_brvm.SGI_JSON_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and save BRVM SGI (broker) data.")
    parser.add_argument("--json", action="store_true", help="Print saved data as JSON to stdout")
    parser.add_argument("--path", default=None, help="Override output path (default: app/data/sgi_brvm.json)")
    args = parser.parse_args()

    try:
        result = fetch_and_save_sgi(save_path=args.path)
        logger.info("Done: %s", result)
        if args.json:
            path = args.path or result.get("path") or SGI_JSON_PATH
            data = load_sgi_local(path=path)
            print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.exception("SGI fetch failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Rich Bourse time-series scraper: fetch chart data (Highcharts) for a symbol and save to CSV.

URL: https://www.richbourse.com/common/mouvements/index/{symbol}
CSV: data/series/{symbol}_{min_date}_{max_date}.csv
Columns: Date,Price,Open,High,Low,Volume (Price = close; Open/High/Low/Volume
empty when the page exposes no OHLC/volume series).
"""
import csv
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.http_client import http_get
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.richbourse.com/common/mouvements/index"
DATA_SERIES_DIR = Path(__file__).resolve().parent.parent / "data" / "series"


def extract_highcharts_series(html: str) -> list[list[int | float]] | None:
    """Extract first Highcharts data array [[timestamp_ms, value], ...] from page."""
    pattern = r"\?\s*(\[\[.*?\]\])\s*:"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(1))


def extract_highcharts_ohlcv(html: str) -> dict[str, Any] | None:
    """Extract the richest OHLCV series from all Highcharts data arrays on the page.

    The mouvements page embeds several charts (line, OHLC, candlestick), each with
    a price series immediately followed by a volume series (``name: "Volume"`` in
    the ~300 chars preceding the data array). Price points are either
    ``[ts_ms, close]`` or ``[ts_ms, open, high, low, close]``.

    Returns ``{"points": [...], "volumes": [...] | None}``: points is the first
    5-element (OHLC) price series found, else the first 2-element (close-only)
    one; volumes is the nearest volume series after it on the page, dropped when
    it does not align with the price points (same count, same first timestamp).
    Falls back to the first data array (close only) when no series could be
    classified. None when the page has no usable data array at all.
    """
    pattern = r"\?\s*(\[\[.*?\]\])\s*:"
    candidates: list[tuple[list, bool]] = []  # (data array, is_volume)
    for match in re.finditer(pattern, html, re.DOTALL):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(data, list) or not data:
            continue
        context = html[max(0, match.start() - 300):match.start()]
        candidates.append((data, 'name: "Volume"' in context))
    if not candidates:
        return None

    def point_arity(data: list) -> int:
        for point in data:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                return len(point)
        return 0

    price_idx: int | None = None
    for wanted in (5, 2):  # prefer OHLC points, fall back to close-only
        for i, (data, is_volume) in enumerate(candidates):
            if not is_volume and point_arity(data) == wanted:
                price_idx = i
                break
        if price_idx is not None:
            break

    if price_idx is None:
        # Classification found nothing: legacy behavior (first array, close only).
        return {"points": candidates[0][0], "volumes": None}

    points = candidates[price_idx][0]
    volumes = None
    for data, is_volume in candidates[price_idx + 1:]:
        if not is_volume:
            continue
        first_price = next((p for p in points if isinstance(p, (list, tuple)) and p), None)
        first_vol = next((p for p in data if isinstance(p, (list, tuple)) and p), None)
        if (
            first_price is not None and first_vol is not None
            and len(data) == len(points) and first_vol[0] == first_price[0]
        ):
            volumes = data
        break  # nearest volume series only; drop it rather than misalign
    return {"points": points, "volumes": volumes}


class RichBourseTimeseriesScraper(BaseScraper):
    """Fetch mouvement page for a symbol, extract time series from Highcharts, save to CSV."""

    def __init__(
        self,
        symbol: str,
        api_key: str | None = None,
        sleep_seconds: float | None = None,
        output_dir: Path | str | None = None,
    ):
        super().__init__(api_key=api_key, sleep_seconds=sleep_seconds)
        self._symbol = (symbol or "").strip().upper()
        self._output_dir = Path(output_dir) if output_dir else DATA_SERIES_DIR

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self._symbol}"

    def scrape(self) -> dict[str, Any]:
        """Fetch page, extract series, write CSV to data/series/{symbol}_{min_date}_{max_date}.csv."""
        out: dict[str, Any] = {
            "source": "richbourse_timeseries",
            "url": self.url,
            "symbol": self._symbol,
            "csv_path": None,
            "date_range": None,
            "rows": 0,
            "error": None,
        }
        if not self._symbol:
            out["error"] = "Le symbole est requis."
            return out

        try:
            self._sleep()
            resp = http_get(
                self.url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"},
            )
            resp.raise_for_status()
            self._sleep()
            html = resp.text
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", self.url, e)
            out["error"] = str(e)
            return out

        extracted = extract_highcharts_ohlcv(html)
        if not extracted or not extracted.get("points"):
            out["error"] = "Aucune série Highcharts trouvée."
            return out

        points = extracted["points"]
        volume_by_ts: dict[Any, Any] = {}
        for item in extracted.get("volumes") or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                volume_by_ts[item[0]] = item[1]

        records = []
        for item in points:
            if not isinstance(item, (list, tuple)) or len(item) not in (2, 5):
                continue
            timestamp_ms = item[0]
            # Highcharts timestamps are UTC milliseconds
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            if len(item) == 5:  # [ts_ms, open, high, low, close]
                record = {
                    "date": dt, "price": item[4],
                    "open": item[1], "high": item[2], "low": item[3],
                }
            else:  # [ts_ms, close]
                record = {"date": dt, "price": item[1], "open": None, "high": None, "low": None}
            record["volume"] = volume_by_ts.get(timestamp_ms)
            records.append(record)

        records.sort(key=lambda r: r["date"])
        if not records:
            out["error"] = "Aucun point de donnée."
            return out

        min_dt = records[0]["date"]
        max_dt = records[-1]["date"]
        min_str = min_dt.strftime("%Y-%m-%d")
        max_str = max_dt.strftime("%Y-%m-%d")
        out["date_range"] = [min_str, max_str]
        out["rows"] = len(records)

        self._output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self._symbol}_{min_str}_{max_str}.csv"
        csv_path = self._output_dir / filename

        # Write to a temp file in the same dir, then atomically move into place,
        # so a concurrent reader never sees a missing or half-written CSV.
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", newline="", encoding="utf-8",
                dir=self._output_dir, prefix=f".{self._symbol}_", suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = Path(f.name)
                w = csv.DictWriter(f, fieldnames=["Date", "Price", "Open", "High", "Low", "Volume"])
                w.writeheader()
                for r in records:
                    w.writerow({
                        "Date": r["date"].strftime("%Y-%m-%d %H:%M:%S"),
                        "Price": r["price"],
                        "Open": r["open"] if r["open"] is not None else "",
                        "High": r["high"] if r["high"] is not None else "",
                        "Low": r["low"] if r["low"] is not None else "",
                        "Volume": r["volume"] if r["volume"] is not None else "",
                    })
            os.replace(tmp_path, csv_path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

        # Remove any old CSV files for this symbol (after the new one is in place)
        # so only the latest remains
        for old_path in self._output_dir.glob(f"{self._symbol}_*.csv"):
            if old_path.name == filename:
                continue
            try:
                old_path.unlink(missing_ok=True)
                logger.debug("Removed old series CSV: %s", old_path.name)
            except OSError as e:
                logger.warning("Could not remove old CSV %s: %s", old_path, e)

        out["csv_path"] = str(csv_path)
        return out

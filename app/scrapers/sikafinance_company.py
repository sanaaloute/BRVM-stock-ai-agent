"""
Fetch BRVM company detail page from Sika Finance: presentation, shareholders, performance (CA, résultat net, dividendes, etc.).

URL pattern: https://www.sikafinance.com/marches/societe/{SYMBOL}.{country_code}
Example: https://www.sikafinance.com/marches/societe/BOAM.ml

Sika Finance blocks direct HTTP clients (Cloudflare 403), so the page is fetched via
Tavily extract (markdown); direct HTTP + BeautifulSoup remains as a fallback.
fetch_and_save_company_details can also merge the COURS/ANALYSE/SECTEUR tabs
(app/scrapers/sikafinance_tabs.py) as market/technical_analysis/sector blocks.

Data is saved to app/data/company_details/{SYMBOL}.json for reuse by the company_details agent.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

import config
from app.scrapers import sikafinance_tabs
from app.utils.brvm_companies import get_symbol_to_sector
from app.utils.http_client import http_get

logger = logging.getLogger(__name__)

SIKAFINANCE_SOCIETE_BASE = "https://www.sikafinance.com/marches/societe"
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "company_details"

# Lines starting with these labels are fields of their own, not dirigeant names:
# they end the "Dirigeants :" continuation block.
_DIRIGEANTS_STOP_PREFIXES = (
    "Téléphone :", "Fax :", "Adresse :", "Nombre de titres :", "Flottant :",
    "Valorisation", "Principaux actionnaires",
)


def _normalize(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()


def _build_url(symbol: str, country_code: str) -> str:
    sym = (symbol or "").strip().upper()
    cc = (country_code or "ci").strip().lower()[:2]
    return f"{SIKAFINANCE_SOCIETE_BASE}/{sym}.{cc}"


# Performance-table row labels (lowercase) -> JSON metric keys.
_PERF_ROW_NAME_MAP = {
    "chiffre d'affaires": "chiffre_affaires", "croissance ca": "croissance_ca",
    "résultat net": "resultat_net", "resultat net": "resultat_net",
    "croissance rn": "croissance_rn", "bnpa": "bnpa", "per": "per", "dividende": "dividende",
}

# Below this size a Tavily extract is treated as a failure (block page, empty page).
_MIN_TAVILY_CONTENT_LEN = 300


def _fetch_tavily_markdown(url: str) -> str:
    """Fetch page markdown via Tavily extract. Sika Finance 403s every direct HTTP
    client (Cloudflare), so Tavily is the primary channel. Returns "" on any failure
    so the caller can fall back to direct HTTP."""
    if not getattr(config, "TAVILY_API_KEY", ""):
        return ""
    try:
        from tavily import TavilyClient
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = TavilyClient(api_key=config.TAVILY_API_KEY).extract(urls=[url])
        results = (resp or {}).get("results") or []
        content = ""
        if results and isinstance(results[0], dict):
            content = (results[0].get("raw_content") or results[0].get("content") or "").strip()
        if len(content) < _MIN_TAVILY_CONTENT_LEN:
            if content:
                logger.warning("Tavily content too short for %s (%d chars)", url, len(content))
            return ""
        return content
    except Exception as e:
        logger.warning("Tavily extract failed for %s: %s", url, e)
        return ""


def _markdown_to_lines(content: str) -> list[str]:
    """Normalize Tavily markdown to plain text lines: "**Label :**" -> "Label :",
    images dropped, links reduced to their text, heading '#' stripped.
    Markdown table rows pass through unchanged."""
    lines: list[str] = []
    for raw in (content or "").split("\n"):
        ln = raw.replace("**", "")
        ln = ln.replace("\\*", "*")  # markdown-escaped '*' (shareholders "NAME\*61,39;...")
        ln = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", ln)  # drop images
        ln = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", ln)  # links -> link text
        ln = ln.strip()
        if ln.startswith("#"):
            ln = ln.lstrip("#").strip()
        ln = _normalize(ln)
        if ln:
            lines.append(ln)
    return lines


def _parse_lines(lines: list[str], out: dict[str, Any]) -> None:
    """Fill company_name/code/presentation/contact/shareholders from normalized text lines."""
    # Title: "BANK OF AFRICA MALI, chiffres clés..." / "... fiche société"
    # (wide window: Tavily markdown starts with navigation junk before the title).
    for ln in lines[:60]:
        if "chiffres clés" in ln.lower() or "fiche société" in ln.lower():
            out["company_name"] = ln.split(",")[0].strip() if "," in ln else ln
            break

    # Code line: "ML0000000520 - BOAM"
    for ln in lines:
        if re.match(r"^[A-Z]{2}\d+\s*-\s*[A-Z]+", ln):
            out["code"] = ln
            break

    # Presentation: long paragraph starting with "La société :"
    for i, ln in enumerate(lines):
        if ln.startswith("La société :") or "ouverte au public" in ln.lower():
            out["presentation"] = ln
            # may continue on next lines
            j = i + 1
            while j < len(lines) and not lines[j].startswith("Téléphone") and not lines[j].startswith("Fax") and len(lines[j]) > 20:
                out["presentation"] += " " + lines[j]
                j += 1
            break

    # Téléphone, Fax, Adresse, Dirigeants
    for i, ln in enumerate(lines):
        if ln.startswith("Téléphone :"):
            out["phone"] = ln.replace("Téléphone :", "").strip()
        elif ln.startswith("Fax :"):
            out["fax"] = ln.replace("Fax :", "").strip()
        elif ln.startswith("Adresse :"):
            out["address"] = ln.replace("Adresse :", "").strip()
        elif ln.startswith("Dirigeants :"):
            out["dirigeants"] = ln.replace("Dirigeants :", "").strip()
            j = i + 1
            while (
                j < len(lines)
                and (lines[j].startswith("Président") or lines[j].startswith("Directeur") or ":" in lines[j])
                and not lines[j].startswith(_DIRIGEANTS_STOP_PREFIXES)
            ):
                out["dirigeants"] += " " + lines[j]
                j += 1
        elif ln.startswith("Nombre de titres :"):
            out["nombre_titres"] = _normalize(ln.replace("Nombre de titres :", ""))
        elif ln.startswith("Flottant :"):
            out["flottant"] = _normalize(ln.replace("Flottant :", ""))
        elif ln.startswith("Valorisation de la société :"):
            out["valorisation"] = _normalize(ln.replace("Valorisation de la société :", ""))

    # Principaux actionnaires: "BOA WEST AFRICA*61,39;DIVERS MALIENS*17,71;..."
    for i, ln in enumerate(lines):
        if "Principaux actionnaires" in ln:
            if i + 1 < len(lines):
                raw = lines[i + 1]
                if "*" in raw:
                    # Split on ";" only: "," is the French decimal separator in the pct
                    for part in raw.split(";"):
                        part = _normalize(part)
                        m = re.search(r"\*([\d\s]+[.,]?\d*)", part)
                        if m:
                            name = _normalize(part[: m.start()])
                            out["shareholders"].append({"name": name, "pct": _normalize(m.group(1))})
            break


def _table_cells(row_ln: str) -> list[str]:
    """Split a markdown table row into stripped cells. Interior empty cells are kept
    (they carry year-column alignment, e.g. "| Croissance CA |  | -0,29% | ...");
    only the artifacts of the leading/trailing pipes are dropped."""
    parts = [c.strip() for c in row_ln.split("|")]
    while parts and not parts[0]:
        parts.pop(0)
    while parts and not parts[-1]:
        parts.pop()
    return parts


def _parse_performance_from_lines(lines: list[str], out: dict[str, Any]) -> None:
    """Markdown performance table: "|  | 2021 | 2022 | ..." header (leading empty
    cell tolerated) followed by "| Chiffre d'affaires | 35 408 | ..." rows."""
    if out["performance"]:
        return
    for i, ln in enumerate(lines):
        if re.match(r"^\|(\s*\|)?\s*\d{4}\s*\|", ln):
            years = re.findall(r"\d{4}", ln)
            for j in range(i + 1, min(i + 15, len(lines))):
                row_ln = lines[j]
                if not row_ln.startswith("|") or "---" in row_ln:
                    continue
                cells = _table_cells(row_ln)
                if len(cells) < 2:
                    continue
                row_name = cells[0].lower()
                key = _PERF_ROW_NAME_MAP.get(row_name) or re.sub(r"[^\w]+", "_", row_name).strip("_")
                if key not in out["performance"]:
                    out["performance"][key] = {}
                for yi, yr in enumerate(years):
                    if yi + 1 < len(cells):
                        out["performance"][key][yr] = _normalize(cells[yi + 1])
            break


def _parse_tavily_markdown(content: str, out: dict[str, Any]) -> None:
    """Parse a Tavily markdown societe page into out (separate helper so tests can
    drive it offline)."""
    lines = _markdown_to_lines(content)
    _parse_lines(lines, out)
    _parse_performance_from_lines(lines, out)


def fetch_company_page(symbol: str, country_code: str) -> dict[str, Any]:
    """
    Fetch one company detail page from Sika Finance and return structured data.
    """
    url = _build_url(symbol, country_code)
    out: dict[str, Any] = {
        "symbol": (symbol or "").strip().upper(),
        "country_code": (country_code or "ci").strip().lower()[:2],
        "source_url": url,
        "company_name": "",
        "code": "",  # e.g. ML0000000520 - BOAM
        "presentation": "",
        "phone": "",
        "fax": "",
        "address": "",
        "dirigeants": "",
        "nombre_titres": "",
        "flottant": "",
        "valorisation": "",
        "shareholders": [],  # list of {name, pct}
        "performance": {},  # metric -> {year: value}, e.g. chiffre_affaires -> {"2020": "32 348", ...}
    }

    # Primary channel: Tavily extract (direct HTTP is Cloudflare-blocked with 403).
    content = _fetch_tavily_markdown(url)
    if content:
        _parse_tavily_markdown(content, out)
        return out

    # Fallback: direct HTTP + BeautifulSoup (kept in case the block is lifted).
    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Sika Finance company page fetch failed %s: %s", url, e)
        out["error"] = str(e)
        return out

    text = soup.get_text(separator="\n")
    lines = [ _normalize(ln) for ln in text.split("\n") if _normalize(ln) ]
    _parse_lines(lines, out)

    # Performance table: parse HTML tables first
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        cells0 = rows[0].find_all(["td", "th"])
        years_cells = [ _normalize(c.get_text() or "") for c in cells0 ]
        years = [y for y in years_cells if re.match(r"^20\d{2}$", y)]
        if not years:
            continue
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            row_label = _normalize((cells[0].get_text() or "").lower())
            if not row_label:
                continue
            key = _PERF_ROW_NAME_MAP.get(row_label) or re.sub(r"[^\w]+", "_", row_label).strip("_")
            if key not in out["performance"]:
                out["performance"][key] = {}
            for yi, yr in enumerate(years):
                if yi + 1 < len(cells):
                    out["performance"][key][yr] = _normalize(cells[yi + 1].get_text() or "")
        if out["performance"]:
            break

    # Fallback: parse from text lines (e.g. markdown-style)
    _parse_performance_from_lines(lines, out)

    return out


def save_company_details(symbol: str, data: dict[str, Any], save_dir: Path | None = None) -> Path:
    """Save company detail dict to app/data/company_details/{SYMBOL}.json."""
    dir_path = save_dir or DATA_DIR
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    sym = (symbol or "").strip().upper()
    path = dir_path / f"{sym}.json"
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
    logger.info("Company details saved: %s", path)
    return path


def load_company_details(symbol: str, load_dir: Path | None = None) -> dict[str, Any] | None:
    """Load company details from app/data/company_details/{SYMBOL}.json. Returns None if missing."""
    dir_path = load_dir or DATA_DIR
    path = Path(dir_path) / f"{(symbol or '').strip().upper()}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load company details %s: %s", path, e)
        return None


def _merge_tab_data(data: dict[str, Any], symbol: str, country_code: str,
                    sector_cache: dict[str, dict[str, Any]] | None = None) -> None:
    """Enrich a fetched company dict with the Sika COURS/ANALYSE/SECTEUR tabs.

    Adds "market" / "technical_analysis" / "sector" (each with a "fetched_at" ISO
    timestamp). A tab that fails is simply omitted (debug log); the societe data
    must still be saved. sector_cache: per-run dict keyed on the Excel sector
    (app/utils/brvm_companies.py Sector column, whose grouping matches Sika's
    "BRVM - X" sectors); symbols of an already-fetched sector reuse its block.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        cotation = sikafinance_tabs.fetch_cotation(symbol, country_code)
    except Exception as e:
        logger.debug("Cotation tab failed for %s: %s", symbol, e)
        cotation = None
    if cotation:
        cotation["fetched_at"] = now
        data["market"] = cotation

    try:
        analyse = sikafinance_tabs.fetch_analyse(symbol, country_code)
    except Exception as e:
        logger.debug("Analyse tab failed for %s: %s", symbol, e)
        analyse = None
    if analyse:
        analyse["fetched_at"] = now
        data["technical_analysis"] = analyse

    excel_sector = ""
    if sector_cache is not None:
        try:
            excel_sector = get_symbol_to_sector().get((symbol or "").strip().upper(), "")
        except Exception:
            excel_sector = ""
    if sector_cache is not None and excel_sector and excel_sector in sector_cache:
        logger.debug("%s: sector block reused from cache (%s)", symbol, excel_sector)
        data["sector"] = sector_cache[excel_sector]
        return
    try:
        secteur = sikafinance_tabs.fetch_secteur(symbol, country_code)
    except Exception as e:
        logger.debug("Secteur tab failed for %s: %s", symbol, e)
        secteur = None
    if secteur:
        secteur["fetched_at"] = now
        data["sector"] = secteur
        if sector_cache is not None and excel_sector:
            sector_cache[excel_sector] = secteur


def fetch_and_save_company_details(symbol: str, country_code: str, save_dir: Path | None = None,
                                   include_tabs: bool = True,
                                   sector_cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fetch company page from Sika Finance and save to app/data/company_details/{SYMBOL}.json.

    When include_tabs and config.SIKA_TABS_ENABLED, also merges the COURS/ANALYSE/SECTEUR
    tabs (market / technical_analysis / sector blocks) before saving."""
    data = fetch_company_page(symbol, country_code)
    if "error" not in data:
        if include_tabs and getattr(config, "SIKA_TABS_ENABLED", True):
            _merge_tab_data(data, data["symbol"], data["country_code"], sector_cache=sector_cache)
        save_company_details(symbol, data, save_dir=save_dir)
    return data

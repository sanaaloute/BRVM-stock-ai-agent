"""
Fetch BRVM company detail page from Sika Finance: presentation, shareholders, performance (CA, résultat net, dividendes, etc.).

URL pattern: https://www.sikafinance.com/marches/societe/{SYMBOL}.{country_code}
Example: https://www.sikafinance.com/marches/societe/BOAM.ml

Data is saved to app/data/company_details/{SYMBOL}.json for reuse by the company_details agent.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

import config
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

    # Title: "BANK OF AFRICA MALI, chiffres clés..."
    for ln in lines[:5]:
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
    for ln in lines:
        if "Principaux actionnaires" in ln:
            idx = lines.index(ln)
            if idx + 1 < len(lines):
                raw = lines[idx + 1]
                if "*" in raw:
                    # Split on ";" only: "," is the French decimal separator in the pct
                    for part in raw.split(";"):
                        part = _normalize(part)
                        m = re.search(r"\*([\d\s]+[.,]?\d*)", part)
                        if m:
                            name = _normalize(part[: m.start()])
                            out["shareholders"].append({"name": name, "pct": _normalize(m.group(1))})
            break

    # Performance table: parse HTML tables first
    row_name_map = {
        "chiffre d'affaires": "chiffre_affaires", "croissance ca": "croissance_ca",
        "résultat net": "resultat_net", "resultat net": "resultat_net",
        "croissance rn": "croissance_rn", "bnpa": "bnpa", "per": "per", "dividende": "dividende",
    }
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
            key = row_name_map.get(row_label) or re.sub(r"[^\w]+", "_", row_label).strip("_")
            if key not in out["performance"]:
                out["performance"][key] = {}
            for yi, yr in enumerate(years):
                if yi + 1 < len(cells):
                    out["performance"][key][yr] = _normalize(cells[yi + 1].get_text() or "")
        if out["performance"]:
            break

    # Fallback: parse from text lines (e.g. markdown-style)
    if not out["performance"]:
        for i, ln in enumerate(lines):
            if re.match(r"^\|\s*\d{4}\s*\|", ln):
                years = re.findall(r"\d{4}", ln)
                for j in range(i + 1, min(i + 15, len(lines))):
                    row_ln = lines[j]
                    if not row_ln.startswith("|") or "---" in row_ln:
                        continue
                    cells = [c.strip() for c in row_ln.split("|") if c.strip()]
                    if len(cells) < 2:
                        continue
                    row_name = cells[0].lower()
                    key = row_name_map.get(row_name) or re.sub(r"[^\w]+", "_", row_name).strip("_")
                    if key not in out["performance"]:
                        out["performance"][key] = {}
                    for yi, yr in enumerate(years):
                        if yi + 1 < len(cells):
                            out["performance"][key][yr] = _normalize(cells[yi + 1])
                break

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


def fetch_and_save_company_details(symbol: str, country_code: str, save_dir: Path | None = None) -> dict[str, Any]:
    """Fetch company page from Sika Finance and save to app/data/company_details/{SYMBOL}.json."""
    data = fetch_company_page(symbol, country_code)
    if "error" not in data:
        save_company_details(symbol, data, save_dir=save_dir)
    return data

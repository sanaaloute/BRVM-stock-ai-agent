"""
Fetch Sika Finance per-company tab pages (COURS, ANALYSE ET CONSEILS, SECTEUR) via Tavily extract.

Sika Finance blocks all non-browser HTTP clients (Cloudflare 403), so Tavily extract
is the only working channel. Each fetcher returns None on failure (never raises into
callers) and parses the markdown `raw_content` Tavily returns.

URL patterns ({SYM} uppercase symbol, {cc} lowercase 2-letter country code):
  cotation: https://www.sikafinance.com/marches/cotation_{SYM}.{cc}
  analyse:  https://www.sikafinance.com/analyses/conseil/{SYM}.{cc}
  secteur:  https://www.sikafinance.com/marches/secteur/{SYM}.{cc}
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from tavily import TavilyClient

import config

logger = logging.getLogger(__name__)

SIKAFINANCE_BASE = "https://www.sikafinance.com"
SLEEP = getattr(config, "SLEEP_SECONDS", 2)

# Below this size a Tavily extract is considered a failure (block page, empty page).
_MIN_CONTENT_LEN = 100

# Range-table row labels -> JSON keys ("| 1 semaine | ... |" -> "1_semaine").
_RANGE_KEYS = {
    "1 semaine": "1_semaine",
    "1 mois": "1_mois",
    "1er janvier": "1er_janvier",
    "1 an": "1_an",
    "3 ans": "3_ans",
    "5 ans": "5_ans",
}

# Analyse tab section headers -> signal groups.
_GROUP_KEYWORDS = (
    ("tendance", "tendance"),
    ("momentum", "momentum"),
    ("oscillateurs", "oscillateurs"),
    ("chandeliers", "volumes_chandeliers"),  # "Volumes et Chandeliers Japonais"
)

_ARROW_DIRECTIONS = (
    ("fleche_up", "up"),
    ("fleche_down", "down"),
    ("fleche_neu", "neutral"),
)


def _parse_fr(value: Any) -> float | None:
    """Parse a French-formatted number ("32 348", "1 234,56", NBSP/narrow-NBSP variants).

    Spaces/NBSP are thousands separators, comma is the decimal separator, a trailing
    "%" is tolerated. Returns None for empty/unparseable input instead of raising.
    (Local copy of the scoring service's _parse_fr_number: scrapers must not import
    from services.)
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\xa0", " ").replace("\u202f", " ")
    s = s.replace(" ", "").replace(",", ".").rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _build_url(path_template: str, symbol: str, country_code: str) -> str:
    sym = (symbol or "").strip().upper()
    cc = (country_code or "ci").strip().lower()[:2]
    return f"{SIKAFINANCE_BASE}{path_template.format(sym=sym, cc=cc)}"


def _extract(url: str) -> str:
    """Fetch one page via Tavily extract and return its markdown raw_content ("" on failure)."""
    if SLEEP > 0:
        time.sleep(SLEEP)
    resp = TavilyClient(api_key=config.TAVILY_API_KEY).extract(urls=[url])
    results = (resp or {}).get("results") or []
    if not results:
        return ""
    first = results[0]
    if not isinstance(first, dict):
        return ""
    return (first.get("raw_content") or first.get("content") or "").strip()


def _fetch_tab(path_template: str, symbol: str, country_code: str) -> str:
    """Extract one tab page; returns "" when unavailable (logged, never raised)."""
    url = _build_url(path_template, symbol, country_code)
    if not getattr(config, "TAVILY_API_KEY", ""):
        logger.warning("TAVILY_API_KEY is not set; skipping %s", url)
        return ""
    try:
        content = _extract(url)
    except Exception as e:
        logger.warning("Tavily extract failed for %s: %s", url, e)
        return ""
    if len(content) < _MIN_CONTENT_LEN:
        logger.warning("Tavily content too short for %s (%d chars)", url, len(content))
        return ""
    return content


def _cells(line: str) -> list[str]:
    """Split a markdown table row into stripped cells (bold ** removed). Interior
    empty cells are kept (column alignment); only the artifacts of the
    leading/trailing pipes are dropped."""
    parts = [c.strip() for c in line.replace("**", "").split("|")]
    while parts and not parts[0]:
        parts.pop(0)
    while parts and not parts[-1]:
        parts.pop()
    return parts


# ---------------------------------------------------------------------------
# COURS tab
# ---------------------------------------------------------------------------
def fetch_cotation(symbol: str, country_code: str) -> dict[str, Any] | None:
    """Parse the COURS tab: beta/RSI snapshot, day OHLC, price ranges, dividend history.

    Returns None when the tab cannot be fetched or nothing could be parsed.
    """
    content = _fetch_tab("/marches/cotation_{sym}.{cc}", symbol, country_code)
    if not content:
        return None

    day: dict[str, float | None] = {
        "ouverture": None, "plus_haut": None, "plus_bas": None,
        "cloture_veille": None, "volume_titres": None, "volume_fcfa": None,
    }
    out: dict[str, Any] = {
        "beta_1an": None,
        "rsi_14": None,
        "capital_echange_pct": None,
        "valorisation_millions": None,
        "day": day,
        "ranges": {},
        "dividend_history": [],
    }
    in_dividend_table = False
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if not cells or "---" in line:
            continue
        label = cells[0].lower()
        # Dividend history: starts after the "| Année | Montant | Rendement |" header.
        if label in ("année", "annee") and len(cells) >= 3:
            in_dividend_table = True
            continue
        if in_dividend_table:
            if re.match(r"^\d{4}$", cells[0]) and len(cells) >= 3:
                montant = _parse_fr(cells[1])
                if montant is not None:
                    out["dividend_history"].append({
                        "year": int(cells[0]),
                        "montant": montant,
                        "rendement_pct": _parse_fr(cells[2]),
                    })
                continue
            in_dividend_table = False  # first non-year row ends the table
        # Range rows: "| 1 semaine | 36 980 | 31 900 | 15,92% |"
        if label in _RANGE_KEYS and len(cells) >= 4:
            plus_haut = _parse_fr(cells[1])
            plus_bas = _parse_fr(cells[2])
            variation = _parse_fr(cells[3])
            if plus_haut is not None or plus_bas is not None or variation is not None:
                out["ranges"][_RANGE_KEYS[label]] = {
                    "plus_haut": plus_haut,
                    "plus_bas": plus_bas,
                    "variation_pct": variation,
                }
            continue
        # Two-column label/value rows (day snapshot + beta/RSI/valorisation).
        if len(cells) != 2:
            continue
        value = cells[1]
        if label.startswith("volume"):
            day["volume_titres" if "titre" in label else "volume_fcfa"] = _parse_fr(value)
        elif label == "ouverture":
            day["ouverture"] = _parse_fr(value)
        elif label == "plus haut":
            day["plus_haut"] = _parse_fr(value)
        elif label == "plus bas":
            day["plus_bas"] = _parse_fr(value)
        elif label.startswith("clôture") or label.startswith("cloture"):
            day["cloture_veille"] = _parse_fr(value)
        elif label.startswith("beta"):
            out["beta_1an"] = _parse_fr(value)
        elif label == "rsi":
            out["rsi_14"] = _parse_fr(value)
        elif label.startswith("capital échangé") or label.startswith("capital echange"):
            out["capital_echange_pct"] = _parse_fr(value)
        elif label == "valorisation":
            # "3 698 000 M" / "178 151 MFCFA" -> millions of FCFA
            raw = re.sub(r"(?i)\s*(mfcfa|fcfa|mds|m)\s*$", "", value)
            out["valorisation_millions"] = _parse_fr(raw)

    if not (out["ranges"] or out["dividend_history"] or any(v is not None for v in day.values())
            or out["beta_1an"] is not None or out["rsi_14"] is not None):
        logger.warning("Cotation tab parsed empty for %s.%s", symbol, country_code)
        return None
    return out


# ---------------------------------------------------------------------------
# ANALYSE ET CONSEILS tab
# ---------------------------------------------------------------------------
def fetch_analyse(symbol: str, country_code: str) -> dict[str, Any] | None:
    """Parse the ANALYSE tab: technical signals grouped by tendance/momentum/oscillateurs/
    volumes_chandeliers, each with an up/down/neutral direction from the arrow image.

    Returns None when the tab cannot be fetched or holds no signal.
    """
    content = _fetch_tab("/analyses/conseil/{sym}.{cc}", symbol, country_code)
    if not content:
        return None

    signals: list[dict[str, str]] = []
    group: str | None = None
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            header = stripped.lstrip("#").strip().lower()
            for keyword, name in _GROUP_KEYWORDS:
                if keyword in header:
                    group = name
                    break
            continue
        if group is None:
            continue
        direction = next((d for arrow, d in _ARROW_DIRECTIONS if arrow in stripped), None)
        if direction is None:
            continue  # includes the bottom disclaimer paragraph (no arrow image)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", stripped)  # drop the arrow image
        text = " ".join(text.split())
        if text:
            signals.append({"group": group, "direction": direction, "text": text})

    if not signals:
        logger.warning("Analyse tab parsed empty for %s.%s", symbol, country_code)
        return None
    return {
        "signals": signals,
        "up": sum(1 for s in signals if s["direction"] == "up"),
        "down": sum(1 for s in signals if s["direction"] == "down"),
        "neutral": sum(1 for s in signals if s["direction"] == "neutral"),
    }


# ---------------------------------------------------------------------------
# SECTEUR tab
# ---------------------------------------------------------------------------
def fetch_secteur(symbol: str, country_code: str) -> dict[str, Any] | None:
    """Parse the SECTEUR tab: BRVM sector name + peer table (dernier, variations).

    Returns None when the tab cannot be fetched or holds neither name nor peers.
    """
    content = _fetch_tab("/marches/secteur/{sym}.{cc}", symbol, country_code)
    if not content:
        return None

    name = ""
    m = re.search(r"appartient au secteur\s+BRVM\s*-\s*(.+)", content)
    if m:
        name = m.group(1).strip().rstrip("#").strip()

    peers: list[dict[str, Any]] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = _cells(stripped)
        if len(cells) < 8 or cells[0].lower() == "nom":
            continue
        # "| [ONATEL BF](/marches/cotation_ONTBF.bf) | 2 940 | ... | -1.87% | +16,10% |"
        link = re.match(r"\[([^\]]*)\]\(/marches/cotation_([A-Za-z0-9]+)\.[a-z]{2}\)", cells[0])
        peer_name = link.group(1).strip() if link else cells[0]
        peer_symbol = link.group(2).upper() if link else None
        peers.append({
            "symbol": peer_symbol,
            "name": peer_name,
            "dernier": _parse_fr(cells[5]),
            "variation_jour_pct": _parse_fr(cells[6]),
            "variation_ytd_pct": _parse_fr(cells[7]),
        })

    if not name and not peers:
        logger.warning("Secteur tab parsed empty for %s.%s", symbol, country_code)
        return None
    return {"name": name, "peers": peers}

"""Load BRVM companies and symbols from data/BRVM_Companies.xlsx for NLU mapping (avoid hallucination)."""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path relative to app package (app/data/BRVM_Companies.xlsx)
BRVM_COMPANIES_FILE = Path(__file__).resolve().parent.parent / "data" / "BRVM_Companies.xlsx"

# Excel column names: Name, Symbol, Sector, industryCluster, Country
COL_NAME = "Name"
COL_SYMBOL = "Symbol"
COL_SECTOR = "Sector"
COL_INDUSTRY_CLUSTER = "industryCluster"
COL_COUNTRY = "Country"

_symbol_to_name: dict[str, str] = {}
_symbol_to_sector: dict[str, str] = {}
_symbol_to_country: dict[str, str] = {}  # symbol -> 2-letter country code (ml, sn, ci, bj, ...)
_name_to_symbol: dict[str, str] = {}
_valid_symbols: set[str] = set()
_loaded = False

# BRVM country name (from Excel) -> Sika Finance URL suffix (2-letter)
_COUNTRY_TO_CODE: dict[str, str] = {
    "mali": "ml", "sénégal": "sn", "senegal": "sn", "côte d'ivoire": "ci", "cote d'ivoire": "ci",
    "bénin": "bj", "benin": "bj", "burkina faso": "bf", "niger": "ne", "togo": "tg",
    "guinée-bissau": "gw", "guinee-bissau": "gw",
}

# Common words that cause wrong symbol resolution when mapped by single word
_STOP_WORDS = frozenset({
    "bank", "africa", "côte", "d'ivoire", "société", "de", "du", "des", "ci", "internationale",
    "international", "bénin", "burkina", "faso", "mali", "niger", "sénégal", "togo",
})


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize(s: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces for lookup."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(_NON_ALNUM_RE.sub(" ", s).split())


# Stop words in normalized form (accents/punctuation stripped like lookups).
_STOP_WORDS_NORM = frozenset(_normalize(w) for w in _STOP_WORDS)


def _cell_value(v: Any) -> str:
    """Get string value from an openpyxl Cell or a raw value."""
    if v is None:
        return ""
    if hasattr(v, "value"):
        v = getattr(v, "value")
    if v is None:
        return ""
    return str(v).strip()


def _load() -> None:
    global _symbol_to_name, _symbol_to_sector, _symbol_to_country, _name_to_symbol, _valid_symbols, _loaded
    if _loaded:
        return
    _symbol_to_name = {}
    _symbol_to_sector = {}
    _symbol_to_country = {}
    _name_to_symbol = {}
    _valid_symbols = set()
    if not BRVM_COMPANIES_FILE.exists():
        logger.warning("BRVM companies file not found: %s", BRVM_COMPANIES_FILE)
        _loaded = True
        return
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.warning("openpyxl not installed. pip install openpyxl to load BRVM_Companies.xlsx")
        _loaded = True
        return
    try:
        wb = load_workbook(BRVM_COMPANIES_FILE, read_only=True, data_only=True)
        sheet = wb.active
        if sheet is None:
            wb.close()
            _loaded = True
            return
        rows = list(sheet.iter_rows(min_row=1, values_only=False))
        wb.close()
    except Exception as e:
        logger.warning("Failed to load BRVM companies from %s: %s", BRVM_COMPANIES_FILE, e)
        _loaded = True
        return
    if not rows:
        _loaded = True
        return
    # First row: header; match column names (case-insensitive for robustness)
    header = [_cell_value(c) for c in rows[0]]
    col_index: dict[str, int] = {}
    for i, h in enumerate(header):
        key = (h or "").strip()
        if key:
            col_index[key.lower()] = i
    name_col = col_index.get(COL_NAME.lower(), col_index.get("name", -1))
    symbol_col = col_index.get(COL_SYMBOL.lower(), col_index.get("symbol", -1))
    sector_col = col_index.get(COL_SECTOR.lower(), col_index.get("sector", -1))
    industry_col = col_index.get(COL_INDUSTRY_CLUSTER.lower(), -1)
    country_col = col_index.get(COL_COUNTRY.lower(), col_index.get("country", -1))
    if symbol_col < 0 or name_col < 0:
        logger.warning("BRVM_Companies.xlsx: expected columns %r and %r in %s", COL_SYMBOL, COL_NAME, list(col_index))
        _loaded = True
        return
    word_keys: dict[str, str | None] = {}  # single-word index; None once ambiguous
    for row in rows[1:]:
        if not row:
            continue
        cells = list(row)
        symbol = _cell_value(cells[symbol_col]) if symbol_col < len(cells) else ""
        name_part = _cell_value(cells[name_col]) if name_col < len(cells) else ""
        if not symbol:
            continue
        symbol = symbol.upper()
        sector = _cell_value(cells[sector_col]) if sector_col >= 0 and sector_col < len(cells) else ""
        if not sector and industry_col >= 0 and industry_col < len(cells):
            sector = _cell_value(cells[industry_col])
        country_name = _cell_value(cells[country_col]) if country_col >= 0 and country_col < len(cells) else ""
        _valid_symbols.add(symbol)
        _symbol_to_name[symbol] = name_part or symbol
        if sector:
            _symbol_to_sector[symbol] = sector
        if country_name:
            code = _COUNTRY_TO_CODE.get(country_name.strip().lower(), "").strip() or country_name.strip()[:2].lower() if len(country_name.strip()) >= 2 else ""
            if code:
                _symbol_to_country[symbol] = code
        _name_to_symbol[_normalize(name_part)] = symbol
        _name_to_symbol[_normalize(symbol)] = symbol
        # Spaceless key so "SODE CI" and "SODECI" resolve the same way.
        compact = _normalize(name_part).replace(" ", "")
        if compact and compact not in _name_to_symbol:
            _name_to_symbol[compact] = symbol
        for word in (name_part or "").replace(",", " ").replace("|", " ").replace("(", " ").replace(")", " ").split():
            w = word.strip()
            if len(w) >= 3 and w.upper() != symbol:
                nw = _normalize(w)
                if nw in _STOP_WORDS_NORM:
                    continue
                # A word shared by several companies (ecobank, totalenergies...)
                # must not resolve at all rather than guess the wrong one.
                if nw in word_keys and word_keys[nw] != symbol:
                    word_keys[nw] = None
                else:
                    word_keys.setdefault(nw, symbol)
    for nw, symbol in word_keys.items():
        if symbol is not None and nw not in _name_to_symbol:
            _name_to_symbol[nw] = symbol
    _canonicalize_sectors()
    _loaded = True


def _canonicalize_sectors() -> None:
    """One display label per sector: the Excel file mixes accent variants
    (« Energie » / « Énergie »). Group by normalized form (no accents) and
    pick the accented variant, then the most frequent, so every company of a
    sector shares the same label."""
    variants: dict[str, Counter[str]] = {}
    for raw in _symbol_to_sector.values():
        variants.setdefault(_normalize(raw), Counter())[raw] += 1
    canonical: dict[str, str] = {}
    for key, counter in variants.items():
        canonical[key] = sorted(
            counter,
            key=lambda v: (not any(ord(c) > 127 for c in v), -counter[v], v),
        )[0]
    for symbol, raw in _symbol_to_sector.items():
        _symbol_to_sector[symbol] = canonical[_normalize(raw)]


def get_valid_symbols() -> set[str]:
    """Return set of valid BRVM symbols."""
    _load()
    return set(_valid_symbols)


def get_symbol_to_name() -> dict[str, str]:
    """Return mapping symbol -> company name."""
    _load()
    return dict(_symbol_to_name)


def get_symbol_to_sector() -> dict[str, str]:
    """Return mapping symbol -> sector (empty string if not set)."""
    _load()
    return dict(_symbol_to_sector)


def get_symbol_to_country() -> dict[str, str]:
    """Return mapping symbol -> 2-letter country code (ml, sn, ci, bj, etc.) for Sika Finance URLs."""
    _load()
    return dict(_symbol_to_country)


def get_country_code_for_symbol(symbol: str) -> str:
    """Return 2-letter country code for symbol. Default 'ci' (Côte d'Ivoire) if unknown."""
    _load()
    sym = (symbol or "").strip().upper()
    return _symbol_to_country.get(sym, "ci")


def get_name_to_symbol() -> dict[str, str]:
    """Return mapping normalized name -> symbol."""
    _load()
    return dict(_name_to_symbol)


# Common abbreviations (user may type "SMB" for SMBC, etc.)
_ABBREVS: dict[str, str] = {
    "smb": "SMBC",  # SMB Société Minière
}


def resolve_to_symbol(mention: str) -> str | None:
    """
    Resolve user mention (symbol or company name) to official symbol.
    Tolerates case, accents, punctuation and spacing variants ("SODE CI" = "SODECI"),
    partial names ("Société Générale") and small typos ("Sontel").
    Returns None if unknown or ambiguous (caller can ask for clarification).
    """
    _load()
    mention = (mention or "").strip()
    if not mention:
        return None
    upper = mention.upper()
    if upper in _valid_symbols:
        return upper
    norm = _normalize(mention)
    if norm in _ABBREVS:
        return _ABBREVS[norm]
    by_name = _name_to_symbol.get(norm)
    if by_name:
        return by_name
    if len(norm) < 4:
        return None
    return _fallback_resolve(norm)


def _fallback_resolve(norm: str) -> str | None:
    by_name = _name_to_symbol.get(norm)
    if by_name:
        return by_name
    by_compact = _name_to_symbol.get(norm.replace(" ", ""))
    if by_compact:
        return by_compact
    by_prefix = _prefix_resolve(norm)
    if by_prefix:
        return by_prefix
    # Users often append "CI" to names registered with "Côte d'Ivoire"
    # ("Orange CI" vs "Orange Côte d'Ivoire"): retry without that suffix.
    if norm.endswith(" ci") and len(norm) > 7:
        by_stripped = _fallback_resolve(norm[:-3])
        if by_stripped:
            return by_stripped
    return _fuzzy_resolve(norm)


def _prefix_resolve(norm: str) -> str | None:
    """Match when the mention is a word-boundary prefix of exactly one company name
    ("Société Générale" -> SGBC; "Ecobank"/"Bank of Africa" stay ambiguous -> None)."""
    matches = {
        symbol
        for symbol, name in _symbol_to_name.items()
        if _normalize(name).startswith(norm + " ")
    }
    return matches.pop() if len(matches) == 1 else None


# Typo fallback: high cutoff + clear margin over the runner-up, so look-alike
# banking symbols (BOAB/BOAC/BOAM...) are never guessed wrong.
_FUZZY_CUTOFF = 0.86
_FUZZY_MARGIN = 0.05


def _fuzzy_resolve(norm: str) -> str | None:
    compact = norm.replace(" ", "")
    best_by_symbol: dict[str, float] = {}
    for key, symbol in _name_to_symbol.items():
        score = max(
            SequenceMatcher(None, norm, key).ratio(),
            SequenceMatcher(None, compact, key).ratio(),
        )
        if score > best_by_symbol.get(symbol, 0.0):
            best_by_symbol[symbol] = score
    if not best_by_symbol:
        return None
    ranked = sorted(best_by_symbol.values(), reverse=True)
    if ranked[0] < _FUZZY_CUTOFF:
        return None
    if len(ranked) > 1 and ranked[0] - ranked[1] < _FUZZY_MARGIN:
        return None
    return max(best_by_symbol, key=lambda s: best_by_symbol[s])


def format_list_for_prompt() -> str:
    """Format the BRVM list for inclusion in NLU system prompt (symbol -> name [sector], one per line)."""
    _load()
    if not _symbol_to_name:
        return "No BRVM company list loaded."
    lines = []
    for sym, name in sorted(_symbol_to_name.items()):
        sector = _symbol_to_sector.get(sym, "")
        if sector:
            lines.append(f"- {sym}: {name} ({sector})")
        else:
            lines.append(f"- {sym}: {name}")
    return "\n".join(lines)


def normalize_entities(entities: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Resolve symbol, symbol_a, symbol_b from entities using the BRVM list.
    Returns (updated_entities, list of unknown mentions to report).
    """
    _load()
    out = dict(entities)
    unknown: list[str] = []
    for key in ("symbol", "symbol_a", "symbol_b"):
        val = out.get(key)
        if not val or not isinstance(val, str):
            continue
        resolved = resolve_to_symbol(val)
        if resolved:
            out[key] = resolved
        else:
            unknown.append(val)
    return out, unknown

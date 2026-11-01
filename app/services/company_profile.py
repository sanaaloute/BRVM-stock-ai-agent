"""Mobile company profile (fiche société) preparation.

The raw fiche (app/data/company_details/{SYMBOL}.json, scraped from Sika
Finance) is cleaned before it reaches the mobile app:

- internal/contact fields are dropped (source_url, phone, fax, address),
- scraping metadata (fetched_at) and the sector peer list are dropped,
- the scraped `presentation` paragraph is never served verbatim: it is an
  external copyrighted text, so it is replaced by an LLM rewrite
  (`presentation_ai`, cached in the fiche JSON, keyed on a hash of the source
  text so a weekly re-fetch triggers a re-rewrite only when the text changed).
  When no rewrite is available (LLM down/not configured), the presentation is
  omitted from the payload rather than served as-is.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Top-level fiche fields that never belong in the app UI.
_DROP_KEYS = frozenset({"source_url", "phone", "fax", "address"})

# Enrichment blocks that carry a scraping timestamp (and peers for sector).
_TAB_BLOCKS = ("market", "technical_analysis", "sector")

_REWRITE_SYSTEM_PROMPT = (
    "Tu réécris la présentation officielle d'une société cotée à la BRVM pour "
    "la fiche investisseur d'une application mobile. Reformule entièrement avec "
    "tes propres mots : ne recopie aucune phrase du texte source. Ton neutre et "
    "professionnel, 4 à 6 phrases en français. Conserve les faits (dates, "
    "chiffres, noms propres), n'invente rien, n'ajoute ni titre ni commentaire."
)


def _source_hash(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


def sanitize_fiche(fiche: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the fiche without internal/contact/scraping fields.
    Unknown keys pass through untouched (the endpoint degrades sections to
    arbitrary dicts like {"error": ...})."""
    clean = {k: v for k, v in (fiche or {}).items() if k not in _DROP_KEYS}
    clean.pop("presentation_ai", None)  # internal cache artifact, see below
    for block_name in _TAB_BLOCKS:
        block = clean.get(block_name)
        if isinstance(block, dict):
            block = dict(block)
            block.pop("fetched_at", None)
            if block_name == "sector":
                block.pop("peers", None)
            clean[block_name] = block
    return clean


def _rewrite_with_llm(raw: str) -> str | None:
    """One LLM rewrite attempt; None on any failure (missing key, timeout…)."""
    try:
        from app.models.llm import get_llm

        llm = get_llm(thinking=False)
        source = raw.removeprefix("La société :").strip()
        resp = llm.invoke(
            [
                ("system", _REWRITE_SYSTEM_PROMPT),
                ("human", f"Texte source à réécrire :\n\n{source}"),
            ]
        )
        text = (getattr(resp, "content", "") or "").strip()
        return text or None
    except Exception as e:  # noqa: BLE001 - the fiche must still be served
        logger.warning("Presentation rewrite failed: %s", e)
        return None


def _persist_rewrite(symbol: str, presentation_ai: dict[str, Any]) -> None:
    """Write the rewrite back into the cached fiche JSON (re-read first so a
    concurrent scraper refresh is not clobbered)."""
    from app.scrapers.sikafinance_company import load_company_details, save_company_details

    try:
        on_disk = load_company_details(symbol)
        if not isinstance(on_disk, dict):
            return
        on_disk["presentation_ai"] = presentation_ai
        save_company_details(symbol, on_disk)
    except Exception as e:  # noqa: BLE001 - cache miss is not fatal
        logger.warning("Could not persist presentation rewrite for %s: %s", symbol, e)


def rewritten_presentation(symbol: str, fiche: dict[str, Any]) -> str | None:
    """Rewrite of the fiche's presentation, from cache when the source text is
    unchanged, otherwise generated (and persisted) on the fly."""
    raw = str(fiche.get("presentation") or "").strip()
    if not raw:
        return None
    src_hash = _source_hash(raw)
    cached = fiche.get("presentation_ai")
    if isinstance(cached, dict):
        text = str(cached.get("text") or "").strip()
        if text and cached.get("src_hash") == src_hash:
            return text
    text = _rewrite_with_llm(raw)
    if not text:
        return None
    _persist_rewrite(
        symbol,
        {
            "text": text,
            "src_hash": src_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return text


def mobile_company_profile(symbol: str, fiche: dict[str, Any]) -> dict[str, Any]:
    """Profile payload for the mobile symbol-detail endpoint: sanitized fiche
    whose `presentation` is the LLM rewrite (key dropped when unavailable)."""
    profile = sanitize_fiche(fiche)
    profile.pop("presentation", None)
    rewrite = rewritten_presentation(symbol, fiche or {})
    if rewrite:
        profile["presentation"] = rewrite
    return profile

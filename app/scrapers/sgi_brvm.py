"""
Fetch and persist BRVM SGI (Sociétés de Gestion et d'Intermédiation) broker data.

Single source: Rich Bourse
- List: https://www.richbourse.com/common/apprendre/liste-sgi
- Detail per SGI: https://www.richbourse.com/common/apprendre/details-sgi/{slug}

Data is saved to data/sgi_brvm.json and does not change frequently.
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

RICHBOURSE_SGI_LIST_URL = "https://www.richbourse.com/common/apprendre/liste-sgi"
RICHBOURSE_SGI_DETAIL_BASE = "https://www.richbourse.com/common/apprendre/details-sgi"
SLEEP = getattr(config, "SLEEP_SECONDS", 2)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SGI_JSON_PATH = DATA_DIR / "sgi_brvm.json"


def _normalize(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()


def fetch_sgi_list_richbourse() -> list[dict[str, Any]]:
    """
    Fetch the SGI list page and return one dict per row: name, country, note, detail_slug.
    """
    out: list[dict[str, Any]] = []
    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(RICHBOURSE_SGI_LIST_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Rich Bourse SGI list fetch failed: %s", e)
        return out

    # Table: # | Noms des SGI | Pays | Note | Détails link
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for tr in rows[1:]:
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            name = _normalize(cells[1].get_text() or "")
            if not name:
                continue
            country = _normalize(cells[2].get_text() or "")
            note_cell = cells[3].get_text() or ""
            note = _normalize(note_cell)
            detail_slug = ""
            for a in tr.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if "/details-sgi/" in href:
                    detail_slug = href.split("/details-sgi/")[-1].split("?")[0].strip("/")
                    break
            out.append({
                "name": name,
                "country": country,
                "note": note,
                "detail_slug": detail_slug,
            })
        if out:
            break
    return out


def fetch_sgi_detail_richbourse(slug: str) -> dict[str, Any]:
    """
    Fetch one SGI detail page and return address, phone, website, min_amount, email, etc.
    """
    url = f"{RICHBOURSE_SGI_DETAIL_BASE}/{slug}"
    out: dict[str, Any] = {}
    try:
        if SLEEP > 0:
            time.sleep(SLEEP)
        resp = http_get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.debug("Rich Bourse SGI detail %s failed: %s", slug, e)
        return out

    # Detail page: table or definition list with Nom, Pays, Téléphone, Adresse, Site Web,
    # Montant minimum, Informations complémentaires (may contain Email)
    text = soup.get_text(separator="\n")
    out["address"] = ""
    out["phone"] = ""
    out["website"] = ""
    out["min_amount"] = ""
    out["email"] = ""
    out["other_countries"] = ""
    out["tarifs_url"] = ""
    out["documents_url"] = ""

    # Tables: rows with label (th or td) and value (td); or dl dt/dd
    def set_from_row(label: str, value: str, href: str = "") -> None:
        label = label.lower()
        if "nom" in label and not out.get("name"):
            out["name"] = value
        elif "pays" in label and "autres" not in label:
            out["country"] = value
        elif "autres pays" in label:
            out["other_countries"] = value
        elif "téléphone" in label or "telephone" in label:
            out["phone"] = value
        elif "adresse" in label:
            out["address"] = value
        elif "site web" in label:
            out["website"] = href if href.startswith("http") else value
        elif "montant" in label or "minimum" in label:
            out["min_amount"] = value
        elif "tarifs" in label and href:
            out["tarifs_url"] = href if href.startswith("http") else ("https://www.richbourse.com" + href)
        elif "documents" in label and href:
            out["documents_url"] = href if href.startswith("http") else ("https://www.richbourse.com" + href)
        elif "informations complémentaires" in label or "informations complementaires" in label:
            out["info"] = value
            email_m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", value)
            if email_m:
                out["email"] = email_m.group(0)

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = _normalize(cells[0].get_text() or "")
            value = _normalize(cells[1].get_text() or "")
            link = cells[1].find("a", href=True)
            href = (link.get("href") or "").strip() if link else ""
            set_from_row(label, value, href)

    # Montant minimum often appears as standalone line before "NB : Le montant"
    if not out.get("min_amount"):
        m = re.search(r"(\d[\d\s]*\s*FCFA)", text)
        if m:
            out["min_amount"] = _normalize(m.group(1))

    # Site Web link might be in a cell with "Visiter le site"
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.startswith("http") and "richbourse.com" not in href and not out.get("website"):
            if "visiter" in (a.get_text() or "").lower() or "site" in (a.get_text() or "").lower():
                out["website"] = href
                break

    return out


def fetch_all_sgi_richbourse() -> list[dict[str, Any]]:
    """
    Fetch list of SGIs from Rich Bourse, then fetch each detail page and merge into one list.
    """
    list_rows = fetch_sgi_list_richbourse()
    if not list_rows:
        return []

    result: list[dict[str, Any]] = []
    for i, row in enumerate(list_rows):
        name = row.get("name") or ""
        country = row.get("country") or ""
        note = row.get("note") or ""
        slug = row.get("detail_slug") or ""
        entry: dict[str, Any] = {
            "name": name,
            "country": country,
            "country_code": _country_to_code(country),
            "note": note,
            "min_amount": "",
            "address": "",
            "phone": "",
            "website": "",
            "email": "",
            "other_countries": "",
            "tarifs_url": "",
            "documents_url": "",
            "detail_url": f"{RICHBOURSE_SGI_DETAIL_BASE}/{slug}" if slug else "",
        }
        if slug:
            detail = fetch_sgi_detail_richbourse(slug)
            entry["min_amount"] = detail.get("min_amount") or ""
            entry["address"] = detail.get("address") or ""
            entry["phone"] = detail.get("phone") or ""
            entry["website"] = detail.get("website") or ""
            entry["email"] = detail.get("email") or ""
            entry["other_countries"] = detail.get("other_countries") or ""
            entry["tarifs_url"] = detail.get("tarifs_url") or ""
            entry["documents_url"] = detail.get("documents_url") or ""
            if detail.get("info"):
                entry["info"] = detail["info"]
        result.append(entry)
        logger.debug("SGI %s/%s: %s", i + 1, len(list_rows), name)
    return result


def _country_to_code(country: str) -> str:
    """Map country name to 2-letter lowercase ISO code (matches brvm_companies codes)."""
    m = {
        "bénin": "bj",
        "benin": "bj",
        "burkina faso": "bf",
        "côte d'ivoire": "ci",
        "cote d'ivoire": "ci",
        "guinée-bissau": "gw",
        "guinee-bissau": "gw",
        "mali": "ml",
        "niger": "ne",
        "sénégal": "sn",
        "senegal": "sn",
        "togo": "tg",
    }
    key = (country or "").strip().lower()
    return m.get(key, "")


def fetch_and_save_sgi(save_path: Path | None = None) -> dict[str, Any]:
    """
    Fetch all SGI data from Rich Bourse (list + detail pages) and save to JSON.
    """
    path = save_path or SGI_JSON_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sgi_list = fetch_all_sgi_richbourse()
    payload = {
        "source_url": RICHBOURSE_SGI_LIST_URL,
        "source_name": "Rich Bourse",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(sgi_list),
        "sgi": sgi_list,
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    logger.info("SGI data saved: %s (%d brokers)", path, len(sgi_list))
    return {
        "path": str(path),
        "count": len(sgi_list),
    }


def load_sgi_local(path: Path | None = None) -> dict[str, Any]:
    """Load SGI data from local JSON. Returns dict with 'sgi' list and metadata."""
    p = path or SGI_JSON_PATH
    if not Path(p).exists():
        return {"sgi": [], "count": 0, "updated_at": None}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not load SGI data from %s: %s", p, e)
        return {"sgi": [], "count": 0, "updated_at": None}

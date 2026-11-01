"""Unit tests for app.services.company_profile: fiche sanitization and the
LLM presentation rewrite (cache keyed on the source-text hash).

Run:  python tests/test_company_profile.py   (or: pytest tests/)
"""
from pathlib import Path

from app.scrapers import sikafinance_company
from app.services import company_profile


def _fiche() -> dict:
    return {
        "symbol": "SNTS",
        "country_code": "sn",
        "source_url": "https://www.sikafinance.com/marches/societe/SNTS.sn",
        "company_name": "SONATEL",
        "code": "SN0000000019 - SNTS",
        "presentation": "La société : SONATEL est le premier opérateur téléphonique au Sénégal.",
        "phone": "(+221) 33-839-12-00",
        "fax": "(+221) 33-839-12-12",
        "address": "6 Rue WAGANE DIOUF, Sénégal",
        "dirigeants": "Président : A",
        "nombre_titres": "100 000 000",
        "flottant": "22,47%",
        "valorisation": "3 100 000 MFCFA",
        "shareholders": [{"name": "ORANGE", "pct": "42,33"}],
        "performance": {"per": {"2024": "7,87"}},
        "market": {"beta_1an": 1.31, "fetched_at": "2026-08-22T23:03:33+00:00"},
        "technical_analysis": {
            "signals": [{"group": "tendance", "direction": "up", "text": "…"}],
            "up": 1,
            "fetched_at": "2026-08-22T23:03:33+00:00",
        },
        "sector": {
            "name": "TELECOMMUNICATIONS",
            "peers": [{"symbol": "ORAC"}],
            "fetched_at": "2026-08-22T23:03:16+00:00",
        },
    }


# ---------------- sanitize_fiche ----------------


def test_sanitize_drops_contact_and_scraping_fields():
    clean = company_profile.sanitize_fiche(_fiche())
    for key in ("source_url", "phone", "fax", "address"):
        assert key not in clean, key
    for block in ("market", "technical_analysis", "sector"):
        assert "fetched_at" not in clean[block], block
    assert "peers" not in clean["sector"]
    assert clean["sector"]["name"] == "TELECOMMUNICATIONS"
    # Investor-relevant fields are kept.
    assert clean["company_name"] == "SONATEL"
    assert clean["shareholders"] == [{"name": "ORANGE", "pct": "42,33"}]
    assert clean["market"]["beta_1an"] == 1.31


def test_sanitize_keeps_unknown_keys_and_does_not_mutate():
    fiche = {"stubbed": "load_company_details", "sector": {"name": "X"}}
    clean = company_profile.sanitize_fiche(fiche)
    assert clean["stubbed"] == "load_company_details"  # degraded-section dicts pass through
    full = _fiche()
    company_profile.sanitize_fiche(full)
    assert "fetched_at" in full["market"]  # input untouched
    assert "peers" in full["sector"]


# ---------------- rewritten_presentation ----------------


def test_presentation_rewrite_cached_on_source_hash(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        company_profile, "_rewrite_with_llm", lambda raw: calls.append(raw) or "Texte réécrit."
    )
    monkeypatch.setattr(company_profile, "_persist_rewrite", lambda sym, ai: None)

    fiche = _fiche()
    first = company_profile.rewritten_presentation("SNTS", fiche)
    assert first == "Texte réécrit."
    assert len(calls) == 1

    # Cache hit: same source hash -> no new LLM call.
    fiche["presentation_ai"] = {
        "text": "Texte réécrit.",
        "src_hash": company_profile._source_hash(fiche["presentation"]),
    }
    assert company_profile.rewritten_presentation("SNTS", fiche) == "Texte réécrit."
    assert len(calls) == 1

    # Source text changed (weekly refresh) -> rewrite renewed.
    fiche["presentation"] = "La société : autre texte."
    assert company_profile.rewritten_presentation("SNTS", fiche) == "Texte réécrit."
    assert len(calls) == 2


def test_presentation_rewrite_failure_returns_none(monkeypatch):
    monkeypatch.setattr(company_profile, "_rewrite_with_llm", lambda raw: None)
    monkeypatch.setattr(company_profile, "_persist_rewrite", lambda sym, ai: None)
    assert company_profile.rewritten_presentation("SNTS", _fiche()) is None
    assert company_profile.rewritten_presentation("SNTS", {"presentation": "  "}) is None


def test_persist_rewrite_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / "SNTS.json"
    sikafinance_company.save_company_details("SNTS", _fiche(), save_dir=tmp_path)
    monkeypatch.setattr(sikafinance_company, "DATA_DIR", tmp_path)

    company_profile._persist_rewrite("SNTS", {"text": "T", "src_hash": "h"})

    on_disk = sikafinance_company.load_company_details("SNTS", load_dir=tmp_path)
    assert on_disk["presentation_ai"] == {"text": "T", "src_hash": "h"}
    assert on_disk["company_name"] == "SONATEL"  # rest of the fiche preserved
    assert path.exists()


# ---------------- mobile_company_profile ----------------


def test_mobile_profile_replaces_presentation_with_rewrite(monkeypatch):
    monkeypatch.setattr(company_profile, "_rewrite_with_llm", lambda raw: "Version reformulée.")
    monkeypatch.setattr(company_profile, "_persist_rewrite", lambda sym, ai: None)

    profile = company_profile.mobile_company_profile("SNTS", _fiche())
    assert profile["presentation"] == "Version reformulée."
    assert "La société :" not in profile["presentation"]
    assert "presentation_ai" not in profile
    assert "source_url" not in profile


def test_mobile_profile_omits_presentation_when_no_rewrite(monkeypatch):
    monkeypatch.setattr(company_profile, "_rewrite_with_llm", lambda raw: None)
    profile = company_profile.mobile_company_profile("SNTS", _fiche())
    assert "presentation" not in profile
    # Everything else is still served.
    assert profile["company_name"] == "SONATEL"


def test_mobile_profile_tolerates_empty_fiche():
    assert company_profile.mobile_company_profile("SNTS", {}) == {}


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([str(Path(__file__))]))

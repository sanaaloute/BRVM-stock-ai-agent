"""BRVM symbol resolution robustness tests.

Users rarely type the exact registered name: they write "SODE CI" for SODECI,
"Nestle" for Nestlé, append "CI", or make small typos. resolve_to_symbol must
still map them to the right symbol — while ambiguous mentions shared by several
companies (Ecobank, TotalEnergies, Bank of Africa) must stay unresolved so the
caller asks for clarification instead of guessing wrong.

Run:
    .venv/bin/python -m pytest tests/test_brvm_companies.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils.brvm_companies import normalize_entities, resolve_to_symbol  # noqa: E402


def test_symbol_and_full_name_still_work():
    assert resolve_to_symbol("SNTS") == "SNTS"
    assert resolve_to_symbol("snts") == "SNTS"
    assert resolve_to_symbol("Sonatel Sénégal") == "SNTS"
    assert resolve_to_symbol("BOAB") == "BOAB"
    assert resolve_to_symbol("SMB") == "SMBC"  # abbreviation


def test_spacing_accent_and_ci_suffix_variants():
    assert resolve_to_symbol("SODE CI") == "SDCC"
    assert resolve_to_symbol("SODECI") == "SDCC"
    assert resolve_to_symbol("sodéci") == "SDCC"
    assert resolve_to_symbol("Nestle") == "NTLC"
    assert resolve_to_symbol("Nestlé CI") == "NTLC"
    assert resolve_to_symbol("orange ci") == "ORAC"


def test_partial_company_names():
    assert resolve_to_symbol("sonatel") == "SNTS"
    assert resolve_to_symbol("Société Générale") == "SGBC"
    assert resolve_to_symbol("compagnie ivoirienne") == "CIEC"
    assert resolve_to_symbol("bernabe") == "BNBC"


def test_small_typos_resolve():
    assert resolve_to_symbol("Sontel") == "SNTS"
    assert resolve_to_symbol("sode cii") == "SDCC"
    assert resolve_to_symbol("solibraa") == "SLBC"


def test_ambiguous_mentions_stay_unresolved():
    # Words shared by several BRVM companies: guessing would be wrong.
    for mention in ("Ecobank", "TotalEnergies", "Bank of Africa", "motors", "BOA"):
        assert resolve_to_symbol(mention) is None, mention


def test_unknown_mentions_stay_unresolved():
    for mention in ("", "XXXX", "ACME Corp", "ci"):
        assert resolve_to_symbol(mention) is None, repr(mention)


def test_normalize_entities_maps_mentions():
    entities, unknown = normalize_entities({"symbol": "SODE CI", "symbol_a": "sonatel"})
    assert unknown == []
    assert entities["symbol"] == "SDCC"
    assert entities["symbol_a"] == "SNTS"

    entities, unknown = normalize_entities({"symbol": "ACME Corp"})
    assert unknown == ["ACME Corp"]


def test_nlu_parse_resolves_sode_ci():
    """End-to-end on the NLU path: the mention copied by the model is resolved
    in code instead of producing the 'introuvable' clarification."""
    from app.agents.nlu_agent import _parse_nlu_response

    sd, clar = _parse_nlu_response(
        '{"intent": "price_query", "entities": {"symbol": "SODE CI"}, "suggested_worker": "analytics"}'
    )
    assert clar is None, clar
    assert sd["entities"]["symbol"] == "SDCC", sd


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

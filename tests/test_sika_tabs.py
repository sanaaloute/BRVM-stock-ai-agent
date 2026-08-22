"""Offline tests for the Sika Finance tab fetchers (app/scrapers/sikafinance_tabs.py)
and the Tavily-markdown societe parser (app/scrapers/sikafinance_company.py).

Fixtures in tests/fixtures/ are real Tavily raw_content captures for SNTS (SONATEL):
  - sika_cotation_snts.txt : /marches/cotation_SNTS.sn  (COURS tab)
  - sika_analyse_snts.txt  : /analyses/conseil/SNTS.sn  (ANALYSE ET CONSEILS tab)
  - sika_secteur_snts.txt  : /marches/secteur/SNTS.sn   (SECTEUR tab)

The network is stubbed by monkeypatching each module's extract function, so the
suite runs fully offline. Run:  python tests/test_sika_tabs.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).resolve().parent / "fixtures"

import config  # noqa: E402
from app.scrapers import sikafinance_tabs as tabs  # noqa: E402
from app.scrapers import sikafinance_company as sfc  # noqa: E402

# The fetchers refuse to run without an API key; tests patch the network away.
if not getattr(config, "TAVILY_API_KEY", ""):
    config.TAVILY_API_KEY = "test-key"


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def fake_extract(url, **_kwargs):
    """Dispatch on the tab URL, like Tavily would."""
    if "/marches/cotation_" in url:
        return read_fixture("sika_cotation_snts.txt")
    if "/analyses/conseil/" in url:
        return read_fixture("sika_analyse_snts.txt")
    if "/marches/secteur/" in url:
        return read_fixture("sika_secteur_snts.txt")
    return ""


# Minimal Tavily-markdown societe page (bold labels + performance table shape,
# as returned by Tavily extract for /marches/societe/BOAM.ml).
SOCIETE_MD = """![menu mobile](/img/vector.png)

**CONNECTEZ-VOUS**

[Liste de valeurs](/listes/displaylist)

# BANK OF AFRICA MALI, fiche société

![](/i/ml.png "Mali")

**La société :** BANK OF AFRICA - MALI (BOA-MALI), ouverte au public en janvier 1982, détient actuellement un capital de 27,45 milliards FCFA.
BOA-MALI fait son introduction à la Bourse Régionale des Valeurs Mobilières (BRVM) fin mai 2016, et devient la 1ère entreprise malienne cotée en bourse.

**Téléphone :** (223) 20 70 05 00

**Fax :** (223) 20 70 05 60

**Adresse :** 418, Avenue de la Marne – Bamako

**Dirigeants :** Président du Conseil d'Administration : Paul DERREUMAUX
Directeur général : Georges NABI

**Nombre de titres :**  27 450 000

**Flottant :**  21,44%

**Valorisation de la société :**  178 151 MFCFA

**Principaux actionnaires**

BOA WEST AFRICA\\*61,39;DIVERS MALIENS\\*17,71;DIVERS ACTIONNAIRES PRIVES (BOURSE)\\*16,18

|  | 2021 | 2022 | 2023 | 2024 | 2025 |
| --- | --- | --- | --- | --- | --- |
| **Chiffre d'affaires** | 35 408 | 35 307 | 35 519 | 36 157 | 37 997 |
| **Croissance CA** |  | -0,29% | 0,60% | 1,80% | 5,09% |
| **Résultat net** | 2 095 | 2 461 | 5 778 | 9 123 | 11 081 |
| **Croissance RN** |  | 17,47% | 134,78% | 57,90% | 21,46% |
| **BNPA** | 76,33 | 89,63 | 210,50 | 332,00 | 403,69 |
| **PER** | 85,03 | 72,41 | 30,83 | 19,55 | 16,08 |
| **Dividende** | - | - | 96,00 | 237,15 | 305,04 |

![](/i/facebook.png)
"""


def _assert_societe_out(out):
    """Shared assertions for a parsed SOCIETE_MD dict."""
    assert "error" not in out, out.get("error")
    assert out["company_name"] == "BANK OF AFRICA MALI", out["company_name"]
    assert out["phone"] == "(223) 20 70 05 00", out["phone"]
    assert out["fax"] == "(223) 20 70 05 60", out["fax"]
    assert "Avenue de la Marne" in out["address"], out["address"]
    assert "DERREUMAUX" in out["dirigeants"] and "NABI" in out["dirigeants"], out["dirigeants"]
    assert "Nombre de titres" not in out["dirigeants"], out["dirigeants"]
    assert out["nombre_titres"] == "27 450 000", out["nombre_titres"]
    assert out["flottant"] == "21,44%", out["flottant"]
    assert out["valorisation"] == "178 151 MFCFA", out["valorisation"]
    assert len(out["shareholders"]) == 3, out["shareholders"]
    assert out["shareholders"][0] == {"name": "BOA WEST AFRICA", "pct": "61,39"}, out["shareholders"]
    perf = out["performance"]
    for key in ("chiffre_affaires", "croissance_ca", "resultat_net", "croissance_rn", "bnpa", "per", "dividende"):
        assert key in perf, f"missing metric {key}: {sorted(perf)}"
        assert len(perf[key]) == 5, (key, perf[key])
    assert perf["chiffre_affaires"]["2025"] == "37 997", perf["chiffre_affaires"]
    assert perf["chiffre_affaires"]["2021"] == "35 408", perf["chiffre_affaires"]
    assert perf["per"]["2025"] == "16,08", perf["per"]
    assert perf["dividende"]["2021"] == "-", perf["dividende"]
    assert perf["croissance_ca"]["2021"] == "", perf["croissance_ca"]


# ---------------------------------------------------------------------------
def test_parse_fr():
    assert tabs._parse_fr("1 334 874") == 1334874.0
    assert tabs._parse_fr("2 524,59") == 2524.59
    assert tabs._parse_fr("1\xa0334\xa0874") == 1334874.0          # NBSP thousands
    assert tabs._parse_fr("1\u202f334\u202f874") == 1334874.0     # narrow NBSP
    assert tabs._parse_fr("16,08") == 16.08
    assert tabs._parse_fr("7,25%") == 7.25
    assert tabs._parse_fr("+41,58%") == 41.58
    assert tabs._parse_fr("-1.87%") == -1.87
    assert tabs._parse_fr("") is None
    assert tabs._parse_fr("abc") is None
    assert tabs._parse_fr("-") is None
    assert tabs._parse_fr(None) is None
    assert tabs._parse_fr(42) == 42.0


def test_cotation_parse():
    tabs._extract = fake_extract
    out = tabs.fetch_cotation("SNTS", "sn")
    assert out is not None
    assert out["beta_1an"] == 1.31, out["beta_1an"]
    assert out["rsi_14"] == 86.03, out["rsi_14"]
    assert out["capital_echange_pct"] == 0.01, out["capital_echange_pct"]
    assert out["valorisation_millions"] == 3698000.0, out["valorisation_millions"]
    day = out["day"]
    assert day["ouverture"] == 34400.0, day
    assert day["plus_haut"] == 36980.0, day
    assert day["plus_bas"] == 34400.0, day
    assert day["cloture_veille"] == 34400.0, day
    assert day["volume_titres"] == 13615.0, day
    assert day["volume_fcfa"] == 503482700.0, day
    assert set(out["ranges"]) == {"1_semaine", "1_mois", "1er_janvier", "1_an", "3_ans", "5_ans"}, out["ranges"]
    r1a = out["ranges"]["1_an"]
    assert r1a == {"plus_haut": 36980.0, "plus_bas": 24400.0, "variation_pct": 49.14}, r1a
    assert out["ranges"]["1_semaine"]["variation_pct"] == 15.92, out["ranges"]["1_semaine"]
    assert out["ranges"]["5_ans"]["plus_bas"] == 13500.0, out["ranges"]["5_ans"]
    div = out["dividend_history"]
    assert len(div) == 5, div
    assert div[0] == {"year": 2025, "montant": 1740.0, "rendement_pct": 7.25}, div[0]
    assert div[-1] == {"year": 2021, "montant": 1400.0, "rendement_pct": 10.37}, div[-1]


def test_analyse_parse():
    tabs._extract = fake_extract
    out = tabs.fetch_analyse("SNTS", "sn")
    assert out is not None
    signals = out["signals"]
    assert len(signals) == 11, len(signals)
    assert out["up"] == 7 and out["down"] == 2 and out["neutral"] == 2, out
    by_group = {}
    for s in signals:
        by_group.setdefault(s["group"], []).append(s)
    assert set(by_group) == {"tendance", "momentum", "oscillateurs", "volumes_chandeliers"}, by_group
    assert len(by_group["tendance"]) == 5, by_group
    assert len(by_group["momentum"]) == 2, by_group
    assert len(by_group["oscillateurs"]) == 2, by_group
    assert len(by_group["volumes_chandeliers"]) == 2, by_group
    assert by_group["momentum"][0]["direction"] == "down", by_group["momentum"]
    assert signals[0]["group"] == "tendance" and signals[0]["direction"] == "up", signals[0]
    assert signals[0]["text"] == "Les cours évoluent au-dessus de leur moyenne mobile à 20 jours.", signals[0]
    for s in signals:
        assert "![" not in s["text"] and "fleche" not in s["text"], s
    # The bottom disclaimer paragraph is not a signal.
    assert not any("aucune valeur contractuelle" in s["text"] for s in signals)


def test_secteur_parse():
    tabs._extract = fake_extract
    out = tabs.fetch_secteur("SNTS", "sn")
    assert out is not None
    assert out["name"] == "TELECOMMUNICATIONS", out["name"]
    peers = out["peers"]
    assert len(peers) == 3, peers
    assert {p["symbol"] for p in peers} == {"ONTBF", "ORAC", "SNTS"}, peers
    snts = next(p for p in peers if p["symbol"] == "SNTS")
    assert snts["name"] == "SONATEL", snts
    assert snts["dernier"] == 36980.0, snts
    assert snts["variation_jour_pct"] == 7.5, snts
    assert snts["variation_ytd_pct"] == 41.58, snts
    ontbf = next(p for p in peers if p["symbol"] == "ONTBF")
    assert ontbf["name"] == "ONATEL BF" and ontbf["variation_ytd_pct"] == 16.10, ontbf


def test_fetchers_return_none_on_failure():
    def boom(url, **_kwargs):
        raise RuntimeError("tavily down")

    tabs._extract = boom
    assert tabs.fetch_cotation("SNTS", "sn") is None
    assert tabs.fetch_analyse("SNTS", "sn") is None
    assert tabs.fetch_secteur("SNTS", "sn") is None

    tabs._extract = lambda url, **_: ""  # empty content (block page)
    assert tabs.fetch_cotation("SNTS", "sn") is None
    assert tabs.fetch_analyse("SNTS", "sn") is None
    assert tabs.fetch_secteur("SNTS", "sn") is None


def test_societe_markdown_parse():
    out = {"company_name": "", "code": "", "presentation": "", "phone": "", "fax": "",
           "address": "", "dirigeants": "", "nombre_titres": "", "flottant": "",
           "valorisation": "", "shareholders": [], "performance": {}}
    sfc._parse_tavily_markdown(SOCIETE_MD, out)
    _assert_societe_out(out)


def test_fetch_company_page_tavily_path_offline():
    sfc.SLEEP = 0
    sfc._fetch_tavily_markdown = lambda url: SOCIETE_MD

    def no_http(*_a, **_k):
        raise AssertionError("http fallback must not run when Tavily succeeds")

    sfc.http_get = no_http
    out = sfc.fetch_company_page("BOAM", "ml")
    assert out["symbol"] == "BOAM" and out["country_code"] == "ml"
    assert out["source_url"].endswith("/marches/societe/BOAM.ml"), out["source_url"]
    _assert_societe_out(out)


def test_fetch_and_save_merges_tabs():
    sfc.SLEEP = 0
    sfc._fetch_tavily_markdown = lambda url: SOCIETE_MD
    secteur_calls = []

    def counting_extract(url, **_kwargs):
        if "/marches/secteur/" in url:
            secteur_calls.append(url)
        return fake_extract(url)

    tabs._extract = counting_extract
    with tempfile.TemporaryDirectory() as tmp:
        cache = {}
        # SNTS and ONTBF share the Excel sector "Télécommunications": one secteur fetch.
        d1 = sfc.fetch_and_save_company_details("SNTS", "sn", save_dir=Path(tmp), sector_cache=cache)
        d2 = sfc.fetch_and_save_company_details("ONTBF", "bf", save_dir=Path(tmp), sector_cache=cache)
        for d in (d1, d2):
            assert "error" not in d, d.get("error")
            for key in ("market", "technical_analysis", "sector"):
                assert key in d, f"{key} missing from {d['symbol']}"
                assert d[key]["fetched_at"], d[key]
        assert d1["market"]["beta_1an"] == 1.31
        assert d1["technical_analysis"]["up"] == 7
        assert d1["sector"]["name"] == "TELECOMMUNICATIONS"
        assert d2["sector"] == d1["sector"], "sector block should be reused from cache"
        assert len(secteur_calls) == 1, secteur_calls  # dedupe: second symbol reused
        saved = json.loads((Path(tmp) / "SNTS.json").read_text(encoding="utf-8"))
        assert saved["market"]["ranges"]["1_an"]["variation_pct"] == 49.14
        assert saved["sector"]["peers"][0]["symbol"] == "ONTBF"

        # include_tabs=False: plain societe dict.
        d3 = sfc.fetch_and_save_company_details("SNTS", "sn", save_dir=Path(tmp), include_tabs=False)
        assert all(k not in d3 for k in ("market", "technical_analysis", "sector")), sorted(d3)


def test_fetch_and_save_saves_societe_when_tabs_fail():
    sfc.SLEEP = 0
    sfc._fetch_tavily_markdown = lambda url: SOCIETE_MD
    tabs._extract = lambda url, **_: ""  # every tab fails
    with tempfile.TemporaryDirectory() as tmp:
        d = sfc.fetch_and_save_company_details("BOAM", "ml", save_dir=Path(tmp))
        assert "error" not in d, d.get("error")
        assert all(k not in d for k in ("market", "technical_analysis", "sector")), sorted(d)
        saved = json.loads((Path(tmp) / "BOAM.json").read_text(encoding="utf-8"))
        assert saved["performance"]["per"]["2025"] == "16,08", saved["performance"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

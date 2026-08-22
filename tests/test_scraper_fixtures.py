"""Golden-fixture regression tests for the HTML scraper parsers.

Fixtures in tests/fixtures/ are HTML snapshots:
  - richbourse_variation.html : live capture of /common/variation/index
  - richbourse_news.html      : live capture of /common/news/index/NTLC
  - brvm_announcements.html   : live capture of BRVM convocations page
  - sikafinance_bourse.html   : SYNTHETIC (site blocks non-browser clients)

They detect silent parser breakage when a site changes its markup, without
any network access. If a live site legitimately changes, re-capture the
fixture (see header of each file) and update the anchored assertions below.

Run: python tests/test_scraper_fixtures.py   (requires the project venv)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).resolve().parent / "fixtures"

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS {name}")
    except Exception as e:
        RESULTS.append((name, False, repr(e)))
        print(f"FAIL {name}: {e!r}")


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8", errors="ignore")


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


def patch_get(module, html, recorder=None):
    """Stub the scraper's network call. Scrapers fetch via
    `from app.utils.http_client import http_get`, so patch the name on the
    scraper module itself."""
    def fake_get(url, *args, **kwargs):
        if recorder is not None:
            recorder.append(url)
        return FakeResponse(html)
    module.http_get = fake_get


# ---------------------------------------------------------------------------
def test_richbourse_variation_table():
    import app.scrapers.richbourse as rb

    called = []
    patch_get(rb, read_fixture("richbourse_variation.html"), recorder=called)
    out = rb.RichBourseScraper(period="veille", progression="tout", sleep_seconds=0).scrape()

    assert called and "richbourse.com/common/variation/index/veille/tout" in called[0], called
    stocks = out["stocks"]
    assert len(stocks) >= 40, f"expected ~43 rows, got {len(stocks)}"
    assert out["date"], "no French date found on page"
    assert out["hausses"] is not None and out["baisses"] is not None, "summary counts missing"
    for s in stocks:
        assert len(s["symbol"]) in (4, 5) and s["symbol"].isalpha(), s
        assert s["name"], s
    cbibf = next((s for s in stocks if s["symbol"] == "CBIBF"), None)
    assert cbibf is not None, "CBIBF row missing"
    assert cbibf["variation_pct"] == 7.5, cbibf
    assert cbibf["cours_actuel"] == 29610, cbibf
    assert cbibf["volume"] == 1181, cbibf


def test_richbourse_variation_garbage_html():
    import app.scrapers.richbourse as rb

    patch_get(rb, "<html><body><p>Site maintenance</p></body></html>")
    out = rb.RichBourseScraper(sleep_seconds=0).scrape()
    assert out["stocks"] == [], out


def test_richbourse_news_items():
    import app.scrapers.richbourse_news as rbn

    rbn.SLEEP = 0
    called = []
    patch_get(rbn, read_fixture("richbourse_news.html"), recorder=called)
    out = rbn.fetch_company_news("NTLC")

    assert out["error"] is None, out["error"]
    assert called and called[0].endswith("/common/news/index/NTLC"), called
    items = out["items"]
    assert len(items) == 9, f"fixture holds 9 unique articles (x2 desktop/mobile), got {len(items)}"
    for it in items:
        assert it["title"] and it["title"] != "Lire la suite...", it
        assert it["url"].startswith("https://www.richbourse.com/common/apprendre/article/"), it
    first = items[0]
    assert first["date"] == "01 Novembre 2025 - 10h:47", first
    assert first["title"].startswith("Nestl"), first
    assert first["snippet"], first


def test_brvm_announcements():
    import app.scrapers.brvm_announcements as ba

    ba.SLEEP = 0
    patch_get(ba, read_fixture("brvm_announcements.html"))
    out = ba.fetch_brvm_announcements()

    assert out["error"] is None, out["error"]
    items = out["items"]
    assert len(items) >= 10, f"expected 15 announcements, got {len(items)}"
    assert items[0]["date"] == "05/07/2026", items[0]
    assert items[0]["company"] == "ORAGROUP", items[0]
    with_pdf = [it for it in items if it["pdf_url"]]
    assert len(with_pdf) >= 10, f"pdf_url missing on most rows ({len(with_pdf)}/{len(items)})"
    assert all(u.startswith("https://www.brvm.org/sites/default/files/") for u in (it["pdf_url"] for it in with_pdf))
    # company filter
    out2 = ba.fetch_brvm_announcements(company_filter="oragroup")
    assert out2["items"] and all("ORAGROUP" in it["company"].upper() for it in out2["items"]), out2["items"][:2]


def test_sikafinance_news_synthetic():
    import app.scrapers.sikafinance_news as sfn

    sfn.SLEEP = 0
    patch_get(sfn, read_fixture("sikafinance_bourse.html"))
    out = sfn.fetch_bourse_news()

    assert out["error"] is None, out["error"]
    items = out["items"]
    assert len(items) == 3, items  # only the BOURSE section, not SOCIETES
    assert items[0]["date"] == "10/07/2026", items[0]
    assert items[0]["url"] == "https://www.sikafinance.com/marches/bourse_1001.ci", items[0]
    assert items[1]["url"] == "https://www.sikafinance.com/marches/bourse_1000.ci", items[1]
    assert items[2]["url"] == "https://www.sikafinance.com/marches/bourse_0999.ci", items[2]
    assert "BRVM" in items[0]["title"], items[0]


def test_fetch_error_returns_error_field():
    import app.scrapers.brvm_announcements as ba

    ba.SLEEP = 0

    def boom(*a, **k):
        raise RuntimeError("connection refused")

    ba.http_get = boom
    out = ba.fetch_brvm_announcements()
    assert out["items"] == [] and out["error"], out


if __name__ == "__main__":
    check("test_richbourse_variation_table", test_richbourse_variation_table)
    check("test_richbourse_variation_garbage_html", test_richbourse_variation_garbage_html)
    check("test_richbourse_news_items", test_richbourse_news_items)
    check("test_brvm_announcements", test_brvm_announcements)
    check("test_sikafinance_news_synthetic", test_sikafinance_news_synthetic)
    check("test_fetch_error_returns_error_field", test_fetch_error_returns_error_field)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)

import io
import json
from datetime import date, timedelta

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

import config
from app.api.mobile import router
from app.api.mobile_auth import require_app_user
from app.db import engine as db_engine
from app.db import models
from app.services import sgi_import
from app.utils import user_db

USER_ID = 123
OTHER_USER_ID = 999


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(user_db, "DB_PATH", tmp_path / "test.db")
    user_db.reset_engine()
    user_db.init_db()
    yield
    user_db.reset_engine()


def make_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
        })
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 10 Tf 20 370 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def make_docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def test_pdf_and_docx_text_extraction():
    pdf_text, _ = sgi_import.extract_document_text("statement.pdf", make_pdf("NTLC 10 50000"))
    assert "NTLC" in pdf_text
    docx_text, _ = sgi_import.extract_document_text("statement.docx", make_docx("NTLC 10 50000"))
    assert "NTLC" in docx_text


def test_document_format_and_empty_errors():
    with pytest.raises(sgi_import.DocumentError) as error:
        sgi_import.extract_document_text("statement.doc", b"legacy")
    assert error.value.code == "legacy_doc"
    with pytest.raises(sgi_import.DocumentError) as error:
        sgi_import.extract_document_text("statement.pdf", make_pdf(""))
    assert error.value.code == "no_text"
    with pytest.raises(sgi_import.DocumentError) as error:
        sgi_import.extract_document_text("statement.pdf", b"")
    assert error.value.code == "empty_document"


def test_llm_extraction_and_validation(monkeypatch):
    class FakeLlm:
        content = json.dumps([
            {"symbol": "NTLC", "side": "achat", "date": "2026-01-15", "quantity": 10, "price": 50000},
            {"symbol": "NTLC", "side": "vente", "date": "2026-02-01", "quantity": 3, "price": 52000},
            {"symbol": "UNKNOWN", "side": "buy", "date": "2026-02-01", "quantity": 1, "price": 1},
        ])

        def invoke(self, messages):
            return self

    monkeypatch.setattr(sgi_import, "get_llm", lambda: FakeLlm())
    transactions, warnings = sgi_import.extract_transactions("Relevé SGI")
    assert len(transactions) == 2
    assert transactions[0]["side"] == "buy"
    assert transactions[1]["side"] == "sell"
    assert len(warnings) == 1


def test_strict_validation_rejects_duplicates():
    raw = [
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 1, "price": 50000},
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 1, "price": 50000},
    ]
    with pytest.raises(sgi_import.DocumentError) as error:
        sgi_import.validate_transactions(raw, strict=True)
    assert error.value.code == "duplicate_transaction"


def test_apply_import_and_history(temp_db, monkeypatch):
    transactions = [
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 10, "price": 50000},
        {"symbol": "NTLC", "side": "buy", "date": "2026-02-01", "quantity": 5, "price": 52000},
        {"symbol": "NTLC", "side": "sell", "date": "2026-03-01", "quantity": 3, "price": 53000},
    ]
    result = user_db.portfolio_apply_import(USER_ID, "a" * 64, transactions)
    assert result["ok"], result
    position = user_db.portfolio_positions(USER_ID)[0]
    assert position["quantity"] == 12
    assert position["total_cost"] == 610000
    assert user_db.portfolio_apply_import(USER_ID, "a" * 64, transactions)["error"] == "already_imported"

    oversell = user_db.portfolio_apply_import(USER_ID, "b" * 64, [
        {"symbol": "NTLC", "side": "sell", "date": "2026-03-02", "quantity": 100, "price": 50000},
    ])
    assert not oversell["ok"], oversell
    assert user_db.portfolio_positions(USER_ID)[0]["quantity"] == 12
    with db_engine.session_scope() as session:
        assert len(session.execute(select(models.PortfolioImport)).scalars().all()) == 1

    today = date.today()
    rows = [
        {"date": today - timedelta(days=20), "price": 50000.0},
        {"date": today - timedelta(days=10), "price": 52000.0},
        {"date": today, "price": 60000.0},
    ]
    monkeypatch.setattr(user_db, "load_series", lambda *args, **kwargs: rows)
    history = user_db.portfolio_history(USER_ID, 90)
    assert all(point["day"] >= (today - timedelta(days=89)).isoformat() for point in history)
    assert history[-1]["total_value_fcfa"] == 720000
    assert history[-1]["total_cost_fcfa"] == 610000
    assert history[-1]["gain_loss_fcfa"] == 110000
    assert user_db.portfolio_positions(OTHER_USER_ID) == []


def test_canonical_sgi_and_dividend_validation():
    transactions, warnings = sgi_import.validate_transactions([
        {
            "symbol": "NTLC",
            "side": "dividende",
            "date": "2026-02-15",
            "quantity": 0,
            "price": 0,
            "amount": 1000,
            "sgi": "SGI Phoenix Capital Management",
        },
        {
            "symbol": "NTLC",
            "side": "dividend",
            "date": "2026-02-16",
            "quantity": 0,
            "price": 0,
            "amount": 500,
            "sgi": "Unknown broker",
        },
    ])
    assert transactions[0]["sgi"] == "PHOENIX CAPITAL MANAGEMENT"
    assert transactions[0]["amount"] == 1000
    assert transactions[1]["sgi"] == "Non affecté"
    assert any("courtier non identifié" in warning for warning in warnings)


def test_sgi_specific_sale_and_dividends(temp_db, monkeypatch):
    transactions = [
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 10, "price": 50000, "amount": 500000, "sgi": "PHOENIX CAPITAL MANAGEMENT"},
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-20", "quantity": 5, "price": 52000, "amount": 260000, "sgi": "BSIC Capital SA"},
        {"symbol": "NTLC", "side": "sell", "date": "2026-02-01", "quantity": 2, "price": 53000, "amount": 106000, "sgi": "PHOENIX CAPITAL MANAGEMENT"},
        {"symbol": "NTLC", "side": "dividend", "date": "2026-02-15", "quantity": 0, "price": 0, "amount": 1000, "sgi": "PHOENIX CAPITAL MANAGEMENT"},
    ]
    result = user_db.portfolio_apply_import(USER_ID, "c" * 64, transactions)
    assert result["ok"], result
    assert result["dividend_count"] == 1
    positions = {position["sgi"]: position for position in user_db.portfolio_positions(USER_ID)}
    assert positions["PHOENIX CAPITAL MANAGEMENT"]["quantity"] == 8
    assert positions["BSIC Capital SA"]["quantity"] == 5
    breakdown = user_db.portfolio_sgi_breakdown(USER_ID)
    phoenix = next(group for group in breakdown if group["sgi"] == "PHOENIX CAPITAL MANAGEMENT")
    assert phoenix["dividends_fcfa"] == 1000
    assert phoenix["positions_count"] == 1

    today = date.today()
    rows = [
        {"date": today - timedelta(days=20), "price": 50000.0},
        {"date": today - timedelta(days=10), "price": 53000.0},
        {"date": today, "price": 60000.0},
    ]
    monkeypatch.setattr(user_db, "load_series", lambda *args, **kwargs: rows)
    history = user_db.portfolio_history(USER_ID, 90)
    assert history[-1]["dividends_fcfa"] == 1000
    assert history[-1]["total_value_fcfa"] == 780000
    assert history[-1]["total_cost_fcfa"] == 660000
    assert history[-1]["gain_loss_fcfa"] == 120000


def test_sgi_breakdown_includes_dividend_only_brokers(temp_db):
    """An SGI with dividends but no current position must still appear in the
    breakdown — otherwise the SGI chart's 'Dividendes' view shows nothing."""
    assert user_db.portfolio_add(USER_ID, "NTLC", 50000, "2026-01-15", 10)["ok"]
    assert user_db.portfolio_dividend_add(
        USER_ID, "NTLC", 1000, "2026-02-15", sgi="PHOENIX CAPITAL MANAGEMENT"
    )["ok"]

    breakdown = {group["sgi"]: group for group in user_db.portfolio_sgi_breakdown(USER_ID)}
    assert breakdown["Non affecté"]["positions_count"] == 1
    assert breakdown["Non affecté"]["dividends_fcfa"] == 0
    phoenix = breakdown["PHOENIX CAPITAL MANAGEMENT"]
    assert phoenix["positions_count"] == 0
    assert phoenix["dividends_fcfa"] == 1000


def test_parse_and_confirm_api(temp_db, monkeypatch):
    transactions = [
        {"symbol": "NTLC", "side": "buy", "date": "2026-01-15", "quantity": 2, "price": 50000, "amount": 100000, "sgi": "PHOENIX CAPITAL MANAGEMENT"},
        {"symbol": "NTLC", "side": "sell", "date": "2026-02-01", "quantity": 1, "price": 52000, "amount": 52000, "sgi": "PHOENIX CAPITAL MANAGEMENT"},
    ]
    monkeypatch.setattr(
        sgi_import,
        "extract_transactions",
        lambda text: (transactions, ["test warning"]),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_app_user] = lambda: {"id": "user", "principal_id": USER_ID}
    client = TestClient(app)
    response = client.post(
        "/mobile/v1/portfolio/import/parse",
        files={"file": ("statement.pdf", make_pdf("NTLC 2 50000"), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["warnings"] == ["test warning"]
    assert payload["transactions"] == transactions

    confirm = client.post(
        "/mobile/v1/portfolio/import/confirm",
        json={"content_hash": payload["content_hash"], "transactions": payload["transactions"]},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["buy_count"] == 1
    assert confirm.json()["sell_count"] == 1
    duplicate = client.post(
        "/mobile/v1/portfolio/import/confirm",
        json={"content_hash": payload["content_hash"], "transactions": payload["transactions"]},
    )
    assert duplicate.status_code == 409
    assert user_db.portfolio_positions(USER_ID)[0]["quantity"] == 1
    assert user_db.portfolio_positions(OTHER_USER_ID) == []


def test_manual_dividend_api_summary_and_history(temp_db, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_app_user] = lambda: {"id": "user", "principal_id": USER_ID}
    client = TestClient(app)
    assert user_db.portfolio_add(
        USER_ID, "NTLC", 50000, "2026-01-15", 10, sgi="PHOENIX CAPITAL MANAGEMENT"
    )["ok"]
    payment_date = (date.today() - timedelta(days=10)).isoformat()
    response = client.post(
        "/mobile/v1/portfolio/dividends",
        json={
            "symbol": "NTLC",
            "amount": 1000,
            "payment_date": payment_date,
            "sgi": "PHOENIX CAPITAL MANAGEMENT",
        },
    )
    assert response.status_code == 200, response.text
    with db_engine.session_scope() as session:
        row = session.execute(select(models.PortfolioDividend)).scalar_one()
        assert row.import_id is None
        assert row.amount == 1000

    monkeypatch.setattr(user_db, "_current_price", lambda symbol: 60000.0)
    summary = user_db.portfolio_summary(USER_ID)
    assert summary["gain_loss_fcfa"] == 100000
    assert summary["dividends_fcfa"] == 1000
    assert summary["total_gain_loss_fcfa"] == 101000
    assert summary["total_gain_loss_pct"] == 20.2
    assert user_db.portfolio_summary(USER_ID, sgi="BSIC Capital SA")["dividends_fcfa"] == 0
    assert user_db.portfolio_summary(OTHER_USER_ID)["dividends_fcfa"] == 0

    today = date.today()
    rows = [
        {"date": today - timedelta(days=20), "price": 50000.0},
        {"date": today - timedelta(days=10), "price": 55000.0},
        {"date": today, "price": 60000.0},
    ]
    monkeypatch.setattr(user_db, "load_series", lambda *args, **kwargs: rows)
    history = user_db.portfolio_history(USER_ID, 90)
    assert history[-1]["dividends_fcfa"] == 1000
    assert history[-1]["total_value_fcfa"] == 600000


def test_manual_dividend_update_delete(temp_db):
    """Dividends are listed in the portfolio payload and can be edited/deleted."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_app_user] = lambda: {"id": "user", "principal_id": USER_ID}
    client = TestClient(app)

    response = client.post(
        "/mobile/v1/portfolio/dividends",
        json={
            "symbol": "NTLC",
            "amount": 1000,
            "payment_date": "2026-01-20",
            "sgi": "PHOENIX CAPITAL MANAGEMENT",
        },
    )
    assert response.status_code == 200, response.text

    body = client.get("/mobile/v1/portfolio").json()
    assert len(body["dividends"]) == 1
    dividend = body["dividends"][0]
    assert dividend["symbol"] == "NTLC"
    assert dividend["amount"] == 1000
    assert dividend["sgi"] == "PHOENIX CAPITAL MANAGEMENT"
    assert "sector" in dividend
    dividend_id = dividend["id"]

    response = client.put(
        f"/mobile/v1/portfolio/dividends/{dividend_id}",
        json={"amount": 2500, "payment_date": "2026-02-01", "sgi": "BSIC Capital SA"},
    )
    assert response.status_code == 200, response.text
    dividend = client.get("/mobile/v1/portfolio").json()["dividends"][0]
    assert dividend["amount"] == 2500
    assert dividend["payment_date"] == "2026-02-01"
    assert dividend["sgi"] == "BSIC Capital SA"
    assert user_db.portfolio_dividends_total(USER_ID) == 2500

    # The SGI filter applies to the dividends list too.
    assert client.get("/mobile/v1/portfolio", params={"sgi": "PHOENIX CAPITAL MANAGEMENT"}).json()["dividends"] == []
    assert len(client.get("/mobile/v1/portfolio", params={"sgi": "BSIC Capital SA"}).json()["dividends"]) == 1

    # Another user cannot edit or delete it.
    app.dependency_overrides[require_app_user] = lambda: {"id": "other", "principal_id": OTHER_USER_ID}
    assert client.put(
        f"/mobile/v1/portfolio/dividends/{dividend_id}", json={"amount": 1}
    ).status_code == 404
    assert client.delete(f"/mobile/v1/portfolio/dividends/{dividend_id}").status_code == 404

    app.dependency_overrides[require_app_user] = lambda: {"id": "user", "principal_id": USER_ID}
    assert client.delete(f"/mobile/v1/portfolio/dividends/{dividend_id}").status_code == 200
    assert client.get("/mobile/v1/portfolio").json()["dividends"] == []
    assert user_db.portfolio_dividends_total(USER_ID) == 0

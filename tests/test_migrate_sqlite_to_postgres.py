from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql

from app.db.models import AppUser, Base, Portfolio, PortfolioImport, User
import scripts.migrate_sqlite_to_postgres as migration
from scripts.migrate_sqlite_to_postgres import (
    _readonly_sqlite_engine,
    _sync_postgres_sequence,
    import_user_data,
)


def _database(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return engine


def test_import_preserves_app_accounts_and_portfolio_and_is_idempotent(tmp_path):
    source = _database(tmp_path / "source.db")
    target = _database(tmp_path / "target.db")
    app_user_id = uuid.uuid4()

    with source.begin() as connection:
        connection.execute(
            User.__table__.insert().values(telegram_id=123, help_sent_at="sent")
        )
        connection.execute(User.__table__.insert().values(telegram_id=-123))
        connection.execute(
            AppUser.__table__.insert().values(
                id=app_user_id,
                principal_id=-123,
                email="investor@example.com",
                password_hash="existing-password-hash",
            )
        )
        connection.execute(
            Portfolio.__table__.insert().values(
                telegram_id=-123,
                symbol="NTLC",
                buy_price=1000,
                buy_date="2026-01-02",
                quantity=2,
            )
        )

    with target.begin() as connection:
        result = import_user_data(source, connection)
    assert result["app_users"] == 1
    assert result["portfolio"] == 1

    with target.connect() as connection:
        account = connection.execute(
            select(AppUser.__table__).where(AppUser.id == app_user_id)
        ).mappings().one()
        assert account["email"] == "investor@example.com"
        assert account["password_hash"] == "existing-password-hash"
        assert connection.execute(select(Portfolio.__table__)).mappings().one()["quantity"] == 2

    with target.begin() as connection:
        repeated = import_user_data(source, connection)
    assert repeated["app_users"] == 0
    assert repeated["app_users (already identical)"] == 1

    source.dispose()
    target.dispose()


def test_import_source_opens_read_only_sqlite_database(tmp_path):
    source_path = tmp_path / "source.db"
    writable_source = _database(source_path)
    with writable_source.begin() as connection:
        connection.execute(User.__table__.insert().values(telegram_id=789))
    writable_source.dispose()

    source = _readonly_sqlite_engine(source_path)
    target = _database(tmp_path / "target.db")
    with target.begin() as connection:
        result = import_user_data(source, connection)
    assert result["users"] == 1
    source.dispose()
    target.dispose()


def test_import_creates_missing_user_row_for_app_account(tmp_path):
    source = _database(tmp_path / "source.db")
    target = _database(tmp_path / "target.db")
    app_user_id = uuid.uuid4()
    principal_id = -2004400736916

    with source.begin() as connection:
        connection.execute(
            AppUser.__table__.insert().values(
                id=app_user_id,
                principal_id=principal_id,
                email="account@example.com",
                password_hash="password-hash",
            )
        )
        connection.execute(
            PortfolioImport.__table__.insert().values(
                telegram_id=principal_id,
                content_hash="import-hash",
                transactions_json="[]",
            )
        )

    with target.begin() as connection:
        result = import_user_data(source, connection)
    assert result["users (created for app accounts)"] == 1

    with target.connect() as connection:
        assert connection.execute(
            select(User.telegram_id).where(User.telegram_id == principal_id)
        ).scalar_one() == principal_id
        assert connection.execute(
            select(PortfolioImport.telegram_id)
        ).scalar_one() == principal_id

    with target.begin() as connection:
        repeated = import_user_data(source, connection)
    assert repeated["users (created for app accounts)"] == 0

    source.dispose()
    target.dispose()


def test_postgres_sequence_sync_never_sets_negative_ids():
    class FakeConnection:
        dialect = postgresql.dialect()

        def __init__(self):
            self.statement = None

        def execute(self, statement, parameters):
            self.statement = str(statement)

    connection = FakeConnection()
    _sync_postgres_sequence(connection, User.__table__)

    assert "GREATEST(COALESCE(MAX(telegram_id), 1), 1)" in connection.statement
    assert "COALESCE(MAX(telegram_id), 0) >= 1" in connection.statement


def test_dry_run_skips_sequence_sync(tmp_path, monkeypatch):
    source = _database(tmp_path / "source.db")
    target = _database(tmp_path / "target.db")
    with source.begin() as connection:
        connection.execute(User.__table__.insert().values(telegram_id=-123))

    def unexpected_sequence_sync(*_args):
        raise AssertionError("dry run must not change PostgreSQL sequences")

    monkeypatch.setattr(migration, "_sync_postgres_sequence", unexpected_sequence_sync)
    with target.begin() as connection:
        result = import_user_data(source, connection, sync_sequences=False)
    assert result["users"] == 1

    source.dispose()
    target.dispose()


def test_import_refuses_to_overwrite_conflicting_target_rows(tmp_path):
    source = _database(tmp_path / "source.db")
    target = _database(tmp_path / "target.db")
    with source.begin() as connection:
        connection.execute(User.__table__.insert().values(telegram_id=456))
    with target.begin() as connection:
        connection.execute(
            User.__table__.insert().values(telegram_id=456, help_sent_at="different")
        )

    with target.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(ValueError, match="Conflicting target row"):
            import_user_data(source, connection)
        transaction.rollback()

    source.dispose()
    target.dispose()

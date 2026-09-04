"""SGI broker profiles: sync the scraped broker list into the local DB and
serve list/detail from there (the app renders details in-app)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update

from app.db import engine as db_engine
from app.db import migrate as db_migrate
from app.db import models as db_models

logger = logging.getLogger(__name__)


def sync_sgi_to_db() -> int:
    """Import the local sgi_brvm.json into sgi_brokers (upsert by name)."""
    from app.scrapers.sgi_brvm import load_sgi_local

    data = load_sgi_local() or {}
    entries = data.get("sgi") or data.get("brokers") or []
    if not entries:
        return 0
    db_migrate.ensure_schema()
    now = datetime.now(timezone.utc)
    with db_engine.session_scope() as s:
        existing = {r[0]: r[1] for r in s.execute(select(db_models.SgiBroker.name, db_models.SgiBroker.id)).all()}
        for e in entries:
            name = (e.get("name") or "").strip()
            if not name:
                continue
            fields = {
                "country": e.get("country"),
                "country_code": e.get("country_code"),
                "phone": e.get("phone"),
                "email": e.get("email"),
                "website": e.get("website"),
                "address": e.get("address"),
                "info": e.get("info"),
                "min_amount": e.get("min_amount"),
                "note": e.get("note"),
                "other_countries": e.get("other_countries"),
                "raw_json": json.dumps(e, ensure_ascii=False),
                "updated_at": now,
            }
            if name in existing:
                s.execute(update(db_models.SgiBroker).where(db_models.SgiBroker.id == existing[name]).values(**fields))
            else:
                s.execute(db_models.SgiBroker.__table__.insert().values(name=name, **fields))
    return len(entries)


def _row_to_dict(r: db_models.SgiBroker, *, detail: bool = False) -> dict[str, Any]:
    out = {
        "id": r.id,
        "name": r.name,
        "country": r.country,
        "country_code": r.country_code,
        "phone": r.phone,
        "email": r.email,
        "website": r.website,
        "address": r.address,
        "min_amount": r.min_amount,
        "note": r.note,
        "other_countries": r.other_countries,
    }
    if detail:
        out["info"] = r.info
        out["detail_text"] = r.detail_text
    return out


def list_brokers(country: str | None = None) -> list[dict[str, Any]]:
    db_migrate.ensure_schema()
    stmt = select(db_models.SgiBroker).order_by(db_models.SgiBroker.country, db_models.SgiBroker.name)
    if country:
        stmt = stmt.where(db_models.SgiBroker.country.ilike(f"%{country}%"))
    with db_engine.session_scope() as s:
        return [_row_to_dict(r) for r in s.execute(stmt).scalars().all()]


def get_broker(broker_id: int) -> dict[str, Any] | None:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        r = s.execute(select(db_models.SgiBroker).where(db_models.SgiBroker.id == broker_id)).scalars().first()
        return _row_to_dict(r, detail=True) if r else None


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def brokers_count() -> int:
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        return len(s.execute(select(db_models.SgiBroker.id)).all())

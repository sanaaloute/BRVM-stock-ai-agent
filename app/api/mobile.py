"""Mobile app REST API (Flutter). Everything here requires a JWT bearer token
issued by /mobile/v1/auth — the mobile client never uses the bot's shared
API_SECRET_KEY. User data is keyed by the app user's principal id, which is
shared with the Telegram identity when the accounts are linked.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import config
from app.api.mobile_auth import require_app_user
from app.services import auth_service
from app.utils import user_db

router = APIRouter(prefix="/mobile/v1", tags=["mobile"])


def _principal(user: dict[str, Any]) -> int:
    return int(user["principal_id"])


# --- Market data (no AI round-trip) -------------------------------------------

@router.get("/market/palmares")
def market_palmares(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    from app.services.market_data import palmares_for_api

    stocks = palmares_for_api()
    return {"stocks": stocks}


@router.get("/market/predictions")
def market_predictions(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Latest daily AI predictions (computed post-close), most confident first.
    Empty list + day=None until the first post-close run."""
    from app.utils.brvm_companies import get_symbol_to_name

    rows = user_db.get_latest_predictions()
    names = get_symbol_to_name()
    items = [{
        "symbol": r["symbol"],
        "name": names.get(r["symbol"]),
        "price": r.get("price"),
        "direction": r.get("direction"),
        "confidence_pct": r.get("confidence_pct"),
        "expected_move_pct": r.get("expected_move_pct"),
        "score": r.get("score"),
        "signal": r.get("signal"),
    } for r in rows]
    items.sort(key=lambda r: r["confidence_pct"] or 0.0, reverse=True)
    return {"day": rows[0]["day"] if rows else None, "predictions": items}


@router.get("/market/predictions/{symbol}")
def market_prediction_detail(symbol: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Full prediction for one symbol: targets, explanation, computed metrics."""
    from app.utils.brvm_companies import get_symbol_to_name

    sym = symbol.strip().upper()
    if sym not in user_db.get_valid_symbols():
        raise HTTPException(status_code=404, detail=f"{sym} n'est pas un symbole BRVM coté.")
    row = user_db.get_prediction(sym)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Aucune prévision disponible pour {sym}.")
    try:
        details = json.loads(row.get("details_json") or "{}")
    except (TypeError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    return {
        "symbol": row["symbol"],
        "name": get_symbol_to_name().get(sym),
        "day": row.get("day"),
        "price": row.get("price"),
        "direction": row.get("direction"),
        "confidence_pct": row.get("confidence_pct"),
        "expected_move_pct": row.get("expected_move_pct"),
        "target_low": row.get("target_low"),
        "target_high": row.get("target_high"),
        "score": row.get("score"),
        "signal": row.get("signal"),
        "explanation": row.get("explanation"),
        "details": details,
    }


@router.get("/market/quotes/{symbol}")
def market_quote(symbol: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if sym not in user_db.get_valid_symbols():
        raise HTTPException(status_code=404, detail=f"{sym} n'est pas un symbole BRVM coté.")
    return {"symbol": sym, "price": user_db.current_price(sym)}


@router.get("/market/companies/{symbol}")
def market_company(symbol: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    from app.scrapers.sikafinance_company import load_company_details

    sym = symbol.strip().upper()
    data = load_company_details(sym)
    if not data:
        raise HTTPException(status_code=404, detail=f"Aucune fiche société pour {sym}.")
    return {"symbol": sym, "details": data}


@router.get("/market/brokers")
def market_brokers(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """SGI broker list from the local DB (fast, no external site involved)."""
    from app.services import sgi_service

    brokers = sgi_service.list_brokers()
    if not brokers:
        # First run: import from the fetched broker file (or fetch it once).
        try:
            from app.scrapers.sgi_brvm import fetch_and_save_sgi

            fetch_and_save_sgi()
        except Exception:
            pass
        sgi_service.sync_sgi_to_db()
        brokers = sgi_service.list_brokers()
    if not brokers:
        raise HTTPException(status_code=404, detail="Aucune donnée courtier disponible pour le moment.")
    return {"brokers": {"items": brokers, "count": len(brokers)}}


@router.get("/market/brokers/{broker_id}")
def market_broker_detail(broker_id: int, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Full in-app SGI profile: conditions, contact, address, countries…"""
    from app.services import sgi_service

    broker = sgi_service.get_broker(broker_id)
    if broker is None:
        raise HTTPException(status_code=404, detail="Courtier introuvable.")
    return {"broker": broker}


# --- Market news ---------------------------------------------------------------
_NEWS_CACHE_TTL = 1800.0  # 30 min: news sections must not re-scrape per request
_news_cache: dict[str, Any] = {"at": 0.0, "payload": None}

# User-facing payloads never name external data vendors: sources are presented
# neutrally and vendor URLs are dropped from the app surface.
_VENDOR_SOURCES = {
    "sikafinance_bourse": "BRVM Invest",
    "sikafinance_actualites": "BRVM Invest",
    "sikafinance_communiques": "BRVM Invest",
    "richbourse": "BRVM Invest",
    "brvm_announcements": "BRVM",
}
_VENDOR_URL_MARKERS = ("sikafinance.com", "richbourse.com")


def _scrub_vendor_refs(section: Any) -> Any:
    """Neutralize source names and vendor listing URLs inside one payload
    section (in place). Item-level article links are kept: opening a news
    article in the browser is expected behavior."""
    if not isinstance(section, dict):
        return section
    src = section.get("source")
    if isinstance(src, str):
        section["source"] = _VENDOR_SOURCES.get(src, src)
    for key in ("url", "tarifs_url", "documents_url", "detail_url", "pdf_url"):
        v = section.get(key)
        if isinstance(v, str) and any(m in v for m in _VENDOR_URL_MARKERS):
            section.pop(key, None)
    section.pop("warning", None)
    return section


def _tavily_site_news(limit: int = 20) -> dict[str, Any]:
    """Discover market news via the search API (server-side fetch — works even
    when the source site blocks our network). Returns the standard news shape."""
    import config

    out: dict[str, Any] = {"source": "search", "url": "", "items": [], "error": None}
    if not config.TAVILY_API_KEY:
        out["error"] = "search unavailable"
        return out
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=config.TAVILY_API_KEY)
        r = client.search(
            query="actualités bourse BRVM Côte d'Ivoire UEMOA",
            include_domains=["sikafinance.com"],
            max_results=min(limit, 20),
            search_depth="basic",
        )
        seen: set[str] = set()
        for res in r.get("results", []):
            url = res.get("url") or ""
            title = (res.get("title") or "").strip()
            if not url or not title or url in seen:
                continue
            if "/marches/" not in url:
                continue
            seen.add(url)
            snippet = (res.get("content") or "").strip()
            out["items"].append({
                "date": (res.get("published_date") or "")[:10],
                "title": title,
                "url": url,
                "snippet": snippet[:300],
            })
        if not out["items"]:
            out["error"] = "search returned no items"
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def _market_news_payload() -> dict[str, Any]:
    import time

    now = time.monotonic()
    cached = _news_cache["payload"]
    if cached is not None and now - _news_cache["at"] < _NEWS_CACHE_TTL:
        return cached
    from app.utils.news import get_brvm_official_announcements, get_sikafinance_actualites_bourse

    # Chain: direct scrape → browser render (inside the scraper) → search API →
    # BRVM official announcements. First source with items wins.
    payload = get_sikafinance_actualites_bourse(limit=25)
    items = payload.get("items") or []
    if not items:
        payload = _tavily_site_news(limit=20)
        items = payload.get("items") or []
    if not items:
        fallback = get_brvm_official_announcements(limit=25)
        fb_items = fallback.get("items") or []
        if fb_items:
            payload = {
                "source": "BRVM",
                "items": [
                    {
                        "date": it.get("date"),
                        "title": it.get("title"),
                        "url": it.get("pdf_url") or it.get("url") or "https://www.brvm.org/",
                        "snippet": it.get("company"),
                    }
                    for it in fb_items
                ],
            }
    payload = _scrub_vendor_refs(payload)
    _news_cache["payload"] = payload
    _news_cache["at"] = now
    return payload


@router.get("/market/news")
def market_news(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    return {"news": _market_news_payload()}


@router.get("/news/article")
def news_article(url: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """In-app article reader: fetches the article server-side (the source site
    blocks device browsers) and returns clean readable content."""
    from app.services.article import fetch_article

    article = fetch_article(url)
    if article is None:
        raise HTTPException(status_code=502, detail="Impossible de charger l'article pour le moment.")
    return {"article": article}


# --- Stock detail (aggregated investor view) -----------------------------------

_PERIOD_DAYS = {"1M": 30, "3M": 90, "6M": 182, "1Y": 365, "ALL": None}
_HISTORY_MAX_POINTS = 250


def _load_history(symbol: str, period: str) -> list[dict[str, Any]]:
    from datetime import date, timedelta

    from app.utils._data import load_series

    days = _PERIOD_DAYS.get(period.upper(), 90)
    start = date.today() - timedelta(days=days) if days else None
    rows = load_series(symbol, start_date=start) if start else load_series(symbol)
    points = [{"date": r["date"].isoformat(), "price": r["price"]} for r in rows if r.get("price")]
    if len(points) > _HISTORY_MAX_POINTS:  # downsample evenly for the chart
        stride = len(points) / _HISTORY_MAX_POINTS
        points = [points[int(i * stride)] for i in range(_HISTORY_MAX_POINTS)]
    return points


def _safe_section(fn, *args, **kwargs) -> dict[str, Any]:
    """Run one detail-section fetch; failures degrade to {error} instead of 500."""
    try:
        return fn(*args, **kwargs) or {}
    except Exception as e:  # noqa: BLE001 - section-level graceful degradation
        return {"error": str(e)[:200]}


@router.get("/market/symbols/{symbol}")
def market_symbol_detail(symbol: str, period: str = "3M", user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Aggregated investor view for one stock: quote + price history + company
    fiche (fundamentals) + dividends + news/activity + technical prediction.
    Sections degrade independently (scrapers can be slow/down)."""
    from app.scrapers.sikafinance_company import load_company_details
    from app.services.market_data import palmares_for_api
    from app.utils.news import get_company_news, get_richbourse_dividends, get_richbourse_prediction

    sym = symbol.strip().upper()
    if sym not in user_db.get_valid_symbols():
        raise HTTPException(status_code=404, detail=f"{sym} n'est pas un symbole BRVM coté.")

    palmares_row = next(
        (s for s in palmares_for_api() if (s.get("symbol") or "").strip().upper() == sym),
        None,
    )
    history = _safe_section(lambda: {"points": _load_history(sym, period)})
    fiche = _safe_section(load_company_details, sym)
    dividends = _safe_section(get_richbourse_dividends, 50, sym)
    news = _safe_section(get_company_news, sym)
    prediction = _safe_section(get_richbourse_prediction, sym)
    score = _safe_section(_latest_score, sym)

    return {
        "symbol": sym,
        "period": period.upper(),
        "quote": palmares_row,
        "history": history.get("points") if "points" in history else history,
        "profile": _scrub_vendor_refs(fiche),
        "dividends": _scrub_vendor_refs(dividends),
        "news": _scrub_vendor_refs(news),
        "prediction": _scrub_vendor_refs(prediction),
        "score": score,
    }


def _latest_score(symbol: str) -> dict[str, Any]:
    from app.utils.user_db import get_latest_snapshots

    for snap in get_latest_snapshots()[:200]:
        if snap.get("symbol") == symbol:
            return {"day": snap.get("day"), "score": snap.get("score"), "signal": snap.get("signal")}
    return {}


# --- Portfolio ----------------------------------------------------------------

class HoldingBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    buy_price: float = Field(gt=0)
    buy_date: str = Field(min_length=8, max_length=10)  # AAAA-MM-JJ
    quantity: float = Field(default=1.0, gt=0)


@router.get("/portfolio")
def portfolio_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Aggregated positions (one per symbol) with the individual buy lots."""
    pid = _principal(user)
    return {
        "summary": user_db.portfolio_summary(pid),
        "positions": user_db.portfolio_with_prices(pid),
    }


@router.post("/portfolio")
def portfolio_add(body: HoldingBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Record one buy lot (never overwrites previous purchases)."""
    result = user_db.portfolio_add(
        _principal(user), body.symbol, body.buy_price, body.buy_date, body.quantity
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


class LotBody(BaseModel):
    buy_price: float | None = Field(default=None, gt=0)
    buy_date: str | None = Field(default=None, min_length=8, max_length=10)
    quantity: float | None = Field(default=None, gt=0)


@router.put("/portfolio/lots/{lot_id}")
def portfolio_lot_update(lot_id: int, body: LotBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.portfolio_lot_update(
        _principal(user), lot_id,
        buy_price=body.buy_price, buy_date=body.buy_date, quantity=body.quantity,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.delete("/portfolio/lots/{lot_id}")
def portfolio_lot_delete(lot_id: int, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.portfolio_lot_remove(_principal(user), lot_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.delete("/portfolio/{symbol}")
def portfolio_delete(symbol: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Remove ALL lots of a symbol."""
    result = user_db.portfolio_remove(_principal(user), symbol)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


# --- Watchlist ----------------------------------------------------------------

class SymbolBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)


@router.get("/watchlist")
def watchlist_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    pid = _principal(user)
    symbols = [r["symbol"] for r in user_db.tracking_list(pid)]
    prices = {sym: user_db.current_price(sym) for sym in symbols}
    return {"symbols": [{"symbol": sym, "price": prices.get(sym)} for sym in symbols]}


@router.post("/watchlist")
def watchlist_add(body: SymbolBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.tracking_add(_principal(user), body.symbol)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/watchlist/{symbol}")
def watchlist_delete(symbol: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.tracking_remove(_principal(user), symbol)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


# --- Price alerts -------------------------------------------------------------

class AlertBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    target_price: float = Field(gt=0)
    direction: str = Field(default="above", pattern="^(above|below)$")


@router.get("/alerts")
def alerts_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    return {"alerts": user_db.target_list(_principal(user))}


@router.post("/alerts")
def alerts_add(body: AlertBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.target_add(_principal(user), body.symbol, body.target_price, body.direction)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/alerts/{alert_id}")
def alerts_delete(alert_id: int, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    result = user_db.target_remove_by_id(_principal(user), alert_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


# --- Digest subscription ------------------------------------------------------

class DigestBody(BaseModel):
    frequency: str = Field(pattern="^(daily|weekly)$")
    enabled: bool = True


@router.get("/digest")
def digest_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    row = user_db.digest_get(_principal(user))
    if row is None:
        return {"enabled": False, "frequency": "daily"}
    return {"enabled": bool(row["enabled"]), "frequency": row["frequency"]}


@router.put("/digest")
def digest_put(body: DigestBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    pid = _principal(user)
    if not body.enabled:
        user_db.digest_unsubscribe(pid)
        return {"ok": True, "enabled": False}
    result = user_db.digest_set(pid, body.frequency)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return {"ok": True, "enabled": True, "frequency": body.frequency}


# --- Quota ---------------------------------------------------------------------

@router.get("/quota")
def quota_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    used = user_db.get_daily_usage(user_key(user))
    return {"used": used, "limit": config.DAILY_FREE_QUOTA, "exempt": user_key(user) in config.QUOTA_EXEMPT_IDS}


@router.get("/me")
def me_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Fresh profile for the account screen."""
    from app.services import auth_service

    fresh = auth_service.get_app_user_by_id(user["id"]) or user
    return {
        "id": str(fresh["id"]),
        "email": fresh.get("email"),
        "phone": fresh.get("phone"),
        "has_telegram": fresh.get("telegram_id") is not None,
        "has_password": bool(fresh.get("has_password")),
    }


class DeleteAccountBody(BaseModel):
    password: str | None = Field(default=None, max_length=200)


@router.delete("/me")
def me_delete(body: DeleteAccountBody | None = None, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Delete the account and all its data (Google Play requirement). Accounts
    with a password must confirm it; passwordless (demo) accounts delete
    without one. Body is optional."""
    result = auth_service.delete_app_user(user, password=body.password if body else None)
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    return {"ok": True}


def user_key(user: dict[str, Any]) -> str:
    """Channel-agnostic key for rate limits / daily quota."""
    return f"app:{user['id']}"


# --- AI chat -------------------------------------------------------------------

class MobileChatBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=120)


@router.post("/chat")
async def mobile_chat(body: MobileChatBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    from app.api.chat import ChatRequest, run_chat

    thread_id = body.thread_id or f"app:{user['id']}"
    result = await run_chat(ChatRequest(
        query=body.query,
        thread_id=thread_id,
        telegram_user_id=_principal(user),  # agent tools (portfolio etc.) key on this
        user_id=user_key(user),             # rate limit / quota key
    ))
    payload = result.model_dump()
    if not getattr(result, "error", None):
        payload["quota_remaining"] = max(0, config.DAILY_FREE_QUOTA - user_db.get_daily_usage(user_key(user)))
        payload["thread_id"] = thread_id
    return payload


# --- Conversations --------------------------------------------------------------

def _thread_prefix(user: dict[str, Any]) -> str:
    return f"app:{user['id']}"


def _owns_thread(user: dict[str, Any], thread_id: str) -> bool:
    prefix = _thread_prefix(user)
    return thread_id == prefix or thread_id.startswith(prefix + ":")


def _checkpoint_messages(thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Replay the conversation from the LangGraph checkpoint: alternating
    user/assistant messages (tool internals hidden), most recent last."""
    from app.api.chat import _get_checkpointer

    try:
        tuple_ = _get_checkpointer().get_tuple({"configurable": {"thread_id": thread_id}})
    except Exception:
        return []
    if tuple_ is None:
        return []
    checkpoint = tuple_.checkpoint or {}
    messages = (checkpoint.get("channel_values") or {}).get("messages") or []
    out = []
    for m in messages:
        role = getattr(m, "type", None)
        if role not in ("human", "ai"):
            continue
        content = getattr(m, "content", "")
        if isinstance(content, list):  # multimodal blocks → text parts only
            content = " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
        content = (content or "").strip()
        if not content:
            continue
        out.append({"role": "user" if role == "human" else "assistant", "text": content})
    return out[-limit:]


def _conversation_title(user: dict[str, Any], thread_id: str) -> str:
    """Title = first user message of the thread (truncated); fallback to the slug."""
    prefix = _thread_prefix(user)
    if thread_id == prefix:
        slug = ""
    else:
        slug = thread_id[len(prefix) + 1:]
    msgs = _checkpoint_messages(thread_id, limit=20)
    for m in msgs:
        if m["role"] == "user":
            title = m["text"].replace("\n", " ").strip()
            return title[:48] + ("…" if len(title) > 48 else "")
    return slug or "Discussion"


@router.get("/conversations")
def conversations_get(user: dict = Depends(require_app_user)) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db import engine as db_engine
    from app.db import migrate as db_migrate
    from app.db import models as db_models

    db_migrate.ensure_schema()
    prefix = _thread_prefix(user)
    with db_engine.session_scope() as s:
        rows = s.execute(
            select(db_models.ThreadActivity.thread_id, db_models.ThreadActivity.last_seen)
            .where(
                (db_models.ThreadActivity.thread_id == prefix)
                | db_models.ThreadActivity.thread_id.like(prefix + ":%")
            )
            .order_by(db_models.ThreadActivity.last_seen.desc())
            .limit(50)
        ).mappings().all()
    return {"conversations": [
        {
            "thread_id": r["thread_id"],
            "title": _conversation_title(user, r["thread_id"]),
            "last_seen": r["last_seen"],
        }
        for r in rows
    ]}


@router.get("/conversations/{thread_id}/messages")
def conversations_messages(thread_id: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    """Message history of one of the user's conversations (for restoring the
    chat screen). The agent itself already reads the same checkpoint, so its
    answers take the full history into account."""
    if not _owns_thread(user, thread_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    return {"thread_id": thread_id, "messages": _checkpoint_messages(thread_id)}


@router.delete("/conversations/{thread_id}")
def conversations_delete(thread_id: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    from sqlalchemy import delete

    from app.api.chat import _get_checkpointer
    from app.db import engine as db_engine
    from app.db import migrate as db_migrate
    from app.db import models as db_models

    if not _owns_thread(user, thread_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    try:
        _get_checkpointer().delete_thread(thread_id)
    except Exception:
        pass  # checkpoint may not exist
    db_migrate.ensure_schema()
    with db_engine.session_scope() as s:
        s.execute(delete(db_models.ThreadActivity).where(db_models.ThreadActivity.thread_id == thread_id))
    return {"ok": True}


# --- Devices (push notifications) ----------------------------------------------

class DeviceBody(BaseModel):
    fcm_token: str = Field(min_length=10, max_length=512)
    platform: str = Field(pattern="^(android|ios)$")


@router.post("/devices")
def devices_register(body: DeviceBody, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    auth_service.register_device(user["id"], body.fcm_token, body.platform)
    return {"ok": True}


@router.delete("/devices/{fcm_token}")
def devices_delete(fcm_token: str, user: dict = Depends(require_app_user)) -> dict[str, Any]:
    removed = auth_service.remove_device(fcm_token)
    return {"ok": True, "removed": removed}

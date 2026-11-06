"""Admin area: /admin/dashboard (metrics + user management page), /admin/docs
(developer docs), /admin/v1/* (JSON API). Exactly one admin exists — the
ADMIN_USERNAME/ADMIN_PASSWORD env pair; sessions are tokens signed with
JWT_SECRET, delivered as an HttpOnly SameSite=Strict cookie at login
(the /admin/v1/* API also accepts the raw token as a Bearer header).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

import config
from app.services import admin_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_DASHBOARD_HTML = Path(__file__).resolve().parent.parent / "admin" / "dashboard.html"

# Admin session cookie: HttpOnly (JS never reads it — XSS can't steal it) and
# SameSite=Strict (never sent cross-site — kills CSRF on the admin actions).
_COOKIE_NAME = "kb_admin_session"

# --- Login brute-force protection (in-memory, per-process; same pattern as
# the /chat rate limiter) ---
_LOGIN_WINDOW_SEC = 60.0
_LOGIN_MAX_PER_ACCOUNT = 10   # attempts per (IP, username) — slows credential stuffing
_LOGIN_MAX_PER_IP = 50        # attempts per IP — the tunnel shares one client IP
_login_hits: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _bucket_limited(hits: list[float], limit: int, now: float) -> tuple[list[float], bool]:
    recent = [t for t in hits if now - t < _LOGIN_WINDOW_SEC]
    if len(recent) >= limit:
        return recent, True
    recent.append(now)
    return recent, False


def _login_rate_limited(ip: str, username: str) -> bool:
    now = time.monotonic()
    with _login_lock:
        account_bucket, limited = _bucket_limited(
            _login_hits.get(f"u:{ip}:{username}", []), _LOGIN_MAX_PER_ACCOUNT, now
        )
        _login_hits[f"u:{ip}:{username}"] = account_bucket
        ip_bucket, ip_limited = _bucket_limited(
            _login_hits.get(f"i:{ip}", []), _LOGIN_MAX_PER_IP, now
        )
        _login_hits[f"i:{ip}"] = ip_bucket
        if len(_login_hits) > 10_000:  # keep the dict bounded
            _login_hits.clear()
    return limited or ip_limited


def _extract_token(request: Request) -> str | None:
    """Session token from the Bearer header (API clients) or the login cookie
    (browser pages: /admin/dashboard, /admin/docs)."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    cookie = request.cookies.get(_COOKIE_NAME)
    return cookie.strip() if cookie else None


def require_admin(request: Request) -> None:
    """Gate every admin endpoint/page on a valid session token."""
    if not admin_service.admin_enabled():
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard is not configured (set ADMIN_PASSWORD and JWT_SECRET).",
        )
    token = _extract_token(request)
    if not token or not admin_service.authenticate_token(token):
        raise HTTPException(status_code=401, detail="Admin authentication required.")


AdminDep = Depends(require_admin)


class LoginBody(BaseModel):
    username: str = Field(default="", max_length=120)
    password: str = Field(default="", max_length=200)


@router.post("/admin/v1/login")
def admin_login(body: LoginBody, request: Request, response: Response) -> dict:
    if not admin_service.admin_enabled():
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard is not configured (set ADMIN_PASSWORD and JWT_SECRET).",
        )
    client = request.client.host if request.client else "unknown"
    username = (body.username or "").strip().lower()
    if _login_rate_limited(client, username):
        raise HTTPException(status_code=429, detail="Too many attempts. Retry in a minute.")
    session = admin_service.login(body.username, body.password)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    # Browser session: the same token rides an HttpOnly cookie so the dashboard
    # and docs pages work across tabs/navigation without JS token handling.
    response.set_cookie(
        _COOKIE_NAME,
        session["token"],
        max_age=config.ADMIN_TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return session


@router.post("/admin/v1/logout")
def admin_logout(response: Response) -> dict:
    """Drop the browser session cookie (idempotent; no auth needed)."""
    response.delete_cookie(_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/admin/v1/session", dependencies=[AdminDep])
def admin_session() -> dict:
    """Cheap auth probe used by the dashboard page on load."""
    return {"ok": True}


@router.get("/admin/v1/overview", dependencies=[AdminDep])
def admin_overview() -> dict:
    return admin_service.overview()


@router.get("/admin/v1/timeseries", dependencies=[AdminDep])
def admin_timeseries(days: int = Query(30, ge=7, le=90)) -> dict:
    return admin_service.timeseries(days)


@router.get("/admin/v1/users", dependencies=[AdminDep])
def admin_users(
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query("all", pattern="^(all|active|deactivated)$"),
    sort: str = Query("created_at", pattern="^(created_at|last_active|messages)$"),
) -> dict:
    return admin_service.list_users(q, page, page_size, status=status, sort=sort)


@router.get("/admin/v1/users/{user_id}", dependencies=[AdminDep])
def admin_user_detail(user_id: uuid.UUID) -> dict:
    detail = admin_service.get_user(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return detail


@router.post("/admin/v1/users/{user_id}/deactivate", dependencies=[AdminDep])
def admin_user_deactivate(user_id: uuid.UUID) -> dict:
    if not admin_service.set_user_active(user_id, False):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "is_active": False}


@router.post("/admin/v1/users/{user_id}/activate", dependencies=[AdminDep])
def admin_user_activate(user_id: uuid.UUID) -> dict:
    if not admin_service.set_user_active(user_id, True):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "is_active": True}


@router.post("/admin/v1/users/{user_id}/reset-quota", dependencies=[AdminDep])
def admin_user_reset_quota(user_id: uuid.UUID) -> dict:
    deleted = admin_service.reset_user_quota(user_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "cleared": deleted}


@router.delete("/admin/v1/users/{user_id}", dependencies=[AdminDep])
def admin_user_delete(user_id: uuid.UUID) -> dict:
    if not admin_service.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}


# Security headers for the dashboard page: everything is inline (no external
# assets), so the CSP can be tight — API calls go to same origin only.
_PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

# The docs page is Swagger UI. The assets are vendored under app/admin/docs-assets
# (the CDN is unreliable on some networks and the page must work anywhere the
# dashboard works); the spec and any "try it" calls go to same origin.
_DOCS_ASSETS = _DASHBOARD_HTML.parent / "docs-assets"
_DOCS_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; "
        "img-src data: 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@router.get("/admin", include_in_schema=False)
def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard", status_code=308)


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def admin_page() -> HTMLResponse:
    """The dashboard page (public HTML; all data calls require a session)."""
    try:
        html = _DASHBOARD_HTML.read_text(encoding="utf-8")
    except OSError:
        logger.error("Admin dashboard page missing: %s", _DASHBOARD_HTML)
        raise HTTPException(status_code=500, detail="Dashboard page not installed.")
    return HTMLResponse(content=html, headers=_PAGE_HEADERS)


@router.get("/admin/docs-assets/swagger-ui-bundle.js", dependencies=[AdminDep], include_in_schema=False)
def admin_docs_js() -> FileResponse:
    return FileResponse(_DOCS_ASSETS / "swagger-ui-bundle.js", media_type="text/javascript",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/admin/docs-assets/swagger-ui.css", dependencies=[AdminDep], include_in_schema=False)
def admin_docs_css() -> FileResponse:
    return FileResponse(_DOCS_ASSETS / "swagger-ui.css", media_type="text/css",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/admin/docs", dependencies=[AdminDep], include_in_schema=False)
def admin_docs() -> HTMLResponse:
    """Developer API docs (Swagger UI). The public /docs is disabled — these
    docs exist only behind the admin session."""
    from fastapi.openapi.docs import get_swagger_ui_html

    response = get_swagger_ui_html(
        openapi_url="/admin/openapi.json",
        title="Kora Bourse — API docs",
        swagger_js_url="/admin/docs-assets/swagger-ui-bundle.js",
        swagger_css_url="/admin/docs-assets/swagger-ui.css",
        swagger_favicon_url="",
        init_oauth=None,
    )
    for key, value in _DOCS_HEADERS.items():
        response.headers[key] = value
    return response


@router.get("/admin/openapi.json", dependencies=[AdminDep], include_in_schema=False)
def admin_openapi(request: Request) -> JSONResponse:
    return JSONResponse(request.app.openapi())

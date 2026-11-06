"""HTTPS enforcement for requests arriving through the TLS-terminating ingress
(the Cloudflare tunnel). The origin itself speaks plain HTTP inside the private
Docker network — TLS lives at the edge — so the ingress reports the visitor's
scheme as X-Forwarded-Proto. When it says "http", bounce the client to the
https:// URL (308, method preserved) and answer https traffic with HSTS so
browsers stick to TLS for a year. Direct origin access carries no forwarded
header (local dev, Docker healthcheck) and is left untouched.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

_HSTS_VALUE = "max-age=31536000"


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def _enforce_https(request: Request, call_next):
        proto = request.headers.get("x-forwarded-proto", "").strip().lower()
        if proto == "http":
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
        response = await call_next(request)
        if proto == "https":
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response

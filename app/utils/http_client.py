"""Shared HTTP client using httpx + certifi for SSL verification (fixes CERTIFICATE_VERIFY_FAILED, UNEXPECTED_EOF_WHILE_READING)."""
from __future__ import annotations

import logging
import random
import ssl
import time

import certifi
import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"
HTTP_GET_RETRIES = 3
HTTP_GET_RETRY_DELAY = 2.0

# Explicit SSL context with certifi CA bundle for all HTTPS requests (trends, prediction, scrapers)
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _is_retryable_ssl_error(exc: BaseException) -> bool:
    err_str = str(exc).lower()
    return (
        "ssl" in err_str
        or "eof" in err_str
        or "unexpected_eof" in err_str
        or "connection" in err_str
        or "timeout" in err_str
        or "timed out" in err_str
    )


def http_get(
    url: str,
    *,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    retries: int = HTTP_GET_RETRIES,
    verify: bool = True,
) -> httpx.Response:
    """
    GET url with SSL verification via certifi and configurable timeout.
    Retries on transient SSL/connection errors (e.g. UNEXPECTED_EOF_WHILE_READING).
    Set verify=False to skip certificate verification (e.g. for hosts with bad chains).
    Caller should call response.raise_for_status() and use response.text as needed.
    """
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    request_headers = headers if headers is not None else {"User-Agent": DEFAULT_USER_AGENT}
    verify_ctx: bool | ssl.SSLContext = _SSL_CONTEXT if verify else False
    last_exc: BaseException | None = None
    for attempt in range(max(1, retries)):
        try:
            with httpx.Client(
                verify=verify_ctx,
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                return client.get(url, headers=request_headers)
        except (httpx.HTTPError, OSError) as e:
            last_exc = e
            # httpx timeout exceptions stringify as "timed out"; always retryable
            retryable = isinstance(e, httpx.TimeoutException) or _is_retryable_ssl_error(e)
            if attempt < retries - 1 and retryable:
                delay = HTTP_GET_RETRY_DELAY * (attempt + 1) + random.uniform(0, 0.5)
                logger.warning("HTTP GET %s failed (attempt %s/%s): %s. Retrying in %.1fs.", url, attempt + 1, retries, e, delay)
                time.sleep(delay)
            else:
                raise
    raise last_exc or RuntimeError("http_get failed")

"""In-app news article fetching: given a news article URL, return clean
readable content. The source site blocks plain clients (and even device
browsers via Cloudflare), so the chain is: direct fetch → Tavily extract
(server-side, works) → browser render. Results are cached briefly.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import config

logger = logging.getLogger(__name__)

# Only these hosts may be fetched (SSRF guard): the news sources we link to.
_ALLOWED_HOSTS = ("sikafinance.com", "brvm.org")

_CACHE_TTL = 1800.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _host_allowed(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def _is_block_page(html: str, title: str) -> bool:
    """Cloudflare/bot-wall pages come back as HTTP 200 — detect them."""
    blob = (html[:4000] + " " + title).lower()
    return any(
        marker in blob
        for marker in (
            "attention required",
            "you have been blocked",
            "cf-chl-",
            "cf_chl_",
            "just a moment",
            "checking your browser",
        )
    )


def _extract_from_html(html: str, url: str) -> dict[str, Any] | None:
    """Parse an article page: title + main body paragraphs."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    title = ""
    og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and not title:
        title = h1.get_text(" ", strip=True)

    if _is_block_page(html, title):
        return None

    date = ""
    for attrs in ({"property": "article:published_time"}, {"name": "date"}, {"itemprop": "datePublished"}):
        m = soup.find("meta", attrs=attrs)
        if m and m.get("content"):
            date = str(m["content"])[:10]
            break

    container = (
        soup.find("article")
        or soup.find("div", class_=re.compile(r"article|contenu|content|post", re.I))
        or soup.body
    )
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in (container.find_all("p") if container else [])
    ]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    if len(text) < 200:
        return None
    return {"title": title, "date": date, "url": url, "text": text[:12000]}


def _fetch_direct(url: str) -> dict[str, Any] | None:
    try:
        from app.utils.http_client import http_get

        resp = http_get(url, timeout=30, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        final_host = (urlparse(str(resp.url)).hostname or "").lower()
        if not any(final_host == h or final_host.endswith("." + h) for h in _ALLOWED_HOSTS):
            return None  # redirected outside the allow-list
        return _extract_from_html(resp.text, url)
    except Exception as e:
        logger.info("Direct article fetch failed (%s): %s", url, e)
        return None


_LINK_LINE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _clean_markdown(raw: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)       # images
    text = re.sub(r"\[\s*\]\([^)]*\)", "", text)          # bare share/icon links
    # Drop site-chrome lines that are almost entirely navigation links.
    kept = []
    for ln in text.splitlines():
        links = _LINK_LINE.findall(ln)
        if links and sum(len(x) for x in links) >= max(10, len(ln) * 0.4):
            continue
        kept.append(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", ln))
    text = "\n".join(kept)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _body_quality(text: str) -> bool:
    """A real article body: substantial length + several long prose lines
    (a preamble-only extract has just nav fragments and a title)."""
    if len(text) < 300:
        return False
    long_lines = sum(1 for ln in text.splitlines() if len(ln.strip()) >= 60)
    return long_lines >= 3


def _trim_boilerplate(text: str, title: str) -> str:
    """Extract the article body from raw_content. Site chrome (menus, login
    prompts, share rows) is always short fragments; the article body is the
    longest run of long lines. Layout-independent: the upstream extractor
    returns varying slices, so no fixed anchors or windows."""
    lines = text.splitlines()
    # Longest run of prose lines (>=40 chars), tolerating one short line
    # inside a run (subtitles, bylines).
    best_start, best_len = 0, 0
    cur_start, cur_len, shorts = 0, 0, 0
    for i, ln in enumerate(lines):
        if len(ln.strip()) >= 40:
            if cur_len == 0:
                cur_start, shorts = i, 0
            cur_len += 1
        else:
            shorts += 1
            if shorts > 1:  # run broken
                if cur_len > best_len:
                    best_start, best_len = cur_start, cur_len
                cur_len = 0
    if cur_len > best_len:
        best_start, best_len = cur_start, cur_len
    if best_len == 0:
        return text
    body = "\n".join(lines[best_start:]).strip()
    # Trim trailing short footer fragments left after the body run.
    out = body.splitlines()
    while out and len(out[-1].strip()) < 40:
        out.pop()
    result = "\n".join(out).strip() or body
    # Drop a leading heading that duplicates the article title (the reader
    # screen already shows the title).
    if title:
        first = result.splitlines()[0].lstrip("# ").strip() if result else ""
        if first and (first in title or title.startswith(first[:30])):
            result = "\n".join(result.splitlines()[1:]).strip() or result
    return result


def _fetch_tavily(url: str) -> dict[str, Any] | None:
    if not config.TAVILY_API_KEY:
        return None
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=config.TAVILY_API_KEY)

        # 1) Plain extract.
        try:
            r = client.extract([url], raw=True)
            res = (r.get("results") or [{}])[0]
            raw = (res.get("raw_content") or "").strip()
            if len(raw) >= 200:
                title = (res.get("title") or "").strip()
                text = _trim_boilerplate(_clean_markdown(raw), title)
                if _body_quality(text):
                    return {"title": title, "date": "", "url": url, "text": text[:12000]}
        except Exception:
            pass

        # 2) Search-by-URL with raw content (extract often returns only the
        # page preamble for this source; search indexes the article body).
        r = client.search(
            query=url,
            include_raw_content=True,
            max_results=3,
            search_depth="advanced",
        )
        for hit in r.get("results", []):
            hit_url = (hit.get("url") or "").rstrip("/")
            # Match the article despite slug drift: the news list carries
            # truncated/partial slugs, the canonical URL may add segments or
            # a numeric suffix. Same host + one slug containing the other.
            hit_slug = hit_url.rsplit("/", 1)[-1]
            q_slug = url.rstrip("/").rsplit("/", 1)[-1]
            if not (
                _host_allowed(hit_url) and hit_slug and q_slug
                and (q_slug in hit_slug or hit_slug in q_slug)
            ):
                continue
            raw = (hit.get("raw_content") or "").strip()
            if len(raw) < 200:
                raw = (hit.get("content") or "").strip()
            if len(raw) >= 200:
                title = (hit.get("title") or "").strip()
                text = _trim_boilerplate(_clean_markdown(raw), title)
                if _body_quality(text):
                    return {"title": title, "date": "", "url": url, "text": text[:12000]}
    except Exception as e:
        logger.info("Tavily article fetch failed (%s): %s", url, e)
    return None


def _fetch_browser(url: str) -> dict[str, Any] | None:
    try:
        from app.utils.browser_fetch import fetch_html_browser

        html = fetch_html_browser(url, wait_selector="p")
        if not html:
            return None
        return _extract_from_html(html, url)
    except Exception as e:
        logger.info("Browser article fetch failed (%s): %s", url, e)
        return None


def fetch_article(url: str) -> dict[str, Any] | None:
    """Full chain with short cache. Returns {title, date, url, text} or None."""
    url = (url or "").strip()
    if not url or not _host_allowed(url):
        return None
    now = time.monotonic()
    hit = _cache.get(url)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    for step in (_fetch_direct, _fetch_tavily, _fetch_browser):
        article = step(url)
        if article:
            _cache[url] = (now, article)
            return article
    return None

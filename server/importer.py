"""Import an article from a web page straight into the "Read anything" paste box (v0.6,
Helperbird parity): the server fetches the page (so the browser never needs CORS access to an
arbitrary site) and extracts the article text with `trafilatura` (falling back to
`readability-lxml` if that isn't installed; 503 if neither is).

Anonymous readers may import, exactly like `/api/rewrite` -- subject to the same `paste_chars`
quota (`server/billing.py`). An import over that limit is truncated with a note instead of
rejected outright, so a free reader always gets *something* into the box; the note points at
Pro (a bigger limit) or the library (a whole book, chapter by chapter).

SSRF hardening, since this fetches a URL the caller controls:
 - only `http`/`https`, and only a plain hostname/IP (no embedded credentials trusted further
   than urlparse already strips them)
 - the hostname is resolved and every returned address is checked against loopback/private/
   link-local/reserved/multicast/unspecified ranges (blocks localhost, 127.0.0.1, 10/8, 172.16/12,
   192.168/16, 169.254.0.0/16 including the cloud metadata address, etc.) before any request is
   made, and again on every redirect hop
 - at most 3 redirects, a 10s timeout, and a 2MB cap on the response body (streamed, so an
   oversized body is abandoned mid-download rather than buffered in full first)
 - a fixed, identifying User-Agent (`UnwindWords/0.2 (+https://unwindwords.com)`)

Successful imports are cached in-process for an hour, keyed on a hash of the requested URL, so
re-importing the same link (a reader hitting back/forward, or two readers sharing a link) does
not refetch or re-extract it.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import threading
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import auth, billing, db

router = APIRouter(prefix="/api/import")

USER_AGENT = "UnwindWords/0.2 (+https://unwindwords.com)"
FETCH_TIMEOUT = 10.0
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3

# Test hook, same spirit as src/dyslexic_rewrite/rewrite/llm.py's DYSREWRITE_LLM_TRANSPORT: set
# to an httpx.BaseTransport (typically httpx.MockTransport) to bypass the network entirely.
# Production code never touches it.
IMPORTER_TRANSPORT: Any = None

_CACHE_TTL_S = 3600.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


# ---------------------------------------------------------------------------------------
# auth (a private copy of server.app's optional_user, kept local like billing.py does, so
# this module has no import dependency on server.app)
# ---------------------------------------------------------------------------------------
def _optional_user(request: Request) -> dict | None:
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    if not uid:
        return None
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()


# ---------------------------------------------------------------------------------------
# SSRF guards
# ---------------------------------------------------------------------------------------
def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable -- refuse rather than guess
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
        or addr.is_multicast or addr.is_unspecified
    )


def _check_host(host: str) -> None:
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise HTTPException(400, "That address isn't allowed.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise HTTPException(400, "We could not find that address.") from e
    if not infos:
        raise HTTPException(400, "We could not find that address.")
    for info in infos:
        if _is_blocked_ip(info[4][0]):
            raise HTTPException(400, "That address isn't allowed.")


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http:// and https:// links are supported.")
    if not parsed.hostname:
        raise HTTPException(400, "That doesn't look like a web address.")
    _check_host(parsed.hostname)
    return url


# ---------------------------------------------------------------------------------------
# fetch (manual redirect handling so every hop is re-validated)
# ---------------------------------------------------------------------------------------
def _client() -> httpx.Client:
    kwargs: dict[str, Any] = {}
    if IMPORTER_TRANSPORT is not None:
        kwargs["transport"] = IMPORTER_TRANSPORT
    return httpx.Client(
        follow_redirects=False, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT}, **kwargs
    )


def _fetch(url: str) -> tuple[str, str]:
    """Returns `(final_url, html)`. Raises `HTTPException` on any failure."""
    current = _validate_url(url)
    with _client() as client:
        for _hop in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as r:
                    if r.is_redirect:
                        location = r.headers.get("location")
                        if not location:
                            raise HTTPException(502, "That page redirected without a destination.")
                        current = _validate_url(urljoin(current, location))
                        continue
                    if r.status_code != 200:
                        raise HTTPException(502, f"That page returned an error ({r.status_code}).")
                    ctype = r.headers.get("content-type", "")
                    if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
                        raise HTTPException(400, "That address isn't a web page we can read.")
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise HTTPException(400, "That page is too large to import.")
                    return current, body.decode(r.encoding or "utf-8", errors="replace")
            except httpx.TimeoutException as e:
                raise HTTPException(504, "That page took too long to respond.") from e
            except httpx.TransportError as e:
                raise HTTPException(502, "We could not reach that page.") from e
    raise HTTPException(400, "That page redirected too many times.")


# ---------------------------------------------------------------------------------------
# extraction: trafilatura first, readability-lxml as a fallback, 503 if neither is installed
# ---------------------------------------------------------------------------------------
def _extract(html: str, url: str) -> tuple[str, str | None, str | None]:
    """Returns `(text, title, byline)`."""
    try:
        import trafilatura
    except ImportError:
        trafilatura = None  # type: ignore[assignment]

    if trafilatura is not None:
        extracted = trafilatura.extract(
            html, url=url, output_format="json", with_metadata=True,
            include_comments=False, include_tables=False,
        )
        if extracted:
            data = json.loads(extracted)
            text = (data.get("text") or "").strip()
            if text:
                return text, (data.get("title") or None), (data.get("author") or None)

    try:
        from readability import Document
    except ImportError:
        Document = None  # type: ignore[assignment]

    if Document is not None:
        from bs4 import BeautifulSoup

        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        paras = [
            el.get_text(" ", strip=True)
            for el in soup.find_all(["h1", "h2", "h3", "p", "li", "blockquote"])
        ]
        text = "\n\n".join(p for p in paras if p)
        if text.strip():
            return text, (doc.short_title() or None), None

    if trafilatura is None and Document is None:
        raise HTTPException(
            503, "Importing from a web page needs an extraction library that isn't installed "
                 "on this server yet.",
        )
    raise HTTPException(422, "We could not find an article on that page.")


# ---------------------------------------------------------------------------------------
# cache: URL hash -> extracted result, for an hour
# ---------------------------------------------------------------------------------------
def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _cache_get(url: str) -> dict[str, Any] | None:
    with _cache_lock:
        entry = _cache.get(_cache_key(url))
    if entry is None or time.monotonic() - entry[0] >= _CACHE_TTL_S:
        return None
    return entry[1]


def _cache_put(url: str, result: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[_cache_key(url)] = (time.monotonic(), result)
        if len(_cache) > 500:  # opportunistic, best-effort trim of the oldest half
            for k, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[:250]:
                _cache.pop(k, None)


# ---------------------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------------------
class UrlIn(BaseModel):
    url: str = Field(max_length=2000)


@router.post("/url")
def import_url(body: UrlIn, u: dict | None = Depends(_optional_user)):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "Paste a web address first.")

    result = _cache_get(url)
    if result is None:
        final_url, html = _fetch(url)
        text, title, byline = _extract(html, final_url)
        result = {"title": title, "byline": byline, "text": text, "source_url": final_url}
        _cache_put(url, result)

    limit = billing.quota(u)["paste_chars"]
    text = result["text"]
    note = None
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
        note = (
            f"That article runs longer than your {limit:,}-character limit, so we cut it off "
            "there. Upgrade to Unwind Words Pro for a bigger limit, or add it to your library "
            "instead to read the whole thing chapter by chapter."
        )

    return {
        "title": result["title"], "byline": result["byline"], "text": text,
        "words": len(text.split()), "source_url": result["source_url"], "note": note,
    }

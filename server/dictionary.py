"""Dictionary on tap (v0.6, Helperbird parity): `GET /api/define?word=` proxies the free,
keyless `api.dictionaryapi.dev`, cached in Postgres (`definitions`, migration
011_import_dictionary_summaries.sql) so a repeated lookup -- a common word, several readers --
never re-hits the upstream API. A definite "not found" is cached too, so a typo doesn't hammer
it either.

Anonymous readers may use this. Rate-limited in-process to 60 requests per minute per client IP
(same in-process-only caveat as server/marketing.py's newsletter limiter -- not shared across
workers/instances, good enough to stop a single abusive script).
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from . import db

router = APIRouter(prefix="/api")

UPSTREAM = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
TIMEOUT = 2.0
MAX_MEANINGS = 3

# Test hook, same spirit as src/dyslexic_rewrite/rewrite/llm.py's DYSREWRITE_LLM_TRANSPORT.
DICTIONARY_TRANSPORT: Any = None

_RATE_WINDOW_S = 60.0
_RATE_LIMIT = 60
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}

_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z' -]{0,49}$")
_MISSING = {"_missing": True}


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(key, []) if now - t < _RATE_WINDOW_S]
        if len(hits) >= _RATE_LIMIT:
            _rate_hits[key] = hits
            return True
        hits.append(now)
        _rate_hits[key] = hits
        return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _normalise_word(word: str) -> str:
    return word.strip().lower()


# ---------------------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------------------
def _cache_get(word: str) -> dict[str, Any] | None:
    with db.conn() as c:
        row = c.execute("SELECT payload FROM definitions WHERE word = %s", (word,)).fetchone()
    return row["payload"] if row else None


def _cache_put(word: str, payload: dict[str, Any]) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO definitions (word, payload, fetched_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (word) DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()",
            (word, json.dumps(payload)),
        )
        c.commit()


# ---------------------------------------------------------------------------------------
# upstream
# ---------------------------------------------------------------------------------------
def _client() -> httpx.Client:
    kwargs: dict[str, Any] = {}
    if DICTIONARY_TRANSPORT is not None:
        kwargs["transport"] = DICTIONARY_TRANSPORT
    return httpx.Client(timeout=TIMEOUT, **kwargs)


def _trim(data: list) -> dict[str, Any]:
    entry = data[0] if data else {}
    phonetics = entry.get("phonetics") or []
    phonetic = entry.get("phonetic") or next((p.get("text") for p in phonetics if p.get("text")), None)
    audio_url = next((p.get("audio") for p in phonetics if p.get("audio")), None)
    meanings = []
    for m in (entry.get("meanings") or [])[:MAX_MEANINGS]:
        defs = m.get("definitions") or []
        if not defs:
            continue
        d = defs[0]
        meanings.append({
            "pos": m.get("partOfSpeech", ""), "definition": d.get("definition", ""),
            "example": d.get("example"),
        })
    return {
        "word": entry.get("word", ""), "phonetic": phonetic or None,
        "meanings": meanings, "audio_url": audio_url or None,
    }


def _fetch_upstream(word: str) -> dict[str, Any] | None:
    """`None` means a definite "not found" (upstream 404); raises for any other failure."""
    try:
        with _client() as c:
            r = c.get(UPSTREAM.format(word=word))
    except httpx.TimeoutException as e:
        raise HTTPException(504, "The dictionary took too long to respond.") from e
    except httpx.TransportError as e:
        raise HTTPException(502, "We could not reach the dictionary.") from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise HTTPException(502, "The dictionary returned an error.")
    try:
        data = r.json()
    except ValueError as e:
        raise HTTPException(502, "The dictionary returned something we could not read.") from e
    return _trim(data)


# ---------------------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------------------
@router.get("/define")
def define(word: str, request: Request):
    if _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Too many lookups — wait a moment and try again.")

    w = _normalise_word(word)
    if not w or not _WORD_RE.match(w):
        raise HTTPException(400, "That doesn't look like a single word.")

    cached = _cache_get(w)
    if cached is not None:
        if cached.get("_missing"):
            raise HTTPException(404, f'No definition found for "{w}".')
        return cached

    payload = _fetch_upstream(w)
    if payload is None:
        _cache_put(w, _MISSING)
        raise HTTPException(404, f'No definition found for "{w}".')
    _cache_put(w, payload)
    return payload

"""AI summaries (v0.6, Pro only): a 3-6 bullet plain-language summary of a passage
(`POST /api/summaries`) or a library book's chapter (`POST /api/books/{id}/summary`), using the
package's optional LLM engine (`src/dyslexic_rewrite/rewrite/llm.py`) -- the same OpenAI-
compatible endpoint the "llm" book/rewrite engine already talks to, so it needs no config of its
own beyond `DYSREWRITE_LLM_BASE_URL`/`DYSREWRITE_LLM_API_KEY`.

Fidelity: a summary necessarily drops detail, so there is no automated fidelity gate the way the
rewrite engine has one -- the prompt itself is the safeguard, telling the model to add nothing
that isn't in the text and to keep every bullet traceable back to it. This is a materially
weaker guarantee than the rewrite engine's, and the UI is expected to label the result plainly
("AI summary -- read the text for the details") rather than imply it's been fact-checked.

Gated by `billing.require_pro`; 503 when no LLM is configured on this server at all (distinct
from the 402 Pro gate, which fires regardless of configuration -- a free reader is never told
"you'd need the engine" when the real answer is "you'd need Pro"). Results are cached
(`summaries`, migration 011_import_dictionary_summaries.sql) keyed on
sha256(model | prompt version | profile fingerprint | max_sentence_words | text), the same
spirit as `server/cache.py`'s `llm_cache` -- a re-summarise of the same text under an unchanged
profile costs nothing to run again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dyslexic_rewrite.io import read_chapters
from dyslexic_rewrite.rewrite import llm as llm_engine

from . import auth, billing, cache, db, library, service

router = APIRouter(prefix="/api")

NO_LLM_MESSAGE = "Summaries need the hosted engine — not set up on this server yet."
PROMPT_VERSION = "1"
MIN_BULLETS, MAX_BULLETS = 3, 6

SYSTEM_PROMPT = """You write short, plain-language summaries for a reader with dyslexia.

Rules, in priority order:
1. Add nothing that is not in the text below. No outside facts, no guesses, no opinions of
   your own, and never resolve something the text itself leaves unclear.
2. Every bullet must be traceable to a specific part of the text -- a reader who doubts a
   bullet should be able to find the sentence it came from.
3. Write between {min_bullets} and {max_bullets} short bullets, one idea per bullet, each at
   most {max_words} words.
4. Use plain, common words. Keep names, numbers, dates and quotations exact.
5. Output ONLY the bullets, one per line, each starting with "- ". No preface, no heading, and
   no closing remark."""


# ---------------------------------------------------------------------------------------
# auth (a private copy of server.app's current_user/optional_user, kept local like billing.py
# does, so this module has no import dependency on server.app)
# ---------------------------------------------------------------------------------------
def _optional_user(request: Request) -> dict | None:
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    if not uid:
        return None
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()


def _current_user(request: Request) -> dict:
    u = _optional_user(request)
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def _llm_configured() -> bool:
    return bool(os.environ.get("DYSREWRITE_LLM_BASE_URL") or os.environ.get("DYSREWRITE_LLM_API_KEY"))


# ---------------------------------------------------------------------------------------
# cache: sha256(model | prompt version | profile fingerprint | max_sentence_words | text) ->
# the bullet list, stored as a JSON array in `summaries.text`.
# ---------------------------------------------------------------------------------------
def _summary_key(text: str, profile, model: str) -> str:
    fp = cache.profile_fingerprint(profile)
    blob = "|".join([model, PROMPT_VERSION, fp, str(profile.max_sentence_words), text])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> list[str] | None:
    with db.conn() as c:
        row = c.execute("SELECT text FROM summaries WHERE key = %s", (key,)).fetchone()
    return json.loads(row["text"]) if row else None


def _cache_put(key: str, bullets: list[str]) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO summaries (key, text) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (key, json.dumps(bullets)),
        )
        c.commit()


_BULLET_RE = re.compile(r"^[-*•]\s*")


def _parse_bullets(raw: str) -> list[str]:
    out = []
    for line in raw.splitlines():
        line = _BULLET_RE.sub("", line.strip()).strip()
        if line:
            out.append(line)
    return out[:MAX_BULLETS]


def _generate_summary(text: str, profile) -> list[str]:
    model = llm_engine.model_name()
    key = _summary_key(text, profile, model)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(
                min_bullets=MIN_BULLETS, max_bullets=MAX_BULLETS, max_words=profile.max_sentence_words)},
            {"role": "user", "content": text},
        ],
    }
    try:
        with llm_engine._client() as c:
            data = llm_engine._post_with_retries(c, body)
    except Exception as e:  # network / HTTP error after retries are exhausted
        raise HTTPException(502, f"The summary engine failed: {e}") from e
    try:
        raw = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise HTTPException(502, "The summary engine returned something we could not read.") from e

    bullets = _parse_bullets(raw)
    if not bullets:
        raise HTTPException(502, "The summary engine did not return a usable summary.")
    _cache_put(key, bullets)
    return bullets


def _bullets_response(bullets: list[str]) -> dict[str, Any]:
    return {"bullets": bullets, "summary": "\n".join(f"- {b}" for b in bullets)}


# ---------------------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------------------
class SummaryIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


@router.post("/summaries")
def summarise_text(body: SummaryIn, u: dict | None = Depends(_optional_user)):
    billing.require_pro(u, "AI summaries are part of Unwind Words Pro.")
    if not _llm_configured():
        raise HTTPException(503, NO_LLM_MESSAGE)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Paste some text first.")
    profile, _ = service.get_profile(u["id"], u["base_profile"])
    return _bullets_response(_generate_summary(text, profile))


def _own_book(book_id: int, user_id: int) -> dict:
    with db.conn() as c:
        b = c.execute("SELECT * FROM books WHERE id = %s AND user_id = %s", (book_id, user_id)).fetchone()
    if not b:
        raise HTTPException(404, "No such book.")
    return b


@router.post("/books/{book_id}/summary")
def summarise_book_chapter(book_id: int, chapter: int = 0, u: dict = Depends(_current_user)):
    billing.require_pro(u, "AI summaries are part of Unwind Words Pro.")
    if not _llm_configured():
        raise HTTPException(503, NO_LLM_MESSAGE)
    book = _own_book(book_id, u["id"])
    if book["status"] != "ready":
        raise HTTPException(409, "This book isn't ready yet.")
    chapters = read_chapters(library.resolve_key(book["source_key"]))
    if not (0 <= chapter < len(chapters)):
        raise HTTPException(404, "No such chapter.")
    profile, _ = service.get_profile(u["id"], u["base_profile"])
    out = _bullets_response(_generate_summary(chapters[chapter]["text"], profile))
    out["chapter"] = chapter
    out["title"] = chapters[chapter]["title"]
    return out

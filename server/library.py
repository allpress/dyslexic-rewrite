""""Your library" (v0.5): upload a book, get it back rewritten, read it on the site or a Kindle.

Files live under `BOOKS_DIR` (default `./data/books`; on Fly `/data/books`, the same mounted
volume `AUDIO_DIR` uses), one subfolder per user, using the same traversal-safe key pattern
`server/storage.py` uses for recordings.

Processing (reading the upload's chapters, rewriting each one, writing the output EPUB) happens
on a single background worker thread with a queue, started from the app's lifespan hook
(`server/app.py`). Rows are only ever `queued`/`processing`/`ready`/`failed` in the database, so a
restart just re-queues anything left `queued` or `processing` (`requeue_incomplete`); tests drive
the same worker synchronously with `run_pending()` instead of waiting on a thread.

Billing (migration 006, `server/billing.py`) is built concurrently and may not exist yet in this
checkout -- imported defensively with a same-signature local stub (free-tier limits, `is_pro`
always False) so this module works alone and picks up the real thing once it lands.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from dyslexic_rewrite.io import read_chapters, write_epub

from . import auth, cache, db, service

try:
    from . import billing  # type: ignore  # noqa: F401 -- lands with migration 006
except ImportError:  # pragma: no cover - exercised until billing.py merges
    class _BillingStub:
        """Same signatures as the real `server/billing.py`, free-tier behaviour only."""

        @staticmethod
        def is_pro(user_row: dict) -> bool:
            return False

        @staticmethod
        def require_pro(user: dict) -> None:
            raise HTTPException(402, "This needs Unwind Words Pro.")

        @staticmethod
        def quota(user: dict) -> dict:
            return {"books_total": 1, "paste_chars": 20_000, "llm_tier": False}

    billing = _BillingStub()  # type: ignore

BOOKS_DIR = Path(os.environ.get("BOOKS_DIR", "./data/books")).resolve()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_WORDS_HARD = 300_000     # nobody, Pro included, can upload more than this
MAX_WORDS_FREE = 60_000      # free readers are capped lower
# .pdf/.docx (v0.6, Helperbird parity) added alongside the original three; migration
# 011_import_dictionary_summaries.sql relaxes the matching `books.source_kind` CHECK constraint.
SOURCE_KINDS = ("epub", "txt", "md", "pdf", "docx")

_UNSAFE_FS_CHARS = re.compile(r"[^A-Za-z0-9 ._-]+")


def safe_filename(name: str) -> str:
    return (_UNSAFE_FS_CHARS.sub("", name).strip() or "book")[:120]


# ---------------------------------------------------------------------------------------
# storage: BOOKS_DIR/<user_id>/<uuid>.<ext>, same traversal-safe pattern as storage.py
# ---------------------------------------------------------------------------------------
def resolve_key(key: str) -> Path:
    path = (BOOKS_DIR / key).resolve()
    if path != BOOKS_DIR and BOOKS_DIR not in path.parents:
        raise ValueError("Invalid storage key.")
    return path


def _save_source(user_id: int, data: bytes, kind: str) -> str:
    key = f"{user_id}/{uuid.uuid4()}.{kind}"
    path = resolve_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def delete_files(*keys: str | None) -> None:
    for key in keys:
        if not key:
            continue
        try:
            resolve_key(key).unlink(missing_ok=True)
        except ValueError:
            pass


def delete_user_books(user_id: int) -> None:
    """Every book file for a user (called from `DELETE /api/me`, before the row cascade)."""
    with db.conn() as c:
        rows = c.execute("SELECT source_key, output_key FROM books WHERE user_id = %s", (user_id,)).fetchall()
    for r in rows:
        delete_files(r["source_key"], r["output_key"])
    user_dir = BOOKS_DIR / str(user_id)
    if user_dir.is_dir():
        try:
            user_dir.rmdir()
        except OSError:
            pass


def _source_kind(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix if suffix in SOURCE_KINDS else None


def _llm_configured() -> bool:
    return bool(os.environ.get("DYSREWRITE_LLM_BASE_URL") or os.environ.get("DYSREWRITE_LLM_API_KEY"))


# ---------------------------------------------------------------------------------------
# API shape
# ---------------------------------------------------------------------------------------
def book_json(row: dict) -> dict[str, Any]:
    return {
        "id": row["id"], "title": row["title"], "author": row["author"],
        "source_name": row["source_name"], "source_kind": row["source_kind"],
        "words": row["words"], "chapters": row["chapters"], "status": row["status"],
        "engine": row["engine"], "progress": row["progress"], "error": row["error"],
        "created_at": row["created_at"].isoformat(),
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "last_opened_at": row["last_opened_at"].isoformat() if row["last_opened_at"] else None,
        "kindle_sent_at": row["kindle_sent_at"].isoformat() if row["kindle_sent_at"] else None,
        # Hosted-LLM tier visibility (migration 009_llm_cache.sql): null for a rules-engine book.
        "cost_usd": float(row["cost_usd"]) if row.get("cost_usd") is not None else None,
        "llm_usage": row.get("llm_usage"),
        # "partial-llm" when more than 30% of some chapter's paragraphs fell back to the rules
        # engine (see `_process_book`) -- lets the UI say "some paragraphs used the rules engine".
        "engine_note": row.get("engine_note"),
    }


def create_book(user: dict, filename: str, data: bytes, title: str | None, author: str | None,
                engine: str) -> dict[str, Any]:
    """Validate, save, and queue a new upload. Raises HTTPException(400|402) on any rejection."""
    kind = _source_kind(filename or "")
    if kind is None:
        raise HTTPException(400, "Upload a .epub, .txt, .md, .pdf, or .docx file.")
    if not data:
        raise HTTPException(400, "That file came through empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Books can be at most 25 MB.")

    is_pro = billing.is_pro(user)
    q = billing.quota(user)
    if q.get("books_total") is not None:
        with db.conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM books WHERE user_id = %s", (user["id"],)).fetchone()["n"]
        if n >= q["books_total"]:
            raise HTTPException(
                402, "Your first book is free. Upgrade to Unwind Words Pro to add more books to your library.",
            )

    key = _save_source(user["id"], data, kind)
    try:
        chapters = read_chapters(resolve_key(key))
    except Exception as e:
        delete_files(key)
        raise HTTPException(400, f"We could not read that file: {e}") from e
    if not chapters:
        delete_files(key)
        raise HTTPException(400, "No text found in that file.")

    words = sum(len(ch["text"].split()) for ch in chapters)
    if words > MAX_WORDS_HARD:
        delete_files(key)
        raise HTTPException(400, "That book is too long (over 300,000 words).")
    if words > MAX_WORDS_FREE and not is_pro:
        delete_files(key)
        raise HTTPException(
            402, "That book is over 60,000 words. Upgrade to Unwind Words Pro for longer books.",
        )

    use_engine = "llm" if (engine == "llm" and is_pro and _llm_configured()) else "rules"
    book_title = (title or Path(filename).stem or "Untitled").strip()[:200] or "Untitled"
    with db.conn() as c:
        row = c.execute(
            "INSERT INTO books (user_id, title, author, source_name, source_kind, words, chapters, "
            "status, engine, source_key) VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s) RETURNING *",
            (user["id"], book_title, (author or None), filename, kind, words, len(chapters), use_engine, key),
        ).fetchone()
        c.commit()
    enqueue(row["id"])
    return book_json(row)


# ---------------------------------------------------------------------------------------
# rewriting a chapter -> segments the reader view can render, same shape as /api/rewrite
# ---------------------------------------------------------------------------------------
def render_chapter(text: str, profile, engine: str, mode: str, llm_cache=None) -> tuple[list[dict], dict, list[dict], bool]:
    """(segments, stats, phonetic_map, cached). `engine='rules'` goes through the shared rewrite
    cache (server/cache.py) so a re-run under the same profile is instant; `engine='llm'` (Pro
    only, see `_llm_configured`) rewrites paragraphs concurrently through the LLM engine, checking
    the *paragraph*-level LLM cache first (`server/cache.py`'s `LlmCache`, built automatically
    from `profile` when `llm_cache` isn't passed in) -- so a re-run under an unchanged profile,
    or the same public-domain text for two readers who share a profile, calls the model for
    nothing. `stats` additionally carries `llm_paragraphs`/`llm_fallbacks` (and `llm_usage`/
    `llm_cost_usd` when the model returned usage) for the LLM engine."""
    if engine == "llm":
        from dyslexic_rewrite.analyze import analyze
        from dyslexic_rewrite.rewrite import llm as llm_engine
        from dyslexic_rewrite.rewrite.engine import rewrite as _rewrite
        if llm_cache is None:
            llm_cache = cache.LlmCache(profile, llm_engine.model_name())
        report = analyze(text, profile)
        result = _rewrite(text, profile, engine="llm", report=report, llm_cache=llm_cache)
        segs = service.to_segments(result)
        st = result.stats
        stats = {"sentences": st["sentences"], "sentences_changed": st["sentences_changed"],
                 "changes": st["changes"], "load_before": st["load_before"], "load_after": st.get("load_after"),
                 "llm_paragraphs": st.get("llm_paragraphs", 0), "llm_fallbacks": st.get("llm_fallbacks", 0)}
        if st.get("llm_usage"):
            stats["llm_usage"] = st["llm_usage"]
            stats["llm_cost_usd"] = st.get("llm_cost_usd", 0.0)
        phon = service.compute_phonetic_map(segs, profile, mode)
        return segs, stats, phon, False
    return cache.cached_rewrite(text, profile, mode)


def _segments_to_chapter_html(segments: list[dict], phonetic_map: list[dict]) -> str:
    """EPUB body-inner XHTML for one chapter's segments + phonetic map, mirroring
    `dyslexic_rewrite.render.to_html`'s markup (changed words underlined-by-title, flagged
    words get an inline `<ruby>`) without any of the JS interactivity a static book can't have."""
    import html as _html

    paragraphs: list[str] = []
    cur: list[str] = []
    pos = 0

    def flush():
        if cur:
            paragraphs.append(f"<p>{''.join(cur)}</p>")
            cur.clear()

    for seg in segments:
        t = seg["t"]
        if t == "para":
            flush()
            pos += 2
            continue
        if t == "heading":
            flush()
            paragraphs.append(f"<h2>{_html.escape(seg['s'])}</h2>")
            pos += len(seg["s"])
            continue
        text = seg.get("s", "")
        start, end = pos, pos + len(text)
        pos = end
        if t == "text":
            cur.append(_html.escape(text))
        elif t == "change":
            cur.append(
                f'<span class="orig" title="{_html.escape(seg["orig"], quote=True)}">'
                f"{_html.escape(text)}</span>"
            )
        elif t == "note":
            word_html = _html.escape(text)
            entry = next((e for e in phonetic_map if e["start"] >= start and e["end"] <= end), None)
            if entry:
                word_html = f"<ruby>{word_html}<rt>{_html.escape(entry['respell'])}</rt></ruby>"
            cur.append(word_html)
    flush()
    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------------------
# background worker: single thread + queue, started from server/app.py's lifespan hook
# ---------------------------------------------------------------------------------------
_queue: queue.Queue[int] = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def enqueue(book_id: int) -> None:
    _queue.put(book_id)


def start_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="library-worker")
        _worker_thread.start()


def _worker_loop() -> None:
    while True:
        book_id = _queue.get()
        try:
            _process_book(book_id)
        except Exception as e:  # pragma: no cover - one bad book must never kill the worker
            print(f"[library] book {book_id} failed: {e}")
        finally:
            _queue.task_done()


def requeue_incomplete() -> None:
    """Called at startup: a book left `queued`/`processing` by a restart picks back up."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT id FROM books WHERE status IN ('queued', 'processing') ORDER BY id"
        ).fetchall()
    for r in rows:
        enqueue(r["id"])


def run_pending() -> None:
    """Test helper: process every currently-queued book synchronously, on the calling thread,
    instead of waiting on the background worker."""
    while True:
        try:
            book_id = _queue.get_nowait()
        except queue.Empty:
            return
        try:
            _process_book(book_id)
        finally:
            _queue.task_done()


def _process_book(book_id: int) -> None:
    with db.conn() as c:
        book = c.execute("SELECT * FROM books WHERE id = %s", (book_id,)).fetchone()
    if not book:
        return
    with db.conn() as c:
        user = c.execute("SELECT * FROM users WHERE id = %s", (book["user_id"],)).fetchone()
    if not user:
        return

    with db.conn() as c:
        c.execute("UPDATE books SET status = 'processing', error = NULL WHERE id = %s", (book_id,))
        c.commit()

    try:
        path = resolve_key(book["source_key"])
        chapters = read_chapters(path)
        profile, _ = service.get_profile(user["id"], user["base_profile"])
        fp = cache.profile_fingerprint(profile)
        engine = book["engine"] if (book["engine"] == "llm" and billing.is_pro(user) and _llm_configured()) else "rules"
        epub_mode = "always" if getattr(profile, "phonetic_map", "off") != "off" else "off"

        # One paragraph cache shared across every chapter of this book, so a chapter that
        # repeats a phrase (or a re-run under a tweaked profile) never pays twice.
        llm_cache_obj = None
        if engine == "llm":
            from dyslexic_rewrite.rewrite import llm as llm_engine
            llm_cache_obj = cache.LlmCache(profile, llm_engine.model_name())
        cost_total = 0.0
        usage_totals: dict[str, int] = {}
        any_chapter_partial = False

        rendered = []
        for i, ch in enumerate(chapters):
            segs, stats, phon, _cached = render_chapter(ch["text"], profile, engine, epub_mode, llm_cache=llm_cache_obj)
            if engine == "llm":
                lp, lf = stats.get("llm_paragraphs", 0), stats.get("llm_fallbacks", 0)
                if (lp + lf) and lf / (lp + lf) > 0.3:
                    any_chapter_partial = True
                if stats.get("llm_cost_usd"):
                    cost_total += stats["llm_cost_usd"]
                for k, v in (stats.get("llm_usage") or {}).items():
                    usage_totals[k] = usage_totals.get(k, 0) + v
            rendered.append({"title": ch["title"], "html": _segments_to_chapter_html(segs, phon)})
            with db.conn() as c:
                c.execute(
                    "UPDATE books SET progress = %s, chapters = %s WHERE id = %s",
                    (i + 1, len(chapters), book_id),
                )
                c.commit()

        out_key = f"{user['id']}/{uuid.uuid4()}.epub"
        write_epub(None, resolve_key(out_key), title=book["title"], author=book["author"],
                   chapters=rendered, profile=profile)
        words = sum(len(ch["text"].split()) for ch in chapters)
        engine_note = "partial-llm" if (engine == "llm" and any_chapter_partial) else None
        with db.conn() as c:
            c.execute(
                "UPDATE books SET status = 'ready', words = %s, chapters = %s, progress = %s, "
                "output_key = %s, engine = %s, profile_fingerprint = %s, finished_at = now(), error = NULL, "
                "cost_usd = %s, llm_usage = %s, engine_note = %s "
                "WHERE id = %s",
                (words, len(chapters), len(chapters), out_key, engine, fp,
                 round(cost_total, 6) if (engine == "llm" and usage_totals) else None,
                 json.dumps(usage_totals) if (engine == "llm" and usage_totals) else None,
                 engine_note, book_id),
            )
            c.commit()
    except Exception as e:
        with db.conn() as c:
            c.execute("UPDATE books SET status = 'failed', error = %s WHERE id = %s", (str(e)[:2000], book_id))
            c.commit()


# ---------------------------------------------------------------------------------------
# Send to Kindle: emails the EPUB as a Resend attachment (base64), reusing auth.py's client/env.
# The reader must add the sending address to Amazon's "Approved Personal Document E-mail List"
# (Amazon > Manage Your Content and Devices > Preferences > Personal Document Settings) or Kindle
# will silently drop the email.
# ---------------------------------------------------------------------------------------
def send_to_kindle(book: dict, user: dict) -> None:
    kindle_email = user.get("kindle_email")
    if not kindle_email:
        raise HTTPException(400, "Add your Kindle email address first (Profile > Send to Kindle).")
    if book["status"] != "ready" or not book["output_key"]:
        raise HTTPException(409, "This book isn't ready yet.")

    data = resolve_key(book["output_key"]).read_bytes()
    filename = f"{safe_filename(book['title'])}.epub"
    if not auth.RESEND_API_KEY:
        print(f"[library] would send {filename!r} to {kindle_email} (no RESEND_API_KEY set)")
        return
    b64 = base64.b64encode(data).decode("ascii")
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {auth.RESEND_API_KEY}"},
        json={
            "from": f"{auth.APP_NAME} <{auth.FROM_EMAIL}>",
            "to": [kindle_email],
            "subject": book["title"],
            "text": "Your book from Unwind Words is attached.",
            "attachments": [{"filename": filename, "content": b64}],
        },
        timeout=30,
    )
    r.raise_for_status()

"""Tests for "Your library": read_chapters/write_epub (package) and the /api/books flow (server).

The server half needs a Postgres at DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise, same
as tests/test_server.py. BOOKS_DIR points at a throwaway temp directory so this never touches
./data/books, and LIBRARY_WORKER=0 keeps the background thread off -- the API tests below drive
the same worker deterministically with `library.run_pending()`.
"""

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("ebooklib")

os.environ.setdefault("BOOKS_DIR", tempfile.mkdtemp(prefix="dysrewrite-books-"))
os.environ.setdefault("LIBRARY_WORKER", "0")

from dyslexic_rewrite.io import read_chapters, write_epub  # noqa: E402
from dyslexic_rewrite.profile import load_profile  # noqa: E402
from dyslexic_rewrite.rewrite.engine import rewrite  # noqa: E402


# =========================================================================================
# Package: read_chapters() / write_epub()
# =========================================================================================
def _write_sample_epub(path: Path) -> None:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book-id")
    book.set_title("A Small Test Book")
    book.set_language("en")
    book.add_author("Someone")

    c1 = epub.EpubHtml(title="Chapter One", file_name="c1.xhtml", lang="en")
    c1.content = "<h1>Chapter One</h1><p>The wind blew across the moor that night.</p>"
    c2 = epub.EpubHtml(title="Chapter Two", file_name="c2.xhtml", lang="en")
    c2.content = "<h1>Chapter Two</h1><p>She tried to tear the page, but a tear fell instead.</p>"
    for item in (c1, c2):
        book.add_item(item)
    book.toc = (c1, c2)
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [nav, c1, c2]
    epub.write_epub(str(path), book)


def test_read_chapters_epub(tmp_path):
    path = tmp_path / "sample.epub"
    _write_sample_epub(path)
    chapters = read_chapters(path)
    assert [c["title"] for c in chapters] == ["Chapter One", "Chapter Two"]
    assert "wind blew" in chapters[0]["text"]
    assert "tear fell" in chapters[1]["text"]


def test_read_chapters_txt_with_chapter_headings(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(
        "Chapter 1\n\n"
        "The wind blew hard across the moor while Grandpa wound the old clock again.\n\n"
        "Chapter 2\n\n"
        "She tried to tear the page, but a tear fell instead.\n",
        encoding="utf-8",
    )
    chapters = read_chapters(path)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "Chapter 1"
    assert chapters[1]["title"] == "Chapter 2"
    assert "wind blew" in chapters[0]["text"]
    assert "tear fell" in chapters[1]["text"]


def test_read_chapters_txt_no_headings_falls_back_to_one_chapter(tmp_path):
    path = tmp_path / "plain.txt"
    path.write_text("Just some ordinary text with no chapter markers at all.\n", encoding="utf-8")
    chapters = read_chapters(path)
    assert len(chapters) == 1
    assert chapters[0]["title"] == "Chapter 1"


def test_read_chapters_txt_huge_single_chapter_is_chunked(tmp_path):
    # ~20,000 words, no headings: should split into ~8k-word chunks.
    para = ("word " * 200).strip()
    path = tmp_path / "huge.txt"
    path.write_text("\n\n".join([para] * 100), encoding="utf-8")
    chapters = read_chapters(path)
    assert len(chapters) >= 2
    assert all(len(c["text"].split()) <= 8500 for c in chapters)


def test_write_epub_roundtrip_with_ruby_and_original(tmp_path):
    import ebooklib
    from ebooklib import epub

    text = (
        "Chapter 1\n\n"
        "The wind blew hard across the moor while Grandpa wound the old clock again tonight.\n\n"
        "Chapter 2\n\n"
        "She tried to tear the page, but a tear fell instead.\n"
    )
    profile = load_profile("default")
    profile.phonetic_map = "always"
    chapters_in = read_chapters_from_text(tmp_path, text)

    chapters = []
    for ch in chapters_in:
        result = rewrite(ch["text"], profile)
        chapters.append((ch["title"], result))

    out_path = tmp_path / "out.epub"
    write_epub(None, out_path, "Test Book", author="Someone", chapters=chapters, profile=profile)
    assert out_path.exists()

    book = epub.read_epub(str(out_path))
    docs = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    # nav + one front-matter page + one page per chapter
    assert len(docs) == len(chapters) + 2

    full_html = "".join(d.get_content().decode("utf-8") for d in docs)
    assert "Unwind Words" in full_html and "reversible" in full_html
    assert "<ruby>" in full_html
    assert 'class="orig"' in full_html


def test_write_epub_no_ruby_when_phonetic_map_off(tmp_path):
    import ebooklib
    from ebooklib import epub

    text = "The wind blew hard across the moor while Grandpa wound the old clock again tonight."
    profile = load_profile("default")
    profile.phonetic_map = "off"
    result = rewrite(text, profile)

    out_path = tmp_path / "off.epub"
    write_epub(result, out_path, "Off Book", profile=profile)

    book = epub.read_epub(str(out_path))
    full_html = "".join(
        d.get_content().decode("utf-8") for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
    )
    assert "<ruby>" not in full_html


def read_chapters_from_text(tmp_path, text):
    p = tmp_path / f"src_{abs(hash(text))}.txt"
    p.write_text(text, encoding="utf-8")
    return read_chapters(p)


# =========================================================================================
# Server: /api/books flow
# =========================================================================================
pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault(
    "DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite")
)
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)

try:
    import psycopg

    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for library API tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import library  # noqa: E402
from server.app import app  # noqa: E402

BOOK_EMAIL = "pytest-library@example.com"
BOOK_TXT = (
    b"Chapter 1\n\n"
    b"The wind blew hard across the moor while Grandpa wound the old clock again tonight.\n\n"
    b"Chapter 2\n\n"
    b"She tried to tear the page, but a tear fell instead.\n"
)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
        c.delete("/api/me")


@pytest.fixture()
def signed_in(client):
    r = client.post("/api/auth/request-code", json={"email": BOOK_EMAIL}).json()
    ok = client.post("/api/auth/verify", json={"email": BOOK_EMAIL, "code": r["dev_code"]})
    assert ok.status_code == 200
    return client


def test_upload_process_read_download(signed_in):
    c = signed_in
    up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")})
    assert up.status_code == 201, up.text
    book = up.json()
    assert book["status"] == "queued" and book["chapters"] == 2 and book["words"] > 0

    library.run_pending()

    got = c.get(f"/api/books/{book['id']}").json()
    assert got["status"] == "ready"
    assert got["progress"] == got["chapters"] == 2
    assert got["finished_at"] is not None

    listed = c.get("/api/books").json()
    assert any(b["id"] == book["id"] for b in listed)

    chapter0 = c.get(f"/api/books/{book['id']}/read", params={"chapter": 0})
    assert chapter0.status_code == 200
    body = chapter0.json()
    assert body["chapter"] == 0 and body["chapters"] == 2
    assert isinstance(body["segments"], list) and len(body["segments"]) > 0
    assert isinstance(body["phonetic_map"], list)
    assert "stats" in body

    missing_chapter = c.get(f"/api/books/{book['id']}/read", params={"chapter": 99})
    assert missing_chapter.status_code == 404

    dl = c.get(f"/api/books/{book['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"] in ("application/epub+zip",)
    assert "attachment" in dl.headers["content-disposition"]

    import ebooklib
    from ebooklib import epub

    tmp = Path(library.BOOKS_DIR) / "downloaded_test.epub"
    tmp.write_bytes(dl.content)
    try:
        parsed = epub.read_epub(str(tmp))
        assert len(list(parsed.get_items_of_type(ebooklib.ITEM_DOCUMENT))) == 4  # nav + front matter + 2 chapters
    finally:
        tmp.unlink(missing_ok=True)


def test_second_upload_as_free_user_is_quota_blocked(signed_in):
    c = signed_in
    up1 = c.post("/api/books", files={"file": ("book1.txt", BOOK_TXT, "text/plain")})
    assert up1.status_code == 201
    library.run_pending()

    up2 = c.post("/api/books", files={"file": ("book2.txt", BOOK_TXT, "text/plain")})
    assert up2.status_code == 402
    assert "free" in up2.json()["error"].lower() or "pro" in up2.json()["error"].lower()


def test_upload_rejects_bad_extension(signed_in):
    c = signed_in
    r = c.post("/api/books", files={"file": ("book.pdf", b"not a book", "application/pdf")})
    assert r.status_code == 400


def test_kindle_requires_kindle_email(signed_in):
    c = signed_in
    up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")})
    book = up.json()
    library.run_pending()
    r = c.post(f"/api/books/{book['id']}/kindle")
    assert r.status_code == 400
    c.patch("/api/me", json={"kindle_email": "reader@kindle.com"})
    r2 = c.post(f"/api/books/{book['id']}/kindle")
    assert r2.status_code == 200  # no RESEND_API_KEY -> dev no-op "send", still marked ok
    got = c.get(f"/api/books/{book['id']}").json()
    assert got["kindle_sent_at"] is not None


def test_rerun_requires_pro(signed_in):
    c = signed_in
    up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")})
    book = up.json()
    library.run_pending()
    r = c.post(f"/api/books/{book['id']}/rerun")
    assert r.status_code == 402  # billing stub: nobody is Pro


def test_delete_book_removes_row_and_files(signed_in):
    from server import db

    c = signed_in
    up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")})
    book = up.json()
    library.run_pending()

    with db.conn() as conn:
        row = conn.execute(
            "SELECT source_key, output_key FROM books WHERE id = %s", (book["id"],)
        ).fetchone()
    source_path = library.resolve_key(row["source_key"])
    output_path = library.resolve_key(row["output_key"])
    assert source_path.exists() and output_path.exists()

    d = c.delete(f"/api/books/{book['id']}")
    assert d.status_code == 200 and d.json()["ok"] is True

    assert c.get(f"/api/books/{book['id']}").status_code == 404
    assert not source_path.exists()
    assert not output_path.exists()


def test_delete_account_removes_all_books(signed_in):
    c = signed_in
    up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")})
    book_id = up.json()["id"]
    library.run_pending()
    assert c.delete("/api/me").status_code == 200
    # re-sign in as the same email creates a brand new account with no books
    r = c.post("/api/auth/request-code", json={"email": BOOK_EMAIL}).json()
    c.post("/api/auth/verify", json={"email": BOOK_EMAIL, "code": r["dev_code"]})
    assert c.get(f"/api/books/{book_id}").status_code == 404


# =========================================================================================
# Hosted LLM engine (v0.6): server/cache.py's paragraph cache, server/library.py's cost/usage
# rollup and `engine_note`. No real network call -- an in-process mock via the
# DYSREWRITE_LLM_TRANSPORT test hook (see tests/test_llm.py for the engine-level tests).
# =========================================================================================
def test_llm_engine_book_records_cost_usage_and_no_partial_note(signed_in, monkeypatch):
    import json as _json

    import httpx

    from dyslexic_rewrite.rewrite import llm as llm_engine

    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr(library.billing, "is_pro", lambda user: True)

    def handler(request):
        body = _json.loads(request.content)
        user_msg = body["messages"][1]["content"]
        paragraph = user_msg.rsplit("PARAGRAPH:\n", 1)[1]
        return httpx.Response(200, json={
            "choices": [{"message": {"content": paragraph}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 20,
                      "prompt_cache_hit_tokens": 400, "prompt_cache_miss_tokens": 100},
        })

    llm_engine.DYSREWRITE_LLM_TRANSPORT = httpx.MockTransport(handler)
    try:
        c = signed_in
        up = c.post("/api/books", files={"file": ("book.txt", BOOK_TXT, "text/plain")}, data={"engine": "llm"})
        assert up.status_code == 201, up.text
        assert up.json()["engine"] == "llm"

        library.run_pending()

        got = c.get(f"/api/books/{up.json()['id']}").json()
        assert got["status"] == "ready"
        assert got["cost_usd"] is not None and got["cost_usd"] > 0
        assert got["llm_usage"]["prompt_tokens"] > 0
        assert got["engine_note"] is None  # every paragraph was accepted, nothing fell back
    finally:
        llm_engine.DYSREWRITE_LLM_TRANSPORT = None


def test_llm_paragraph_cache_avoids_a_second_model_call(signed_in, monkeypatch):
    """A second book with the *same paragraph text* under the same profile hits the paragraph
    cache (server/cache.py) instead of calling the model again."""
    import json as _json
    import uuid

    import httpx

    from dyslexic_rewrite.rewrite import llm as llm_engine

    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr(library.billing, "is_pro", lambda user: True)
    monkeypatch.setattr(library.billing, "quota", lambda user: {"books_total": None, "paste_chars": 200_000, "llm_tier": True})

    # A paragraph unique to this test run, so a cache row left by an earlier test can't hide a
    # real cache miss on the first upload.
    marker = uuid.uuid4().hex
    book_txt = f"Chapter 1\n\nThe wind blew hard across the moor, marker {marker}, that night.\n".encode()

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        body = _json.loads(request.content)
        user_msg = body["messages"][1]["content"]
        paragraph = user_msg.rsplit("PARAGRAPH:\n", 1)[1]
        return httpx.Response(200, json={"choices": [{"message": {"content": paragraph}}]})

    llm_engine.DYSREWRITE_LLM_TRANSPORT = httpx.MockTransport(handler)
    try:
        c = signed_in
        up1 = c.post("/api/books", files={"file": ("book1.txt", book_txt, "text/plain")}, data={"engine": "llm"})
        assert up1.status_code == 201, up1.text
        library.run_pending()
        first_calls = calls["n"]
        assert first_calls > 0

        up2 = c.post("/api/books", files={"file": ("book2.txt", book_txt, "text/plain")}, data={"engine": "llm"})
        assert up2.status_code == 201, up2.text
        library.run_pending()
        assert calls["n"] == first_calls  # identical paragraphs, same profile -> cache hit, no new calls
    finally:
        llm_engine.DYSREWRITE_LLM_TRANSPORT = None

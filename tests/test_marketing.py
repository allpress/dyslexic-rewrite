"""Marketing surface tests (v0.5): server-rendered book pages, sitemap/robots, newsletter
signup + unsubscribe, the page-view counter, and admin stats. Need a Postgres at DATABASE_URL
(or TEST_DATABASE_URL); skipped otherwise."""

import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite"))
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)
os.environ.pop("ADMIN_KEY", None)

try:
    import psycopg
    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for API tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import db, marketing  # noqa: E402
from server.app import app  # noqa: E402
from server.samples import list_samples  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _clear_email(email: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM newsletter_signups WHERE email = %s", (email,))
        c.commit()


def _clear_path(path: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM page_views WHERE path = %s", (path,))
        c.commit()


# ---------------------------------------------------------------------------------------
# server-rendered book pages
# ---------------------------------------------------------------------------------------
def test_books_index_lists_samples(client):
    r = client.get("/books")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    for s in list_samples():
        assert s["title"] in r.text
        assert f'/books/{s["slug"]}' in r.text


def test_book_page_has_title_ruby_and_jsonld(client):
    r = client.get("/books/wind-in-the-willows")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "<title>Read The Wind in the Willows, dyslexia-friendly | Unwind Words</title>" in r.text
    assert "<ruby>" in r.text and "<rt>" in r.text
    assert '"@type": "Book"' in r.text
    assert '"@type": "WebPage"' in r.text
    assert 'rel="canonical"' in r.text
    assert "/read?sample=wind-in-the-willows" in r.text
    assert "gutenberg.org" in r.text.lower()


def test_book_page_404_for_unknown_slug(client):
    assert client.get("/books/not-a-real-book").status_code == 404


def test_book_page_tracks_a_view(client):
    _clear_path("/books/wind-in-the-willows")
    client.get("/books/wind-in-the-willows")
    with db.conn() as c:
        n = c.execute(
            "SELECT COALESCE(SUM(count), 0) AS n FROM page_views WHERE path = %s",
            ("/books/wind-in-the-willows",),
        ).fetchone()["n"]
    assert n >= 1


# ---------------------------------------------------------------------------------------
# sitemap / robots
# ---------------------------------------------------------------------------------------
def test_sitemap_lists_sample_slugs(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and "xml" in r.headers["content-type"]
    assert "<loc>https://unwindwords.com/</loc>" in r.text
    for s in list_samples():
        assert f'/books/{s["slug"]}</loc>' in r.text


def test_robots_txt(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap:" in r.text and "sitemap.xml" in r.text


# ---------------------------------------------------------------------------------------
# newsletter
# ---------------------------------------------------------------------------------------
def test_newsletter_signup_upserts(client):
    email = "pytest-newsletter@example.com"
    _clear_email(email)
    marketing._rate_hits.clear()
    try:
        r1 = client.post("/api/newsletter", json={"email": email, "source": "landing"})
        assert r1.status_code == 200 and r1.json()["ok"] is True
        # A second signup from the same address should not error, and should not clobber
        # the first-seen source.
        r2 = client.post("/api/newsletter", json={"email": email, "source": "footer"})
        assert r2.status_code == 200
        with db.conn() as c:
            row = c.execute(
                "SELECT source, unsubscribed_at FROM newsletter_signups WHERE email = %s", (email,),
            ).fetchone()
        assert row["source"] == "landing"
        assert row["unsubscribed_at"] is None
    finally:
        _clear_email(email)


def test_newsletter_rejects_bad_email(client):
    marketing._rate_hits.clear()
    r = client.post("/api/newsletter", json={"email": "not-an-email"})
    assert r.status_code == 400


def test_newsletter_rate_limited_after_five_per_minute(client):
    marketing._rate_hits.clear()
    try:
        for i in range(5):
            r = client.post("/api/newsletter", json={"email": f"pytest-rl-{i}@example.com"})
            assert r.status_code == 200
        r = client.post("/api/newsletter", json={"email": "pytest-rl-sixth@example.com"})
        assert r.status_code == 429
    finally:
        with db.conn() as c:
            c.execute("DELETE FROM newsletter_signups WHERE email LIKE 'pytest-rl-%'")
            c.commit()
        marketing._rate_hits.clear()


def test_newsletter_unsubscribe(client):
    email = "pytest-unsub@example.com"
    _clear_email(email)
    marketing._rate_hits.clear()
    try:
        client.post("/api/newsletter", json={"email": email})
        token = marketing.make_unsubscribe_token(email)
        r = client.get(f"/api/newsletter/unsubscribe?token={token}")
        assert r.status_code == 200
        with db.conn() as c:
            row = c.execute(
                "SELECT unsubscribed_at FROM newsletter_signups WHERE email = %s", (email,),
            ).fetchone()
        assert row["unsubscribed_at"] is not None
    finally:
        _clear_email(email)


def test_newsletter_unsubscribe_rejects_bad_token(client):
    assert client.get("/api/newsletter/unsubscribe?token=not-a-real-token").status_code == 400


# ---------------------------------------------------------------------------------------
# page-view tracking
# ---------------------------------------------------------------------------------------
def test_track_increments(client):
    path = "/pytest-track-test"
    _clear_path(path)
    try:
        client.post("/api/track", json={"path": path})
        client.post("/api/track", json={"path": path})
        with db.conn() as c:
            n = c.execute(
                "SELECT COALESCE(SUM(count), 0) AS n FROM page_views WHERE path = %s", (path,),
            ).fetchone()["n"]
        assert n == 2
    finally:
        _clear_path(path)


def test_track_never_stores_full_referrer_url(client):
    path = "/pytest-track-referrer"
    _clear_path(path)
    try:
        client.post("/api/track", json={"path": path}, headers={"Referer": "https://example.com/some/page?x=1"})
        with db.conn() as c:
            row = c.execute(
                "SELECT referrer_host FROM page_views WHERE path = %s", (path,),
            ).fetchone()
        assert row["referrer_host"] == "example.com"
    finally:
        _clear_path(path)


# ---------------------------------------------------------------------------------------
# admin stats
# ---------------------------------------------------------------------------------------
def test_admin_stats_404_without_key(client, monkeypatch):
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert client.get("/api/admin/stats").status_code == 404
    assert client.get("/api/admin/stats?key=anything").status_code == 404


def test_admin_stats_json_with_correct_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    assert client.get("/api/admin/stats?key=wrong").status_code == 404
    r = client.get("/api/admin/stats?key=test-admin-key")
    assert r.status_code == 200
    body = r.json()
    for key in ("signups", "page_views_30d", "users", "pro_users", "books", "generated_at"):
        assert key in body
    assert isinstance(body["signups"], int)
    assert isinstance(body["users"], int)
    assert isinstance(body["page_views_30d"], list)

"""Tests for server/importer.py: URL validation (incl. the private-IP SSRF block), extraction
via a mocked upstream (httpx.MockTransport, no real network), and the in-process cache.

Every "fetch" test uses an IP-literal URL (e.g. http://93.184.216.34/...) so the SSRF hostname
resolution (a real `socket.getaddrinfo` call) never needs DNS or network access -- resolving an
address that is already a literal IP is a pure, offline string-to-struct parse.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault(
    "DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite")
)
os.environ["SECURE_COOKIES"] = "0"

try:
    import psycopg

    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for importer tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import importer  # noqa: E402
from server.app import app  # noqa: E402

ARTICLE_HTML = """
<html><head><title>A Test Article</title></head>
<body>
<nav>skip this nav</nav>
<article>
<h1>A Test Article</h1>
<p>The wind blew hard across the moor that whole long night.</p>
<p>Grandpa wound the old clock again, just as he always had.</p>
</article>
<footer>skip this footer</footer>
</body></html>
"""


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_cache_and_transport():
    importer._cache.clear()
    yield
    importer.IMPORTER_TRANSPORT = None
    importer._cache.clear()


def _install(handler) -> None:
    importer.IMPORTER_TRANSPORT = httpx.MockTransport(handler)


# ---- URL validation / SSRF ---------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost/secret",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://192.168.1.1/",
        "http://[::1]/",
    ],
)
def test_private_and_loopback_addresses_are_blocked(client, url):
    r = client.post("/api/import/url", json={"url": url})
    assert r.status_code == 400, r.text


def test_non_http_scheme_is_rejected(client):
    r = client.post("/api/import/url", json={"url": "ftp://93.184.216.34/file"})
    assert r.status_code == 400


def test_unresolvable_host_is_rejected(client):
    r = client.post("/api/import/url", json={"url": "http://this-host-does-not-exist.invalid/"})
    assert r.status_code == 400


# ---- extraction (mocked upstream) ---------------------------------------------------------
def test_import_extracts_article_title_and_text(client):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=ARTICLE_HTML)

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/article"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "wind blew hard" in body["text"]
    assert "Grandpa wound" in body["text"]
    assert body["source_url"] == "http://93.184.216.34/article"
    assert body["words"] > 0
    assert body["note"] is None


def test_import_follows_a_redirect_and_validates_the_target(client):
    def handler(request):
        if str(request.url) == "http://93.184.216.34/old":
            return httpx.Response(302, headers={"location": "http://93.184.216.34/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE_HTML)

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/old"})
    assert r.status_code == 200, r.text
    assert r.json()["source_url"] == "http://93.184.216.34/new"


def test_redirect_to_a_private_address_is_blocked(client):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/old"})
    assert r.status_code == 400


def test_too_many_redirects_is_rejected(client):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://93.184.216.34/next"})

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/loop"})
    assert r.status_code == 400


def test_response_over_the_size_cap_is_rejected(client):
    big = ("<html><body><article><p>" + ("word " * 500_000) + "</p></article></body></html>").encode()

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=big)

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/huge"})
    assert r.status_code == 400


def test_non_html_content_type_is_rejected(client):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/file.pdf"})
    assert r.status_code == 400


def test_upstream_error_status_surfaces_as_502(client):
    def handler(request):
        return httpx.Response(500)

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/broken"})
    assert r.status_code == 502


# ---- quota (anonymous callers get the free paste_chars limit) -----------------------------
def test_over_quota_text_is_truncated_with_a_note(client, monkeypatch):
    from server import billing

    monkeypatch.setattr(billing, "FREE_PASTE_CHARS", 20)

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE_HTML)

    _install(handler)
    r = client.post("/api/import/url", json={"url": "http://93.184.216.34/article"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["text"]) <= 20
    assert body["note"] is not None
    assert "pro" in body["note"].lower() or "library" in body["note"].lower()


# ---- caching --------------------------------------------------------------------------------
def test_repeat_import_of_the_same_url_hits_the_cache(client):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE_HTML)

    _install(handler)
    r1 = client.post("/api/import/url", json={"url": "http://93.184.216.34/cached"})
    r2 = client.post("/api/import/url", json={"url": "http://93.184.216.34/cached"})
    assert r1.status_code == r2.status_code == 200
    assert calls["n"] == 1
    assert r1.json()["text"] == r2.json()["text"]


def test_cache_expires_after_ttl(client, monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE_HTML)

    _install(handler)
    client.post("/api/import/url", json={"url": "http://93.184.216.34/expiring"})
    monkeypatch.setattr(importer, "_CACHE_TTL_S", -1.0)  # already expired
    calls = {"n": 0}

    def handler2(request):
        calls["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE_HTML)

    _install(handler2)
    client.post("/api/import/url", json={"url": "http://93.184.216.34/expiring"})
    assert calls["n"] == 1

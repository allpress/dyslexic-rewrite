"""Tests for server/dictionary.py: a mocked upstream (httpx.MockTransport, no real network),
the Postgres cache (definitions table, migration 011_import_dictionary_summaries.sql), and the
404/rate-limit behaviour.
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
    pytest.skip(f"no Postgres for dictionary tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import db, dictionary  # noqa: E402
from server.app import app  # noqa: E402

CLOCK_ENTRY = [
    {
        "word": "clock",
        "phonetic": "/klɒk/",
        "phonetics": [{"text": "/klɒk/", "audio": "https://example.com/clock.mp3"}],
        "meanings": [
            {
                "partOfSpeech": "noun",
                "definitions": [
                    {"definition": "A device that measures and shows time.", "example": "The clock struck noon."},
                ],
            },
            {
                "partOfSpeech": "verb",
                "definitions": [{"definition": "To record the time of an event."}],
            },
        ],
    }
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_table():
    with db.conn() as c:
        c.execute("DELETE FROM definitions WHERE word IN ('clock', 'zzzznotaword', 'wind')")
        c.commit()
    yield
    dictionary.DICTIONARY_TRANSPORT = None
    dictionary._rate_hits.clear()
    with db.conn() as c:
        c.execute("DELETE FROM definitions WHERE word IN ('clock', 'zzzznotaword', 'wind')")
        c.commit()


def _install(handler) -> None:
    dictionary.DICTIONARY_TRANSPORT = httpx.MockTransport(handler)


def test_define_returns_trimmed_shape(client):
    def handler(request):
        assert request.url.path.endswith("/clock")
        return httpx.Response(200, json=CLOCK_ENTRY)

    _install(handler)
    r = client.get("/api/define", params={"word": "Clock"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["word"] == "clock"
    assert body["phonetic"] == "/klɒk/"
    assert body["audio_url"] == "https://example.com/clock.mp3"
    assert len(body["meanings"]) == 2
    assert body["meanings"][0] == {
        "pos": "noun", "definition": "A device that measures and shows time.", "example": "The clock struck noon.",
    }


def test_define_trims_to_three_meanings(client):
    entry = [{**CLOCK_ENTRY[0], "meanings": CLOCK_ENTRY[0]["meanings"] * 3}]  # 6 meanings available

    def handler(request):
        return httpx.Response(200, json=entry)

    _install(handler)
    r = client.get("/api/define", params={"word": "clock"})
    assert len(r.json()["meanings"]) == 3


def test_unknown_word_is_404(client):
    def handler(request):
        return httpx.Response(404, json={"title": "No Definitions Found"})

    _install(handler)
    r = client.get("/api/define", params={"word": "zzzznotaword"})
    assert r.status_code == 404


def test_cache_hit_avoids_a_second_upstream_call(client):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=CLOCK_ENTRY)

    _install(handler)
    r1 = client.get("/api/define", params={"word": "wind"})
    r2 = client.get("/api/define", params={"word": "wind"})
    assert r1.status_code == r2.status_code == 200
    assert calls["n"] == 1
    with db.conn() as c:
        row = c.execute("SELECT word FROM definitions WHERE word = 'wind'").fetchone()
    assert row is not None


def test_missing_word_result_is_also_cached(client):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={"title": "No Definitions Found"})

    _install(handler)
    client.get("/api/define", params={"word": "zzzznotaword"})
    r2 = client.get("/api/define", params={"word": "zzzznotaword"})
    assert r2.status_code == 404
    assert calls["n"] == 1


def test_invalid_word_is_400(client):
    r = client.get("/api/define", params={"word": "not a word!!"})
    assert r.status_code == 400


def test_rate_limit_kicks_in_after_60_per_minute(client):
    def handler(request):
        return httpx.Response(200, json=CLOCK_ENTRY)

    _install(handler)
    for _ in range(60):
        r = client.get("/api/define", params={"word": "clock"})
        assert r.status_code == 200
    r = client.get("/api/define", params={"word": "clock"})
    assert r.status_code == 429

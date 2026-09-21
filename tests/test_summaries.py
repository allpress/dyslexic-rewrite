"""Tests for server/summaries.py: a mocked LLM transport (same pattern as tests/test_llm.py,
via src/dyslexic_rewrite/rewrite/llm.py's DYSREWRITE_LLM_TRANSPORT hook), the Pro gate (402),
the "no LLM configured" gate (503), and the summaries cache.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

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
    pytest.skip(f"no Postgres for summaries tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from dyslexic_rewrite.rewrite import llm as llm_engine  # noqa: E402
from server import db  # noqa: E402
from server.app import app  # noqa: E402

SUMMARY_EMAIL = "pytest-summaries@example.com"
PASSAGE = (
    "Grandpa wound the old clock every night before bed, just as he always had. "
    "The house stayed quiet until morning, when the birds outside began to sing."
)


def _reply(bullets: list[str]) -> dict:
    text = "\n".join(f"- {b}" for b in bullets)
    return {"choices": [{"message": {"content": text}}]}


def _install(handler) -> None:
    llm_engine.DYSREWRITE_LLM_TRANSPORT = httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for k in ("DYSREWRITE_LLM_BASE_URL", "DYSREWRITE_LLM_MODEL", "DYSREWRITE_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield
    llm_engine.DYSREWRITE_LLM_TRANSPORT = None
    with db.conn() as c:
        c.execute("DELETE FROM summaries")
        c.commit()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
        c.delete("/api/me")


@pytest.fixture()
def signed_in(client):
    r = client.post("/api/auth/request-code", json={"email": SUMMARY_EMAIL}).json()
    ok = client.post("/api/auth/verify", json={"email": SUMMARY_EMAIL, "code": r["dev_code"]})
    assert ok.status_code == 200
    return client


@pytest.fixture()
def pro_signed_in(signed_in):
    with db.conn() as c:
        c.execute("UPDATE users SET plan = 'pro' WHERE email = %s", (SUMMARY_EMAIL,))
        c.commit()
    return signed_in


# ---- gating -----------------------------------------------------------------------------
def test_summaries_require_pro_even_when_llm_is_configured(signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    r = signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 402
    assert r.json()["error"] == "pro_required"


def test_summaries_require_pro_for_anonymous_callers(client, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    r = client.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 402


def test_summaries_503_when_no_llm_configured_even_for_pro(pro_signed_in):
    r = pro_signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 503
    assert "hosted engine" in r.json()["error"].lower()


# ---- happy path + cache -------------------------------------------------------------------
def test_pro_reader_gets_a_bulleted_summary(pro_signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        body = json.loads(request.content)
        assert "no new facts" in body["messages"][0]["content"].lower() or "add nothing" in body["messages"][0]["content"].lower()
        assert body["messages"][1]["content"] == PASSAGE
        return httpx.Response(200, json=_reply(["Grandpa wound the clock nightly.", "The house was quiet till morning."]))

    _install(handler)
    r = pro_signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bullets"] == ["Grandpa wound the clock nightly.", "The house was quiet till morning."]
    assert calls["n"] == 1

    # Re-summarising the exact same text under the same profile hits the cache.
    r2 = pro_signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r2.status_code == 200
    assert r2.json()["bullets"] == body["bullets"]
    assert calls["n"] == 1


def test_summary_is_capped_to_six_bullets(pro_signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")

    def handler(request):
        return httpx.Response(200, json=_reply([f"Point number {i}." for i in range(9)]))

    _install(handler)
    r = pro_signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 200
    assert len(r.json()["bullets"]) == 6


def test_empty_model_output_is_a_502(pro_signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    _install(handler)
    r = pro_signed_in.post("/api/summaries", json={"text": PASSAGE})
    assert r.status_code == 502


def test_blank_text_is_rejected(pro_signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    r = pro_signed_in.post("/api/summaries", json={"text": "   "})
    assert r.status_code == 400


# ---- book chapter summaries ---------------------------------------------------------------
def test_book_chapter_summary_requires_pro_and_a_ready_book(pro_signed_in, monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    r = pro_signed_in.post("/api/books/999999/summary")
    assert r.status_code == 404  # not this reader's book


def test_signed_out_book_summary_is_401(client):
    r = client.post("/api/books/1/summary")
    assert r.status_code == 401

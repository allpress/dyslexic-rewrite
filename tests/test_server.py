"""API tests. Need a Postgres at DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise."""

import json
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite"))
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)

try:
    import psycopg
    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for API tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import db  # noqa: E402
from server.app import app  # noqa: E402


def _clear_rewrite_cache() -> None:
    """The cache table is real Postgres state that outlives one pytest run, so cache tests
    start from a known-empty table rather than assuming nothing has been cached yet."""
    with db.conn() as c:
        c.execute("DELETE FROM rewrite_cache")
        c.commit()

EMAIL = "pytest-user@example.com"
SAMPLE = ("I finished the shelves today!! Took forever but I love it. Marisol helped with the trim and we got "
          "pizza after. Tomorrow I paint. Not sure about the colour yet, maybe the green? We'll see. Lol. ") * 12


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
        # clean up
        c.delete("/api/me")


@pytest.fixture(scope="module")
def signed_in(client):
    r = client.post("/api/auth/request-code", json={"email": EMAIL}).json()
    assert r["ok"] and "dev_code" in r
    bad = client.post("/api/auth/verify", json={"email": EMAIL, "code": "000000"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/verify", json={"email": EMAIL, "code": r["dev_code"]})
    assert ok.status_code == 200 and ok.json()["user"]["email"] == EMAIL
    return client


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_onboarding_and_writing_sample_keeps_no_content(signed_in):
    c = signed_in
    u = c.patch("/api/me", json={"name": "Pat", "base_profile": "attention"}).json()["user"]
    assert u["name"] == "Pat" and u["base_profile"] == "attention"
    short = c.post("/api/me/writing-sample", json={"text": "too short"})
    assert short.status_code == 400
    r = c.post("/api/me/writing-sample", json={"text": SAMPLE})
    assert r.status_code == 200
    blob = json.dumps(r.json())
    assert "Marisol" not in blob and "pizza after" not in blob and "shelves today" not in blob
    assert r.json()["style"]["sample_sentences"] > 10
    me = c.get("/api/me").json()
    assert me["user"]["has_personal_profile"] and me["profile"]["style"]["sample_words"] > 0


def test_ab_test_flow(signed_in):
    c = signed_in
    t = c.post("/api/tests", json={}).json()
    assert {i["condition"] for i in t["items"]} == {"original", "rewritten"}
    assert all(len(i["questions"]) == 5 for i in t["items"])
    assert all("answer" not in q for i in t["items"] for q in i["questions"])
    assert all("phonetic_map" in i and isinstance(i["phonetic_map"], list) for i in t["items"])
    rewritten = next(i for i in t["items"] if i["condition"] == "rewritten")
    assert any(s["t"] in ("change", "note") for s in rewritten["segments"])
    for i in t["items"]:
        assert c.post(f"/api/tests/{t['id']}/items/{i['index']}/start").status_code == 200
        too_fast = c.post(f"/api/tests/{t['id']}/items/{i['index']}/finish",
                          json={"seconds": 1, "answers": {}, "tripped": [], "ease": 3})
        assert too_fast.status_code == 400
        res = c.post(f"/api/tests/{t['id']}/items/{i['index']}/finish",
                     json={"seconds": 90, "answers": {q["id"]: 1 for q in i["questions"]},
                           "tripped": ["Harrow", "wind"], "ease": 4, "read_aloud": i["index"] == 0}).json()
        assert res["total"] == 5 and 0 <= res["correct"] <= 5 and res["wpm"] > 0
        assert res["tripped"] == ["harrow", "wind"]
        assert res["phonetic_map"] == "on_demand"
        assert res["read_aloud"] == (i["index"] == 0)
    dup = c.post(f"/api/tests/{t['id']}/items/0/finish", json={"seconds": 90, "answers": {}, "tripped": [], "ease": 3})
    assert dup.status_code == 409
    results = c.get("/api/results").json()
    assert results["totals"]["original"]["n"] == 1 and results["totals"]["rewritten"]["n"] == 1
    assert results["tests"][0]["completed"] is True
    again = c.get(f"/api/tests/{t['id']}").json()
    assert again["items"][0]["result"]["phonetic_map"] == "on_demand"
    assert again["items"][0]["result"]["read_aloud"] is True


def test_phonetic_map_preference(signed_in):
    c = signed_in
    me = c.get("/api/me").json()
    assert me["user"]["phonetic_map"] == "on_demand"  # default
    bad = c.patch("/api/me", json={"phonetic_map": "nonsense"})
    assert bad.status_code == 400
    u = c.patch("/api/me", json={"phonetic_map": "always"}).json()["user"]
    assert u["phonetic_map"] == "always"
    r = c.post("/api/rewrite", json={"text": "Grandpa would wind the clock."}).json()
    assert "phonetic_map" in r and isinstance(r["phonetic_map"], list)
    c.patch("/api/me", json={"phonetic_map": "on_demand"})  # reset for later tests


def test_triggers_and_read_anything(signed_in):
    c = signed_in
    p = c.post("/api/me/triggers", json={"add": ["wind"]}).json()["profile"]
    assert "wind" in p["trigger_words"]
    r = c.post("/api/rewrite", json={"text": "Grandpa would wind the clock while the wind blew."}).json()
    assert any(s["t"] == "change" and s["orig"] == "wind" for s in r["segments"])
    p = c.post("/api/me/triggers", json={"remove": ["wind"]}).json()["profile"]
    assert "wind" not in p["trigger_words"]


def test_anonymous_rewrite_and_spa_fallback(client):
    with TestClient(app) as anon:
        r = anon.post("/api/rewrite", json={"text": "She tried to tear the page, but a tear fell."})
        assert r.status_code == 200 and r.json()["stats"]["changes"] >= 1
        assert anon.get("/api/results").status_code == 401
        page = anon.get("/test")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]


SAMPLE_SLUGS = {"wind-in-the-willows", "alice-in-wonderland", "wizard-of-oz", "christmas-carol"}


def test_samples_list(client):
    listed = client.get("/api/samples").json()
    assert {s["slug"] for s in listed} == SAMPLE_SLUGS
    for s in listed:
        assert s["title"] and s["author"] and s["year"] and s["chapter"]
        assert s["source"].startswith("https://")
        assert s["blurb"] and s["words"] > 0
    wind = next(s for s in listed if s["slug"] == "wind-in-the-willows")
    assert wind["title"] == "The Wind in the Willows" and wind["author"] == "Kenneth Grahame"
    assert wind["year"] == 1908


def test_sample_anonymous_is_allowed(client):
    with TestClient(app) as anon:
        r = anon.get("/api/samples/wind-in-the-willows")
        body = r.json()
        assert r.status_code == 200
        assert body["title"] == "The Wind in the Willows" and body["author"] == "Kenneth Grahame"
        assert isinstance(body["segments"], list) and len(body["segments"]) > 0
        assert isinstance(body["phonetic_map"], list) and "stats" in body
        assert isinstance(body["cached"], bool)  # may already be warm from startup


def test_sample_unknown_slug_404(client):
    assert client.get("/api/samples/not-a-real-book").status_code == 404


def test_sample_rewrite_is_cached_per_profile(signed_in):
    c = signed_in
    _clear_rewrite_cache()
    c.patch("/api/me", json={"base_profile": "visual"})
    r1 = c.get("/api/samples/wind-in-the-willows").json()
    assert r1["cached"] is False
    assert r1["title"] == "The Wind in the Willows" and r1["author"] == "Kenneth Grahame"
    assert r1["chapter"] and r1["source"].startswith("https://")
    assert len(r1["segments"]) > 0

    r2 = c.get("/api/samples/wind-in-the-willows").json()
    assert r2["cached"] is True
    assert r2["segments"] == r1["segments"] and r2["phonetic_map"] == r1["phonetic_map"]

    c.patch("/api/me", json={"base_profile": "attention"})  # a different profile -> cache miss
    r3 = c.get("/api/samples/wind-in-the-willows").json()
    assert r3["cached"] is False
    c.patch("/api/me", json={"base_profile": "default"})


def test_rewrite_is_cached(signed_in):
    c = signed_in
    _clear_rewrite_cache()
    text = "The wind blew hard across the moor while Grandpa wound the old clock again tonight."
    r1 = c.post("/api/rewrite", json={"text": text}).json()
    assert r1["cached"] is False
    r2 = c.post("/api/rewrite", json={"text": text}).json()
    assert r2["cached"] is True
    assert r2["segments"] == r1["segments"]

    c.patch("/api/me", json={"base_profile": "phonological"})  # a different profile -> cache miss
    r3 = c.post("/api/rewrite", json={"text": text}).json()
    assert r3["cached"] is False
    c.patch("/api/me", json={"base_profile": "default"})


def test_delete_account(signed_in):
    c = signed_in
    assert c.delete("/api/me").json()["ok"] is True
    assert c.get("/api/me").status_code == 401

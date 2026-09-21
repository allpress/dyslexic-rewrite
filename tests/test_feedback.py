"""Feedback (v0.6) tests: anonymous + signed-in submit, rate limiting, the admin list (json and
markdown), status patching, the summary, the export "pulse" bundle, and the 404-without-key gate.
Need a Postgres at DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise.

Test order matters here: `signed_in` reuses the same module-scoped `client`, so every test that
checks anonymous/401 behaviour on that shared client runs *before* any test that requests
`signed_in` -- once that fixture signs in, the client stays signed in for the rest of the module
(same pattern as tests/test_server.py)."""

import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite"))
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)
os.environ.pop("ADMIN_KEY", None)
os.environ.pop("FEEDBACK_NOTIFY_EMAIL", None)

try:
    import psycopg
    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for API tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import db, feedback  # noqa: E402
from server.app import app  # noqa: E402

EMAIL = "pytest-feedback-user@example.com"


def _clear_feedback(like: str = "pytest-%") -> None:
    with db.conn() as c:
        c.execute("DELETE FROM feedback WHERE message LIKE %s", (like,))
        c.commit()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
        c.delete("/api/me")
        _clear_feedback()


@pytest.fixture(scope="module")
def signed_in(client):
    r = client.post("/api/auth/request-code", json={"email": EMAIL}).json()
    ok = client.post("/api/auth/verify", json={"email": EMAIL, "code": r["dev_code"]})
    assert ok.status_code == 200
    return client


def setup_function(_fn):
    feedback._rate_hits.clear()


# ---------------------------------------------------------------------------------------
# submit, anonymous -- must run before anything signs the shared `client` in
# ---------------------------------------------------------------------------------------
def test_submit_anonymous(client):
    r = client.post(
        "/api/feedback/submit",
        json={"kind": "idea", "message": "pytest-anon: dark mode please", "page": "/read"},
    )
    assert r.status_code == 201
    fid = r.json()["id"]
    with db.conn() as c:
        row = c.execute("SELECT * FROM feedback WHERE id = %s", (fid,)).fetchone()
    assert row["user_id"] is None and row["kind"] == "idea" and row["status"] == "new"


def test_submit_anonymous_with_email_and_context(client):
    r = client.post(
        "/api/feedback/submit",
        json={
            "kind": "bug",
            "message": "pytest-anon-email: the button is missing",
            "email": "reader@example.com",
            "rating": 2,
            "page": "/library",
            "context": {"app_version": "0.1.0", "viewport": "390x844"},
        },
    )
    assert r.status_code == 201
    with db.conn() as c:
        row = c.execute("SELECT * FROM feedback WHERE id = %s", (r.json()["id"],)).fetchone()
    assert row["email"] == "reader@example.com"
    assert row["rating"] == 2
    assert row["context"]["app_version"] == "0.1.0"


def test_submit_rejects_bad_email(client):
    r = client.post(
        "/api/feedback/submit",
        json={"kind": "idea", "message": "pytest-bad-email", "email": "not-an-email"},
    )
    assert r.status_code == 400


def test_submit_rejects_empty_message(client):
    r = client.post("/api/feedback/submit", json={"kind": "idea", "message": ""})
    assert r.status_code == 422


def test_submit_rejects_unknown_kind(client):
    r = client.post("/api/feedback/submit", json={"kind": "tripped", "message": "pytest-nope"})
    assert r.status_code == 422


def test_submit_rate_limited_after_ten_per_hour(client):
    try:
        for i in range(10):
            r = client.post(
                "/api/feedback/submit",
                json={"kind": "idea", "message": f"pytest-rl-{i}"},
            )
            assert r.status_code == 201
        r = client.post("/api/feedback/submit", json={"kind": "idea", "message": "pytest-rl-11th"})
        assert r.status_code == 429
    finally:
        _clear_feedback("pytest-rl-%")


def test_mine_requires_login(client):
    assert client.get("/api/feedback/mine").status_code == 401


# ---------------------------------------------------------------------------------------
# signed in from here on -- `signed_in` permanently signs the shared `client` in
# ---------------------------------------------------------------------------------------
def test_submit_signed_in_attaches_user(signed_in):
    r = signed_in.post(
        "/api/feedback/submit",
        json={"kind": "praise", "message": "pytest-signed-in: this is great", "rating": 5},
    )
    assert r.status_code == 201
    with db.conn() as c:
        row = c.execute("SELECT user_id FROM feedback WHERE id = %s", (r.json()["id"],)).fetchone()
    assert row["user_id"] is not None


def test_mine_lists_only_own(signed_in):
    r = signed_in.get("/api/feedback/mine")
    assert r.status_code == 200
    body = r.json()
    assert any(item["message"].startswith("pytest-signed-in") for item in body)
    for item in body:
        assert "status" in item and "kind" in item


def test_tripped_feedback_writes_a_row(signed_in):
    r = signed_in.post("/api/feedback", json={"tripped": ["pytest-trippedword"], "safe": []})
    assert r.status_code == 200
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM feedback WHERE kind = 'tripped' AND message LIKE %s ORDER BY created_at DESC LIMIT 1",
            ("%pytest-trippedword%",),
        ).fetchone()
    assert row is not None
    assert row["context"]["tripped"] == ["pytest-trippedword"]


# ---------------------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------------------
def test_admin_routes_404_without_key(client, monkeypatch):
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert client.get("/api/admin/feedback").status_code == 404
    assert client.get("/api/admin/feedback?key=anything").status_code == 404
    assert client.get("/api/admin/feedback/summary").status_code == 404
    assert client.get("/api/admin/export").status_code == 404
    assert client.patch("/api/admin/feedback/1", json={"status": "triaged"}).status_code == 404


def test_admin_list_json_and_filters(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    client.post("/api/feedback/submit", json={"kind": "bug", "message": "pytest-admin-bug", "page": "/x"})
    assert client.get("/api/admin/feedback?key=wrong").status_code == 404
    r = client.get("/api/admin/feedback?key=test-admin-key&kind=bug")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert all(item["kind"] == "bug" for item in body)
    assert any(item["message"] == "pytest-admin-bug" for item in body)


def test_admin_list_rejects_bad_since(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    r = client.get("/api/admin/feedback?key=test-admin-key&since=not-a-date")
    assert r.status_code == 400


def test_admin_list_markdown_digest(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    client.post("/api/feedback/submit", json={"kind": "idea", "message": "pytest-md-digest-item", "page": "/x"})
    r = client.get("/api/admin/feedback?key=test-admin-key&format=md")
    assert r.status_code == 200
    assert "markdown" in r.headers["content-type"]
    assert "# Feedback digest" in r.text
    assert "pytest-md-digest-item" in r.text
    assert "## Idea" in r.text


def test_admin_patch_status_and_tags(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    created = client.post(
        "/api/feedback/submit", json={"kind": "question", "message": "pytest-patch-me"},
    ).json()
    r = client.patch(
        f"/api/admin/feedback/{created['id']}?key=test-admin-key",
        json={"status": "triaged", "tags": ["pytest", "onboarding"], "admin_note": "looking into it"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "triaged"
    assert body["tags"] == ["pytest", "onboarding"]
    assert body["admin_note"] == "looking into it"


def test_admin_patch_404_for_unknown_id(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    r = client.patch("/api/admin/feedback/999999999?key=test-admin-key", json={"status": "done"})
    assert r.status_code == 404


def test_admin_summary_shape(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    client.post("/api/feedback/submit", json={"kind": "praise", "message": "pytest-summary-item", "rating": 5})
    r = client.get("/api/admin/feedback/summary?key=test-admin-key")
    assert r.status_code == 200
    body = r.json()
    for key in ("last_7d", "last_30d", "top_pages", "generated_at"):
        assert key in body
    for window in (body["last_7d"], body["last_30d"]):
        assert "count" in window and "by_kind" in window and "by_status" in window and "avg_rating" in window


def test_admin_export_bundle(client, monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
    client.post("/api/feedback/submit", json={"kind": "bug", "message": "pytest-export-item"})
    r = client.get("/api/admin/export?key=test-admin-key")
    assert r.status_code == 200
    body = r.json()
    for key in ("feedback", "stats", "battery", "ab_test", "generated_at"):
        assert key in body
    assert any(item["message"] == "pytest-export-item" for item in body["feedback"])
    assert "signups" in body["stats"]
    assert "runs" in body["battery"] and "mean_support_by_axis" in body["battery"]

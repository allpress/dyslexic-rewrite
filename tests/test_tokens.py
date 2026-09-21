"""Personal API tokens (v0.6): server/tokens.py, plus the bearer-auth hook in server/app.py's
`current_user`/`optional_user` and the CORS allowance for extension origins. Needs Postgres at
DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise -- same guard as tests/test_server.py."""

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

from server.app import app  # noqa: E402

EMAIL = "pytest-tokens@example.com"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
        c.delete("/api/me")


@pytest.fixture(scope="module")
def signed_in(client):
    r = client.post("/api/auth/request-code", json={"email": EMAIL}).json()
    ok = client.post("/api/auth/verify", json={"email": EMAIL, "code": r["dev_code"]})
    assert ok.status_code == 200
    return client


def test_create_list_revoke(signed_in):
    c = signed_in
    created = c.post("/api/me/tokens", json={"name": "My laptop"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "My laptop"
    assert body["token"].startswith("uw_")
    assert len(body["token"]) == len("uw_") + 40
    assert body["prefix"] == body["token"][len("uw_"):len("uw_") + 10]
    assert body["revoked_at"] is None
    assert body["last_used_at"] is None

    listed = c.get("/api/me/tokens").json()
    assert any(t["id"] == body["id"] for t in listed)
    # the plaintext token is never returned again
    assert all("token" not in t for t in listed)

    empty_name = c.post("/api/me/tokens", json={"name": ""})
    assert empty_name.status_code == 422

    revoked = c.delete(f"/api/me/tokens/{body['id']}")
    assert revoked.status_code == 200 and revoked.json()["ok"] is True

    again = c.delete(f"/api/me/tokens/{body['id']}")
    assert again.status_code == 404

    listed_after = c.get("/api/me/tokens").json()
    row = next(t for t in listed_after if t["id"] == body["id"])
    assert row["revoked_at"] is not None


def test_bearer_auth_on_me_and_rewrite(signed_in):
    c = signed_in
    created = c.post("/api/me/tokens", json={"name": "Extension"}).json()
    token = created["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # A fresh client with no cookie jar at all, to prove the header alone is enough.
    with TestClient(app) as anon:
        me = anon.get("/api/me", headers=headers)
        assert me.status_code == 200 and me.json()["user"]["email"] == EMAIL

        rewritten = anon.post(
            "/api/rewrite", json={"text": "Grandpa would wind the clock every night."}, headers=headers,
        )
        assert rewritten.status_code == 200

        no_auth = anon.get("/api/me")
        assert no_auth.status_code == 401

        bad_scheme = anon.get("/api/me", headers={"Authorization": token})
        assert bad_scheme.status_code == 401

        bad_token = anon.get("/api/me", headers={"Authorization": "Bearer uw_not-a-real-token"})
        assert bad_token.status_code == 401

    c.delete(f"/api/me/tokens/{created['id']}")


def test_revoked_token_401(signed_in):
    c = signed_in
    created = c.post("/api/me/tokens", json={"name": "Old phone"}).json()
    token = created["token"]
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as anon:
        ok = anon.get("/api/me", headers=headers)
        assert ok.status_code == 200

    c.delete(f"/api/me/tokens/{created['id']}")

    with TestClient(app) as anon:
        after_revoke = anon.get("/api/me", headers=headers)
        assert after_revoke.status_code == 401


def test_cors_preflight_from_extension_origin(client):
    origin = "chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef"
    r = client.options(
        "/api/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin
    allow_headers = r.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers

    firefox_origin = "moz-extension://11111111-2222-3333-4444-555555555555"
    r2 = client.options(
        "/api/me",
        headers={
            "Origin": firefox_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r2.status_code in (200, 204)
    assert r2.headers.get("access-control-allow-origin") == firefox_origin

    disallowed = client.options(
        "/api/me",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in disallowed.headers.keys()}

"""Personal API tokens (v0.6): "Bearer uw_..." auth for the browser extension.

The extension has no cookie jar it can rely on (a content-script fetch on someone else's page
does not carry unwindwords.com's session cookie), so a reader who wants their own profile and
Pro limits pastes a personal token into the extension's settings instead. A token authenticates
exactly like the session cookie -- see the small, surgical check added to `current_user`/
`optional_user` in server/app.py, which tries the `Authorization` header first and falls back to
the cookie.

Only a SHA-256 hash of the token is ever stored; the plaintext is returned exactly once, from
`POST /api/me/tokens`, the same "shown once" pattern as a sign-in code or a Stripe secret.
`prefix` (the token's first 10 characters after the `uw_` marker) is kept in the clear purely so
the list view can show a reader which token is which ("uw_9f2a3c6b1d...") without ever being able
to reconstruct the secret from it.

See server/API.md, "API tokens (v0.6)", and server/migrations/012_api_tokens.sql for the schema.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter(prefix="/api/me/tokens")

TOKEN_PREFIX = "uw_"
TOKEN_RANDOM_CHARS = 40
MAX_TOKENS_PER_USER = 20


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    """A new plaintext token: `uw_` + 40 url-safe characters."""
    # token_urlsafe(30) yields 40 base64url characters (no padding).
    return TOKEN_PREFIX + secrets.token_urlsafe(30)[:TOKEN_RANDOM_CHARS]


def user_from_bearer(header_value: str) -> dict | None:
    """Authenticate an `Authorization: Bearer uw_...` header. Returns the user row, touches
    `last_used_at`, or returns None for anything that isn't a live, unrevoked token -- including
    a header that isn't a bearer token at all, which callers treat the same as "no token given"
    so a cookie-based session can still work.
    """
    if not header_value.startswith("Bearer "):
        return None
    token = header_value[len("Bearer "):].strip()
    if not token.startswith(TOKEN_PREFIX):
        return None
    with db.conn() as c:
        row = c.execute(
            "SELECT t.id AS token_id, u.* FROM api_tokens t JOIN users u ON u.id = t.user_id "
            "WHERE t.token_hash = %s AND t.revoked_at IS NULL",
            (_hash(token),),
        ).fetchone()
        if not row:
            return None
        c.execute("UPDATE api_tokens SET last_used_at = now() WHERE id = %s", (row["token_id"],))
        c.commit()
    row.pop("token_id", None)
    return row


# ---------------------------------------------------------------------------------------
# auth helper -- standalone (not imported from server.app) so this module has no import cycle
# with it, the same pattern server/feedback.py uses.
# ---------------------------------------------------------------------------------------
def _current_user(request: Request) -> dict:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if header:
        u = user_from_bearer(header)
        if u:
            return u
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    if uid:
        with db.conn() as c:
            u = c.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()
        if u:
            return u
    raise HTTPException(401, "Please sign in.")


# ---------------------------------------------------------------------------------------
# models / JSON shape
# ---------------------------------------------------------------------------------------
class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _token_json(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "prefix": r["prefix"],
        "created_at": r["created_at"].isoformat(),
        "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
    }


# ---------------------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------------------
@router.post("", status_code=201)
def create_token(body: TokenCreateIn, u: dict = Depends(_current_user)):
    with db.conn() as c:
        count = c.execute(
            "SELECT COUNT(*) AS n FROM api_tokens WHERE user_id = %s AND revoked_at IS NULL", (u["id"],),
        ).fetchone()["n"]
        if count >= MAX_TOKENS_PER_USER:
            raise HTTPException(400, f"You can have at most {MAX_TOKENS_PER_USER} active tokens. Revoke one first.")
        token = generate_token()
        prefix = token[len(TOKEN_PREFIX):len(TOKEN_PREFIX) + 10]
        row = c.execute(
            "INSERT INTO api_tokens (user_id, name, token_hash, prefix) VALUES (%s, %s, %s, %s) RETURNING *",
            (u["id"], body.name.strip(), _hash(token), prefix),
        ).fetchone()
        c.commit()
    out = _token_json(row)
    out["token"] = token  # shown exactly once
    return out


@router.get("")
def list_tokens(u: dict = Depends(_current_user)):
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM api_tokens WHERE user_id = %s ORDER BY created_at DESC", (u["id"],),
        ).fetchall()
    return [_token_json(r) for r in rows]


@router.delete("/{token_id}")
def revoke_token(token_id: int, u: dict = Depends(_current_user)):
    with db.conn() as c:
        row = c.execute(
            "UPDATE api_tokens SET revoked_at = %s WHERE id = %s AND user_id = %s AND revoked_at IS NULL "
            "RETURNING id",
            (datetime.now(timezone.utc), token_id, u["id"]),
        ).fetchone()
        c.commit()
    if not row:
        raise HTTPException(404, "No such token.")
    return {"ok": True}

"""Marketing surface (v0.5): newsletter signups, a cookie-free page-view counter, and an
admin stats endpoint. See server/API.md.

Privacy: `page_views` never stores an IP address or a cookie -- only a day, a path and the
referring site's hostname (never the full referrer URL, which can carry query strings). The
newsletter list is a plain, single-opt-in email list for v1 (no confirmation email); every
address gets a one-click, tokenised unsubscribe link and `DELETE /api/me` never touches this
table because a newsletter signup does not require an account.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter(prefix="/api")

APP_NAME = os.environ.get("APP_NAME", "Unwind Words")
SITE_URL = os.environ.get("SITE_URL", "https://unwindwords.com").rstrip("/")
UNSUBSCRIBE_SALT = "newsletter-unsub"
_unsub_serializer = URLSafeSerializer(auth.SECRET, salt=UNSUBSCRIBE_SALT)

# ---------------------------------------------------------------------------------------
# in-process rate limit: 5 signups per minute per client IP. Not shared across workers/
# instances -- good enough to stop a single abusive script, not a distributed defence.
# ---------------------------------------------------------------------------------------
_RATE_WINDOW_S = 60.0
_RATE_LIMIT = 5
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(key, []) if now - t < _RATE_WINDOW_S]
        if len(hits) >= _RATE_LIMIT:
            _rate_hits[key] = hits
            return True
        hits.append(now)
        _rate_hits[key] = hits
        return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------------------
# newsletter
# ---------------------------------------------------------------------------------------
class NewsletterIn(BaseModel):
    email: str
    source: str | None = Field(default=None, max_length=80)


def make_unsubscribe_token(email: str) -> str:
    return _unsub_serializer.dumps(email)


def read_unsubscribe_token(token: str) -> str | None:
    try:
        return _unsub_serializer.loads(token)
    except BadSignature:
        return None


def _send_welcome_email(email: str) -> None:
    unsub_url = f"{SITE_URL}/api/newsletter/unsubscribe?token={make_unsubscribe_token(email)}"
    text = (
        f"Thanks for signing up to {APP_NAME}.\n\n"
        "We'll email you when the site launches and as we add more free, dyslexia-friendly "
        "classics.\n\n"
        f"Unsubscribe any time: {unsub_url}"
    )
    html = (
        f"<p style='font-family:sans-serif;font-size:16px;line-height:1.8'>Thanks for signing up "
        f"to {APP_NAME}.</p>"
        "<p style='font-family:sans-serif;font-size:16px;line-height:1.8'>We'll email you when the "
        "site launches and as we add more free, dyslexia-friendly classics.</p>"
        f"<p style='font-family:sans-serif;font-size:13px;color:#666'>"
        f"<a href='{unsub_url}'>Unsubscribe</a> any time.</p>"
    )
    auth.send_email(email, f"You're on the {APP_NAME} list", text, html)


@router.post("/newsletter")
def newsletter_signup(body: NewsletterIn, request: Request):
    if _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Too many requests. Try again in a minute.")
    email = auth.normalise_email(body.email)
    with db.conn() as c:
        c.execute(
            "INSERT INTO newsletter_signups (email, source) VALUES (%s, %s) "
            "ON CONFLICT (email) DO UPDATE SET "
            "  source = COALESCE(newsletter_signups.source, EXCLUDED.source), "
            "  unsubscribed_at = NULL",
            (email, body.source),
        )
        c.commit()
    if auth.RESEND_API_KEY:
        try:
            _send_welcome_email(email)
        except Exception as e:  # provider hiccup should never fail the signup itself
            print(f"[marketing] welcome email failed: {e}")
    return {"ok": True}


@router.get("/newsletter/unsubscribe")
def newsletter_unsubscribe(token: str):
    email = read_unsubscribe_token(token)
    if not email:
        raise HTTPException(400, "That unsubscribe link isn't valid.")
    with db.conn() as c:
        c.execute(
            "UPDATE newsletter_signups SET unsubscribed_at = now() WHERE email = %s",
            (email,),
        )
        c.commit()
    return {"ok": True, "email": email}


# ---------------------------------------------------------------------------------------
# page-view counter -- no cookies, no IP, referrer host only
# ---------------------------------------------------------------------------------------
class TrackIn(BaseModel):
    path: str = Field(max_length=300)


def referrer_host(request: Request) -> str:
    ref = request.headers.get("referer", "")
    try:
        host = urlparse(ref).hostname or ""
    except ValueError:
        host = ""
    return host[:255]


def record_page_view(path: str, ref_host: str) -> None:
    p = (path or "/").strip()[:300]
    if not p.startswith("/"):
        p = "/" + p
    with db.conn() as c:
        c.execute(
            "INSERT INTO page_views (day, path, referrer_host, count) VALUES (CURRENT_DATE, %s, %s, 1) "
            "ON CONFLICT (day, path, referrer_host) DO UPDATE SET count = page_views.count + 1",
            (p, ref_host or ""),
        )
        c.commit()


@router.post("/track")
def track(body: TrackIn, request: Request):
    record_page_view(body.path, referrer_host(request))
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# admin stats -- 404s outright when ADMIN_KEY isn't set, so the route is invisible by default
# ---------------------------------------------------------------------------------------
def _guarded_count(c, sql: str) -> int | None:
    """Run a COUNT(*) that may reference a table/column another migration hasn't added yet
    (e.g. billing's `users.plan`, the library's `books`). None means "not available", not zero."""
    try:
        return c.execute(sql).fetchone()["n"]
    except Exception:
        c.rollback()
        return None


def stats() -> dict:
    """The body of `GET /api/admin/stats`, pulled out so `server/feedback.py`'s
    `GET /api/admin/export` (v0.6) can fold the same numbers into its "pulse" bundle without
    another admin-key check or another HTTP round trip."""
    with db.conn() as c:
        signups = c.execute("SELECT COUNT(*) AS n FROM newsletter_signups").fetchone()["n"]
        views = c.execute(
            "SELECT path, SUM(count) AS n FROM page_views "
            "WHERE day >= CURRENT_DATE - INTERVAL '30 days' GROUP BY path ORDER BY n DESC"
        ).fetchall()
        users = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        pro_users = _guarded_count(c, "SELECT COUNT(*) AS n FROM users WHERE plan = 'pro'")
        books = _guarded_count(c, "SELECT COUNT(*) AS n FROM books")
    return {
        "signups": signups,
        "page_views_30d": [{"path": r["path"], "count": r["n"]} for r in views],
        "users": users,
        "pro_users": pro_users,
        "books": books,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/stats")
def admin_stats(key: str | None = None):
    admin_key = os.environ.get("ADMIN_KEY")
    if not admin_key or key != admin_key:
        raise HTTPException(404, "Not found.")
    return stats()

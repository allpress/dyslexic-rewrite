"""Email-code sign-in (the same flow as Chowder) and a signed session cookie.

- A 6-digit code is emailed through Resend. With no RESEND_API_KEY the code is returned to the
  client as `dev_code` so local development works without email.
- Codes are stored hashed and expire after 10 minutes; five wrong tries burn the code.
- The session is an itsdangerous-signed cookie holding the user id; no server-side session table.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import db

SECRET = os.environ.get("SESSION_SECRET") or ("dev-secret-" + hashlib.sha256(b"dysrewrite").hexdigest()[:16])
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("LOGIN_FROM_EMAIL", "login@unwindwords.com")
APP_NAME = os.environ.get("APP_NAME", "Unwind Words")
# While the sending domain is still being verified, showing the code on screen keeps the site usable.
DEV_CODE_FALLBACK = os.environ.get("DEV_CODE_FALLBACK", "0") == "1"
CODE_TTL = timedelta(minutes=10)
SESSION_MAX_AGE = 60 * 60 * 24 * 90  # 90 days
COOKIE = "session"

_serializer = URLSafeTimedSerializer(SECRET, salt="session")


def _hash(email: str, code: str) -> str:
    return hmac.new(SECRET.encode(), f"{email.lower()}:{code}".encode(), hashlib.sha256).hexdigest()


def normalise_email(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e or "." not in e.split("@")[-1] or len(e) > 254:
        raise ValueError("That doesn't look like an email address.")
    return e


def request_code(email: str) -> str | None:
    """Create and send a code. Returns the code only when email isn't configured (dev)."""
    email = normalise_email(email)
    code = f"{secrets.randbelow(1_000_000):06d}"
    with db.conn() as c:
        c.execute("UPDATE login_codes SET used = TRUE WHERE email = %s AND used = FALSE", (email,))
        c.execute(
            "INSERT INTO login_codes (email, code_hash, expires_at) VALUES (%s, %s, %s)",
            (email, _hash(email, code), datetime.now(timezone.utc) + CODE_TTL),
        )
        c.commit()
    if not RESEND_API_KEY:
        return code
    try:
        _send_email(email, code)
    except Exception as e:  # provider down, domain not verified yet, bad key ...
        print(f"[auth] email send failed: {e}")
        if DEV_CODE_FALLBACK:
            return code
        raise ValueError("We couldn't send the email just now. Please try again in a minute.") from e
    return None


def _send_email(email: str, code: str) -> None:
    body = (
        f"Your {APP_NAME} sign-in code is:\n\n    {code}\n\n"
        f"It works for 10 minutes. If you didn't ask for it, ignore this email."
    )
    html = (
        f"<p style='font-family:sans-serif;font-size:18px;line-height:1.8'>Your {APP_NAME} sign-in code is</p>"
        f"<p style='font-family:monospace;font-size:36px;letter-spacing:0.2em'>{code}</p>"
        f"<p style='font-family:sans-serif;font-size:16px;line-height:1.8'>It works for 10 minutes. "
        f"If you didn't ask for it, ignore this email.</p>"
    )
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": f"{APP_NAME} <{FROM_EMAIL}>", "to": [email], "subject": f"{code} is your {APP_NAME} code",
              "text": body, "html": html},
        timeout=15,
    )
    r.raise_for_status()


def verify_code(email: str, code: str) -> int:
    """Return the user id (creating the user on first sign-in) or raise ValueError."""
    email = normalise_email(email)
    code = (code or "").strip().replace(" ", "")
    now = datetime.now(timezone.utc)
    with db.conn() as c:
        row = c.execute(
            "SELECT id, code_hash, expires_at FROM login_codes WHERE email = %s AND used = FALSE "
            "ORDER BY created_at DESC LIMIT 1", (email,),
        ).fetchone()
        if not row or row["expires_at"] < now:
            raise ValueError("That code has expired. Ask for a new one.")
        if not hmac.compare_digest(row["code_hash"], _hash(email, code)):
            raise ValueError("That code isn't right. Check the email and try again.")
        c.execute("UPDATE login_codes SET used = TRUE WHERE id = %s", (row["id"],))
        user = c.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if user is None:
            user = c.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (email,)).fetchone()
        c.commit()
        return int(user["id"])


def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session(token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None

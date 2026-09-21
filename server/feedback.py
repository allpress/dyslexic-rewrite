"""User feedback (v0.6): a small inbox a Claude skill rolls up weekly into work.

- `POST /api/feedback/submit` -- the floating feedback widget and the inline post-test/post-
  conversion prompt both post here. Anonymous submissions are allowed; a signed-in caller's
  `user_id` is attached automatically. Rate-limited in-process to 10 requests per hour per client
  IP (the same in-process-only spirit as `server/marketing.py`'s newsletter limiter).
- `GET /api/feedback/mine` -- a signed-in reader's own submissions, for Profile's "Your feedback".
- `GET/PATCH /api/admin/feedback*` and `GET /api/admin/export` -- admin-only, gated on `ADMIN_KEY`
  exactly like `server/marketing.py`'s `/api/admin/stats` (404s outright when unset). The `md`
  format of the list endpoint is the markdown digest the weekly skill reads; `/admin/export` is
  the broader "pulse" bundle (feedback + marketing stats + battery/A-B aggregates) it starts from.

See server/API.md, "Feedback (v0.6)", and server/migrations/010_feedback.sql for the schema.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import auth, db, marketing

router = APIRouter(prefix="/api")

FeedbackKind = Literal["bug", "idea", "praise", "question"]
FeedbackStatus = Literal["new", "triaged", "planned", "done", "wontfix"]

# ---------------------------------------------------------------------------------------
# auth helpers -- standalone (not imported from server.app) so this module has no import
# cycle with it; server/app.py imports *this* module, not the other way around.
# ---------------------------------------------------------------------------------------
def _optional_user(request: Request) -> dict | None:
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    if not uid:
        return None
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()


def _current_user(request: Request) -> dict:
    u = _optional_user(request)
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def _require_admin(key: str | None) -> None:
    admin_key = os.environ.get("ADMIN_KEY")
    if not admin_key or key != admin_key:
        raise HTTPException(404, "Not found.")


# ---------------------------------------------------------------------------------------
# in-process rate limit: 10 submissions per hour per client IP. Same caveat as marketing.py's
# newsletter limiter -- not shared across workers/instances, good enough to stop a single script.
# ---------------------------------------------------------------------------------------
_RATE_WINDOW_S = 3600.0
_RATE_LIMIT = 10
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
# models
# ---------------------------------------------------------------------------------------
class FeedbackSubmitIn(BaseModel):
    kind: FeedbackKind
    message: str = Field(min_length=1, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    page: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackAdminPatch(BaseModel):
    status: FeedbackStatus | None = None
    tags: list[str] | None = None
    admin_note: str | None = Field(default=None, max_length=4000)


def _row_json(r: dict) -> dict:
    return {
        "id": r["id"], "user_id": r["user_id"], "email": r["email"], "kind": r["kind"],
        "message": r["message"], "rating": r["rating"], "page": r["page"], "context": r["context"] or {},
        "status": r["status"], "tags": r["tags"] or [], "admin_note": r["admin_note"],
        "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
    }


def _mine_json(r: dict) -> dict:
    return {
        "id": r["id"], "kind": r["kind"], "message": r["message"], "rating": r["rating"],
        "page": r["page"], "status": r["status"], "created_at": r["created_at"].isoformat(),
    }


def _notify(row: dict) -> None:
    """Best-effort one-line email to FEEDBACK_NOTIFY_EMAIL, only when both that and
    RESEND_API_KEY are set. Never raises -- a notification failure must not fail the submit."""
    notify_to = os.environ.get("FEEDBACK_NOTIFY_EMAIL")
    if not auth.RESEND_API_KEY or not notify_to:
        return
    try:
        summary = row["message"].strip().replace("\n", " ")[:200]
        text = f"New {row['kind']} feedback on {row['page'] or '(no page)'}:\n\n{summary}"
        html = f"<p style='font-family:sans-serif;font-size:15px'>New <b>{row['kind']}</b> feedback on {row['page'] or '(no page)'}:</p><p style='font-family:sans-serif;font-size:15px'>{summary}</p>"
        auth.send_email(notify_to, f"[feedback] {row['kind']} #{row['id']}", text, html)
    except Exception as e:  # provider hiccup should never fail the submission itself
        print(f"[feedback] notify email failed: {e}")


# ---------------------------------------------------------------------------------------
# submit / mine
# ---------------------------------------------------------------------------------------
@router.post("/feedback/submit", status_code=201)
def submit_feedback(body: FeedbackSubmitIn, request: Request, u: dict | None = Depends(_optional_user)):
    if _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Too many requests. Try again in a bit.")
    email = None
    if not u and body.email and body.email.strip():
        try:
            email = auth.normalise_email(body.email)
        except ValueError:
            raise HTTPException(400, "That doesn't look like an email address.")
    context = body.context if isinstance(body.context, dict) else {}
    if len(json.dumps(context)) > 4000:
        raise HTTPException(400, "That's too much context to send.")
    with db.conn() as c:
        row = c.execute(
            "INSERT INTO feedback (user_id, email, kind, message, rating, page, context) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING *",
            (u["id"] if u else None, email, body.kind, body.message.strip(), body.rating,
             body.page, json.dumps(context)),
        ).fetchone()
        c.commit()
    _notify(row)
    return {"id": row["id"]}


@router.get("/feedback/mine")
def my_feedback(u: dict = Depends(_current_user)):
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM feedback WHERE user_id = %s ORDER BY created_at DESC", (u["id"],),
        ).fetchall()
    return [_mine_json(r) for r in rows]


# ---------------------------------------------------------------------------------------
# reader-marked-a-word-as-tripping-them-up (from the read-anything view). Called from
# server/app.py's existing `POST /api/feedback` handler, which stays where it is (it manages
# ProfileSummary trigger words, not this table) -- this just also files a `kind='tripped'` row
# so those reports show up in the weekly digest alongside the widget's bug/idea/praise/question.
# ---------------------------------------------------------------------------------------
def record_tripped(u: dict, tripped: list[str], safe: list[str]) -> None:
    if not tripped and not safe:
        return
    if tripped:
        message = f"Marked {len(tripped)} word(s) as tripping them up: {', '.join(tripped[:20])}"
    else:
        message = f"Marked {len(safe)} word(s) as fine after all."
    context = {"tripped": tripped[:50], "safe": safe[:50]}
    with db.conn() as c:
        c.execute(
            "INSERT INTO feedback (user_id, kind, message, page, context) "
            "VALUES (%s, 'tripped', %s, %s, %s::jsonb)",
            (u["id"], message[:4000], "/read", json.dumps(context)),
        )
        c.commit()


# ---------------------------------------------------------------------------------------
# admin -- all require ?key=ADMIN_KEY, 404 outright when ADMIN_KEY isn't set (see
# server/marketing.py's admin_stats for the same pattern).
# ---------------------------------------------------------------------------------------
def _context_summary(ctx: dict) -> str:
    if not ctx:
        return ""
    parts = [f"{k}={v}" for k, v in ctx.items() if k != "user_agent" and v not in (None, "", [])]
    return ", ".join(parts)[:240]


def _digest_markdown(rows: list[dict]) -> str:
    by_kind: dict[str, list[dict]] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    lines = [f"# Feedback digest ({len(rows)} item{'s' if len(rows) != 1 else ''})", ""]
    for kind in ("bug", "idea", "question", "tripped", "praise"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines.append(f"## {kind.capitalize()} ({len(items)})")
        lines.append("")
        for r in items:  # already newest-first from the query below
            ctx = r["context"] or {}
            plan = ctx.get("plan", "unknown")
            lines.append(
                f"- **#{r['id']}** {r['created_at'].isoformat()} · plan={plan} · "
                f"page={r['page'] or '-'}" + (f" · rating={r['rating']}/5" if r["rating"] else ""),
            )
            lines.append(f"  {r['message'].strip()}")
            summary = _context_summary(ctx)
            if summary:
                lines.append(f"  _context: {summary}_")
            lines.append("")
    return "\n".join(lines)


@router.get("/admin/feedback")
def admin_list_feedback(
    key: str | None = None,
    since: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    format: str = "json",  # noqa: A002 -- matches the query param name in server/API.md
):
    _require_admin(key)
    clauses: list[str] = []
    params: list[Any] = []
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "since must be an ISO-8601 date/time.")
        clauses.append("created_at >= %s")
        params.append(since_dt)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if kind:
        clauses.append("kind = %s")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.conn() as c:
        rows = c.execute(f"SELECT * FROM feedback {where} ORDER BY created_at DESC", params).fetchall()
    if format == "md":
        return Response(content=_digest_markdown(rows), media_type="text/markdown; charset=utf-8")
    return [_row_json(r) for r in rows]


@router.patch("/admin/feedback/{feedback_id}")
def admin_patch_feedback(feedback_id: int, body: FeedbackAdminPatch, key: str | None = None):
    _require_admin(key)
    with db.conn() as c:
        row = c.execute(
            "UPDATE feedback SET status = COALESCE(%s, status), tags = COALESCE(%s, tags), "
            "admin_note = COALESCE(%s, admin_note), updated_at = now() WHERE id = %s RETURNING *",
            (body.status, body.tags, body.admin_note, feedback_id),
        ).fetchone()
        c.commit()
    if not row:
        raise HTTPException(404, "No such feedback.")
    return _row_json(row)


@router.get("/admin/feedback/summary")
def admin_feedback_summary(key: str | None = None):
    _require_admin(key)
    now = datetime.now(timezone.utc)

    def _window(c, days: int) -> dict:
        since = now - timedelta(days=days)
        by_kind = c.execute(
            "SELECT kind, COUNT(*) AS n FROM feedback WHERE created_at >= %s GROUP BY kind", (since,),
        ).fetchall()
        by_status = c.execute(
            "SELECT status, COUNT(*) AS n FROM feedback WHERE created_at >= %s GROUP BY status", (since,),
        ).fetchall()
        avg_rating = c.execute(
            "SELECT AVG(rating) AS avg FROM feedback WHERE created_at >= %s AND rating IS NOT NULL", (since,),
        ).fetchone()["avg"]
        count = c.execute(
            "SELECT COUNT(*) AS n FROM feedback WHERE created_at >= %s", (since,),
        ).fetchone()["n"]
        return {
            "count": count,
            "by_kind": {r["kind"]: r["n"] for r in by_kind},
            "by_status": {r["status"]: r["n"] for r in by_status},
            "avg_rating": round(float(avg_rating), 2) if avg_rating is not None else None,
        }

    with db.conn() as c:
        last_7d = _window(c, 7)
        last_30d = _window(c, 30)
        top_pages = c.execute(
            "SELECT page, COUNT(*) AS n FROM feedback WHERE created_at >= %s AND page IS NOT NULL "
            "GROUP BY page ORDER BY n DESC LIMIT 10",
            (now - timedelta(days=30),),
        ).fetchall()
    return {
        "last_7d": last_7d,
        "last_30d": last_30d,
        "top_pages": [{"page": r["page"], "count": r["n"]} for r in top_pages],
        "generated_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------------------
# admin export -- the weekly skill's starting "pulse": feedback + marketing stats + anonymous
# battery/A-B aggregates. No per-user data anywhere in the bundle.
# ---------------------------------------------------------------------------------------
@router.get("/admin/export")
def admin_export(key: str | None = None):
    _require_admin(key)
    since = datetime.now(timezone.utc) - timedelta(days=90)
    with db.conn() as c:
        feedback_rows = c.execute(
            "SELECT * FROM feedback WHERE created_at >= %s ORDER BY created_at DESC", (since,),
        ).fetchall()
        battery_runs = c.execute(
            "SELECT scores FROM battery_runs WHERE finished_at IS NOT NULL AND scores IS NOT NULL",
        ).fetchall()
        ab_rows = c.execute(
            "SELECT condition, AVG(wpm) AS avg_wpm, COUNT(*) AS n FROM test_items "
            "WHERE recorded_at IS NOT NULL AND total > 0 GROUP BY condition",
        ).fetchall()

    axis_supports: dict[str, list[float]] = {}
    for r in battery_runs:
        for axis in (r["scores"] or {}).get("axes", []):
            axis_supports.setdefault(axis["id"], []).append(axis["support"])
    ab_aggregate = {
        r["condition"]: {"mean_wpm": round(r["avg_wpm"], 1) if r["avg_wpm"] is not None else None, "n": r["n"]}
        for r in ab_rows
    }
    return {
        "feedback": [_row_json(r) for r in feedback_rows],
        "stats": marketing.stats(),
        "battery": {
            "runs": len(battery_runs),
            "mean_support_by_axis": {k: round(sum(v) / len(v), 1) for k, v in axis_supports.items()},
        },
        "ab_test": ab_aggregate,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

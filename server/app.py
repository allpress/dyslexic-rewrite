"""FastAPI app: the JSON API from server/API.md plus the built React app from web/dist."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dyslexic_rewrite import __version__
from dyslexic_rewrite.profile import BUILTIN_PROFILES

from . import auth, db, passages, prompts, service, storage

app = FastAPI(title="Unwind Words", version=__version__, docs_url=None, redoc_url=None)
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "1") == "1"
WEB_DIST = Path(os.environ.get("WEB_DIST", Path(__file__).resolve().parent.parent / "web" / "dist"))


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _lifespan(_: FastAPI):
    applied = db.migrate()
    with db.conn() as c:
        passages.seed(c)
    if applied:
        print("migrations applied:", ", ".join(applied))
    yield
    db.close()


app.router.lifespan_context = _lifespan


@app.exception_handler(HTTPException)
async def _http_exc(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(ValueError)
async def _value_exc(_: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)


# ---------------------------------------------------------------------------------------
# auth helpers
# ---------------------------------------------------------------------------------------
def _user_row(user_id: int) -> dict | None:
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def _user_json(u: dict) -> dict:
    with db.conn() as c:
        has = c.execute("SELECT 1 FROM profiles WHERE user_id = %s", (u["id"],)).fetchone() is not None
    return {"id": u["id"], "email": u["email"], "name": u["name"], "base_profile": u["base_profile"],
            "onboarded": u["onboarded"], "has_personal_profile": has, "phonetic_map": u["phonetic_map"],
            "created_at": u["created_at"].isoformat()}


def current_user(request: Request) -> dict:
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    u = _user_row(uid) if uid else None
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def optional_user(request: Request) -> dict | None:
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    return _user_row(uid) if uid else None


# ---------------------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------------------
class EmailIn(BaseModel):
    email: str


class VerifyIn(BaseModel):
    email: str
    code: str


class MePatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    base_profile: str | None = None
    onboarded: bool | None = None
    phonetic_map: str | None = None


class TextIn(BaseModel):
    text: str = Field(max_length=60_000)


class TriggersIn(BaseModel):
    add: list[str] = []
    remove: list[str] = []
    safe: list[str] = []


class TestIn(BaseModel):
    pair: str | None = None


class FinishIn(BaseModel):
    seconds: float = Field(gt=0, lt=7200)
    answers: dict[str, int] = {}
    tripped: list[str] = []
    ease: int = Field(ge=1, le=5)
    read_aloud: bool = False


class FeedbackIn(BaseModel):
    tripped: list[str] = []
    safe: list[str] = []


# ---------------------------------------------------------------------------------------
# health / auth
# ---------------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.post("/api/auth/request-code")
def request_code(body: EmailIn):
    code = auth.request_code(body.email)
    out: dict[str, Any] = {"ok": True}
    if code:
        out["dev_code"] = code
    return out


@app.post("/api/auth/verify")
def verify(body: VerifyIn, response: Response):
    uid = auth.verify_code(body.email, body.code)
    response.set_cookie(auth.COOKIE, auth.make_session(uid), max_age=auth.SESSION_MAX_AGE, httponly=True,
                        samesite="lax", secure=SECURE_COOKIES, path="/")
    return {"user": _user_json(_user_row(uid))}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# me
# ---------------------------------------------------------------------------------------
@app.get("/api/me")
def me(u: dict = Depends(current_user)):
    p, _ = service.get_profile(u["id"], u["base_profile"])
    with db.conn() as c:
        has = c.execute("SELECT 1 FROM profiles WHERE user_id = %s", (u["id"],)).fetchone() is not None
    return {"user": _user_json(u), "profile": service.profile_summary(p, u["base_profile"]) if has else None}


@app.patch("/api/me")
def patch_me(body: MePatch, u: dict = Depends(current_user)):
    if body.base_profile is not None and body.base_profile not in BUILTIN_PROFILES:
        raise HTTPException(400, f"base_profile must be one of {list(BUILTIN_PROFILES)}")
    if body.phonetic_map is not None and body.phonetic_map not in service.PHONETIC_MAP_MODES:
        raise HTTPException(400, f"phonetic_map must be one of {list(service.PHONETIC_MAP_MODES)}")
    with db.conn() as c:
        c.execute(
            "UPDATE users SET name = COALESCE(%s, name), base_profile = COALESCE(%s, base_profile), "
            "onboarded = COALESCE(%s, onboarded), phonetic_map = COALESCE(%s, phonetic_map) WHERE id = %s",
            (body.name.strip() if body.name else None, body.base_profile, body.onboarded,
             body.phonetic_map, u["id"]),
        )
        c.commit()
    if body.base_profile and body.base_profile != u["base_profile"]:
        with db.conn() as c:
            if c.execute("SELECT 1 FROM profiles WHERE user_id = %s", (u["id"],)).fetchone():
                service.rebase_profile(u["id"], body.base_profile)
    return {"user": _user_json(_user_row(u["id"]))}


@app.post("/api/me/writing-sample")
def writing_sample(body: TextIn, u: dict = Depends(current_user)):
    if len(body.text.split()) < 150:
        raise HTTPException(400, "Paste at least 150 words so the measurements are stable.")
    profile, style = service.learn_from_text(u["id"], body.text, u["base_profile"], u["name"] or "personal")
    return {"style": style, "profile": service.profile_summary(profile, u["base_profile"])}


@app.post("/api/me/triggers")
def me_triggers(body: TriggersIn, u: dict = Depends(current_user)):
    p = service.update_triggers(u["id"], u["base_profile"], body.add, body.remove, body.safe)
    return {"profile": service.profile_summary(p, u["base_profile"])}


@app.delete("/api/me")
def delete_me(response: Response, u: dict = Depends(current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM users WHERE id = %s", (u["id"],))  # cascades to profile, tests, items, recordings
        c.execute("DELETE FROM login_codes WHERE email = %s", (u["email"],))
        c.commit()
    storage.delete_user(u["id"])
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# passages & tests
# ---------------------------------------------------------------------------------------
@app.get("/api/passages")
def list_passages():
    with db.conn() as c:
        rows = c.execute("SELECT id, slug, title, words, level, pair FROM passages ORDER BY pair, id").fetchall()
    return rows


def _questions_public(qs: list[dict]) -> list[dict]:
    return [{"id": q["id"], "prompt": q["prompt"], "options": q["options"]} for q in qs]


def _build_item(passage: dict, condition: str, profile) -> tuple[list[dict], int]:
    if condition == "rewritten":
        segs, _ = service.rewrite_text(passage["body"], profile)
    else:
        segs = service.original_segments(passage["body"])
    return segs, service.word_count(segs)


def _test_json(test_id: int, u: dict) -> dict:
    with db.conn() as c:
        t = c.execute("SELECT * FROM tests WHERE id = %s AND user_id = %s", (test_id, u["id"])).fetchone()
        if not t:
            raise HTTPException(404, "No such test.")
        items = c.execute(
            "SELECT ti.*, p.title, p.body, p.questions FROM test_items ti JOIN passages p ON p.id = ti.passage_id "
            "WHERE ti.test_id = %s ORDER BY ti.idx", (test_id,),
        ).fetchall()
    profile, _ = service.get_profile(u["id"], u["base_profile"])
    out_items = []
    for it in items:
        segs, _ = _build_item(it, it["condition"], profile)
        phonetic_map = service.compute_phonetic_map(segs, profile, u["phonetic_map"])
        result = None
        if it["recorded_at"]:
            result = {"seconds": it["seconds"], "wpm": it["wpm"], "correct": it["correct"], "total": it["total"],
                      "ease": it["ease"], "tripped": it["tripped"] or [], "recorded_at": it["recorded_at"].isoformat(),
                      "phonetic_map": it["phonetic_map"], "read_aloud": it["read_aloud"]}
        out_items.append({
            "index": it["idx"], "passage_id": it["passage_id"], "title": it["title"], "condition": it["condition"],
            "words": it["words"], "segments": segs, "phonetic_map": phonetic_map,
            "questions": _questions_public(it["questions"]), "result": result,
        })
    return {"id": t["id"], "pair": t["pair"], "created_at": t["created_at"].isoformat(),
            "completed": all(i["result"] for i in out_items), "items": out_items}


@app.post("/api/tests")
def create_test(body: TestIn, u: dict = Depends(current_user)):
    with db.conn() as c:
        pairs = [r["pair"] for r in c.execute("SELECT DISTINCT pair FROM passages ORDER BY pair").fetchall()]
        used = [r["pair"] for r in c.execute(
            "SELECT pair FROM tests WHERE user_id = %s ORDER BY created_at", (u["id"],)).fetchall()]
    if not pairs:
        raise HTTPException(500, "No passages are loaded.")
    pair = body.pair
    if pair is None:
        unused = [p for p in pairs if p not in used]
        pair = unused[0] if unused else pairs[len(used) % len(pairs)]
    elif pair not in pairs:
        raise HTTPException(400, "Unknown passage pair.")
    with db.conn() as c:
        ps = c.execute("SELECT * FROM passages WHERE pair = %s ORDER BY id", (pair,)).fetchall()
    if len(ps) < 2:
        raise HTTPException(500, "That pair is incomplete.")
    ps = ps[:2]
    random.shuffle(ps)
    rewritten_idx = random.randrange(2)
    profile, _ = service.get_profile(u["id"], u["base_profile"])
    with db.conn() as c:
        t = c.execute("INSERT INTO tests (user_id, pair, profile_name) VALUES (%s, %s, %s) RETURNING id",
                      (u["id"], pair, profile.name)).fetchone()
        for i, p in enumerate(ps):
            cond = "rewritten" if i == rewritten_idx else "original"
            _, words = _build_item(p, cond, profile)
            c.execute("INSERT INTO test_items (test_id, idx, passage_id, condition, words) VALUES (%s,%s,%s,%s,%s)",
                      (t["id"], i, p["id"], cond, words))
        c.commit()
    return _test_json(t["id"], u)


@app.get("/api/tests/{test_id}")
def get_test(test_id: int, u: dict = Depends(current_user)):
    return _test_json(test_id, u)


@app.post("/api/tests/{test_id}/items/{index}/start")
def start_item(test_id: int, index: int, u: dict = Depends(current_user)):
    now = datetime.now(timezone.utc)
    with db.conn() as c:
        r = c.execute(
            "UPDATE test_items ti SET started_at = COALESCE(ti.started_at, %s) FROM tests t "
            "WHERE ti.test_id = t.id AND t.user_id = %s AND ti.test_id = %s AND ti.idx = %s RETURNING ti.started_at",
            (now, u["id"], test_id, index),
        ).fetchone()
        c.commit()
    if not r:
        raise HTTPException(404, "No such test item.")
    return {"started_at": r["started_at"].isoformat()}


@app.post("/api/tests/{test_id}/items/{index}/finish")
def finish_item(test_id: int, index: int, body: FinishIn, u: dict = Depends(current_user)):
    with db.conn() as c:
        it = c.execute(
            "SELECT ti.*, p.questions FROM test_items ti JOIN tests t ON t.id = ti.test_id "
            "JOIN passages p ON p.id = ti.passage_id WHERE t.user_id = %s AND ti.test_id = %s AND ti.idx = %s",
            (u["id"], test_id, index),
        ).fetchone()
        if not it:
            raise HTTPException(404, "No such test item.")
        if it["recorded_at"]:
            raise HTTPException(409, "This passage was already recorded.")
        qs = it["questions"]
        correct = sum(1 for q in qs if body.answers.get(q["id"]) == q["answer"])
        wpm = round(it["words"] / (body.seconds / 60.0), 1)
        if wpm > 1200:
            raise HTTPException(400, "That was too quick to be a real read — it looks like the timer ran "
                                     "before you started. Take the passage again.")
        tripped = sorted({w.strip().lower() for w in body.tripped if w.strip()})[:200]
        now = datetime.now(timezone.utc)
        c.execute(
            "UPDATE test_items SET seconds=%s, wpm=%s, correct=%s, total=%s, ease=%s, tripped=%s, answers=%s, "
            "recorded_at=%s, phonetic_map=%s, read_aloud=%s WHERE test_id=%s AND idx=%s",
            (body.seconds, wpm, correct, len(qs), body.ease, json.dumps(tripped), json.dumps(body.answers), now,
             u["phonetic_map"], body.read_aloud, test_id, index),
        )
        c.commit()
    return {"seconds": body.seconds, "wpm": wpm, "correct": correct, "total": len(qs), "ease": body.ease,
            "tripped": tripped, "recorded_at": now.isoformat(), "phonetic_map": u["phonetic_map"],
            "read_aloud": body.read_aloud}


@app.get("/api/results")
def results(u: dict = Depends(current_user)):
    with db.conn() as c:
        tests = c.execute("SELECT * FROM tests WHERE user_id = %s ORDER BY created_at DESC", (u["id"],)).fetchall()
        items = c.execute(
            "SELECT ti.*, p.title FROM test_items ti JOIN tests t ON t.id = ti.test_id JOIN passages p ON p.id = ti.passage_id "
            "WHERE t.user_id = %s ORDER BY ti.test_id, ti.idx", (u["id"],),
        ).fetchall()
    by_test: dict[int, list] = {}
    for it in items:
        by_test.setdefault(it["test_id"], []).append(it)
    totals = {k: {"wpm": 0.0, "comprehension": 0.0, "n": 0} for k in ("original", "rewritten")}
    acc = {k: {"wpm": [], "comp": []} for k in totals}
    out_tests = []
    for t in tests:
        its = by_test.get(t["id"], [])
        out_tests.append({
            "id": t["id"], "pair": t["pair"], "created_at": t["created_at"].isoformat(),
            "completed": bool(its) and all(i["recorded_at"] for i in its),
            "items": [{"condition": i["condition"], "title": i["title"], "wpm": i["wpm"], "correct": i["correct"],
                       "total": i["total"], "ease": i["ease"]} for i in its],
        })
        for i in its:
            if i["recorded_at"] and i["total"]:
                acc[i["condition"]]["wpm"].append(i["wpm"])
                acc[i["condition"]]["comp"].append(i["correct"] / i["total"])
    for k in totals:
        n = len(acc[k]["wpm"])
        totals[k] = {"n": n, "wpm": round(sum(acc[k]["wpm"]) / n, 1) if n else 0.0,
                     "comprehension": round(100 * sum(acc[k]["comp"]) / n, 1) if n else 0.0}
    return {"tests": out_tests, "totals": totals}


# ---------------------------------------------------------------------------------------
# read anything
# ---------------------------------------------------------------------------------------
@app.post("/api/rewrite")
def rewrite_any(body: TextIn, u: dict | None = Depends(optional_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Paste some text first.")
    if len(text) > 20_000:
        raise HTTPException(400, "That's a lot at once — try up to 20,000 characters.")
    profile, _ = service.get_profile(u["id"], u["base_profile"]) if u else (service.load_profile("default"), None)
    segs, stats = service.rewrite_text(text, profile)
    mode = u["phonetic_map"] if u else "on_demand"
    phonetic_map = service.compute_phonetic_map(segs, profile, mode)
    return {"segments": segs, "stats": stats, "phonetic_map": phonetic_map}


@app.post("/api/feedback")
def feedback(body: FeedbackIn, u: dict = Depends(current_user)):
    p = service.update_triggers(u["id"], u["base_profile"], add=body.tripped, safe=body.safe)
    return {"profile": service.profile_summary(p, u["base_profile"])}


# ---------------------------------------------------------------------------------------
# voice recordings (the site stores audio only; an offline pipeline analyses it)
# ---------------------------------------------------------------------------------------
RECORDING_KINDS = {"read_aloud", "free_speech"}
MAX_RECORDING_BYTES = 25 * 1024 * 1024
MAX_RECORDING_SECONDS = 15 * 60
MAX_RECORDINGS_PER_USER = 50
MIME_EXTENSIONS = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3",
    "audio/wav": "wav", "audio/x-m4a": "m4a", "audio/aac": "aac", "audio/flac": "flac",
}


def _recording_json(r: dict) -> dict:
    prompt = prompts.PROMPTS_BY_ID.get(r["prompt_id"]) if r["prompt_id"] else None
    return {"id": r["id"], "created_at": r["created_at"].isoformat(), "kind": r["kind"],
            "prompt_id": r["prompt_id"], "prompt_title": prompt["title"] if prompt else None,
            "seconds": r["seconds"], "bytes": r["bytes"], "mime": r["mime"], "status": r["status"],
            "note": r["note"]}


@app.get("/api/read-aloud-prompts")
def read_aloud_prompts():
    return prompts.all_prompts()


@app.post("/api/me/recordings", status_code=201)
def create_recording(
    file: UploadFile = File(...),
    kind: str = Form(...),
    prompt_id: str | None = Form(default=None),
    seconds: float | None = Form(default=None),
    u: dict = Depends(current_user),
):
    if kind not in RECORDING_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(RECORDING_KINDS)}.")
    if prompt_id and prompt_id not in prompts.PROMPTS_BY_ID:
        raise HTTPException(400, "That prompt doesn't exist.")
    ext = MIME_EXTENSIONS.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "That audio type isn't supported. Try recording again.")
    if seconds is not None and seconds > MAX_RECORDING_SECONDS:
        raise HTTPException(400, "Recordings can be at most 15 minutes.")
    data = file.file.read()
    if len(data) > MAX_RECORDING_BYTES:
        raise HTTPException(400, "Recordings can be at most 25 MB.")
    if not data:
        raise HTTPException(400, "That recording came through empty. Try again.")
    with db.conn() as c:
        count = c.execute("SELECT COUNT(*) AS n FROM recordings WHERE user_id = %s", (u["id"],)).fetchone()["n"]
        if count >= MAX_RECORDINGS_PER_USER:
            raise HTTPException(400, "You've reached the limit of 50 recordings. Delete one to add another.")
        key = storage.save(u["id"], data, ext)
        row = c.execute(
            "INSERT INTO recordings (user_id, kind, prompt_id, seconds, bytes, mime, storage_key) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (u["id"], kind, prompt_id, seconds, len(data), file.content_type, key),
        ).fetchone()
        c.commit()
    return _recording_json(row)


@app.get("/api/me/recordings")
def list_recordings(u: dict = Depends(current_user)):
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM recordings WHERE user_id = %s ORDER BY created_at DESC", (u["id"],),
        ).fetchall()
    totals = {"count": len(rows), "seconds": sum(r["seconds"] or 0 for r in rows), "bytes": sum(r["bytes"] for r in rows)}
    return {"recordings": [_recording_json(r) for r in rows], "totals": totals}


@app.get("/api/me/recordings/{recording_id}/audio")
def recording_audio(recording_id: int, u: dict = Depends(current_user)):
    with db.conn() as c:
        r = c.execute(
            "SELECT * FROM recordings WHERE id = %s AND user_id = %s", (recording_id, u["id"]),
        ).fetchone()
    if not r:
        raise HTTPException(404, "No such recording.")
    try:
        with storage.open_file(r["storage_key"]) as f:
            data = f.read()
    except (ValueError, FileNotFoundError, OSError):
        raise HTTPException(404, "No such recording.")
    return Response(content=data, media_type=r["mime"], headers={"Content-Disposition": "inline"})


@app.delete("/api/me/recordings/{recording_id}")
def delete_recording(recording_id: int, u: dict = Depends(current_user)):
    with db.conn() as c:
        r = c.execute(
            "DELETE FROM recordings WHERE id = %s AND user_id = %s RETURNING storage_key", (recording_id, u["id"]),
        ).fetchone()
        c.commit()
    if not r:
        raise HTTPException(404, "No such recording.")
    storage.delete(r["storage_key"])
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# static front end (client-side routing: unknown paths fall back to index.html)
# ---------------------------------------------------------------------------------------
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = WEB_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")

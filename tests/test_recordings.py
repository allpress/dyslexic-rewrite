"""Voice recording API tests. Need a Postgres at DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise."""

import io
import os
import shutil
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite"))
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)
_AUDIO_TMP = tempfile.mkdtemp(prefix="dysrewrite-recordings-test-")
os.environ["AUDIO_DIR"] = _AUDIO_TMP

try:
    import psycopg
    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    shutil.rmtree(_AUDIO_TMP, ignore_errors=True)
    pytest.skip(f"no Postgres for API tests: {e}", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from server import storage  # noqa: E402
from server.app import app  # noqa: E402

EMAIL = "pytest-recordings@example.com"
EMAIL_OTHER = "pytest-recordings-other@example.com"


def _sign_in(client, email):
    r = client.post("/api/auth/request-code", json={"email": email}).json()
    assert r["ok"] and "dev_code" in r
    ok = client.post("/api/auth/verify", json={"email": email, "code": r["dev_code"]})
    assert ok.status_code == 200
    return client


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
        c.delete("/api/me")


@pytest.fixture(scope="module")
def signed_in(client):
    return _sign_in(client, EMAIL)


@pytest.fixture(scope="module", autouse=True)
def _cleanup_audio_dir():
    yield
    shutil.rmtree(_AUDIO_TMP, ignore_errors=True)


def _wav_bytes(n: int = 2000) -> bytes:
    # Not a real WAV file, but the endpoint only cares about the declared content type and size.
    return b"RIFF" + bytes(n)


def test_prompts_endpoint(client):
    prompts = client.get("/api/read-aloud-prompts").json()
    assert len(prompts) == 8
    for p in prompts:
        assert set(p) == {"id", "kind", "title", "text", "words"}
        assert p["kind"] in ("read_aloud", "free_speech")
    read_aloud = [p for p in prompts if p["kind"] == "read_aloud"]
    free_speech = [p for p in prompts if p["kind"] == "free_speech"]
    assert len(read_aloud) == 4 and len(free_speech) == 4
    for p in read_aloud:
        assert 60 <= p["words"] <= 110
    for p in free_speech:
        assert p["words"] == 0


def test_recordings_require_login(client):
    assert client.get("/api/me/recordings").status_code == 401
    r = client.post("/api/me/recordings", data={"kind": "free_speech"},
                     files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert r.status_code == 401


def test_upload_list_and_playback(signed_in):
    c = signed_in
    all_prompts = c.get("/api/read-aloud-prompts").json()
    read_aloud_id = next(p["id"] for p in all_prompts if p["kind"] == "read_aloud")
    data = _wav_bytes(4000)
    up = c.post("/api/me/recordings", data={"kind": "read_aloud", "prompt_id": read_aloud_id, "seconds": "12.5"},
                files={"file": ("sample.wav", data, "audio/wav")})
    assert up.status_code == 201
    rec = up.json()
    assert rec["status"] == "pending_analysis"
    assert rec["kind"] == "read_aloud"
    assert rec["prompt_id"] == read_aloud_id
    assert rec["prompt_title"]
    assert rec["bytes"] == len(data)
    assert rec["mime"] == "audio/wav"

    listed = c.get("/api/me/recordings").json()
    assert listed["totals"]["count"] >= 1
    assert any(r["id"] == rec["id"] for r in listed["recordings"])

    played = c.get(f"/api/me/recordings/{rec['id']}/audio")
    assert played.status_code == 200
    assert played.content == data
    assert played.headers["content-disposition"] == "inline"

    assert c.delete(f"/api/me/recordings/{rec['id']}").json()["ok"] is True
    assert c.get(f"/api/me/recordings/{rec['id']}/audio").status_code == 404


def test_rejected_content_type(signed_in):
    c = signed_in
    r = c.post("/api/me/recordings", data={"kind": "free_speech"},
               files={"file": ("clip.txt", b"not audio", "text/plain")})
    assert r.status_code == 400


def test_bad_kind_and_bad_prompt(signed_in):
    c = signed_in
    r = c.post("/api/me/recordings", data={"kind": "singing"},
               files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert r.status_code == 400
    r = c.post("/api/me/recordings", data={"kind": "free_speech", "prompt_id": "does-not-exist"},
               files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert r.status_code == 400


def test_size_limit(signed_in):
    c = signed_in
    too_big = io.BytesIO(b"0" * (25 * 1024 * 1024 + 1))
    r = c.post("/api/me/recordings", data={"kind": "free_speech"},
               files={"file": ("big.wav", too_big, "audio/wav")})
    assert r.status_code == 400


def test_duration_limit(signed_in):
    c = signed_in
    r = c.post("/api/me/recordings", data={"kind": "free_speech", "seconds": str(15 * 60 + 1)},
               files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert r.status_code == 400


def test_cannot_touch_another_users_recording(signed_in, client):
    c = signed_in
    up = c.post("/api/me/recordings", data={"kind": "free_speech"},
                files={"file": ("mine.wav", _wav_bytes(), "audio/wav")})
    rec_id = up.json()["id"]

    with TestClient(app) as other:
        _sign_in(other, EMAIL_OTHER)
        assert other.get(f"/api/me/recordings/{rec_id}/audio").status_code == 404
        assert other.delete(f"/api/me/recordings/{rec_id}").status_code == 404
        other.delete("/api/me")

    # still there for the owner
    assert c.get(f"/api/me/recordings/{rec_id}/audio").status_code == 200
    c.delete(f"/api/me/recordings/{rec_id}")


def test_delete_removes_file_from_disk(signed_in):
    c = signed_in
    up = c.post("/api/me/recordings", data={"kind": "free_speech"},
                files={"file": ("todelete.wav", _wav_bytes(), "audio/wav")})
    rec_id = up.json()["id"]
    user_dir = storage.AUDIO_DIR
    before = list(user_dir.rglob("*.wav"))
    assert before
    c.delete(f"/api/me/recordings/{rec_id}")
    after = list(user_dir.rglob("*.wav"))
    assert len(after) < len(before)


def test_delete_account_removes_audio_files(signed_in):
    c = signed_in
    c.post("/api/me/recordings", data={"kind": "free_speech"},
           files={"file": ("keepsake.wav", _wav_bytes(), "audio/wav")})
    assert any(storage.AUDIO_DIR.rglob("*.wav"))
    assert c.delete("/api/me").json()["ok"] is True
    assert not any(storage.AUDIO_DIR.rglob("*.wav"))

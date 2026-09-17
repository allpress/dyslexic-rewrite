"""A tiny file store for voice recordings.

One file per recording, written under `AUDIO_DIR` (default `./data/recordings`) at
`<user_id>/<uuid4>.<ext>`. Nothing else reads this directory; the offline analysis pipeline
reads straight from the database and this same directory.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "./data/recordings")).resolve()


def _resolve(key: str) -> Path:
    """Resolve a storage key to a path inside AUDIO_DIR, raising on path traversal."""
    path = (AUDIO_DIR / key).resolve()
    if path != AUDIO_DIR and AUDIO_DIR not in path.parents:
        raise ValueError("Invalid storage key.")
    return path


def save(user_id: int, data: bytes, ext: str) -> str:
    """Write bytes for a user and return the storage key."""
    key = f"{user_id}/{uuid.uuid4()}.{ext}"
    path = _resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def open_file(key: str):
    """Open a stored file for reading in binary mode."""
    return _resolve(key).open("rb")


def delete(key: str) -> None:
    """Delete a single stored file, if present."""
    path = _resolve(key)
    path.unlink(missing_ok=True)


def delete_user(user_id: int) -> None:
    """Delete every file stored for a user."""
    user_dir = _resolve(str(user_id))
    if not user_dir.is_dir():
        return
    for child in user_dir.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
    try:
        user_dir.rmdir()
    except OSError:
        pass

"""Sample books for "Show me an example" on the read-anything page.

Four short, public-domain excerpts live in `server/data/samples/`: an `index.json` with the
metadata (title, author, year, chapter, source, blurb) and one `.txt` file per excerpt, paragraphs
separated by a blank line. Both are loaded once, at import time, so serving a sample never touches
disk again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data" / "samples"


def _load() -> dict[str, dict[str, Any]]:
    index = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for entry in index:
        text = (DATA_DIR / entry["file"]).read_text(encoding="utf-8").strip()
        out[entry["slug"]] = {**entry, "text": text, "words": len(text.split())}
    return out


SAMPLES: dict[str, dict[str, Any]] = _load()


def list_samples() -> list[dict[str, Any]]:
    """Public listing shape: everything except the excerpt's own text."""
    return [
        {k: v for k, v in s.items() if k not in ("text", "file")}
        for s in SAMPLES.values()
    ]


def get_sample(slug: str) -> dict[str, Any] | None:
    return SAMPLES.get(slug)

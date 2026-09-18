"""Rewrite cache: avoid re-running analyze/rewrite/phonetic-map for text we've already seen.

A cache row is keyed on the text, the reader's profile (everything about it that could change
the output) and the engine's own version, so a code change or a profile edit both naturally
miss. The phonetic map only depends on the reader's `phonetic_map` mode in how the `always`
flag on each entry is set (see `dyslexic_rewrite.pronounce.phonetic_map`); which entries appear
at all is fixed by the rest of the profile. So every row is computed once as if the mode were
"always" (the full entry list, each carrying its own `kind`), and `mode` is applied to that
stored list on every read -- one row serves every mode a reader might be in.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from dyslexic_rewrite import __version__, load_profile
from dyslexic_rewrite.profile import ReaderProfile

from . import db, samples, service

ENGINE = "dyslexic_rewrite"

# ReaderProfile fields that can change a rewrite or phonetic map. Excludes name/description
# (cosmetic labels) and layout (a display preference the engine never reads).
_FINGERPRINT_EXCLUDE = {"name", "description", "layout"}

MAX_CACHED_CHARS = 20_000
MAX_ROWS = 5_000
STALE_AFTER_SQL = "90 days"
CLEANUP_ODDS = 50  # opportunistic: roughly 1-in-50 inserts triggers a sweep


def profile_fingerprint(profile: ReaderProfile) -> str:
    """sha256 of the canonical JSON of every profile field that affects a rewrite or map."""
    d = {k: v for k, v in profile.to_dict().items() if k not in _FINGERPRINT_EXCLUDE}
    blob = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def make_key(text: str, profile: ReaderProfile, *, sample_slug: str | None = None) -> str:
    fp = profile_fingerprint(profile)
    digest = hashlib.sha256("|".join([__version__, ENGINE, fp, text]).encode("utf-8")).hexdigest()
    return f"sample:{sample_slug}:{digest}" if sample_slug else digest


def get(key: str) -> dict[str, Any] | None:
    """A hit bumps `hits`/`last_hit` atomically; returns None on a miss without writing anything."""
    with db.conn() as c:
        row = c.execute(
            "UPDATE rewrite_cache SET hits = hits + 1, last_hit = now() WHERE key = %s "
            "RETURNING segments, stats, phonetic_map",
            (key,),
        ).fetchone()
        c.commit()
    return dict(row) if row else None


def put(key: str, segments: list[dict], stats: dict, phonetic_map: list[dict]) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO rewrite_cache (key, engine, package_version, segments, stats, phonetic_map, last_hit) "
            "VALUES (%s, %s, %s, %s, %s, %s, now()) ON CONFLICT (key) DO NOTHING",
            (key, ENGINE, __version__, json.dumps(segments), json.dumps(stats), json.dumps(phonetic_map)),
        )
        c.commit()
    if random.randrange(CLEANUP_ODDS) == 0:
        _cleanup()


def _cleanup() -> None:
    """Best-effort eviction: drop stale rows, then trim to `MAX_ROWS`. Never touches samples."""
    try:
        with db.conn() as c:
            c.execute(
                "DELETE FROM rewrite_cache WHERE key NOT LIKE 'sample:%' "
                f"AND last_hit < now() - interval '{STALE_AFTER_SQL}'"
            )
            n = c.execute(
                "SELECT COUNT(*) AS n FROM rewrite_cache WHERE key NOT LIKE 'sample:%'"
            ).fetchone()["n"]
            if n > MAX_ROWS:
                c.execute(
                    "DELETE FROM rewrite_cache WHERE key IN ("
                    "  SELECT key FROM rewrite_cache WHERE key NOT LIKE 'sample:%' "
                    "  ORDER BY last_hit NULLS FIRST LIMIT %s)",
                    (n - MAX_ROWS,),
                )
            c.commit()
    except Exception:  # cleanup is opportunistic; never let it break a request
        pass


def _served_map(entries: list[dict], profile: ReaderProfile, mode: str) -> list[dict]:
    """Re-derive the `always` flag on stored (mode="always") entries for the requested mode."""
    if mode == "off" or not entries:
        return []
    always_kinds = set(profile.phonetic_map_always_kinds)
    return [
        {**e, "always": mode == "always" or e["kind"] in always_kinds or e["kind"] == "personal"}
        for e in entries
    ]


def cached_rewrite(
    text: str, profile: ReaderProfile, mode: str, *, sample_slug: str | None = None,
) -> tuple[list[dict], dict, list[dict], bool]:
    """Rewrite + phonetic map for `text` under `profile`, from cache when possible.

    Returns `(segments, stats, phonetic_map, cached)`. Used by both `/api/rewrite` and
    `/api/samples/{slug}` so a hit in one warms the other whenever the text and profile match.
    """
    key = make_key(text, profile, sample_slug=sample_slug)
    hit = get(key)
    if hit is not None:
        return hit["segments"], hit["stats"], _served_map(hit["phonetic_map"], profile, mode), True

    segments, stats = service.rewrite_text(text, profile)
    entries = service.compute_phonetic_map(segments, profile, "always")
    if sample_slug or len(text) <= MAX_CACHED_CHARS:
        put(key, segments, stats, entries)
    return segments, stats, _served_map(entries, profile, mode), False


def warm_samples() -> None:
    """Pre-populate the cache for the sample books under the default profile, so the first
    reader to try one doesn't pay for the analyze/rewrite pass. Called from the app's startup
    hook, off the request path, and safe to call repeatedly (a warm cache is a no-op)."""
    profile = load_profile("default")
    for slug, s in samples.SAMPLES.items():
        cached_rewrite(s["text"], profile, "on_demand", sample_slug=slug)

"""Glue between the web API and the dyslexic_rewrite engine.

Everything that touches a reader's own words lives here so the privacy rule is easy to audit:
`learn_from_text` returns only aggregate metadata; nothing in this module writes raw text anywhere.
"""

from __future__ import annotations

import json
import re
from typing import Any

from dyslexic_rewrite import analyze, load_profile, rewrite
from dyslexic_rewrite.learn import analyze_style, learn_profile
from dyslexic_rewrite.profile import BUILTIN_PROFILES, ReaderProfile

from . import db

# The phonetic-map module (respellings like "in-TEN-shun") is built separately; import it
# defensively so the server still starts, and every phonetic-map call still degrades to "no
# entries", if that module is not present yet.
try:
    from dyslexic_rewrite.pronounce import phonetic_map as _phonetic_map
except ImportError:  # pragma: no cover - exercised once dyslexic_rewrite.pronounce lands
    _phonetic_map = None

PHONETIC_MAP_MODES = ("off", "on_demand", "always")


# ---------------------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------------------
def get_profile(user_id: int, base: str = "default") -> tuple[ReaderProfile, dict | None]:
    with db.conn() as c:
        row = c.execute("SELECT profile, style FROM profiles WHERE user_id = %s", (user_id,)).fetchone()
    if row:
        return ReaderProfile.from_dict(row["profile"]), row["style"]
    return load_profile(base if base in BUILTIN_PROFILES else "default"), None


def save_profile(user_id: int, profile: ReaderProfile, style: dict | None = None) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, profile, style, updated_at) VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET profile = EXCLUDED.profile, "
            "style = COALESCE(EXCLUDED.style, profiles.style), updated_at = now()",
            (user_id, json.dumps(profile.to_dict()), json.dumps(style) if style is not None else None),
        )
        c.commit()


def profile_summary(p: ReaderProfile, base: str) -> dict[str, Any]:
    return {
        "name": p.name, "base_profile": base,
        "max_sentence_words": p.max_sentence_words, "min_zipf": p.min_zipf,
        "trigger_words": p.trigger_words, "safe_words": p.safe_words,
        "vocabulary_size": len(p.vocabulary),
        "style": {
            "median_sentence_words": p.style.median_sentence_words,
            "p75_sentence_words": p.style.p75_sentence_words,
            "passive_rate": p.style.passive_rate, "clause_depth": p.style.clause_depth,
            "median_zipf": p.style.median_zipf, "sample_words": p.style.sample_words,
        },
    }


def learn_from_text(user_id: int, text: str, base: str, name: str) -> tuple[ReaderProfile, dict]:
    """Measure the reader's writing, store only the aggregates, and discard the text."""
    report = analyze_style([text])
    profile = learn_profile([text], base=base, name=name or "personal", report=report)
    # carry over trigger words the reader already told us about
    existing, _ = get_profile(user_id, base)
    profile.trigger_words = sorted(set(existing.trigger_words))
    profile.replacements = dict(existing.replacements)
    style = report.to_dict()
    save_profile(user_id, profile, style)
    del text  # nothing below may use it
    return profile, style


def rebase_profile(user_id: int, base: str) -> ReaderProfile:
    """Switch the built-in base while keeping what was learned about this reader."""
    existing, style = get_profile(user_id, base)
    fresh = load_profile(base if base in BUILTIN_PROFILES else "default")
    fresh.name = existing.name if existing.name not in BUILTIN_PROFILES else "personal"
    fresh.trigger_words = existing.trigger_words
    fresh.safe_words = existing.safe_words
    fresh.replacements = existing.replacements
    fresh.vocabulary = existing.vocabulary
    fresh.style = existing.style
    if existing.style.sample_words:
        fresh.max_sentence_words = existing.max_sentence_words
        fresh.min_zipf = existing.min_zipf
    save_profile(user_id, fresh)
    return fresh


def update_triggers(user_id: int, base: str, add=None, remove=None, safe=None) -> ReaderProfile:
    p, _ = get_profile(user_id, base)
    p.add_feedback(list(add or []), list(safe or []))
    for w in remove or []:
        w = w.strip().lower()
        if w in p.trigger_words:
            p.trigger_words.remove(w)
    save_profile(user_id, p)
    return p


# ---------------------------------------------------------------------------------------
# reading settings ("Aa" panel) -- comfort settings only, see docs/RESEARCH.md §2. These never
# feed the rewrite engine (server/cache.py excludes "layout" from the fingerprint), so a bad or
# unusual value here can only ever change how the page looks, not what it says.
# ---------------------------------------------------------------------------------------
LAYOUT_RANGES: dict[str, tuple[float, float]] = {
    "font_size_px": (16, 32),
    "line_height": (1.4, 2.4),
    "letter_spacing_em": (0.0, 0.15),
    "word_spacing_em": (0.0, 0.5),
    "max_line_chars": (40, 90),
    "paragraph_gap_em": (0.0, 3.0),
    "ruler_height_px": (24, 160),
    "ruler_dim": (0.0, 1.0),
    "autoscroll_speed": (0, 5),
    "tts_rate": (0.6, 1.6),
    "tts_pitch": (0.0, 2.0),
}
_LAYOUT_INT_KEYS = {"font_size_px", "max_line_chars", "ruler_height_px", "autoscroll_speed"}

LAYOUT_CHOICES: dict[str, tuple[str, ...]] = {
    "font_family": ("system", "atkinson", "lexend", "opendyslexic", "mono"),
    "text_align": ("left", "justify"),
    "theme": ("light", "dark", "sepia", "high_contrast", "tint"),
}

LAYOUT_BOOL_KEYS = ("ruler_enabled", "spotlight_enabled")

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def sanitize_layout(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a reader-supplied layout patch onto `current`, validating every recognised key.

    Unknown keys are dropped rather than rejected, so older/newer clients (and the built-in
    profiles' own `background`/`text`/`highlight_changes` keys, which this endpoint does not
    manage) round-trip harmlessly. A recognised key with a bad value raises ValueError, which
    `server/app.py`'s generic handler turns into a 400.
    """
    out = dict(current)
    for key, value in patch.items():
        if key in LAYOUT_RANGES:
            lo, hi = LAYOUT_RANGES[key]
            try:
                num = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number") from None
            if not (lo <= num <= hi):
                raise ValueError(f"{key} must be between {lo} and {hi}")
            out[key] = int(round(num)) if key in _LAYOUT_INT_KEYS else num
        elif key in LAYOUT_CHOICES:
            if value not in LAYOUT_CHOICES[key]:
                raise ValueError(f"{key} must be one of {list(LAYOUT_CHOICES[key])}")
            out[key] = value
        elif key in LAYOUT_BOOL_KEYS:
            out[key] = bool(value)
        elif key == "tint_color":
            if not isinstance(value, str) or not _HEX_COLOR.match(value):
                raise ValueError("tint_color must be a #rrggbb colour")
            out[key] = value
        elif key == "tts_voice":
            if not isinstance(value, str):
                raise ValueError("tts_voice must be a string")
            out[key] = value[:200]
        # else: silently ignored -- not one of ours to validate.
    return out


# ---------------------------------------------------------------------------------------
# rewriting -> segments the reader view can render
# ---------------------------------------------------------------------------------------
def to_segments(result) -> list[dict[str, Any]]:
    segs: list[dict[str, Any]] = []
    for pi, para in enumerate(result.paragraphs):
        if pi:
            segs.append({"t": "para"})
        if para.heading:
            segs.append({"t": "heading", "s": para.text})
            continue
        for s in para.sentences:
            for kind, val in s.segments:
                if kind == "text":
                    if val:
                        segs.append({"t": "text", "s": val})
                elif kind == "change":
                    segs.append({"t": "change", "s": val.replacement, "orig": val.original,
                                 "why": val.reason, "alts": val.alternatives[1:4]})
                elif kind == "note":
                    segs.append({"t": "note", "s": val.text, "why": val.reason, "hint": val.hint or ""})
            segs.append({"t": "text", "s": " "})
    return _merge_text(segs)


def original_segments(text: str) -> list[dict[str, Any]]:
    """The untouched passage in the same segment shape (no marks at all)."""
    import re
    segs: list[dict[str, Any]] = []
    for pi, para in enumerate(p for p in re.split(r"\n\s*\n", text) if p.strip()):
        if pi:
            segs.append({"t": "para"})
        para = " ".join(ln.strip() for ln in para.split("\n") if ln.strip())
        if len(para.split()) <= 8 and not para.endswith(('.', '!', '?', ',', ';', ':')):
            segs.append({"t": "heading", "s": para})
        else:
            segs.append({"t": "text", "s": para})
    return segs


def _merge_text(segs):
    out: list[dict[str, Any]] = []
    for s in segs:
        if s["t"] == "text" and out and out[-1]["t"] == "text":
            out[-1]["s"] += s["s"]
        else:
            out.append(dict(s))
    for s in out:
        if s["t"] == "text":
            s["s"] = s["s"].replace("  ", " ")
    return out


def rewrite_text(text: str, profile: ReaderProfile) -> tuple[list[dict], dict]:
    report = analyze(text, profile)
    result = rewrite(text, profile, report=report)
    st = result.stats
    return to_segments(result), {
        "sentences": st["sentences"], "sentences_changed": st["sentences_changed"], "changes": st["changes"],
        "load_before": st["load_before"], "load_after": st.get("load_after"),
    }


def word_count(segments: list[dict]) -> int:
    return sum(len(s.get("s", "").split()) for s in segments if s["t"] in ("text", "change", "note", "heading"))


# ---------------------------------------------------------------------------------------
# phonetic map -> a respelling ("in-TEN-shun") shown over words the reader might struggle with
# ---------------------------------------------------------------------------------------
def served_text(segments: list[dict]) -> str:
    """Reconstruct the exact text the reader is shown, as one string.

    Mirrors `servedTextSpans` in web/src/components/Reader.tsx: segment strings are
    concatenated in order, and each `para` break becomes two newlines. Char offsets into
    this string are what `phonetic_map` entries are anchored to, and what the client maps
    back onto its segments.
    """
    parts: list[str] = []
    for s in segments:
        parts.append("\n\n" if s["t"] == "para" else s.get("s", ""))
    return "".join(parts)


def compute_phonetic_map(segments: list[dict], profile: ReaderProfile, mode: str) -> list[dict]:
    """Phonetic-map entries for the *served* text, or [] when off, unsupported, or it fails.

    `dyslexic_rewrite.pronounce.phonetic_map` itself branches on `profile.phonetic_map` (it
    returns [] when that's "off", and marks every entry `always=True` when it's "always"), so
    the reader's saved mode -- which this app keeps on `users.phonetic_map`, not in the
    profile blob -- is applied onto the profile for the duration of this one call.
    """
    if _phonetic_map is None or mode == "off":
        return []
    text = served_text(segments)
    if not text.strip():
        return []
    saved_mode = getattr(profile, "phonetic_map", "on_demand")
    try:
        profile.phonetic_map = mode
        entries = _phonetic_map(text, profile=profile)
    except Exception:  # the module may still be evolving; never break passage serving over it
        return []
    finally:
        profile.phonetic_map = saved_mode
    return [
        {
            "start": e.start, "end": e.end, "word": e.word, "respell": e.respell,
            "hint": e.hint, "kind": e.kind, "always": e.always,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------------------
# "Which kind of reader am I?" battery -- see dyslexic_rewrite.assess for the scoring itself.
# ---------------------------------------------------------------------------------------
from dyslexic_rewrite.assess import BatteryScores, profile_from_scores, score_battery  # noqa: E402


def score_battery_raw(raw: dict[str, Any]) -> BatteryScores:
    """Thin re-export so `server/app.py` only ever imports from `service`, not the package."""
    return score_battery(raw)


def apply_battery(user_id: int, base: str, raw: dict[str, Any]) -> ReaderProfile:
    """Fold a finished battery run into the reader's stored profile, keeping what was already
    learned about them (trigger words, vocabulary, writing-style targets)."""
    scores = score_battery(raw)
    existing, style = get_profile(user_id, base)
    updated = profile_from_scores(scores, existing)
    save_profile(user_id, updated, style)
    return updated

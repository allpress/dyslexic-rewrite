"""Glue between the web API and the dyslexic_rewrite engine.

Everything that touches a reader's own words lives here so the privacy rule is easy to audit:
`learn_from_text` returns only aggregate metadata; nothing in this module writes raw text anywhere.
"""

from __future__ import annotations

import json
from typing import Any

from dyslexic_rewrite import analyze, load_profile, rewrite
from dyslexic_rewrite.learn import analyze_style, learn_profile
from dyslexic_rewrite.profile import BUILTIN_PROFILES, ReaderProfile

from . import db


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

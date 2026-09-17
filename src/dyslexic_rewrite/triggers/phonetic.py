"""Phonetic / visual near-neighbour detector.

Two words that sound alike (their / there), share a phonetic code (wind / wined), or are
one letter-swap apart (from / form, quiet / quite) are a known dyslexic stumbling point,
and much worse when they land close together. We flag the *later* word of each pair and
point at the earlier one.

Uses jellyfish's Metaphone for sound-alikes and Damerau-Levenshtein for look-alikes, plus
a curated confusable-pairs list from data/heteronyms.json.
"""

from __future__ import annotations

import jellyfish

from ..nlp import load_data
from .base import Trigger

_MIN_LEN = 3


def _confusable_index() -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for a, b in load_data("heteronyms.json")["confusable_pairs"]:
        idx.setdefault(a, set()).add(b)
        idx.setdefault(b, set()).add(a)
    return idx


def _code(word: str) -> str:
    try:
        return jellyfish.metaphone(word)
    except Exception:  # pragma: no cover
        return ""


def detect_phonetic(doc, profile) -> list[Trigger]:
    window = max(0, int(profile.phonetic_window_sentences))
    confusable = _confusable_index()
    safe = {w.lower() for w in profile.safe_words}

    sents = list(doc.sents)
    recent: list[tuple[int, object, str]] = []  # (sent_index, token, metaphone)
    out = []

    for si, sent in enumerate(sents):
        # drop words that fell out of the window
        recent = [r for r in recent if si - r[0] <= window]
        for tok in sent:
            if not tok.is_alpha or len(tok.text) < _MIN_LEN or tok.pos_ in ("PUNCT", "SPACE"):
                continue
            lw = tok.lower_
            if lw in safe:
                continue
            code = _code(lw)
            for (psi, ptok, pcode) in recent:
                plw = ptok.lower_
                if plw == lw or ptok.lemma_.lower() == tok.lemma_.lower():
                    continue
                kind = None
                content_pair = not (tok.is_stop or ptok.is_stop) and len(lw) >= 4 and len(plw) >= 4
                if plw in confusable.get(lw, ()):
                    kind = "confusable pair"
                elif content_pair and code and code == pcode and abs(len(plw) - len(lw)) <= 2:
                    kind = "sound-alike"
                elif content_pair and jellyfish.damerau_levenshtein_distance(lw, plw) == 1:
                    kind = "look-alike"
                if kind:
                    out.append(Trigger(
                        kind="phonetic", sent_index=si,
                        start=tok.idx, end=tok.idx + len(tok.text), text=tok.text,
                        reason=f"'{tok.text}' and '{ptok.text}' are a {kind} within {si - psi} sentence(s)",
                        score=0.75 if kind == "confusable pair" else 0.6,
                        related=[(ptok.idx, ptok.idx + len(ptok.text))], pos=tok.pos_,
                    ))
                    break
            recent.append((si, tok, code))
    return out

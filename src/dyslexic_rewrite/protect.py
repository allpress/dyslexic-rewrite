"""Protected spans: parts of the text a rewrite must never change.

Names, numbers, dates, quoted speech and code-like tokens carry meaning that a
"simpler" word would destroy. Every engine (rules or LLM) checks its output against
these before accepting a rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_QUOTE_RE = re.compile(r'"[^"\n]{1,200}"|“[^”\n]{1,200}”|‘[^’\n]{1,200}’')
_NUM_RE = re.compile(r"\b\d[\d,.:/%-]*\b")
_CODE_RE = re.compile(r"`[^`\n]+`|\b[A-Za-z_]+\.[A-Za-z_]+\(|https?://\S+")

PROTECTED_ENTS = {"PERSON", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW",
                  "DATE", "TIME", "MONEY", "PERCENT", "QUANTITY", "CARDINAL", "ORDINAL", "FAC", "NORP"}


@dataclass(frozen=True)
class Protected:
    start: int
    end: int
    text: str
    why: str


def find_protected(doc) -> list[Protected]:
    text = doc.text
    spans: list[Protected] = []
    for ent in doc.ents:
        if ent.label_ in PROTECTED_ENTS:
            spans.append(Protected(ent.start_char, ent.end_char, ent.text, ent.label_.lower()))
    for tok in doc:
        if tok.pos_ == "PROPN" and tok.is_alpha and not any(s.start <= tok.idx < s.end for s in spans):
            spans.append(Protected(tok.idx, tok.idx + len(tok.text), tok.text, "proper noun"))
    for rx, why in ((_QUOTE_RE, "quote"), (_NUM_RE, "number"), (_CODE_RE, "code/url")):
        for m in rx.finditer(text):
            spans.append(Protected(m.start(), m.end(), m.group(0), why))
    spans.sort(key=lambda s: (s.start, -s.end))
    return spans


def is_protected(start: int, end: int, spans: list[Protected]) -> bool:
    return any(s.start < end and start < s.end for s in spans)


def check_fidelity(original_spans: list[Protected], rewritten: str) -> list[Protected]:
    """Return the protected spans that are missing from a rewrite. Empty list = OK."""
    missing = []
    low = rewritten.lower()
    for s in original_spans:
        needle = s.text.strip().lower()
        if not needle:
            continue
        # quotes: compare the inside, tolerate straight/curly differences
        needle = needle.strip('"“”‘’')
        if needle and needle not in low:
            missing.append(s)
    return missing

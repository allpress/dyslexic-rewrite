"""Output model shared by every rewrite engine.

A rewritten document is a list of paragraphs; each paragraph is a list of sentence
rewrites; each sentence rewrite is a list of *segments*:

    ("text",  "plain unchanged text")
    ("change", Change)        # a replaced word/phrase, original kept inside
    ("break", None)           # a sentence boundary the rewriter inserted
    ("note", Trigger)         # something flagged but left as-is (shown on demand)

Keeping the original inside every Change is what lets the reader view show it on hover
and lets us produce a clean diff. Nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..triggers.base import Trigger


@dataclass
class Change:
    original: str
    replacement: str
    kind: str
    reason: str
    alternatives: list[str] = field(default_factory=list)


Segment = tuple[str, object]


@dataclass
class SentenceRewrite:
    index: int
    original: str
    segments: list[Segment]
    engine: str = "rules"

    @property
    def text(self) -> str:
        out = []
        for kind, val in self.segments:
            if kind == "text":
                out.append(val)
            elif kind == "change":
                out.append(val.replacement)
            elif kind == "note":
                out.append(val.text)
            elif kind == "break":
                out.append("")
        return "".join(out)

    @property
    def changes(self) -> list[Change]:
        return [v for k, v in self.segments if k == "change"]

    @property
    def notes(self) -> list[Trigger]:
        return [v for k, v in self.segments if k == "note"]

    @property
    def changed(self) -> bool:
        return any(k in ("change", "break") for k, _ in self.segments)


@dataclass
class Paragraph:
    sentences: list[SentenceRewrite]
    heading: bool = False

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.sentences if s.text.strip())

    @property
    def original(self) -> str:
        return " ".join(s.original.strip() for s in self.sentences)


@dataclass
class RewriteResult:
    paragraphs: list[Paragraph]
    profile_name: str
    engine: str
    stats: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs)

    @property
    def original(self) -> str:
        return "\n\n".join(p.original for p in self.paragraphs)

    def all_changes(self) -> list[Change]:
        return [c for p in self.paragraphs for s in p.sentences for c in s.changes]

"""Shared types for trigger detectors.

A Trigger is one thing in the text that may stop a dyslexic reader: a heteronym, a
re-used ambiguous word, a near-homophone pair, a rare or long word, or an over-long
sentence. Detectors only find; the rewriter decides what to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Trigger:
    kind: str                     # one of profile.TRIGGER_KINDS
    sent_index: int               # which sentence (0-based, across the whole document)
    start: int                    # character offset in the document
    end: int
    text: str                     # the exact text flagged
    reason: str                   # human-readable explanation
    score: float = 1.0            # base severity 0..1 before profile weighting
    alternatives: list[str] = field(default_factory=list)   # plain-word options, best first
    related: list[tuple[int, int]] = field(default_factory=list)  # other spans involved (e.g. the clashing word)
    pos: str = ""                 # coarse POS of the flagged token, when it is a single token
    hint: str = ""                # pronunciation / stress cue shown on demand, e.g. "rhymes with 'find'"

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


class Detector(Protocol):
    kind: str

    def __call__(self, doc, profile) -> list[Trigger]: ...

"""Run every detector over a text and produce a Report."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .nlp import get_nlp
from .profile import ReaderProfile
from .triggers import DETECTORS, Trigger


@dataclass
class Report:
    text: str
    profile: ReaderProfile
    triggers: list[Trigger]
    sentence_count: int
    word_count: int
    doc: object = field(repr=False, default=None)

    # ---- summaries -----------------------------------------------------------------------
    def by_kind(self) -> Counter:
        return Counter(t.kind for t in self.triggers)

    def weighted(self, t: Trigger) -> float:
        return t.score * self.profile.weight(t.kind)

    def load(self) -> float:
        """Rough 'reading load' per 100 words: sum of weighted trigger scores."""
        if self.word_count == 0:
            return 0.0
        return 100.0 * sum(self.weighted(t) for t in self.triggers) / self.word_count

    def top_words(self, n: int = 15) -> list[tuple[str, int]]:
        c = Counter(t.text.lower() for t in self.triggers if t.kind != "syntax")
        return c.most_common(n)

    def sentences(self):
        return list(self.doc.sents) if self.doc is not None else []

    def summary(self) -> str:
        kinds = self.by_kind()
        lines = [
            f"Profile: {self.profile.name}",
            f"{self.word_count} words, {self.sentence_count} sentences, "
            f"{len(self.triggers)} triggers, load {self.load():.1f} per 100 words",
            "",
            "By kind:",
        ]
        for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {k:<10} {v:>4}   (weight {self.profile.weight(k):.1f})")
        tw = self.top_words()
        if tw:
            lines += ["", "Most flagged words:"]
            lines += [f"  {w:<16} {c}" for w, c in tw]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.name,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "load_per_100_words": round(self.load(), 2),
            "by_kind": dict(self.by_kind()),
            "triggers": [
                {
                    "kind": t.kind, "sentence": t.sent_index, "start": t.start, "end": t.end,
                    "text": t.text, "reason": t.reason, "score": round(self.weighted(t), 3),
                    "alternatives": t.alternatives, "related": t.related,
                }
                for t in self.triggers
            ],
        }


def analyze(text: str, profile: ReaderProfile | None = None, kinds: list[str] | None = None) -> Report:
    profile = profile or ReaderProfile()
    nlp = get_nlp(profile.language)
    doc = nlp(text)
    triggers: list[Trigger] = []
    for kind, detector in DETECTORS.items():
        if kinds and kind not in kinds:
            continue
        if profile.weight(kind) <= 0:
            continue
        triggers.extend(detector(doc, profile))
    triggers.sort(key=lambda t: (t.start, -t.end))
    words = sum(1 for t in doc if t.is_alpha or t.like_num)
    return Report(
        text=text, profile=profile, triggers=triggers,
        sentence_count=sum(1 for _ in doc.sents), word_count=words, doc=doc,
    )

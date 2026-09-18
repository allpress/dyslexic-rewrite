"""Reader profiles.

A profile is a small JSON file that says what trips this reader up and what their
natural sentence shape looks like. Three layers share one format:

  general      -> profiles/default.json          (works for most dyslexic readers)
  by type      -> profiles/phonological.json ... (weights shifted toward one trigger family)
  individual   -> learned from the reader's own writing/speech + their feedback

Everything stays on the reader's machine. Nothing here phones home.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

BUILTIN_PROFILES = ("default", "phonological", "visual", "attention")

# Trigger families. Weights scale how strongly each family pushes a rewrite.
TRIGGER_KINDS = (
    "heteronym",   # one spelling, two pronunciations/meanings: wind / wind, tear / tear
    "ambiguity",   # same word reused with a different meaning nearby: "wind up" ... "the wind"
    "phrasal",     # phrasal verb whose parts mislead: "wind up" -> "end up"
    "phonetic",    # near-homophones / visually confusable words close together: from/form
    "rare",        # low-frequency words
    "long",        # long words
    "syntax",      # long sentences, passives, embedded clauses
    "personal",    # words this reader reported as triggers
)


@dataclass
class StyleTargets:
    """What the reader's own writing looks like. Learned by `dysrewrite learn`."""

    median_sentence_words: float = 14.0
    p75_sentence_words: float = 20.0
    passive_rate: float = 0.05          # fraction of sentences with a passive
    clause_depth: float = 1.2           # mean number of finite clauses per sentence
    median_zipf: float = 4.6            # median word frequency (wordfreq zipf scale, 1-7)
    sample_words: int = 0               # how many words the profile was learned from


@dataclass
class ReaderProfile:
    name: str = "default"
    language: str = "en"
    description: str = ""

    # Thresholds
    max_sentence_words: int = 20
    min_zipf: float = 3.3               # words rarer than this are "rare"
    max_word_length: int = 12
    phonetic_window_sentences: int = 1  # how far apart two confusable words can be and still clash
    ambiguity_window_sentences: int = 3

    # How much each trigger family matters for this reader (0 = ignore, 1 = normal, 2 = strong)
    weights: dict[str, float] = field(default_factory=lambda: {k: 1.0 for k in TRIGGER_KINDS})

    # Reader-specific knowledge
    trigger_words: list[str] = field(default_factory=list)      # "these words trip me"
    safe_words: list[str] = field(default_factory=list)         # "leave these alone"
    replacements: dict[str, str] = field(default_factory=dict)  # word -> what to use instead
    vocabulary: list[str] = field(default_factory=list)         # words the reader uses when writing

    # Layout preferences for the HTML reader
    layout: dict[str, Any] = field(default_factory=lambda: {
        "font_size_px": 20,
        "line_height": 1.9,
        "letter_spacing_em": 0.04,
        "word_spacing_em": 0.16,
        "max_line_chars": 62,
        "paragraph_gap_em": 1.4,
        "background": "#fbf8f1",
        "text": "#1f2328",
        "highlight_changes": True,
    })

    style: StyleTargets = field(default_factory=StyleTargets)

    # Phonetic map: a friendly respelling shown over words a reader might stumble on.
    # "off" shows none, "on_demand" shows them on hover/tap (plus phonetic_map_always_kinds
    # inline), "always" shows every one inline.
    phonetic_map: str = "on_demand"
    phonetic_map_kinds: list[str] = field(
        default_factory=lambda: ["heteronym", "ambiguity", "personal", "rare", "long", "phonetic"]
    )
    phonetic_map_always_kinds: list[str] = field(
        default_factory=lambda: ["heteronym", "ambiguity", "personal"]
    )

    # ---- helpers -------------------------------------------------------------------------

    def weight(self, kind: str) -> float:
        return float(self.weights.get(kind, 1.0))

    def vocab_set(self) -> set[str]:
        return {w.lower() for w in self.vocabulary}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReaderProfile:
        d = dict(d)
        style = d.pop("style", {}) or {}
        weights = {k: 1.0 for k in TRIGGER_KINDS}
        weights.update(d.pop("weights", {}) or {})
        layout = cls().layout
        layout.update(d.pop("layout", {}) or {})
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in d.items() if k in known}
        p = cls(**clean)
        p.weights = weights
        p.layout = layout
        p.style = StyleTargets(**{k: v for k, v in style.items() if k in StyleTargets.__dataclass_fields__})  # type: ignore[attr-defined]
        return p

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def add_feedback(self, tripped: list[str], safe: list[str] | None = None,
                     replacements: dict[str, str] | None = None) -> None:
        """Fold reader feedback (from the HTML reader's export) into the profile."""
        for w in tripped:
            w = w.strip().lower()
            if w and w not in self.trigger_words:
                self.trigger_words.append(w)
            if w in self.safe_words:
                self.safe_words.remove(w)
        for w in safe or []:
            w = w.strip().lower()
            if w and w not in self.safe_words:
                self.safe_words.append(w)
            if w in self.trigger_words:
                self.trigger_words.remove(w)
        for k, v in (replacements or {}).items():
            self.replacements[k.strip().lower()] = v.strip()


def builtin_profile_path(name: str) -> Path:
    return Path(str(resources.files("dyslexic_rewrite").joinpath("profiles", f"{name}.json")))


def load_profile(name_or_path: str | Path | None = None) -> ReaderProfile:
    """Load a built-in profile by name ('default', 'phonological', ...) or a JSON file by path."""
    if name_or_path is None:
        name_or_path = "default"
    p = Path(str(name_or_path))
    if p.suffix == ".json" and p.exists():
        return ReaderProfile.from_dict(json.loads(p.read_text(encoding="utf-8")))
    if str(name_or_path) in BUILTIN_PROFILES:
        bp = builtin_profile_path(str(name_or_path))
        return ReaderProfile.from_dict(json.loads(bp.read_text(encoding="utf-8")))
    raise FileNotFoundError(
        f"No profile '{name_or_path}'. Use one of {BUILTIN_PROFILES} or a path to a .json file."
    )

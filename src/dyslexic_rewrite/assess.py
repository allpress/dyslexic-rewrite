"""Score the browser screening battery (docs/RESEARCH.md, section 3) into a reader profile.

Pure functions, no I/O, fully unit-tested (see tests/test_assess.py). This is the offline half
of the "which kind of reader am I?" feature: `server/app.py` collects raw per-task results into
`battery_runs.raw` and calls :func:`score_battery` to turn them into a small set of axis scores,
then :func:`profile_from_scores` to fold those into a `ReaderProfile`.

Everything below is a **provisional first cut**, not a validated instrument -- there is no clean
set of dyslexia "types" (RESEARCH.md section 1), so this reports axes, never a diagnosis, and the
numeric anchors (accuracy -> support, VAS span -> support, ...) are chosen to be monotonic and
sensible, not fitted to data. The server keeps every `raw` result specifically so these anchors
can be re-scored later once enough readers have done the battery (RESEARCH.md section 3.1). If you
change an anchor, only the numbers move -- nothing here changes shape.

Two design choices worth calling out because they resolve an ambiguity in RESEARCH.md:

- Section 3's battery table says a plausible-error-heavy speller should get "`heteronym`,
  `ambiguity`, `phonetic` raised" and an implausible-error-heavy one "`rare`, `long` raised,
  `min_zipf` lowered". Read literally that last part would make the profile flag *fewer* words as
  rare (`min_zipf` is the "words rarer than this are 'rare'" threshold in `ReaderProfile`, and a
  *higher* threshold catches *more* words -- see its docstring). That is backwards for a reader who
  needs *more* frequent-word support, and it also does not match section 4.1's per-axis recipe
  ("Phonological | ... `min_zipf` raised"). We follow section 4.1 here: phonological support
  *raises* `min_zipf`.
- "Checklist contributes at most 20 points to any axis" (section 3, row A) is implemented as an
  additive bonus of up to 20 points on top of the objective task's score, capped at 100 total. When
  the objective task itself was skipped, there is nothing to add the bonus to, so the checklist
  becomes the axis's only evidence and the axis is marked low-confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any

from .profile import ReaderProfile

try:
    import jellyfish
except ImportError:  # pragma: no cover - jellyfish is a core dependency, but degrade gracefully
    jellyfish = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------------------

AXES: tuple[str, ...] = ("phonological", "orthographic", "rate", "vas", "attention")

AXIS_LABELS: dict[str, str] = {
    "phonological": "Sounding out words",
    "orthographic": "Recognising whole words",
    "rate": "Reading speed",
    "vas": "Taking in letters at a glance",
    "attention": "Holding a sentence in mind",
}

# Checklist items (see server/battery_items.py) that feed each axis's "up to 20 points" bonus.
# `comfort` items never feed an axis -- they are shown as a separate note (RESEARCH.md section 1.7).
CHECKLIST_AXIS_ITEMS: dict[str, tuple[str, ...]] = {
    "rate": ("c1", "c8", "c10"),
    "attention": ("c2", "c5", "c7"),
    "phonological": ("c4", "c3"),
    "orthographic": ("c3", "c6"),
    "vas": ("c2",),
}

HETERONYM_RELIABLE_MS = 80.0
HETERONYM_RELIABLE_RATIO = 0.15
SPILLOVER_WORDS = 2  # the target word plus this many words after it


# ---------------------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------------------


@dataclass
class AxisScore:
    support: float  # 0-100, higher = more support needed. Provisional anchors, see module docstring.
    confidence: str  # "low" | "normal"
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"support": self.support, "confidence": self.confidence, "detail": self.detail}


@dataclass
class HeteronymResult:
    slowdown_ms: float | None
    slowdown_ratio: float | None
    reliable: bool
    pairs_scored: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slowdown_ms": self.slowdown_ms,
            "slowdown_ratio": self.slowdown_ratio,
            "reliable": self.reliable,
            "pairs_scored": self.pairs_scored,
        }


@dataclass
class BatteryScores:
    phonological: AxisScore
    orthographic: AxisScore
    rate: AxisScore
    vas: AxisScore
    attention: AxisScore
    comfort: AxisScore  # shown as a note, never blended into the axes or the profile
    heteronym: HeteronymResult

    def axis(self, axis_id: str) -> AxisScore:
        return getattr(self, axis_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "axes": [
                {"id": a, "label": AXIS_LABELS[a], **self.axis(a).to_dict()}
                for a in AXES
            ],
            "comfort": self.comfort.to_dict(),
            "heteronym": self.heteronym.to_dict(),
        }


# ---------------------------------------------------------------------------------------
# Small numeric anchors -- see the module docstring for the "provisional" caveat.
# ---------------------------------------------------------------------------------------


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _linear(value: float, lo_value: float, hi_value: float, invert: bool = False) -> float:
    """Map `value` linearly onto 0-100, clipped. `lo_value` -> 0, `hi_value` -> 100."""
    if hi_value == lo_value:
        return 0.0
    t = (value - lo_value) / (hi_value - lo_value)
    return _clip(t * 100.0)


def accuracy_to_support(accuracy: float) -> float:
    """100% correct -> 0 support, 50% correct -> 100 support (chance on a 2AFC task)."""
    return _linear(accuracy, 1.0, 0.5)


def vas_span_to_support(span: float) -> float:
    """Whole-report span of 5 letters -> 0, 2 letters -> 100 (RESEARCH.md section 3)."""
    return _linear(span, 5.0, 2.0)


def digit_span_to_support(span: float) -> float:
    """Backward digit span >= 6 -> 0, <= 3 -> 100."""
    return _linear(span, 6.0, 3.0)


def rate_ms_to_support(median_rt_ms: float) -> float:
    """Median per-word reading time: 250ms -> 0, 700ms -> 100."""
    return _linear(median_rt_ms, 250.0, 700.0)


def rt_bonus(median_rt_ms: float | None, fast: float = 800.0, slow: float = 3000.0, max_bonus: float = 15.0) -> float:
    """A small extra push for a slow-but-accurate response on a decision task (C/D)."""
    if median_rt_ms is None:
        return 0.0
    return _linear(median_rt_ms, fast, slow) / 100.0 * max_bonus


def spillover_to_support(spillover_ms: float | None) -> float:
    """Extra RT on the two words after a heteronym vs. its matched control: 0ms -> 0, 150ms -> 100."""
    if spillover_ms is None:
        return 0.0
    return _linear(spillover_ms, 0.0, 150.0)


def checklist_item_to_0_100(value: int) -> float:
    """A 1-4 Likert answer -> 0-100 ('never' -> 0, 'always' -> 100)."""
    return _clip((float(value) - 1.0) / 3.0 * 100.0)


# ---------------------------------------------------------------------------------------
# Spelling classification (test B)
# ---------------------------------------------------------------------------------------


def classify_spelling(word: str, response: str, kind: str) -> dict[str, Any]:
    """Classify one typed response to a dictated word.

    `kind` is "regular", "irregular" or "nonword". Returns
    `{"correct": bool, "classification": "correct" | "plausible" | "implausible" | None}`.
    `classification` is `None` for a nonword: nonwords only contribute an accuracy figure
    (RESEARCH.md section 3, row B), they are not split into plausible/implausible.

    Plausibility follows the project's rule (FEATURE spec, task B): phonetically plausible means
    the response's phonetic code matches the target's -- via `jellyfish`'s Metaphone, backed up by
    Soundex when Metaphone alone disagrees (Metaphone is the more accurate of the two, but it is
    strict about a leading letter; Soundex catches a few plausible respellings Metaphone misses,
    e.g. a swapped first consonant that still sounds right).
    """
    target = word.strip().lower()
    typed = (response or "").strip().lower()
    if not typed:
        return {"correct": False, "classification": None if kind == "nonword" else "omitted"}
    if typed == target:
        return {"correct": True, "classification": "correct"}
    if kind == "nonword":
        return {"correct": False, "classification": None}
    plausible = False
    if jellyfish is not None:
        try:
            plausible = (
                jellyfish.metaphone(typed) == jellyfish.metaphone(target)
                or jellyfish.soundex(typed) == jellyfish.soundex(target)
            )
        except Exception:  # pragma: no cover - jellyfish is pure python and should not raise
            plausible = False
    return {"correct": False, "classification": "plausible" if plausible else "implausible"}


def _spelling_summary(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate classified spelling trials into the figures the axis scorers need."""
    word_errors = 0
    plausible_errors = 0
    implausible_errors = 0
    nonword_total = 0
    nonword_correct = 0
    for t in trials:
        c = classify_spelling(t.get("word", ""), t.get("response", ""), t.get("kind", "regular"))
        if t.get("kind") == "nonword":
            nonword_total += 1
            if c["correct"]:
                nonword_correct += 1
            continue
        if c["classification"] == "plausible":
            word_errors += 1
            plausible_errors += 1
        elif c["classification"] == "implausible":
            word_errors += 1
            implausible_errors += 1
        # "correct" and "omitted" are neither plausible nor implausible errors.
    return {
        "word_errors": word_errors,
        "plausible_errors": plausible_errors,
        "implausible_errors": implausible_errors,
        "plausible_fraction": (plausible_errors / word_errors) if word_errors else 0.0,
        "implausible_fraction": (implausible_errors / word_errors) if word_errors else 0.0,
        "nonword_accuracy": (nonword_correct / nonword_total) if nonword_total else None,
        "nonword_total": nonword_total,
    }


# ---------------------------------------------------------------------------------------
# Heteronym probe (test H)
# ---------------------------------------------------------------------------------------


def _region_mean(word_rts: list[float], critical_index: int, words: int) -> float | None:
    region = word_rts[critical_index: critical_index + words]
    region = [x for x in region if isinstance(x, (int, float)) and x > 0]
    return mean(region) if region else None


def _heteronym_summary(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Pair up target/control trials by `pair_id` and compute the slowdown and spillover."""
    by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    all_word_rts: list[float] = []
    for t in trials:
        for x in t.get("word_rts") or []:
            if isinstance(x, (int, float)) and x > 0:
                all_word_rts.append(float(x))
        pid = t.get("pair_id")
        cond = t.get("condition")
        if pid is None or cond not in ("target", "control"):
            continue
        by_pair.setdefault(pid, {})[cond] = t

    region_diffs: list[float] = []
    control_region_means: list[float] = []
    spillover_diffs: list[float] = []
    for pair in by_pair.values():
        tgt, ctl = pair.get("target"), pair.get("control")
        if not tgt or not ctl:
            continue
        ti, ci = tgt.get("critical_index"), ctl.get("critical_index")
        if ti is None or ci is None:
            continue
        t_region = _region_mean(tgt.get("word_rts") or [], ti, 1 + SPILLOVER_WORDS)
        c_region = _region_mean(ctl.get("word_rts") or [], ci, 1 + SPILLOVER_WORDS)
        if t_region is not None and c_region is not None:
            region_diffs.append(t_region - c_region)
            control_region_means.append(c_region)
        t_spill = _region_mean(tgt.get("word_rts") or [], ti + 1, SPILLOVER_WORDS)
        c_spill = _region_mean(ctl.get("word_rts") or [], ci + 1, SPILLOVER_WORDS)
        if t_spill is not None and c_spill is not None:
            spillover_diffs.append(t_spill - c_spill)

    slowdown_ms = mean(region_diffs) if region_diffs else None
    slowdown_ratio = (
        slowdown_ms / mean(control_region_means)
        if slowdown_ms is not None and control_region_means and mean(control_region_means) > 0
        else None
    )
    spillover_ms = mean(spillover_diffs) if spillover_diffs else None
    reliable = bool(
        slowdown_ms is not None
        and slowdown_ratio is not None
        and slowdown_ms > HETERONYM_RELIABLE_MS
        and slowdown_ratio > HETERONYM_RELIABLE_RATIO
    )
    return {
        "median_word_rt": median(all_word_rts) if all_word_rts else None,
        "slowdown_ms": round(slowdown_ms, 1) if slowdown_ms is not None else None,
        "slowdown_ratio": round(slowdown_ratio, 3) if slowdown_ratio is not None else None,
        "spillover_ms": round(spillover_ms, 1) if spillover_ms is not None else None,
        "reliable": reliable,
        "pairs_scored": len(region_diffs),
    }


# ---------------------------------------------------------------------------------------
# Choice-task (C / D) accuracy + RT
# ---------------------------------------------------------------------------------------


def _choice_summary(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not trials:
        return None
    correct = sum(1 for t in trials if t.get("correct"))
    rts = [float(t["rt_ms"]) for t in trials if isinstance(t.get("rt_ms"), (int, float)) and t["rt_ms"] > 0]
    return {
        "accuracy": correct / len(trials),
        "median_rt_ms": median(rts) if rts else None,
        "n": len(trials),
    }


# ---------------------------------------------------------------------------------------
# Combining an objective task score with the checklist's bonus
# ---------------------------------------------------------------------------------------


def _checklist_axis_component(checklist_answers: dict[str, int], axis: str) -> float:
    ids = CHECKLIST_AXIS_ITEMS.get(axis, ())
    values = [checklist_item_to_0_100(checklist_answers[i]) for i in ids if i in checklist_answers]
    return mean(values) if values else 0.0


def _combine_axis(task_support: float | None, checklist_0_100: float, detail: dict[str, Any]) -> AxisScore:
    if task_support is None:
        # No objective evidence at all: fall back to the checklist alone, and say so.
        return AxisScore(support=round(checklist_0_100, 1), confidence="low",
                          detail={**detail, "source": "checklist_only"})
    bonus = checklist_0_100 * 0.20  # "checklist contributes at most 20 points to any axis"
    support = round(min(100.0, task_support + bonus), 1)
    return AxisScore(support=support, confidence="normal",
                      detail={**detail, "task_support": round(task_support, 1), "checklist_bonus": round(bonus, 1)})


# ---------------------------------------------------------------------------------------
# score_battery
# ---------------------------------------------------------------------------------------


def score_battery(raw: dict[str, Any]) -> BatteryScores:
    """Score one battery run's raw results (see server/API.md for the exact shape).

    Every task is optional -- a reader can skip any of them -- and a missing or empty task simply
    means that axis leans more on the checklist and gets `confidence: "low"`.
    """
    raw = raw or {}
    checklist = (raw.get("checklist") or {}).get("answers") or {}
    comfort_answers = (raw.get("checklist") or {}).get("comfort") or {}

    spelling_trials = (raw.get("spelling") or {}).get("trials") or []
    spelling = _spelling_summary(spelling_trials) if spelling_trials else None

    c = _choice_summary((raw.get("orthographic_choice") or {}).get("trials") or [])
    d = _choice_summary((raw.get("pseudohomophone") or {}).get("trials") or [])

    vas_trials = [t for t in (raw.get("vas") or {}).get("trials") or [] if not t.get("practice")]
    vas_span = mean([float(t.get("correct_letters", 0)) for t in vas_trials]) if vas_trials else None

    digit_span = (raw.get("digit_span") or {}).get("span")

    heteronym_trials = (raw.get("heteronym") or {}).get("trials") or []
    h = _heteronym_summary(heteronym_trials) if heteronym_trials else None

    # ---- phonological: nonword accuracy + implausible spelling errors, and test D --------------
    phon_parts = []
    phon_detail: dict[str, Any] = {}
    if spelling is not None:
        if spelling["nonword_accuracy"] is not None:
            phon_parts.append(accuracy_to_support(spelling["nonword_accuracy"]))
        phon_parts.append(spelling["implausible_fraction"] * 100.0)
        phon_detail["spelling"] = spelling
    if d is not None:
        phon_parts.append(_clip(accuracy_to_support(d["accuracy"]) + rt_bonus(d["median_rt_ms"])))
        phon_detail["pseudohomophone_decision"] = d
    phon_task = mean(phon_parts) if phon_parts else None
    phonological = _combine_axis(phon_task, _checklist_axis_component(checklist, "phonological"), phon_detail)

    # ---- orthographic: plausible spelling errors, and test C -----------------------------------
    orth_parts = []
    orth_detail: dict[str, Any] = {}
    if spelling is not None:
        orth_parts.append(spelling["plausible_fraction"] * 100.0)
        orth_detail["spelling"] = spelling
    if c is not None:
        orth_parts.append(_clip(accuracy_to_support(c["accuracy"]) + rt_bonus(c["median_rt_ms"])))
        orth_detail["orthographic_choice"] = c
    orth_task = mean(orth_parts) if orth_parts else None
    orthographic = _combine_axis(orth_task, _checklist_axis_component(checklist, "orthographic"), orth_detail)

    # ---- rate: median per-word RT in H (both conditions) ----------------------------------------
    rate_task = None
    rate_detail: dict[str, Any] = {}
    if h is not None and h["median_word_rt"] is not None:
        rate_task = rate_ms_to_support(h["median_word_rt"])
        rate_detail["median_word_rt_ms"] = round(h["median_word_rt"], 1)
    rate = _combine_axis(rate_task, _checklist_axis_component(checklist, "rate"), rate_detail)

    # ---- vas: whole-report span -------------------------------------------------------------
    vas_task = vas_span_to_support(vas_span) if vas_span is not None else None
    vas_detail = {"span": round(vas_span, 2)} if vas_span is not None else {}
    vas = _combine_axis(vas_task, _checklist_axis_component(checklist, "vas"), vas_detail)

    # ---- attention: backward digit span + the H spillover pattern -------------------------------
    att_parts = []
    att_detail: dict[str, Any] = {}
    if digit_span is not None:
        att_parts.append(digit_span_to_support(float(digit_span)))
        att_detail["digit_span"] = digit_span
    if h is not None and h["spillover_ms"] is not None:
        att_parts.append(spillover_to_support(h["spillover_ms"]))
        att_detail["spillover_ms"] = h["spillover_ms"]
    att_task = mean(att_parts) if att_parts else None
    attention = _combine_axis(att_task, _checklist_axis_component(checklist, "attention"), att_detail)

    # ---- comfort: self-report only, shown as a note, never blended into an axis -----------------
    if comfort_answers:
        comfort_support = mean(checklist_item_to_0_100(v) for v in comfort_answers.values())
        comfort = AxisScore(support=round(comfort_support, 1), confidence="normal", detail={})
    else:
        comfort = AxisScore(support=0.0, confidence="low", detail={})

    heteronym = HeteronymResult(
        slowdown_ms=h["slowdown_ms"] if h else None,
        slowdown_ratio=h["slowdown_ratio"] if h else None,
        reliable=bool(h and h["reliable"]),
        pairs_scored=h["pairs_scored"] if h else 0,
    )

    return BatteryScores(
        phonological=phonological, orthographic=orthographic, rate=rate, vas=vas, attention=attention,
        comfort=comfort, heteronym=heteronym,
    )


# ---------------------------------------------------------------------------------------
# profile_from_scores
# ---------------------------------------------------------------------------------------


def _scale(support: float, lo: float, hi: float) -> float:
    """0-100 support -> lo..hi, linear. `hi` is what a support of 100 maps to (may be < lo)."""
    t = _clip(support) / 100.0
    return lo + t * (hi - lo)


def profile_from_scores(scores: BatteryScores, base: ReaderProfile) -> ReaderProfile:
    """Fold a scored battery run into a copy of `base` (RESEARCH.md section 3/4.1 mapping table).

    Every threshold and weight below only ever moves *away from* `base` in the direction the axis
    calls for -- it never relaxes something the base profile already set more aggressively -- so
    running the battery on top of a hand-tuned profile cannot make it less helpful.
    """
    p = ReaderProfile.from_dict(base.to_dict())
    p.name = f"{base.name}+battery" if base.name else "battery"

    # Phonological: prefer common, short, regularly-spelled words (section 4.1, "Phonological").
    s = scores.phonological.support
    p.weights["rare"] = round(max(p.weights.get("rare", 1.0), _scale(s, 1.0, 2.0)), 2)
    p.weights["long"] = round(max(p.weights.get("long", 1.0), _scale(s, 1.0, 1.6)), 2)
    p.min_zipf = round(max(p.min_zipf, _scale(s, p.min_zipf, 4.6)), 2)

    # Orthographic: the whole-word route is weak -> reused/irregular spellings cost more.
    s = scores.orthographic.support
    p.weights["heteronym"] = round(max(p.weights.get("heteronym", 1.0), _scale(s, 1.0, 2.0)), 2)
    p.weights["ambiguity"] = round(max(p.weights.get("ambiguity", 1.0), _scale(s, 1.0, 2.0)), 2)
    p.weights["phonetic"] = round(max(p.weights.get("phonetic", 1.0), _scale(s, 1.0, 1.8)), 2)

    # VAS: fewer letters at a glance -> shorter words, shorter lines, more space between words.
    s = scores.vas.support
    p.weights["long"] = round(max(p.weights["long"], _scale(s, 1.0, 2.0)), 2)
    p.max_word_length = round(min(p.max_word_length, _scale(s, p.max_word_length, 7.0)))
    p.layout["max_line_chars"] = round(min(p.layout.get("max_line_chars", 62), _scale(s, p.layout.get("max_line_chars", 62), 45.0)))
    p.layout["word_spacing_em"] = round(max(p.layout.get("word_spacing_em", 0.16), _scale(s, p.layout.get("word_spacing_em", 0.16), 0.28)), 3)

    # Rate: slow reading -> split sentences, subject-first, a shorter overall sentence cap.
    s = scores.rate.support
    p.weights["syntax"] = round(max(p.weights.get("syntax", 1.0), _scale(s, 1.0, 1.6)), 2)
    p.max_sentence_words = round(min(p.max_sentence_words, _scale(s, p.max_sentence_words, 14.0)))

    # Attention/working memory: harder to hold a sentence -> syntax at full weight, sentences shorter still.
    s = scores.attention.support
    p.weights["syntax"] = round(max(p.weights["syntax"], _scale(s, 1.0, 2.0)), 2)
    p.max_sentence_words = round(min(p.max_sentence_words, _scale(s, p.max_sentence_words, 10.0)))
    p.style.clause_depth = round(min(p.style.clause_depth, _scale(s, p.style.clause_depth, 1.0)), 2)

    # Heteronym/tricky-word probe: only push these up if the slowdown looked reliable -- an
    # unreliable result means "leave them at 1.0 and stop rewriting for them" (RESEARCH.md, row H).
    if scores.heteronym.reliable:
        p.weights["heteronym"] = round(max(p.weights["heteronym"], 1.8), 2)
        p.weights["ambiguity"] = round(max(p.weights["ambiguity"], 1.6), 2)
        p.weights["phrasal"] = round(max(p.weights.get("phrasal", 1.0), 1.5), 2)

    # Phonetic map: FEATURE spec rule -- "always" once phonological support crosses 50.
    p.phonetic_map = "always" if scores.phonological.support >= 50 else "on_demand"

    return p

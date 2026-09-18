"""Unit tests for dyslexic_rewrite.assess: pure scoring for the browser screening battery."""

from __future__ import annotations

from dyslexic_rewrite.assess import (
    accuracy_to_support,
    classify_spelling,
    digit_span_to_support,
    profile_from_scores,
    rate_ms_to_support,
    score_battery,
    vas_span_to_support,
)
from dyslexic_rewrite.profile import ReaderProfile

# ---------------------------------------------------------------------------------------
# Anchors (RESEARCH.md section 3 / FEATURE spec "SCORING")
# ---------------------------------------------------------------------------------------


def test_accuracy_anchor_endpoints():
    assert accuracy_to_support(1.0) == 0
    assert accuracy_to_support(0.5) == 100
    assert accuracy_to_support(0.0) == 100  # clipped, not negative-extrapolated
    assert 0 < accuracy_to_support(0.75) < 100


def test_vas_span_anchor_endpoints():
    assert vas_span_to_support(5.0) == 0
    assert vas_span_to_support(2.0) == 100
    assert vas_span_to_support(0.0) == 100  # clipped


def test_digit_span_anchor_endpoints():
    assert digit_span_to_support(6.0) == 0
    assert digit_span_to_support(3.0) == 100
    assert digit_span_to_support(8.0) == 0  # clipped, not negative
    assert digit_span_to_support(1.0) == 100


def test_rate_anchor_endpoints():
    assert rate_ms_to_support(250.0) == 0
    assert rate_ms_to_support(700.0) == 100
    assert rate_ms_to_support(1000.0) == 100  # clipped


# ---------------------------------------------------------------------------------------
# Spelling classification (task B)
# ---------------------------------------------------------------------------------------


def test_classify_spelling_correct():
    r = classify_spelling("garden", "garden", "regular")
    assert r == {"correct": True, "classification": "correct"}


def test_classify_spelling_is_case_and_whitespace_insensitive():
    r = classify_spelling("garden", "  Garden  ", "regular")
    assert r["correct"] is True


def test_classify_spelling_plausible_error():
    # "fone" sounds exactly like "phone" -- the textbook phonetically-plausible misspelling.
    r = classify_spelling("phone", "fone", "irregular")
    assert r == {"correct": False, "classification": "plausible"}


def test_classify_spelling_implausible_error():
    # Nothing about "xyzzy" shares a sound with "temper".
    r = classify_spelling("temper", "xyzzy", "regular")
    assert r == {"correct": False, "classification": "implausible"}


def test_classify_spelling_nonword_never_gets_plausible_or_implausible():
    correct = classify_spelling("blorp", "blorp", "nonword")
    wrong = classify_spelling("blorp", "blorf", "nonword")
    assert correct == {"correct": True, "classification": "correct"}
    assert wrong == {"correct": False, "classification": None}


def test_classify_spelling_omitted():
    r = classify_spelling("garden", "", "regular")
    assert r == {"correct": False, "classification": "omitted"}


# ---------------------------------------------------------------------------------------
# score_battery
# ---------------------------------------------------------------------------------------


def _heteronym_trial(pair_id, condition, critical_index, word_rts):
    return {"id": f"{pair_id}-{condition[0]}", "pair_id": pair_id, "condition": condition,
            "critical_index": critical_index, "word_rts": word_rts}


def test_score_battery_empty_raw_is_all_low_confidence():
    scores = score_battery({})
    for axis in ("phonological", "orthographic", "rate", "vas", "attention"):
        s = scores.axis(axis)
        assert s.confidence == "low"
        assert s.support == 0.0
    assert scores.comfort.confidence == "low"
    assert scores.heteronym.reliable is False
    assert scores.heteronym.slowdown_ms is None


def test_score_battery_skipped_task_is_low_confidence_others_are_not():
    raw = {
        "checklist": {"answers": {"c4": 4}, "comfort": {"v1": 1, "v2": 1, "v3": 1}},
        # spelling ("B") deliberately omitted -- the reader skipped it.
        "orthographic_choice": {"trials": [{"id": "c0", "correct": True, "rt_ms": 900}] * 24},
    }
    scores = score_battery(raw)
    assert scores.phonological.confidence == "low"  # no spelling, no D
    assert scores.orthographic.confidence == "normal"  # has C
    assert scores.vas.confidence == "low"


def test_score_battery_perfect_scores_mean_low_support():
    raw = {
        "checklist": {
            "answers": {f"c{i}": 1 for i in range(1, 11)},
            "comfort": {"v1": 1, "v2": 1, "v3": 1},
        },
        "spelling": {"trials": [
            {"id": "b0", "word": "garden", "kind": "regular", "response": "garden"},
            {"id": "b1", "word": "yacht", "kind": "irregular", "response": "yacht"},
            {"id": "b2", "word": "blorp", "kind": "nonword", "response": "blorp"},
        ]},
        "orthographic_choice": {"trials": [{"id": f"c{i}", "correct": True, "rt_ms": 700} for i in range(24)]},
        "pseudohomophone": {"trials": [{"id": f"d{i}", "correct": True, "rt_ms": 700} for i in range(24)]},
        "vas": {"trials": [{"id": "e0", "correct_letters": 5, "practice": False}] * 20},
        "digit_span": {"span": 7},
        "heteronym": {"trials": [
            _heteronym_trial("h1", "target", 0, [300, 300, 300, 300]),
            _heteronym_trial("h1", "control", 0, [300, 300, 300, 300]),
        ]},
    }
    scores = score_battery(raw)
    for axis in ("phonological", "orthographic", "rate", "vas", "attention"):
        s = scores.axis(axis)
        assert s.confidence == "normal"
        assert s.support < 15, f"{axis} support too high for a clean run: {s.support}"
    assert scores.heteronym.reliable is False  # no slowdown at all


def test_score_battery_poor_scores_mean_high_support():
    raw = {
        "checklist": {
            "answers": {f"c{i}": 4 for i in range(1, 11)},
            "comfort": {"v1": 4, "v2": 4, "v3": 4},
        },
        "spelling": {"trials": [
            {"id": "b0", "word": "temper", "kind": "regular", "response": "qzxwv"},
            {"id": "b1", "word": "island", "kind": "irregular", "response": "zzzzz"},
            {"id": "b2", "word": "blorp", "kind": "nonword", "response": "wrong"},
        ]},
        "orthographic_choice": {"trials": [{"id": f"c{i}", "correct": False, "rt_ms": 3000} for i in range(24)]},
        "pseudohomophone": {"trials": [{"id": f"d{i}", "correct": False, "rt_ms": 3000} for i in range(24)]},
        "vas": {"trials": [{"id": "e0", "correct_letters": 2, "practice": False}] * 20},
        "digit_span": {"span": 3},
        "heteronym": {"trials": [
            _heteronym_trial("h1", "target", 0, [900, 900, 900]),
            _heteronym_trial("h1", "control", 0, [300, 300, 300]),
        ]},
    }
    scores = score_battery(raw)
    assert scores.phonological.support > 80  # implausible spelling errors + poor D
    assert scores.orthographic.support > 60  # weak C alone, since the spelling errors were implausible
    assert scores.vas.support > 80
    assert scores.attention.support > 80
    assert scores.heteronym.reliable is True
    assert scores.heteronym.slowdown_ms > 80
    assert scores.heteronym.slowdown_ratio > 0.15


def test_heteronym_reliability_thresholds():
    # 60ms / ~20%: over the ratio threshold but under the 80ms floor -> not reliable.
    small = score_battery({"heteronym": {"trials": [
        _heteronym_trial("h1", "target", 0, [360, 360, 360]),
        _heteronym_trial("h1", "control", 0, [300, 300, 300]),
    ]}})
    assert small.heteronym.slowdown_ms == 60
    assert small.heteronym.reliable is False

    # 100ms on a 300ms base is a 33% ratio and over both floors -> reliable.
    big = score_battery({"heteronym": {"trials": [
        _heteronym_trial("h1", "target", 0, [400, 400, 400]),
        _heteronym_trial("h1", "control", 0, [300, 300, 300]),
    ]}})
    assert big.heteronym.reliable is True


def test_checklist_only_axis_is_capped_by_being_the_only_evidence():
    # Every checklist answer is a "4" (always), so the 0-100 checklist figure is 100 -- but with no
    # objective task at all the axis is explicitly low-confidence, not just quietly high-support.
    scores = score_battery({"checklist": {"answers": {"c1": 4, "c8": 4, "c10": 4}, "comfort": {}}})
    assert scores.rate.confidence == "low"
    assert scores.rate.support == 100.0


# ---------------------------------------------------------------------------------------
# profile_from_scores
# ---------------------------------------------------------------------------------------


def test_profile_from_scores_low_support_barely_changes_the_base():
    base = ReaderProfile()
    scores = score_battery({
        "spelling": {"trials": [{"id": "b0", "word": "garden", "kind": "regular", "response": "garden"}]},
        "orthographic_choice": {"trials": [{"id": "c0", "correct": True, "rt_ms": 700}]},
        "pseudohomophone": {"trials": [{"id": "d0", "correct": True, "rt_ms": 700}]},
        "vas": {"trials": [{"id": "e0", "correct_letters": 5, "practice": False}]},
        "digit_span": {"span": 7},
    })
    p = profile_from_scores(scores, base)
    assert p.weights["rare"] < 1.2
    assert p.min_zipf <= base.min_zipf + 0.2
    assert p.phonetic_map == "on_demand"


def test_profile_from_scores_high_support_pushes_every_documented_field():
    base = ReaderProfile()
    scores = score_battery({
        "spelling": {"trials": [
            {"id": "b0", "word": "temper", "kind": "regular", "response": "qzxwv"},
            {"id": "b1", "word": "blorp", "kind": "nonword", "response": "wrong"},
        ]},
        "orthographic_choice": {"trials": [{"id": "c0", "correct": False, "rt_ms": 3000}]},
        "pseudohomophone": {"trials": [{"id": "d0", "correct": False, "rt_ms": 3000}]},
        "vas": {"trials": [{"id": "e0", "correct_letters": 2, "practice": False}]},
        "digit_span": {"span": 3},
        "heteronym": {"trials": [
            _heteronym_trial("h1", "target", 0, [900, 900, 900]),
            _heteronym_trial("h1", "control", 0, [300, 300, 300]),
        ]},
    })
    p = profile_from_scores(scores, base)

    assert p.weights["rare"] > base.weight("rare")
    assert p.weights["long"] > base.weight("long")
    assert p.min_zipf > base.min_zipf
    assert p.weights["heteronym"] > base.weight("heteronym")
    assert p.weights["ambiguity"] > base.weight("ambiguity")
    assert p.weights["phonetic"] > base.weight("phonetic")
    assert p.max_word_length < base.max_word_length
    assert p.layout["max_line_chars"] < base.layout["max_line_chars"]
    assert p.layout["word_spacing_em"] > base.layout["word_spacing_em"]
    assert p.weights["syntax"] > base.weight("syntax")
    assert p.max_sentence_words < base.max_sentence_words
    assert p.weights["phrasal"] > base.weight("phrasal")  # heteronym slowdown was reliable
    assert p.phonetic_map == "always"  # phonological support crossed 50


def test_profile_from_scores_unreliable_heteronym_leaves_phrasal_weight_alone():
    base = ReaderProfile()
    scores = score_battery({"heteronym": {"trials": [
        _heteronym_trial("h1", "target", 0, [310, 310, 310]),
        _heteronym_trial("h1", "control", 0, [300, 300, 300]),
    ]}})
    assert scores.heteronym.reliable is False
    p = profile_from_scores(scores, base)
    assert p.weights["phrasal"] == base.weight("phrasal")


def test_profile_from_scores_never_relaxes_a_more_aggressive_base():
    # A reader whose base profile is already more aggressive than the battery would suggest keeps
    # their own settings -- the battery only ever pushes further in the same direction.
    base = ReaderProfile()
    base.weights["rare"] = 3.0
    base.min_zipf = 5.0
    scores = score_battery({})  # no evidence at all
    p = profile_from_scores(scores, base)
    assert p.weights["rare"] == 3.0
    assert p.min_zipf == 5.0

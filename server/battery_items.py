"""Static stimuli for the "which kind of reader am I?" screening battery (docs/RESEARCH.md, §3).

Everything here is fixed, hand-authored content -- no AI, no network calls. `GET /api/battery/items`
(see server/app.py) calls :func:`build_items` and returns the result; a few tasks (VAS letter
strings, the digit-span ladder, and left/right shuffling of the two-alternative tasks) are
randomised **per call** using the stdlib `random` module, exactly like `server/passages.py` and
`app.py` already randomise passage pairs and which passage is rewritten.

Item banks, and where each one is checked against the FEATURE spec:

- `checklist_items` -- 10 BDA/Vinegrad-style items + 3 visual-comfort items (task A).
- `spelling_items` -- 20 dictation words: 8 regular, 8 irregular, 4 nonwords (task B).
- `orthographic_choice_items` -- 24 real-word/pseudohomophone pairs (task C).
- `pseudohomophone_items` -- 24 nonword/nonword pairs (task D). Every foil was generated to have
  zero `wordfreq` frequency and every "sounds-like" spelling was checked it is not the word's own
  standard spelling; see the comment above `_PSEUDOHOMOPHONE_PAIRS`.
- `vas_trials` -- 2 practice + 20 scored trials of 5 unique consonants each (task E).
- `digit_span_ladder` -- 2 trials at each length 3..8 (task F; adaptive stopping is client-side).
- `heteronym_items` -- 12 heteronym/reused-spelling sentences + 12 matched controls, moving-window
  word lists, with a comprehension question on 6 of the 24 (task H).
"""

from __future__ import annotations

import random
import string
from typing import Any

# ---------------------------------------------------------------------------------------
# A. Checklist (triage only -- never gates access to anything)
# ---------------------------------------------------------------------------------------

CHECKLIST_SCALE = ["Never", "Rarely", "Often", "Always"]

_CHECKLIST_ITEMS: list[tuple[str, str, str]] = [
    ("c1", "rate", "I read more slowly than most people I know."),
    ("c2", "attention", "I lose my place on the page when I'm reading."),
    ("c3", "orthographic", "I mix up words that look or sound alike, like 'was' and 'saw', or 'form' and 'from'."),
    ("c4", "phonological", "My spelling is noticeably worse than my other skills."),
    ("c5", "attention", "I have trouble holding a phone number in my head long enough to dial it."),
    ("c6", "orthographic", "I mix up left and right."),
    ("c7", "attention", "I find forms and paperwork hard to fill in."),
    ("c8", "rate", "I dread being asked to read out loud in front of other people."),
    ("c9", "triage", "Someone in my close family has had similar reading or spelling difficulties."),
    ("c10", "rate", "Reading for more than a few minutes tires me out more than it seems to tire other people."),
]

_COMFORT_ITEMS: list[tuple[str, str]] = [
    ("v1", "Letters seem to move, swim or blur when I look at a page of text."),
    ("v2", "Bright white pages give me glare or make it hard to look at the page."),
    ("v3", "I get headaches or sore eyes after reading for a while."),
]


def checklist_items() -> dict[str, Any]:
    return {
        "scale": CHECKLIST_SCALE,
        "items": [{"id": i, "axis": axis, "prompt": prompt} for i, axis, prompt in _CHECKLIST_ITEMS],
        "comfort_items": [{"id": i, "prompt": prompt} for i, prompt in _COMFORT_ITEMS],
    }


# ---------------------------------------------------------------------------------------
# B. Spelling from dictation
# ---------------------------------------------------------------------------------------

_REGULAR_WORDS = ["blanket", "market", "plastic", "finish", "garden", "pocket", "temper", "window"]
_IRREGULAR_WORDS = ["yacht", "colonel", "island", "answer", "receipt", "biscuit", "choir", "sword"]
_NONWORDS = ["blorp", "trandish", "fimble", "plonket"]


def spelling_items(rng: random.Random) -> dict[str, Any]:
    items = (
        [{"word": w, "kind": "regular"} for w in _REGULAR_WORDS]
        + [{"word": w, "kind": "irregular"} for w in _IRREGULAR_WORDS]
        + [{"word": w, "kind": "nonword"} for w in _NONWORDS]
    )
    rng.shuffle(items)
    return {
        "speech_rate": 0.9,
        "items": [{"id": f"b{i}", **it} for i, it in enumerate(items)],
    }


# ---------------------------------------------------------------------------------------
# C. Orthographic choice: real word vs. a pseudohomophone that is not itself a real word
# ---------------------------------------------------------------------------------------

_ORTHOGRAPHIC_PAIRS = [
    ("rain", "rane"), ("brain", "brane"), ("boat", "bote"), ("night", "nite"),
    ("school", "skool"), ("phone", "fone"), ("laugh", "laff"), ("ocean", "oshun"),
    ("people", "peeple"), ("friend", "frend"), ("enough", "enuff"), ("straight", "strate"),
    ("answer", "anser"), ("knife", "nife"), ("whistle", "wissle"), ("though", "thoe"),
    ("tongue", "tung"), ("listen", "lissen"), ("island", "iland"), ("yacht", "yot"),
    ("receipt", "reseet"), ("colonel", "kernul"), ("biscuit", "biskit"), ("sword", "sord"),
]


def orthographic_choice_items(rng: random.Random) -> list[dict[str, Any]]:
    out = []
    for i, (real, pseudo) in enumerate(_ORTHOGRAPHIC_PAIRS):
        left_is_real = rng.random() < 0.5
        left, right = (real, pseudo) if left_is_real else (pseudo, real)
        out.append({"id": f"c{i}", "left": left, "right": right, "correct": "left" if left_is_real else "right"})
    rng.shuffle(out)
    return out


# ---------------------------------------------------------------------------------------
# D. Pseudohomophone decision: which nonword sounds like a real word?
#
# Every "sounds-like" spelling below reads aloud like the `# target` word in the comment, and is
# not that word's own spelling. Every foil was drawn from a pool of invented CVC/CCVC syllables
# verified to have zero `wordfreq` frequency (see the worktree's scratch check; regenerate with
# `wordfreq.zipf_frequency(word, "en") == 0.0` if this list is ever extended). `harte`/`horte`
# replaces the literal "hart"/"hort" from the FEATURE spec, since "hart" (a deer) is itself a
# real, if uncommon, English word.
# ---------------------------------------------------------------------------------------

_PSEUDOHOMOPHONE_PAIRS = [
    ("brane", "taid"),    # brain
    ("skool", "swoz"),    # school
    ("nite", "gloog"),    # night
    ("fone", "craip"),    # phone
    ("sed", "brouz"),     # said
    ("laff", "plap"),     # laugh
    ("wurd", "gloon"),    # word
    ("hed", "plail"),     # head
    ("boyl", "trais"),    # boil
    ("frend", "glool"),   # friend
    ("kween", "gooz"),    # queen
    ("munny", "gouf"),    # money
    ("fether", "troul"),  # feather
    ("shurt", "naig"),    # shirt
    ("sokk", "plip"),     # sock
    ("klok", "broul"),    # clock
    ("brij", "soox"),     # bridge
    ("harte", "glak"),    # heart
    ("joos", "glav"),     # juice
    ("cheez", "floov"),   # cheese
    ("gloo", "crix"),     # glue
    ("troo", "boup"),     # true
    ("vois", "gloox"),    # voice
    ("syze", "clait"),    # size
]


def pseudohomophone_items(rng: random.Random) -> list[dict[str, Any]]:
    out = []
    for i, (sounds_like, foil) in enumerate(_PSEUDOHOMOPHONE_PAIRS):
        left_is_real_sound = rng.random() < 0.5
        left, right = (sounds_like, foil) if left_is_real_sound else (foil, sounds_like)
        out.append({"id": f"d{i}", "left": left, "right": right,
                     "correct": "left" if left_is_real_sound else "right"})
    rng.shuffle(out)
    return out


# ---------------------------------------------------------------------------------------
# E. VAS whole report: 5 unique consonants, flashed 200ms
# ---------------------------------------------------------------------------------------

_CONSONANTS = [c.upper() for c in string.ascii_lowercase if c not in "aeiou"]


def vas_trials(rng: random.Random, n_practice: int = 2, n_scored: int = 20) -> list[dict[str, Any]]:
    trials = []
    for i in range(n_practice + n_scored):
        letters = rng.sample(_CONSONANTS, 5)
        trials.append({"id": f"e{i}", "letters": letters, "practice": i < n_practice})
    return trials


# ---------------------------------------------------------------------------------------
# F. Backward digit span: the ladder of lengths the client walks (2 trials each, adaptive stop)
# ---------------------------------------------------------------------------------------


def digit_span_trials(rng: random.Random, lengths: range = range(3, 9)) -> list[dict[str, Any]]:
    """Two trials at each length 3..8. Digits never repeat immediately, so a trial can't be
    passed by simply noticing a run. The client stops presenting new lengths once both trials at
    a length are failed; a passed trial with no next length also ends the task."""
    trials = []
    for length in lengths:
        for rep in range(2):
            digits = [rng.randrange(10)]
            while len(digits) < length:
                nxt = rng.randrange(10)
                if nxt == digits[-1]:
                    continue
                digits.append(nxt)
            trials.append({"id": f"f{length}-{rep}", "length": length, "digits": digits})
    return trials


# ---------------------------------------------------------------------------------------
# H. Heteronym probe: 12 heteronym/reused-spelling sentences + 12 matched controls
#
# `critical_index` is the 0-based index (into `words`, split on spaces) of the word the measure is
# built around: for a target sentence, the *second* occurrence of the reused spelling -- the one
# whose meaning must be re-mapped on the fly; for its matched control, the word in the same slot.
# The scored region is that word plus the two words after it (RESEARCH.md §3, row H).
# ---------------------------------------------------------------------------------------


def _index_of(words: list[str], word: str, occurrence: int = 1) -> int:
    """0-based index of the Nth (1-based `occurrence`) case-insensitive match of `word`."""
    seen = 0
    stripped = [w.strip(".,!?;:\"'").lower() for w in words]
    for i, w in enumerate(stripped):
        if w == word.lower():
            seen += 1
            if seen == occurrence:
                return i
    raise ValueError(f"{word!r} occurrence {occurrence} not found in {words!r}")


# Each row: (pair_id, target sentence, target critical word, target question-or-None,
# control sentence, control critical word, control question-or-None). Questions are
# (prompt, answer) pairs. Exactly 3 pairs (6 of the 24 sentences) carry a question, so readers
# read for meaning without turning every sentence into a quiz (FEATURE spec, task H).
_HETERONYM_ROWS: list[tuple[str, str, str, tuple[str, bool] | None, str, str, tuple[str, bool] | None]] = [
    ("h1",
     "The wind was so strong that we had to wind the rope twice around the post.", "wind",
     ("Did they wind the rope around the post?", True),
     "The rain was so heavy that we had to cover the boxes twice before the storm.", "cover",
     ("Did they cover the boxes?", True)),
    ("h2",
     "She had to tear the page out before a tear could fall on it.", "tear", None,
     "She had to fold the letter twice before she could seal it shut.", "seal", None),
    ("h3",
     "Please read the note I read to you yesterday.", "read", None,
     "Please check the list I made for you yesterday.", "made", None),
    ("h4",
     "They will record the record kept in the old book.", "record",
     ("Is the record kept in a new book?", False),
     "They will store the boxes kept in the old shed.", "boxes",
     ("Are the boxes kept in a new shed?", False)),
    ("h5",
     "He will present the present after dinner tonight.", "present", None,
     "He will open the gift after dinner tonight.", "gift", None),
    ("h6",
     "The bass player caught a bass in the lake that afternoon.", "bass", None,
     "The young singer sang a song in the hall that afternoon.", "song", None),
    ("h7",
     "Close the door before the storm gets too close to the old house.", "close", None,
     "Open the window before the pilot flies too near the old tower.", "near", None),
    ("h8",
     "The dove flew away before the pilot dove toward the water below.", "dove", None,
     "The pilot watched the small plane turn toward the water below.", "turn", None),
    ("h9",
     "I object to that heavy object being moved again this week.", "object",
     ("Is the object described as heavy?", True),
     "I agree with that simple plan being made again this week.", "plan",
     ("Is the plan described as complicated?", False)),
    ("h10",
     "Lead the horse away from the old lead pipe in the yard.", "lead", None,
     "Walk the dog away from the old metal fence in the yard.", "fence", None),
    ("h11",
     "The wound on his arm will not wound his pride as much as losing did.", "wound", None,
     "The bruise on his arm will not bother him as much as losing did.", "bother", None),
    ("h12",
     "It takes only a minute to fix, but that minute detail matters a lot.", "minute", None,
     "It takes only a moment to fix, but that small detail matters a lot.", "small", None),
]


def heteronym_items() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pair_id, t_sentence, t_word, t_q, c_sentence, c_word, c_q in _HETERONYM_ROWS:
        t_words = t_sentence.split(" ")
        c_words = c_sentence.split(" ")
        t_index = _index_of(t_words, t_word, occurrence=2)
        c_index = _index_of(c_words, c_word, occurrence=1)
        out.append({
            "id": f"{pair_id}-t", "pair_id": pair_id, "condition": "target",
            "words": t_words, "critical_index": t_index,
            "question": {"prompt": t_q[0], "answer": t_q[1]} if t_q else None,
        })
        out.append({
            "id": f"{pair_id}-c", "pair_id": pair_id, "condition": "control",
            "words": c_words, "critical_index": c_index,
            "question": {"prompt": c_q[0], "answer": c_q[1]} if c_q else None,
        })
    return out


# ---------------------------------------------------------------------------------------
# Everything together
# ---------------------------------------------------------------------------------------


def build_items(seed: int | None = None) -> dict[str, Any]:
    """All stimuli for one battery attempt, randomised per call (RESEARCH.md §3)."""
    rng = random.Random(seed)
    heteronym = heteronym_items()
    rng.shuffle(heteronym)
    return {
        "checklist": checklist_items(),
        "spelling": spelling_items(rng),
        "orthographic_choice": orthographic_choice_items(rng),
        "pseudohomophone": pseudohomophone_items(rng),
        "vas": vas_trials(rng),
        "digit_span": digit_span_trials(rng),
        "heteronym": heteronym,
    }

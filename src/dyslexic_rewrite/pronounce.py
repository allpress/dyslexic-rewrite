"""Friendly respellings ("phonetic map"): a plain-English pronunciation guide shown over
words a dyslexic reader might stumble on -- NOT the International Phonetic Alphabet.

Built on the `cmudict` package (the CMU Pronouncing Dictionary, ARPAbet phonemes). Imported
lazily: if `cmudict` is not installed, :func:`respell` simply returns ``None`` everywhere
and the rest of the tool keeps working without pronunciation cues.

Design, in short:

- Split a word's ARPAbet phonemes into syllables around each vowel, using maximal-onset
  syllabification (the syllable boundary sits after the longest legal English onset
  cluster that can start the next syllable).
- Spell each syllable with a small ARPAbet -> plain-letters table (vowels: AA/ah, AE/a,
  AH0/uh, AH1/u, AO/aw, AW/ow, AY/y (or "eye" alone), EH/e, ER/er, EY/ay, IH/i, IY/ee,
  OW/oh, OY/oy, UH/uu, UW/oo; consonants mostly as-is, with CH/ch, DH/th, HH/h, JH/j,
  NG/ng, SH/sh, TH/th, ZH/zh).
- A vowel immediately followed by "R" in the same syllable (fire, tear, more) is r-coloured
  in real English, so that pair gets its own spelling (EH+R -> "air", IH+R -> "eer", ...)
  instead of being spelled letter-by-letter.
- The syllable carrying stress 1 is UPPERCASE; every other syllable is lowercase. A
  single-syllable word is uppercase outright.
- Heteronyms (wind/wind, record/record, read/read...) have more than one CMUdict
  pronunciation. `respell(word, pos=..., tag=...)` picks the right one using a small
  routing table below, built from three patterns that cover almost every English
  heteronym: a stress shift (record/present/object/... -- NOUN/ADJ stresses the first
  syllable, VERB the second), a vowel-quality difference (wind, tear, lead, live, bow,
  dove, sow, wound -- picked by which vowel phoneme is present), a final-consonant voicing
  difference (use, excuse -- VERB ends /z/, NOUN ends /s/), and one word ("read") whose two
  pronunciations track *tense*, so it is routed by spaCy's fine-grained tag instead of POS.
  Anything not covered by the routing table falls back to the first CMUdict entry with
  `ambiguous=True`.

A couple of specific words are hand-overridden (see IRREGULAR below) because their actual
spelling is too irregular for the phoneme table to produce something a reader would
recognise ("yacht", "colonel"), or because the CMU Pronouncing Dictionary itself carries an
inconsistency for that word ("intention" is transcribed with a CH where it should be SH --
compare "intentional", which CMUdict spells correctly with SH).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from .analyze import Report, analyze
from .nlp import load_data
from .profile import ReaderProfile

# ---------------------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------------------


@dataclass
class Respelling:
    word: str
    respell: str
    syllables: int
    hint: str | None = None
    ambiguous: bool = False
    source: str = "cmudict"


@dataclass
class MapEntry:
    start: int
    end: int
    word: str
    respell: str
    hint: str | None
    kind: str
    always: bool = False


# ---------------------------------------------------------------------------------------
# cmudict: lazy, optional
# ---------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _cmu_dict() -> dict | None:
    try:
        import cmudict
    except ImportError:  # pragma: no cover - exercised only when the extra isn't installed
        return None
    try:
        return cmudict.dict()
    except Exception:  # pragma: no cover
        return None


@functools.lru_cache(maxsize=1)
def _heteronym_table() -> dict:
    try:
        return load_data("heteronyms.json")["words"]
    except Exception:  # pragma: no cover
        return {}


def _hint_for(word: str, pos: str | None) -> str:
    entry = _heteronym_table().get(word)
    if not entry or not pos:
        return ""
    return entry.get("_hint", {}).get(pos, "")


# ---------------------------------------------------------------------------------------
# Irregular spellings: not worth generalising the phoneme table for one word.
# ---------------------------------------------------------------------------------------

# "yacht" -- silent letters the phoneme table cannot reconstruct into something readable.
# "colonel" -- one of English's most irregular spellings (rhymes with "kernel").
# "intention" -- a genuine CMUdict data quirk: it transcribes the "-tion" here with CH,
#   not SH, unlike "intentional"/"intentionally"/every other "-ntion" word in the same
#   dictionary. See the CMUdict gaps note in the module docstring / README.
IRREGULAR: dict[str, tuple[str, int]] = {
    "yacht": ("YOT", 1),
    "colonel": ("KER-nul", 2),
    "intention": ("in-TEN-shun", 3),
}

# ---------------------------------------------------------------------------------------
# Heteronym routing
# ---------------------------------------------------------------------------------------

# Stress-shift class: the NOUN/ADJ sense stresses the first syllable, the VERB sense the
# second ("REC-ord" / "re-CORD"). Applies to most of the classic two-syllable heteronyms.
# Two words here ("content", "minute") have no VERB sense; the ADJ takes the "second
# syllable" slot instead, since that is the sense that actually shifts stress for them.
STRESS_SHIFT_WORDS = {
    "record", "present", "object", "produce", "permit", "contract", "conduct",
    "project", "subject", "refuse", "desert", "content", "minute",
}

# Vowel-quality / final-consonant class: no stress shift, the two senses just use a
# different phoneme somewhere. Routed by "does this CMUdict pronunciation contain (or end
# with) this phoneme".
_CONTAINS = "contains"
_ENDSWITH = "endswith"

CONTAINS_ROUTES: dict[str, dict[str, tuple[str, str]]] = {
    "wind": {"NOUN": (_CONTAINS, "IH"), "VERB": (_CONTAINS, "AY")},
    "tear": {"VERB": (_CONTAINS, "EH"), "NOUN": (_CONTAINS, "IH")},
    "lead": {"VERB": (_CONTAINS, "IY"), "NOUN": (_CONTAINS, "EH")},
    "live": {"VERB": (_CONTAINS, "IH"), "ADJ": (_CONTAINS, "AY")},
    "bow": {"VERB": (_CONTAINS, "AW"), "NOUN": (_CONTAINS, "OW")},
    "close": {"VERB": (_ENDSWITH, "Z"), "ADJ": (_ENDSWITH, "S"), "ADV": (_ENDSWITH, "S")},
    "dove": {"VERB": (_CONTAINS, "OW"), "NOUN": (_CONTAINS, "AH")},
    "sow": {"VERB": (_CONTAINS, "OW"), "NOUN": (_CONTAINS, "AW")},
    "wound": {"VERB": (_CONTAINS, "AW"), "NOUN": (_CONTAINS, "UW")},
    "use": {"VERB": (_ENDSWITH, "Z"), "NOUN": (_ENDSWITH, "S")},
    "excuse": {"VERB": (_ENDSWITH, "Z"), "NOUN": (_ENDSWITH, "S")},
}


def _base_phones(phones: list[str]) -> list[str]:
    return [p.rstrip("012") for p in phones]


def _find_matching(entries: list[list[str]], kind: str, val: str) -> list[str] | None:
    for phones in entries:
        bases = _base_phones(phones)
        if kind == _CONTAINS and val in bases:
            return phones
        if kind == _ENDSWITH and bases and bases[-1] == val:
            return phones
    return None


def _primary_stress_position(phones: list[str]) -> int:
    """Index (among this word's syllable nuclei) of the vowel carrying stress 1.

    Falls back to a stress-2 vowel, then to the first syllable, so this always returns
    something usable even for oddly-marked entries.
    """
    nuclei = [p for p in phones if p[-1].isdigit()]
    stresses = [int(p[-1]) for p in nuclei]
    if 1 in stresses:
        return stresses.index(1)
    if 2 in stresses:
        return stresses.index(2)
    return 0


def _pick_by_stress(entries: list[list[str]], bucket: str) -> list[str]:
    scored = [(_primary_stress_position(ph), i) for i, ph in enumerate(entries)]
    # Ties go to the earlier CMUdict entry, which is the canonical one ("pree-ZENT",
    # not the reduced "per-ZENT").
    best = min(scored) if bucket == "early" else max(scored, key=lambda t: (t[0], -t[1]))
    return entries[best[1]]


def _stress_bucket(word: str, pos_norm: str) -> str:
    if pos_norm == "VERB":
        return "late"
    if pos_norm == "NOUN":
        return "early"
    if pos_norm == "ADJ":
        table = _heteronym_table().get(word, {})
        return "early" if "VERB" in table else "late"
    return "early"


def _generic_fallback(word: str, pos_norm: str, entries: list[list[str]]) -> tuple[list[str], bool]:
    """No curated route for this word: spread the available pronunciations across its
    declared POS keys (in a stable order) so different senses at least *tend* to come out
    different, and say so with ambiguous=True.
    """
    table = _heteronym_table().get(word, {})
    pos_keys = sorted(k for k in table if not k.startswith("_"))
    if pos_norm in pos_keys and len(entries) > 1:
        idx = pos_keys.index(pos_norm) % len(entries)
        return entries[idx], True
    # Not a known heteronym: CMUdict's extra entries are just variant pronunciations
    # ("enough", "either"), so the first one is fine and nothing is ambiguous.
    return entries[0], bool(table)


def _route(word: str, pos: str | None, tag: str | None, entries: list[list[str]]) -> tuple[list[str], bool]:
    pos_norm = "VERB" if pos == "AUX" else (pos or "")

    if word == "read":
        if tag in ("VBD", "VBN"):
            found = _find_matching(entries, _CONTAINS, "EH")
        elif tag in ("VB", "VBP", "VBZ", "VBG"):
            found = _find_matching(entries, _CONTAINS, "IY")
        else:
            found = _find_matching(entries, _CONTAINS, "IY" if pos_norm == "NOUN" else "EH")
        if found:
            return found, False
        return entries[0], True

    if word in STRESS_SHIFT_WORDS:
        return _pick_by_stress(entries, _stress_bucket(word, pos_norm)), False

    route = CONTAINS_ROUTES.get(word, {}).get(pos_norm)
    if route:
        found = _find_matching(entries, *route)
        if found:
            return found, False

    return _generic_fallback(word, pos_norm, entries)


# ---------------------------------------------------------------------------------------
# ARPAbet -> friendly spelling
# ---------------------------------------------------------------------------------------

CONSONANT_MAP = {
    "CH": "ch", "DH": "th", "HH": "h", "JH": "j", "NG": "ng", "SH": "sh", "TH": "th",
    "ZH": "zh", "Y": "y",
    "B": "b", "D": "d", "F": "f", "G": "g", "K": "k", "L": "l", "M": "m", "N": "n",
    "P": "p", "R": "r", "S": "s", "T": "t", "V": "v", "W": "w", "Z": "z",
}

VOWEL_MAP = {
    "AA": "ah", "AE": "a", "AO": "aw", "AW": "ow", "AY": "y", "EH": "e", "ER": "er",
    "EY": "ay", "IH": "i", "IY": "ee", "OW": "oh", "OY": "oy", "UH": "uu", "UW": "oo",
    # AH is stress-dependent: see _vowel_text.
}

# A vowel immediately followed by "R" within the same syllable is r-coloured in real
# English (fire, tear, more, tour...) and reads badly spelled letter-by-letter.
VOWEL_R_MAP = {
    "AA": "ar", "AE": "air", "AH": "er", "AO": "or", "AW": "owr", "AY": "yr", "EH": "air",
    "EY": "air", "IH": "eer", "IY": "eer", "OW": "or", "OY": "oyr", "UH": "oor", "UW": "oor",
}

# A syllable that is *only* the bare vowel (no onset, no coda) reads oddly as a single
# letter -- "i" on its own looks like a typo, "y" looks like the word "why" backwards --
# so those get a fuller, clearer spelling.
BARE_VOWEL_MAP = {"IH": "ih", "AY": "eye", "EH": "eh", "UH": "uh"}

# Short ("lax") vowels: a stressed syllable with one of these takes the following
# consonant as its coda (see _build_respelling).
LAX_VOWELS = {"AE", "EH", "IH", "AH", "UH"}

_NOT_A_LEGAL_ONSET_ALONE = {"NG", "ZH"}

LEGAL_ONSET_2 = {
    ("P", "R"), ("B", "R"), ("T", "R"), ("D", "R"), ("K", "R"), ("G", "R"), ("F", "R"),
    ("TH", "R"), ("SH", "R"),
    ("P", "L"), ("B", "L"), ("K", "L"), ("G", "L"), ("F", "L"), ("S", "L"),
    ("T", "W"), ("D", "W"), ("G", "W"), ("K", "W"), ("S", "W"),
    ("S", "M"), ("S", "N"), ("S", "P"), ("S", "T"), ("S", "K"), ("S", "F"),
    ("P", "Y"), ("B", "Y"), ("T", "Y"), ("D", "Y"), ("K", "Y"), ("G", "Y"),
    ("M", "Y"), ("N", "Y"), ("F", "Y"), ("V", "Y"), ("HH", "Y"), ("L", "Y"),
}
LEGAL_ONSET_3 = {
    ("S", "P", "R"), ("S", "T", "R"), ("S", "K", "R"), ("S", "P", "L"), ("S", "K", "W"),
}


def _is_legal_onset(cluster: tuple[str, ...]) -> bool:
    if len(cluster) == 0:
        return True
    if len(cluster) == 1:
        return cluster[0] not in _NOT_A_LEGAL_ONSET_ALONE
    if len(cluster) == 2:
        return cluster in LEGAL_ONSET_2
    if len(cluster) == 3:
        return cluster in LEGAL_ONSET_3
    return False


def _split_onset(between: list[str]) -> tuple[list[str], list[str]]:
    """Maximal-onset syllabification: push as many consonants as possible onto the next
    syllable, as long as they form a legal English onset cluster. Returns
    (coda of the syllable before, onset of the syllable after).
    """
    n = len(between)
    for k in range(min(n, 3), -1, -1):
        suffix = tuple(between[n - k:]) if k else ()
        if _is_legal_onset(suffix):
            return between[: n - k], list(suffix)
    return between, []  # pragma: no cover - k=0 is always legal, so this never triggers


def _split_phone(phone: str) -> tuple[str, int | None]:
    if phone[-1].isdigit():
        return phone[:-1], int(phone[-1])
    return phone, None


def _vowel_text(base: str, stress: int, bare: bool) -> str:
    if base == "AH":
        return "uh" if stress == 0 else "u"
    if bare and base in BARE_VOWEL_MAP:
        return BARE_VOWEL_MAP[base]
    return VOWEL_MAP.get(base, base.lower())


def _consonants_text(phones: list[str]) -> str:
    return "".join(CONSONANT_MAP.get(p, p.lower()) for p in phones)


def _spell_syllable(onset: list[str], base: str, stress: int, coda: list[str], mono: bool) -> str:
    coda_use = coda
    if coda and coda[0] == "R" and base != "ER":
        vr = VOWEL_R_MAP.get(base)
        if vr is not None:
            vowel_txt = vr
            coda_use = coda[1:]
        else:
            vowel_txt = _vowel_text(base, stress, bare=not onset and not coda)
    else:
        vowel_txt = _vowel_text(base, stress, bare=not onset and not coda)
    text = _consonants_text(onset) + vowel_txt + _consonants_text(coda_use)
    if mono or stress == 1:
        return text.upper()
    return text.lower()


def _build_respelling(phones: list[str]) -> tuple[str, int]:
    parsed = [_split_phone(p) for p in phones]
    nuclei = [i for i, (_, s) in enumerate(parsed) if s is not None]
    if not nuclei:  # pragma: no cover - real English words always have a vowel
        return _consonants_text([b for b, _ in parsed]).upper(), 1

    syllables = []
    cur_onset = [b for b, _ in parsed[: nuclei[0]]]
    for k, ni in enumerate(nuclei):
        base, stress = parsed[ni]
        if k + 1 < len(nuclei):
            between = [b for b, _ in parsed[ni + 1: nuclei[k + 1]]]
            coda, next_onset = _split_onset(between)
            # A stressed short vowel reads wrong when its syllable is left open
            # ("RE-kerd", "JE-nuh-fer"): English spelling closes it, so we do too
            # ("REK-erd", "JEN-uh-fer").
            if stress == 1 and not coda and next_onset and base in LAX_VOWELS:
                coda, next_onset = [next_onset[0]], next_onset[1:]
        else:
            coda = [b for b, _ in parsed[ni + 1:]]
            next_onset = []
        syllables.append((cur_onset, base, stress, coda))
        cur_onset = next_onset

    mono = len(syllables) == 1
    text = "-".join(_spell_syllable(onset, base, stress, coda, mono) for onset, base, stress, coda in syllables)
    return text, len(syllables)


# ---------------------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------------------


def respell(word: str, pos: str | None = None, tag: str | None = None) -> Respelling | None:
    """A friendly respelling for `word`, e.g. respell("intention") -> "in-TEN-shun".

    `pos` (a coarse spaCy POS like "VERB"/"NOUN"/"ADJ") and `tag` (a fine-grained spaCy
    tag like "VBD") disambiguate heteronyms -- words with more than one pronunciation.
    Returns None if the word is not in CMUdict, or if `cmudict` is not installed.
    """
    wl = word.strip().lower()
    if not wl:
        return None

    if wl in IRREGULAR:
        text, syll = IRREGULAR[wl]
        return Respelling(word=word, respell=text, syllables=syll, hint=_hint_for(wl, pos) or None)

    d = _cmu_dict()
    if d is None:
        return None
    entries = d.get(wl)
    if not entries:
        return None

    if len(entries) == 1:
        phones, ambiguous = entries[0], False
    else:
        phones, ambiguous = _route(wl, pos, tag, entries)

    text, syll = _build_respelling(phones)
    return Respelling(word=word, respell=text, syllables=syll, hint=_hint_for(wl, pos) or None, ambiguous=ambiguous)


def phonetic_map(text: str, profile: ReaderProfile | None = None, report: Report | None = None) -> list[MapEntry]:
    """One MapEntry per trigger word this profile wants a pronunciation cue shown for.

    Runs (or reuses) `analyze()`, keeps triggers whose kind is in
    `profile.phonetic_map_kinds` (personal trigger words are always kept), skips
    `profile.safe_words` and duplicate spans, and drops anything `respell()` can't handle.
    Returns [] outright when `profile.phonetic_map == "off"`.
    """
    profile = profile or ReaderProfile()
    if profile.phonetic_map == "off":
        return []
    report = report or analyze(text, profile)

    kinds_wanted = set(profile.phonetic_map_kinds)
    always_kinds = set(profile.phonetic_map_always_kinds)
    safe = {w.lower() for w in profile.safe_words}
    trigger_words = {w.lower() for w in profile.trigger_words}

    seen: set[tuple[int, int]] = set()
    out: list[MapEntry] = []
    for t in report.triggers:
        lw = t.text.lower()
        if lw in safe:
            continue
        is_personal_trigger = t.kind == "personal" and lw in trigger_words
        if t.kind not in kinds_wanted and not is_personal_trigger:
            continue
        span = (t.start, t.end)
        if span in seen:
            continue
        r = respell(t.text, pos=t.pos or None, tag=getattr(t, "tag", "") or None)
        if r is None:
            continue
        seen.add(span)
        always = profile.phonetic_map == "always" or t.kind in always_kinds or is_personal_trigger
        out.append(MapEntry(
            start=t.start, end=t.end, word=t.text,
            respell=r.respell, hint=(t.hint or r.hint or None), kind=t.kind, always=always,
        ))
    out.sort(key=lambda e: e.start)
    return out

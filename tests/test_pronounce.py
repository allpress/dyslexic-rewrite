import json
from pathlib import Path

import pytest

from dyslexic_rewrite.analyze import analyze
from dyslexic_rewrite.profile import ReaderProfile, load_profile
from dyslexic_rewrite.pronounce import _cmu_dict, phonetic_map, respell
from dyslexic_rewrite.render import to_html
from dyslexic_rewrite.rewrite.engine import rewrite

HETERONYMS_PATH = Path(__file__).parent.parent / "src" / "dyslexic_rewrite" / "data" / "heteronyms.json"

# Words in data/heteronyms.json whose two (or more) senses are, per CMUdict, pronounced
# identically -- CMUdict has only ONE pronunciation for the word even though the table
# lists two POS-keyed senses (they were carried over from the broader "same spelling,
# different job" word list, not all of which are true phonetic heteronyms). There is no
# routing table that can make two identical CMUdict entries respell differently, so these
# are a documented skip for the "every heteronym gets two different respellings" check.
SINGLE_PRONUNCIATION_SKIP = {
    "affect", "back", "bank", "bark", "bear", "date", "duck", "entrance", "even", "fly",
    "ground", "house", "kind", "leaves", "left", "light", "like", "long", "match", "mean",
    "number", "park", "plant", "right", "ring", "rock", "row", "saw", "seal", "second",
    "sink", "stalk", "still", "train", "trip", "type", "well",
}


# ---- the worked examples from the spec --------------------------------------------------
@pytest.mark.parametrize(
    "word,pos,tag,expected",
    [
        ("intention", None, None, "in-TEN-shun"),
        ("colonel", None, None, "KER-nul"),
        ("yacht", None, None, "YOT"),
        ("wind", "NOUN", None, "WIND"),
        ("wind", "VERB", None, "WYND"),
        ("tear", "VERB", None, "TAIR"),
        ("tear", "NOUN", None, "TEER"),
        ("read", "VERB", "VBP", "REED"),
        ("read", "VERB", "VBD", "RED"),
        ("photograph", None, None, "FOH-tuh-graf"),
        ("enough", None, None, "ih-NUF"),
        ("knight", None, None, "NYT"),
    ],
)
def test_worked_examples(word, pos, tag, expected):
    r = respell(word, pos=pos, tag=tag)
    assert r is not None
    assert r.respell == expected


def test_unknown_word_returns_none():
    assert respell("zzqxnotaword") is None
    assert respell("") is None


# ---- heteronym table: two senses -> two respellings -------------------------------------
def test_every_heteronym_pair_gets_distinct_respellings():
    data = json.loads(HETERONYMS_PATH.read_text(encoding="utf-8"))["words"]
    d = _cmu_dict()
    assert d is not None, "cmudict must be installed to run this check"
    checked = 0
    for word, entry in data.items():
        pos_keys = [k for k in entry if not k.startswith("_")]
        if len(pos_keys) < 2:
            continue  # only one sense listed: nothing to disambiguate
        prons = d.get(word.lower())
        if not prons or len(prons) < 2:
            assert word in SINGLE_PRONUNCIATION_SKIP, (
                f"{word!r} has < 2 CMUdict pronunciations and is not in the documented skip list"
            )
            continue
        respells = {}
        for pos in pos_keys:
            r = respell(word, pos=pos)
            assert r is not None, f"respell({word!r}, pos={pos!r}) returned None"
            respells[pos] = r.respell
        checked += 1
        assert len(set(respells.values())) > 1, (
            f"{word!r} has {len(pos_keys)} senses but every one respells the same: {respells}"
        )
    assert checked > 20, "sanity check: the heteronym table should have plenty of testable entries"


# ---- phonetic_map() -----------------------------------------------------------------------
def test_phonetic_map_wind_ambiguity():
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    entries = phonetic_map(text)
    respells = {e.respell for e in entries}
    assert respells == {"WYND", "WIND"}
    assert all(e.hint for e in entries)


def test_phonetic_map_respects_safe_words():
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    p = ReaderProfile(safe_words=["wind"])
    assert phonetic_map(text, p) == []


def test_phonetic_map_off():
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    p = ReaderProfile(phonetic_map="off")
    assert phonetic_map(text, p) == []


def test_phonetic_map_dedupes_by_span():
    # "wind" (2nd occurrence) is flagged by both "heteronym" and "ambiguity" -- same token,
    # same char span -- and must appear only once.
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    entries = phonetic_map(text)
    spans = [(e.start, e.end) for e in entries]
    assert len(spans) == len(set(spans))


def test_phonetic_map_personal_always_included():
    p = ReaderProfile(trigger_words=["harvest"], phonetic_map_kinds=["heteronym"])
    entries = phonetic_map("The fields were bare after the harvest.", p)
    assert any(e.word.lower() == "harvest" and e.kind == "personal" and e.always for e in entries)


def test_phonetic_map_uses_report_when_given():
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    profile = ReaderProfile()
    report = analyze(text, profile)
    assert phonetic_map(text, profile, report=report) == phonetic_map(text, profile)


# ---- profile ------------------------------------------------------------------------------
def test_profile_phonetic_map_fields_roundtrip(tmp_path):
    p = ReaderProfile(phonetic_map="always", phonetic_map_kinds=["heteronym"],
                       phonetic_map_always_kinds=["heteronym"])
    path = p.save(tmp_path / "p.json")
    q = load_profile(path)
    assert q.phonetic_map == "always"
    assert q.phonetic_map_kinds == ["heteronym"]
    assert q.phonetic_map_always_kinds == ["heteronym"]


def test_old_profile_json_without_phonetic_map_fields_still_loads(tmp_path):
    old = {"name": "old", "language": "en"}  # no phonetic_map* keys at all
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    p = load_profile(path)
    assert p.phonetic_map == "on_demand"
    assert "heteronym" in p.phonetic_map_kinds
    assert "heteronym" in p.phonetic_map_always_kinds


def test_builtin_profile_phonetic_map_settings():
    assert load_profile("phonological").phonetic_map == "always"
    assert load_profile("visual").phonetic_map == "on_demand"
    attention = load_profile("attention")
    assert attention.phonetic_map == "on_demand"
    assert set(attention.phonetic_map_kinds) == {"heteronym", "ambiguity", "personal"}


# ---- render: ruby/rt + speaker button -----------------------------------------------------
def test_html_contains_phonetic_map_markup():
    profile = load_profile("default")
    res = rewrite("She tried to tear the page, but a tear fell.", profile)
    out = to_html(res, profile, title="t")
    assert "<ruby>" in out and "<rt>" in out
    assert "TEER" in out
    assert "speak-btn" in out
    assert "readAloud" in out
    assert "pmToggle" in out
    assert "phonetic_map_shown" in out


import pytest

from dyslexic_rewrite import analyze, load_profile, rewrite
from dyslexic_rewrite.learn import learn_profile
from dyslexic_rewrite.nlp import get_nlp
from dyslexic_rewrite.profile import BUILTIN_PROFILES, ReaderProfile
from dyslexic_rewrite.protect import check_fidelity, find_protected
from dyslexic_rewrite.render import to_html


def kinds(report, kind):
    return [t for t in report.triggers if t.kind == kind]


# ---- detectors -------------------------------------------------------------------------
def test_heteronym_and_ambiguity_wind():
    text = "Grandpa would wind up the clock. Outside, the wind blows."
    r = analyze(text)
    het = kinds(r, "heteronym")
    assert {t.text for t in het} >= {"wind"}
    amb = kinds(r, "ambiguity")
    assert amb, "second use of 'wind' with a different POS must be flagged"
    assert all(t.text == "wind" for t in amb)
    # a pronunciation hint is carried
    assert any("rhymes" in t.hint for t in het)


def test_phrasal_verb_idiom_vs_literal():
    idiom = analyze("I thought we would wind up at the lake.")
    literal = analyze("Grandpa would wind up the clock before bed.")
    assert kinds(idiom, "phrasal") and kinds(idiom, "phrasal")[0].alternatives[0].startswith("end up")
    assert not kinds(literal, "phrasal"), "'wind up the clock' has a direct object: not the idiom"


def test_phonetic_confusable_pair():
    r = analyze("The form came from the office. It was quite a quiet day.")
    ph = kinds(r, "phonetic")
    flagged = {t.text.lower() for t in ph}
    assert "from" in flagged or "form" in flagged
    assert "quiet" in flagged or "quite" in flagged


def test_rare_and_long_words():
    p = ReaderProfile(min_zipf=3.5, max_word_length=10)
    r = analyze("The committee deliberated over an extraordinarily convoluted proposal.", p)
    assert {t.text for t in kinds(r, "rare")} >= {"deliberated", "convoluted"}
    assert {t.text for t in kinds(r, "long")} >= {"extraordinarily"}


def test_personal_triggers_and_vocab():
    p = ReaderProfile(trigger_words=["harvest"], replacements={"harvest": "crop"}, vocabulary=["convoluted"])
    r = analyze("The fields were bare after the harvest. It was a convoluted plan.", p)
    per = kinds(r, "personal")
    assert per and per[0].alternatives[0] == "crop"
    assert not kinds(r, "rare"), "a word the reader uses themselves is never 'rare' for them"


def test_syntax_flags_long_and_embedded():
    p = ReaderProfile(max_sentence_words=12)
    r = analyze("Mrs. Alvarez, who had lived on Maple Street for forty years, said the pipes would have to go.", p)
    syn = kinds(r, "syntax")
    assert syn and "wedged" in syn[0].reason


# ---- rewriter --------------------------------------------------------------------------
def test_rewrite_defuses_ambiguity_and_keeps_original():
    text = "She tried to tear the page from the book, but a tear ran down her cheek."
    res = rewrite(text)
    assert "rip the page" in res.text
    assert "a tear ran" in res.text            # the noun sense had no safe swap: untouched
    ch = res.all_changes()
    assert ch and ch[0].original == "tear" and ch[0].replacement == "rip"


def test_rewrite_splits_coordinated_and_lifts_relative():
    p = load_profile("attention")
    text = ("Every night Grandpa would wind the clock before bed, and the house would go quiet. "
            "Mrs. Alvarez, who had lived on Maple Street for forty years, said the pipes would have to go.")
    res = rewrite(text, p)
    out = res.text
    assert "before bed. The house would go quiet." in out
    assert "Mrs. Alvarez had lived on Maple Street for forty years. Mrs. Alvarez said" in out


def test_rewrite_leading_because():
    p = ReaderProfile(max_sentence_words=8)
    res = rewrite("Because the storm had knocked out the power, we read by candlelight.", p)
    assert res.text.startswith("The storm had knocked out the power. So we read")


def test_rewrite_trailing_which():
    p = ReaderProfile(max_sentence_words=8)
    res = rewrite("The wind blew across the fields, which had been bare since the harvest.", p)
    assert "fields. They had been bare" in res.text


def test_headings_and_paragraphs_survive():
    text = "The Clock in the Hall\n\nThe old clock stood in the hall. It was tall.\n\nSecond paragraph here."
    res = rewrite(text)
    assert res.paragraphs[0].heading and res.paragraphs[0].text == "The Clock in the Hall"
    assert len(res.paragraphs) == 3
    assert res.paragraphs[1].text.startswith("The old clock")


def test_protected_spans_and_fidelity():
    nlp = get_nlp()
    doc = nlp('Mrs. Alvarez paid $40 on 3 May and said "never again".')
    prot = find_protected(doc)
    texts = {p.text for p in prot}
    assert "Alvarez" in texts or "Mrs. Alvarez" in texts
    assert any("40" in t for t in texts)
    assert check_fidelity(prot, "Someone paid a lot on some day and said nothing.")
    assert not check_fidelity(prot, 'Mrs. Alvarez paid $40 on 3 May and said "never again".')


def test_reading_load_drops_after_rewrite():
    text = open("examples/sample.txt", encoding="utf-8").read()
    res = rewrite(text, load_profile("attention"))
    assert res.stats["load_after"] < res.stats["load_before"]


# ---- profiles & learning ---------------------------------------------------------------
@pytest.mark.parametrize("name", BUILTIN_PROFILES)
def test_builtin_profiles_load(name):
    p = load_profile(name)
    assert p.name == name and p.weight("personal") >= 1.0


def test_profile_roundtrip_and_feedback(tmp_path):
    p = load_profile("default")
    p.add_feedback(["wind", "tear"], safe=["clock"], replacements={"wind": "breeze"})
    path = p.save(tmp_path / "me.json")
    q = load_profile(path)
    assert q.trigger_words == ["wind", "tear"] and q.safe_words == ["clock"] and q.replacements["wind"] == "breeze"


def test_learn_profile_sets_targets():
    short = ["I like short lines. I write like this. It works for me. Keep it plain. One idea per line."] * 6
    p = learn_profile(short, base="default", name="me")
    assert p.name == "me" and p.style.sample_words > 0
    assert 8 <= p.max_sentence_words <= 12
    assert "short" in p.vocabulary and "plain" in p.vocabulary
    assert p.weights["syntax"] >= 1.2


# ---- render ----------------------------------------------------------------------------
def test_html_contains_changes_and_feedback_hooks():
    res = rewrite("She tried to tear the page, but a tear fell.", load_profile("default"))
    html = to_html(res, load_profile("default"), title="t")
    assert 'class="w chg"' in html and 'data-orig="tear"' in html
    assert "Export feedback" in html and "dysrewrite-feedback.json" in html


# ---- learn: json export + privacy ---------------------------------------------------------
def test_learn_from_json_export_keeps_no_content(tmp_path):
    import json as _json

    from dyslexic_rewrite.learn import analyze_style
    posts = [
        {"date": "May 1, 2026", "body": "Finished the bookcase today!! It took forever but I love how it turned out. Doug helped with the trim."},
        {"date": "May 2, 2026", "body": "Okay so the paint is drying and I can't stop looking at it... Zephyrina came over and said it looks amazing."},
        {"date": "May 3, 2026", "body": "Is it weird that I want to redo the hallway now? Asking for a friend (me). Visit https://example.com/plan for pics."},
    ] * 4
    f = tmp_path / "posts.json"
    f.write_text(_json.dumps({"items": posts}), encoding="utf-8")
    from dyslexic_rewrite.io import read_text
    text = read_text(f)
    assert text.count("\n\n") == len(posts) - 1
    rep = analyze_style([text])
    d = rep.to_dict()
    blob = _json.dumps(d)
    # no sentences, names, URLs or numbers from the sample survive in the report
    for leak in ("bookcase today", "Doug", "Zephyrina", "example.com", "May 1"):
        assert leak not in blob
    assert rep.sample_sentences >= 12 and rep.exclamation_rate > 0 and rep.question_rate > 0
    assert "and" in rep.connectives
    p = learn_profile([text], name="t", report=rep)
    assert "zephyrina" not in p.vocabulary and "doug" not in p.vocabulary
    assert "bookcase" in p.vocabulary


def test_semicolon_split_keeps_full_stop_after_flagged_word():
    p = ReaderProfile(min_zipf=3.5)
    res = rewrite("First with brooms, then with dusters; then on ladders and steps and chairs, "
                  "with a brush and a pail of whitewash; till he had dust in his throat.", p)
    assert "dusters. Then on ladders" in res.text and "whitewash. Till" in res.text

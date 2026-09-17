"""Learn a reader profile from how they write (and, via a transcript, how they speak).

The idea: a sentence shaped like the reader's own sentences costs them less to read.
So we measure their natural sentence length, clause depth, use of passive voice, the
frequency band of the words they reach for, and their habits (how sentences start, which
connectives they use, punctuation), then set the rewriter's targets to match.

PRIVACY BY CONSTRUCTION. Nothing here stores a sentence, a phrase, a name, a number, or
a URL from the sample. The output is aggregate metadata only:
  - counts and distributions (sentence lengths, clause depth, passive rate ...)
  - single lowercase common words with their counts (vocabulary, sentence starters,
    connectives) — proper nouns, numbers, emails and URLs are never kept
  - punctuation and emoji *rates*, not the emoji themselves
After `learn` has run, the raw sample can be deleted; the profile does not need it.

Input: any text they wrote — posts, emails, messages, a transcript of them talking.
300+ words gives a stable picture; a few thousand is better.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .nlp import get_nlp, is_content, zipf
from .profile import ReaderProfile, StyleTargets, load_profile
from .triggers.syntax import _finite_clauses, _has_passive

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF]")
_CONNECTIVES = {
    "and", "but", "so", "because", "although", "though", "while", "if", "when", "then", "since",
    "however", "also", "plus", "yet", "or", "unless", "until", "after", "before", "once", "as",
}


@dataclass
class StyleReport:
    """Aggregate, content-free description of how someone writes."""

    sample_words: int = 0
    sample_sentences: int = 0
    sample_paragraphs: int = 0

    # sentence shape
    sentence_words_median: float = 0.0
    sentence_words_p25: float = 0.0
    sentence_words_p75: float = 0.0
    sentence_words_p90: float = 0.0
    sentence_words_max: int = 0
    short_sentence_rate: float = 0.0     # <= 6 words
    long_sentence_rate: float = 0.0      # >= 20 words
    clauses_per_sentence: float = 0.0
    passive_rate: float = 0.0
    centre_embedded_rate: float = 0.0    # clause wedged between subject and verb
    subject_first_rate: float = 0.0      # sentence starts with its grammatical subject
    fragment_rate: float = 0.0           # sentence with no main verb
    question_rate: float = 0.0
    exclamation_rate: float = 0.0
    multi_exclaim_rate: float = 0.0      # "!!" or more
    ellipsis_rate: float = 0.0
    parenthetical_rate: float = 0.0
    comma_per_sentence: float = 0.0

    # words
    word_length_mean: float = 0.0
    word_zipf_median: float = 0.0
    rare_word_rate: float = 0.0          # zipf < 3.3
    long_word_rate: float = 0.0          # > 9 letters
    contraction_rate: float = 0.0        # per sentence
    first_person_rate: float = 0.0       # I/me/my/we/our per 100 words
    emoji_per_sentence: float = 0.0
    caps_word_rate: float = 0.0          # SHOUTED words per 100 words
    type_token_ratio: float = 0.0

    # habits (single common words + counts, nothing else)
    sentence_starters: dict[str, int] = field(default_factory=dict)
    connectives: dict[str, int] = field(default_factory=dict)
    pos_sequence_top: dict[str, int] = field(default_factory=dict)   # e.g. "PRON VERB ADV"
    heteronyms_used: dict[str, int] = field(default_factory=dict)    # trigger-table words they write themselves

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def analyze_style(samples: list[str], language: str = "en") -> StyleReport:
    """Measure a writer. Returns aggregate metadata only — see the module docstring."""
    from .nlp import load_data

    nlp = get_nlp(language)
    het_words = set(load_data("heteronyms.json")["words"].keys())
    text = "\n\n".join(s.strip() for s in samples if s.strip())
    n_paras = sum(1 for p in re.split(r"\n\s*\n", text) if p.strip())
    doc = nlp(text)

    r = StyleReport(sample_paragraphs=n_paras)
    lens: list[int] = []
    clauses: list[int] = []
    n = 0
    passives = embedded = subj_first = fragments = questions = exclaims = multi = ellipses = parens = 0
    commas = contractions = 0
    emoji = 0
    vocab: Counter = Counter()
    starters: Counter = Counter()
    conns: Counter = Counter()
    posseq: Counter = Counter()
    hets: Counter = Counter()
    word_lens: list[int] = []
    zipfs: list[float] = []
    n_words = rare = longw = first_person = caps = 0
    types: set[str] = set()

    for sent in doc.sents:
        words = [t for t in sent if t.is_alpha]
        if not words:
            continue
        n += 1
        lens.append(len(words))
        clauses.append(_finite_clauses(sent))
        passives += int(_has_passive(sent))
        root = sent.root
        subj = next((t for t in root.children if t.dep_ in ("nsubj", "nsubjpass")), None)
        if subj is not None and any(c.dep_ == "relcl" and c.i < root.i for c in subj.children):
            embedded += 1
        first_alpha = words[0]
        if subj is not None and first_alpha.i >= subj.left_edge.i and first_alpha.i <= subj.right_edge.i:
            subj_first += 1
        if root.pos_ not in ("VERB", "AUX"):
            fragments += 1
        st = sent.text
        questions += int("?" in st)
        exclaims += int("!" in st)
        multi += int("!!" in st)
        ellipses += int("..." in st or "…" in st)
        parens += int("(" in st and ")" in st)
        commas += st.count(",")
        emoji += len(_EMOJI_RE.findall(st))
        contractions += sum(1 for t in sent if t.text.startswith("'") or t.text.startswith("’")) \
            + len(re.findall(r"\b\w+n[’']t\b", st))
        starters[first_alpha.lower_] += 1
        posseq[" ".join(t.pos_ for t in words[:3])] += 1
        for t in words:
            n_words += 1
            lw = t.lower_
            types.add(lw)
            word_lens.append(len(t.text))
            if t.pos_ != "PROPN":
                z = zipf(lw, language)
                if z > 0:
                    zipfs.append(z)
                    rare += int(z < 3.3)
            longw += int(len(t.text) > 9)
            if lw in ("i", "me", "my", "mine", "we", "us", "our"):
                first_person += 1
            if t.text.isupper() and len(t.text) >= 3:
                caps += 1
            if lw in _CONNECTIVES:
                conns[lw] += 1
            if lw in het_words:
                hets[lw] += 1
            if is_content(t) and t.pos_ != "PROPN":
                vocab[t.lemma_.lower()] += 1

    if n == 0:
        raise ValueError("No usable sentences in the samples.")

    r.sample_words = n_words
    r.sample_sentences = n
    r.sentence_words_median = float(statistics.median(lens))
    r.sentence_words_p25 = _pct(lens, 0.25)
    r.sentence_words_p75 = _pct(lens, 0.75)
    r.sentence_words_p90 = _pct(lens, 0.90)
    r.sentence_words_max = max(lens)
    r.short_sentence_rate = sum(1 for x in lens if x <= 6) / n
    r.long_sentence_rate = sum(1 for x in lens if x >= 20) / n
    r.clauses_per_sentence = float(statistics.mean(clauses))
    r.passive_rate = passives / n
    r.centre_embedded_rate = embedded / n
    r.subject_first_rate = subj_first / n
    r.fragment_rate = fragments / n
    r.question_rate = questions / n
    r.exclamation_rate = exclaims / n
    r.multi_exclaim_rate = multi / n
    r.ellipsis_rate = ellipses / n
    r.parenthetical_rate = parens / n
    r.comma_per_sentence = commas / n
    r.word_length_mean = float(statistics.mean(word_lens)) if word_lens else 0.0
    r.word_zipf_median = float(statistics.median(zipfs)) if zipfs else 4.6
    r.rare_word_rate = rare / max(1, len(zipfs))
    r.long_word_rate = longw / max(1, n_words)
    r.contraction_rate = contractions / n
    r.first_person_rate = 100.0 * first_person / max(1, n_words)
    r.emoji_per_sentence = emoji / n
    r.caps_word_rate = 100.0 * caps / max(1, n_words)
    r.type_token_ratio = len(types) / max(1, n_words)
    # keep only *common* single words as habits: a word must appear 3+ times and be a
    # dictionary word (zipf > 0) so nothing personal (names, handles, places) survives
    r.sentence_starters = {w: c for w, c in starters.most_common(40) if c >= 3 and zipf(w, language) > 2.5}
    r.connectives = dict(conns.most_common(20))
    r.pos_sequence_top = dict(posseq.most_common(15))
    r.heteronyms_used = dict(hets.most_common(40))
    r._vocab = vocab  # type: ignore[attr-defined]  # consumed by learn_profile, not serialised
    return r


def learn_profile(samples: list[str], base: ReaderProfile | str | None = None,
                  name: str = "personal", report: StyleReport | None = None) -> ReaderProfile:
    profile = base if isinstance(base, ReaderProfile) else load_profile(base or "default")
    r = report or analyze_style(samples, profile.language)
    vocab: Counter = getattr(r, "_vocab", Counter())

    style = StyleTargets(
        median_sentence_words=r.sentence_words_median,
        p75_sentence_words=r.sentence_words_p75,
        passive_rate=r.passive_rate,
        clause_depth=r.clauses_per_sentence,
        median_zipf=r.word_zipf_median,
        sample_words=r.sample_words,
    )

    p = ReaderProfile.from_dict(profile.to_dict())
    p.name = name
    p.description = (f"Personal profile learned from {style.sample_words} words of the reader's own writing "
                     f"(base: {profile.name}). Contains aggregate style metadata only.")
    p.style = style
    # Targets: the reader's own 75th-percentile sentence length is a comfortable ceiling,
    # clamped so a very terse or very florid writer still gets sane behaviour.
    p.max_sentence_words = int(max(8, min(28, round(style.p75_sentence_words))))
    # Words rarer than the reader's own typical word by a margin are "rare" for them.
    p.min_zipf = float(max(2.8, min(4.2, round(style.median_zipf - 1.1, 2))))
    # If they rarely write passives, straighten them harder.
    if style.passive_rate < 0.05:
        p.weights["syntax"] = max(p.weights.get("syntax", 1.0), 1.2)
    # If they write short clauses, weigh sentence shape more.
    if style.clause_depth < 1.4:
        p.weights["syntax"] = max(p.weights.get("syntax", 1.0), 1.3)
    # If they almost never wedge a clause between subject and verb, lifting those matters more.
    if r.centre_embedded_rate < 0.02:
        p.weights["syntax"] = max(p.weights.get("syntax", 1.0), 1.3)
    # Heteronyms they use comfortably themselves are lower-risk for them.
    p.safe_words = sorted(set(p.safe_words) | {w for w, c in r.heteronyms_used.items() if c >= 5})
    # vocabulary: common dictionary lemmas only (2+ uses), never proper nouns
    p.vocabulary = sorted(w for w, c in vocab.items() if c >= 2 and zipf(w, profile.language) > 0)
    return p


def learn_from_files(paths: list[str | Path], base: str | None = None, name: str = "personal"):
    from .io import read_text
    samples = [read_text(p) for p in paths]
    report = analyze_style(samples)
    return learn_profile(samples, base=base, name=name, report=report), report


def transcribe(audio_path: str | Path, language: str = "en") -> str:
    """Speech -> text with faster-whisper (optional extra, runs locally)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise SystemExit("Speech input needs faster-whisper: pip install 'dyslexic-rewrite[speech]'") from e
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=language)
    return " ".join(s.text.strip() for s in segments)

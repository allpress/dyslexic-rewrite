"""Learn a reader profile from how they write (and, via a transcript, how they speak).

The idea: a sentence shaped like the reader's own sentences costs them less to read.
So we measure their natural sentence length, clause depth, use of passive voice, and
the frequency band of the words they reach for, then set the rewriter's targets to match.
Their vocabulary is stored so that alternatives they already use rank first, and words
they use are never treated as "rare" for them.

Input: any text they wrote — emails, messages, journal entries, a transcript of them
talking. More is better; 300+ words gives a stable picture. Everything stays local.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

from .nlp import get_nlp, is_content, zipf
from .profile import ReaderProfile, StyleTargets, load_profile
from .triggers.syntax import _finite_clauses, _has_passive


def learn_profile(samples: list[str], base: ReaderProfile | str | None = None,
                  name: str = "personal") -> ReaderProfile:
    profile = base if isinstance(base, ReaderProfile) else load_profile(base or "default")
    nlp = get_nlp(profile.language)
    text = "\n\n".join(s.strip() for s in samples if s.strip())
    doc = nlp(text)

    sent_lens, clause_counts, passives = [], [], 0
    vocab = Counter()
    zipfs = []
    n_sents = 0
    for sent in doc.sents:
        words = [t for t in sent if t.is_alpha]
        if len(words) < 2:
            continue
        n_sents += 1
        sent_lens.append(len(words))
        clause_counts.append(_finite_clauses(sent))
        passives += int(_has_passive(sent))
        for t in words:
            if is_content(t) and t.pos_ != "PROPN":
                vocab[t.lemma_.lower()] += 1
                z = zipf(t.lower_, profile.language)
                if z > 0:
                    zipfs.append(z)

    if not sent_lens:
        raise ValueError("No usable sentences in the samples.")

    q = statistics.quantiles(sent_lens, n=4) if len(sent_lens) >= 4 else [sent_lens[0]] * 3
    style = StyleTargets(
        median_sentence_words=float(statistics.median(sent_lens)),
        p75_sentence_words=float(q[2]),
        passive_rate=passives / n_sents,
        clause_depth=float(statistics.mean(clause_counts)),
        median_zipf=float(statistics.median(zipfs)) if zipfs else 4.6,
        sample_words=sum(sent_lens),
    )

    p = ReaderProfile.from_dict(profile.to_dict())
    p.name = name
    p.description = (f"Personal profile learned from {style.sample_words} words of the reader's own writing "
                     f"(base: {profile.name}).")
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
    p.vocabulary = sorted(w for w, c in vocab.items() if c >= 1)
    return p


def learn_from_files(paths: list[str | Path], base: str | None = None, name: str = "personal") -> ReaderProfile:
    from .io import read_text
    samples = [read_text(p) for p in paths]
    return learn_profile(samples, base=base, name=name)


def transcribe(audio_path: str | Path, language: str = "en") -> str:
    """Speech -> text with faster-whisper (optional extra, runs locally)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise SystemExit("Speech input needs faster-whisper: pip install 'dyslexic-rewrite[speech]'") from e
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=language)
    return " ".join(s.text.strip() for s in segments)

"""Sentence-shape detector.

Flags sentences whose *structure* costs working memory: too many words, passive voice,
relative clauses jammed between subject and verb (centre-embedding), long chains of
clauses. These are the sentences the rewriter will split or straighten.
"""

from __future__ import annotations

from .base import Trigger


def _finite_clauses(sent) -> int:
    n = 0
    for t in sent:
        if t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX"):
            n += 1
        elif t.dep_ in ("ccomp", "advcl", "relcl", "conj") and t.pos_ in ("VERB", "AUX"):
            n += 1
    return max(1, n)


def _has_passive(sent) -> bool:
    return any(t.dep_ in ("nsubjpass", "auxpass") for t in sent)


def _centre_embedded(sent) -> bool:
    """A relative clause hanging off the subject, before the main verb."""
    root = sent.root
    for t in sent:
        if t.dep_ in ("nsubj", "nsubjpass") and t.head == root:
            for c in t.children:
                if c.dep_ == "relcl" and c.i < root.i:
                    return True
    return False


def detect_syntax(doc, profile) -> list[Trigger]:
    out = []
    for si, sent in enumerate(doc.sents):
        words = [t for t in sent if t.is_alpha or t.like_num]
        n = len(words)
        problems = []
        score = 0.0
        if n > profile.max_sentence_words:
            over = n - profile.max_sentence_words
            problems.append(f"{n} words (target ≤ {profile.max_sentence_words})")
            score += min(0.6, 0.25 + over * 0.02)
        clauses = _finite_clauses(sent)
        if clauses >= 3:
            problems.append(f"{clauses} clauses")
            score += 0.2
        if _centre_embedded(sent):
            problems.append("a clause wedged between the subject and its verb")
            score += 0.3
        if _has_passive(sent):
            problems.append("passive voice")
            score += 0.15
        if not problems:
            continue
        out.append(Trigger(
            kind="syntax", sent_index=si,
            start=sent.start_char, end=sent.end_char, text=sent.text,
            reason="sentence shape: " + ", ".join(problems),
            score=min(1.0, score),
        ))
    return out

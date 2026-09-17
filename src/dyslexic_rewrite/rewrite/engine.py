"""Orchestrates: analyze -> protect -> rewrite each paragraph -> RewriteResult."""

from __future__ import annotations

import re
import sys

from ..analyze import analyze, Report
from ..profile import ReaderProfile
from ..protect import find_protected
from .model import Paragraph, RewriteResult, SentenceRewrite
from .rules import rewrite_sentence

_PARA_RE = re.compile(r"\n\s*\n")


def _paragraph_bounds(text: str) -> list[tuple[int, int]]:
    bounds, last = [], 0
    for m in _PARA_RE.finditer(text):
        if text[last:m.start()].strip():
            bounds.append((last, m.start()))
        last = m.end()
    if text[last:].strip():
        bounds.append((last, len(text)))
    return bounds or [(0, len(text))]


def _looks_like_heading(s: str) -> bool:
    s = s.strip()
    return bool(s) and len(s.split()) <= 8 and not s.endswith(('.', '!', '?', ',', ';', ':')) and "\n" not in s


def rewrite(text: str, profile: ReaderProfile | None = None, engine: str = "rules",
            simplify_vocab: bool = False, report: Report | None = None, verbose: bool = False) -> RewriteResult:
    profile = profile or ReaderProfile()
    report = report or analyze(text, profile)
    doc = report.doc
    protected = find_protected(doc)
    sents = list(doc.sents)
    trig_by_sent: dict[int, list] = {}
    for t in report.triggers:
        trig_by_sent.setdefault(t.sent_index, []).append(t)

    paragraphs: list[Paragraph] = []
    llm_used = llm_fallback = 0
    for (p_start, p_end) in _paragraph_bounds(text):
        p_sents = [(i, s) for i, s in enumerate(sents) if s.start_char >= p_start and s.start_char < p_end]
        if not p_sents:
            continue
        heading = _looks_like_heading(text[p_start:p_end])
        rewritten: list[SentenceRewrite] = []
        if heading:
            for i, s in p_sents:
                rewritten.append(SentenceRewrite(index=i, original=s.text, segments=[("text", s.text)]))
            paragraphs.append(Paragraph(rewritten, heading=True))
            continue

        if engine == "llm":
            from .llm import rewrite_paragraph_llm, diff_segments
            p_text = text[p_start:p_end].strip()
            p_trig = [t for i, _ in p_sents for t in trig_by_sent.get(i, [])]
            p_prot = [p for p in protected if p.start >= p_start and p.end <= p_end]
            out = None
            try:
                out = rewrite_paragraph_llm(p_text, p_trig, profile, p_prot)
            except Exception as e:  # network / model errors -> fall back
                if verbose:
                    print(f"[llm] {e}", file=sys.stderr)
            if out:
                llm_used += 1
                paragraphs.append(Paragraph([diff_segments(p_text, out, p_sents[0][0])]))
                continue
            llm_fallback += 1

        for i, s in p_sents:
            rewritten.append(rewrite_sentence(s, i, trig_by_sent.get(i, []), profile, protected,
                                              simplify_vocab=simplify_vocab))
        paragraphs.append(Paragraph(rewritten))

    result = RewriteResult(paragraphs=paragraphs, profile_name=profile.name, engine=engine)
    changes = result.all_changes()
    result.stats = {
        "sentences": len(sents),
        "sentences_changed": sum(1 for p in paragraphs for s in p.sentences if s.changed),
        "changes": len(changes),
        "changes_by_kind": _count(c.kind for c in changes),
        "triggers_found": len(report.triggers),
        "load_before": round(report.load(), 2),
        "llm_paragraphs": llm_used,
        "llm_fallbacks": llm_fallback,
    }
    # load after: re-analyze the rewritten text (cheap enough for a chapter)
    try:
        after = analyze(result.text, profile)
        result.stats["load_after"] = round(after.load(), 2)
    except Exception:
        pass
    return result


def _count(it):
    d: dict[str, int] = {}
    for k in it:
        d[k] = d.get(k, 0) + 1
    return d

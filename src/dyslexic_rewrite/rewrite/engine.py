"""Orchestrates: analyze -> protect -> rewrite each paragraph -> RewriteResult."""

from __future__ import annotations

import re
import sys

from ..analyze import Report, analyze
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
            simplify_vocab: bool = False, report: Report | None = None, verbose: bool = False,
            llm_cache=None) -> RewriteResult:
    """`llm_cache`, when `engine == "llm"`, is an optional paragraph cache (see
    `rewrite.llm.ParagraphCacheProtocol`) -- `server/cache.py` supplies a Postgres-backed one so
    a re-run of the same text under the same profile calls the model for nothing."""
    profile = profile or ReaderProfile()
    report = report or analyze(text, profile)
    doc = report.doc
    protected = find_protected(doc)
    sents = list(doc.sents)
    trig_by_sent: dict[int, list] = {}
    for t in report.triggers:
        trig_by_sent.setdefault(t.sent_index, []).append(t)

    plans = []
    for (p_start, p_end) in _paragraph_bounds(text):
        p_sents = [(i, s) for i, s in enumerate(sents) if p_start <= s.start_char < p_end]
        if not p_sents:
            continue
        plans.append({
            "start": p_start, "end": p_end, "sents": p_sents,
            "heading": _looks_like_heading(text[p_start:p_end]),
        })

    # For the LLM engine, every non-heading paragraph is dispatched together (concurrently, in
    # a thread pool -- see rewrite.llm.rewrite_paragraphs_llm) before the main assembly loop
    # below, so a slow network round-trip for one paragraph doesn't serialise the whole book.
    llm_outcomes: dict[int, object] = {}
    if engine == "llm":
        from .llm import rewrite_paragraphs_llm
        jobs = []
        job_plan_idx = []
        for idx, plan in enumerate(plans):
            if plan["heading"]:
                continue
            p_text = text[plan["start"]:plan["end"]].strip()
            p_trig = [t for i, _ in plan["sents"] for t in trig_by_sent.get(i, [])]
            p_prot = [p for p in protected if p.start >= plan["start"] and p.end <= plan["end"]]
            jobs.append((p_text, p_trig, p_prot))
            job_plan_idx.append(idx)
        try:
            outcomes = rewrite_paragraphs_llm(jobs, profile, cache=llm_cache) if jobs else []
        except Exception as e:  # pragma: no cover -- rewrite_paragraphs_llm already catches per-job
            if verbose:
                print(f"[llm] {e}", file=sys.stderr)
            outcomes = [None] * len(jobs)
        llm_outcomes = dict(zip(job_plan_idx, outcomes, strict=True))

    paragraphs: list[Paragraph] = []
    llm_used = llm_fallback = 0
    llm_rejections: dict[str, int] = {}
    llm_usage_totals: dict[str, int] = {}
    llm_cost_total = 0.0
    if engine == "llm":
        from .llm import diff_segments, usage_cost_usd

    for idx, plan in enumerate(plans):
        p_sents = plan["sents"]
        if plan["heading"]:
            rewritten = [SentenceRewrite(index=i, original=s.text, segments=[("text", s.text)])
                        for i, s in p_sents]
            paragraphs.append(Paragraph(rewritten, heading=True))
            continue

        if engine == "llm":
            outcome = llm_outcomes.get(idx)
            p_text = text[plan["start"]:plan["end"]].strip()
            if outcome is not None:
                if outcome.usage:
                    for k, v in outcome.usage.items():
                        llm_usage_totals[k] = llm_usage_totals.get(k, 0) + v
                    llm_cost_total += usage_cost_usd(outcome.usage)
                if outcome.text:
                    llm_used += 1
                    paragraphs.append(Paragraph([diff_segments(p_text, outcome.text, p_sents[0][0])]))
                    continue
                reason = outcome.rejection or (f"error:{outcome.error}" if outcome.error else "unknown")
                llm_rejections[reason] = llm_rejections.get(reason, 0) + 1
            llm_fallback += 1

        rewritten = []
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
    if engine == "llm":
        result.stats["llm_rejections"] = llm_rejections
        if llm_usage_totals:
            result.stats["llm_usage"] = llm_usage_totals
            result.stats["llm_cost_usd"] = round(llm_cost_total, 6)
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

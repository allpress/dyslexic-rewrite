"""Optional LLM engine. Off by default; free by default.

Talks to any OpenAI-compatible chat endpoint. The default is a local Ollama server
(http://localhost:11434/v1), so nothing leaves the machine and nothing costs money.
Set DYSREWRITE_LLM_BASE_URL / DYSREWRITE_LLM_MODEL / DYSREWRITE_LLM_API_KEY to point
elsewhere.

Safety net: every paragraph the model returns is checked against the protected spans
(names, numbers, quotes). If anything is missing, or the length drifts too far, we throw
the model's answer away and keep the rule-based rewrite for that paragraph.
"""

from __future__ import annotations

import difflib
import json
import os
import re

from ..protect import Protected, check_fidelity
from ..triggers.base import Trigger
from .model import Change, SentenceRewrite

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:8b"

SYSTEM_PROMPT = """You rewrite text for a reader with dyslexia. Your job is to make each sentence easier to decode WITHOUT changing what it says.

Rules, in priority order:
1. Keep every fact, name, number, date, quotation and technical term exactly. Never summarise, never drop a sentence, never add information.
2. The words listed as TRIGGERS stop this reader cold. Replace each one with a plain, common word that means the same thing in that sentence. If a trigger word is re-used nearby with a different meaning, make sure the two uses no longer share a spelling.
3. Keep sentences short: at most {max_words} words. Split long sentences. Put the subject first, then the verb, then the rest. Prefer active voice.
4. Do not put a clause between a subject and its verb. Move it to its own sentence.
5. Use words the reader already uses when possible (READER VOCABULARY). Avoid rare words.
6. Keep the reader's dignity: do not make the text childish. Same register, same tone, same paragraph.
7. Output ONLY the rewritten paragraph. No preface, no notes, no quotes around it."""


def _client():
    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("The LLM engine needs httpx: pip install 'dyslexic-rewrite[llm]'") from e
    base = os.environ.get("DYSREWRITE_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    key = os.environ.get("DYSREWRITE_LLM_API_KEY", "ollama")
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=120)


def rewrite_paragraph_llm(paragraph: str, triggers: list[Trigger], profile, protected: list[Protected],
                          model: str | None = None) -> str | None:
    """Return the model's rewrite, or None if it failed the fidelity check."""
    model = model or os.environ.get("DYSREWRITE_LLM_MODEL", DEFAULT_MODEL)
    trig_lines = []
    seen = set()
    for t in triggers:
        if t.kind == "syntax" or t.text.lower() in seen:
            continue
        seen.add(t.text.lower())
        alt = f" (try: {', '.join(t.alternatives[:3])})" if t.alternatives else ""
        trig_lines.append(f"- {t.text}: {t.reason}{alt}")
    vocab = ", ".join(sorted(profile.vocab_set())[:200]) or "(none provided)"
    user = (
        "TRIGGERS:\n" + ("\n".join(trig_lines) if trig_lines else "- (none)") +
        f"\n\nREADER VOCABULARY: {vocab}\n\nPARAGRAPH:\n{paragraph}"
    )
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(max_words=profile.max_sentence_words)},
            {"role": "user", "content": user},
        ],
    }
    with _client() as c:
        r = c.post("/chat/completions", content=json.dumps(body), headers={"Content-Type": "application/json"})
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"].strip()
    out = re.sub(r"^```.*?\n|\n```$", "", out, flags=re.S).strip().strip('"')
    # fidelity gates
    ratio = len(out) / max(1, len(paragraph))
    if ratio < 0.6 or ratio > 1.6:
        return None
    if check_fidelity(protected, out):
        return None
    return out


_WORD_RE = re.compile(r"\w+|[^\w\s]|\s+")


def diff_segments(original: str, rewritten: str, index: int) -> SentenceRewrite:
    """Turn (original, rewritten) into segments so the reader view can show what changed."""
    a = _WORD_RE.findall(original)
    b = _WORD_RE.findall(rewritten)
    sm = difflib.SequenceMatcher(a=[x.lower() for x in a], b=[x.lower() for x in b], autojunk=False)
    segs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            segs.append(("text", "".join(b[j1:j2])))
        else:
            orig = "".join(a[i1:i2]).strip()
            repl = "".join(b[j1:j2])
            if not repl.strip():
                continue
            segs.append(("change", Change(original=orig or "(added)", replacement=repl, kind="llm",
                                          reason="rewritten by the language model")))
    return SentenceRewrite(index=index, original=original, segments=segs, engine="llm")

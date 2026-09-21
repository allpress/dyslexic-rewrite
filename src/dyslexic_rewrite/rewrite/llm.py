"""Optional LLM engine. Off by default; free by default.

Talks to any OpenAI-compatible chat endpoint. The default is a local Ollama server
(http://localhost:11434/v1), so nothing leaves the machine and nothing costs money.
Set DYSREWRITE_LLM_BASE_URL / DYSREWRITE_LLM_MODEL / DYSREWRITE_LLM_API_KEY to point
elsewhere -- the documented cheap option is DeepSeek (docs/RESEARCH.md, section 4).

Safety net: every paragraph the model returns goes through a fidelity gate (protected
spans, length ratio, sentence count, no new proper nouns) and an output-format cleanup
(strip prefaces/quotes/meta-comments) before it is accepted. Anything that fails is
thrown away and the rule-based rewrite is kept for that paragraph instead -- a rewrite
that changes a fact is a bug at any price.

Config (all optional; sane defaults for local Ollama):
    DYSREWRITE_LLM_BASE_URL         default http://localhost:11434/v1
    DYSREWRITE_LLM_MODEL            default llama3.1:8b
    DYSREWRITE_LLM_API_KEY          default "ollama" (Ollama ignores it)
    DYSREWRITE_LLM_MAX_CONCURRENCY  default 4 -- paragraphs are rewritten in a thread pool
    DYSREWRITE_LLM_TIMEOUT          default 90 (seconds, per HTTP request)
    DYSREWRITE_LLM_MAX_RETRIES      default 3 -- exponential backoff on 429/5xx/timeouts,
                                     honouring a numeric `Retry-After` header when present
    DYSREWRITE_LLM_PRICE_IN         $ per 1M input tokens, for cost estimates/accounting.
    DYSREWRITE_LLM_PRICE_OUT        $ per 1M output tokens.
                                     Both default to DeepSeek flash's off-peak price
                                     (0.15 / 0.60) when the base URL contains "deepseek",
                                     else 0 (unknown provider -- cost reporting is opt-in).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from ..nlp import get_nlp
from ..profile import ReaderProfile
from ..protect import Protected, check_fidelity
from ..triggers.base import Trigger
from .model import Change, SentenceRewrite

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:8b"

DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_TIMEOUT = 90.0
DEFAULT_MAX_RETRIES = 3

# DeepSeek `deepseek-flash` off-peak pricing, $ per 1M tokens (docs/RESEARCH.md, section 4,
# checked 2026-09-18). The cached-input rate is about 2% of the miss rate; we apply that
# ratio to whichever DYSREWRITE_LLM_PRICE_IN is configured, but only for a DeepSeek base URL
# -- we don't know another provider's cache economics, so a non-DeepSeek prompt-cache split
# (if one is ever returned) is costed at the plain input price instead.
_DEEPSEEK_PRICE_IN = 0.15
_DEEPSEEK_PRICE_OUT = 0.60
_DEEPSEEK_CACHE_DISCOUNT = 0.02

# Bumped whenever the prompt (system or the fixed per-reader block) changes shape, so the
# paragraph cache (server/cache.py) naturally misses instead of serving a stale-format answer.
PROMPT_VERSION = "2"

# Test hook: set this to an httpx.BaseTransport (typically httpx.MockTransport) to bypass the
# network entirely. Tests `import` this module and set the attribute directly; production code
# never touches it. Left as None, httpx uses its normal transport.
DYSREWRITE_LLM_TRANSPORT: Any = None

SYSTEM_PROMPT = """You rewrite text for a reader with dyslexia. Your job is to make each sentence easier to decode WITHOUT changing what it says.

Rules, in priority order:
1. Keep every fact, name, number, date, quotation and technical term exactly. Never summarise, never drop a sentence, never add information.
2. The words listed as TRIGGERS stop this reader cold. Replace each one with a plain, common word that means the same thing in that sentence. If a trigger word is re-used nearby with a different meaning, make sure the two uses no longer share a spelling.
3. Keep sentences short: at most {max_words} words. Split long sentences. Put the subject first, then the verb, then the rest. Prefer active voice.
4. Do not put a clause between a subject and its verb. Move it to its own sentence.
5. Use words the reader already uses when possible (READER VOCABULARY). Avoid rare words.
6. Keep the reader's dignity: do not make the text childish. Same register, same tone, same paragraph.
7. Output ONLY the rewritten paragraph. No preface, no notes, no quotes around it, and no comment about having rewritten anything."""


# -----------------------------------------------------------------------------------------
# config
# -----------------------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def base_url() -> str:
    return os.environ.get("DYSREWRITE_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def model_name() -> str:
    return os.environ.get("DYSREWRITE_LLM_MODEL", DEFAULT_MODEL)


def max_concurrency() -> int:
    return max(1, _env_int("DYSREWRITE_LLM_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY))


def timeout_seconds() -> float:
    return _env_float("DYSREWRITE_LLM_TIMEOUT", DEFAULT_TIMEOUT)


def max_retries() -> int:
    return max(0, _env_int("DYSREWRITE_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES))


def price_per_million() -> tuple[float, float]:
    """($ per 1M input tokens, $ per 1M output tokens) -- DeepSeek defaults when the
    configured base URL looks like DeepSeek's, else 0/0 (no cost claimed for an unknown
    provider unless the reader configures prices themselves)."""
    is_deepseek = "deepseek" in base_url().lower()
    default_in = _DEEPSEEK_PRICE_IN if is_deepseek else 0.0
    default_out = _DEEPSEEK_PRICE_OUT if is_deepseek else 0.0
    return _env_float("DYSREWRITE_LLM_PRICE_IN", default_in), _env_float("DYSREWRITE_LLM_PRICE_OUT", default_out)


def _client():
    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("The LLM engine needs httpx: pip install 'dyslexic-rewrite[llm]'") from e
    key = os.environ.get("DYSREWRITE_LLM_API_KEY", "ollama")
    kwargs: dict[str, Any] = {}
    if DYSREWRITE_LLM_TRANSPORT is not None:
        kwargs["transport"] = DYSREWRITE_LLM_TRANSPORT
    return httpx.Client(base_url=base_url(), headers={"Authorization": f"Bearer {key}"},
                        timeout=timeout_seconds(), **kwargs)


# -----------------------------------------------------------------------------------------
# HTTP with retries
# -----------------------------------------------------------------------------------------
def _backoff_seconds(attempt: int) -> float:
    return min(0.5 * (2 ** attempt), 8.0)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # an HTTP-date Retry-After -- fall back to exponential backoff


def _post_with_retries(client, body: dict) -> dict:
    """POST /chat/completions, retrying 429/5xx/timeouts with exponential backoff (honouring a
    numeric Retry-After when the server sends one). Raises on the last attempt's failure."""
    import httpx

    retries = max_retries()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = client.post("/chat/completions", content=json.dumps(body),
                            headers={"Content-Type": "application/json"})
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
            if attempt >= retries:
                raise
            time.sleep(_backoff_seconds(attempt))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            if attempt >= retries:
                r.raise_for_status()
            wait = _parse_retry_after(r.headers.get("Retry-After"))
            time.sleep(wait if wait is not None else _backoff_seconds(attempt))
            continue
        r.raise_for_status()
        return r.json()
    if last_exc:  # pragma: no cover -- unreachable (raise above), kept for safety
        raise last_exc
    raise RuntimeError("LLM request failed after retries")  # pragma: no cover


# -----------------------------------------------------------------------------------------
# output cleanup + fidelity gate v2
# -----------------------------------------------------------------------------------------
_PREFACE_LINE_RE = re.compile(
    r"^(here(?:'s| is)\b|sure[,!]?\s|of course[,!]?\s|rewritten (paragraph|version|text)\b).{0,80}[:\-]?\s*$",
    re.IGNORECASE,
)
_TRAILING_NOTE_RE = re.compile(r"\n+\s*[\(\[](?:note|this)\b[^)\]]*[\)\]]\s*$", re.IGNORECASE)
_META_REWRITE_RE = re.compile(r"\b(?:rewrit\w*|rewrote)\b", re.IGNORECASE)


def _clean_output(raw: str) -> str:
    """Strip a code fence, a "Here is..." preface line, wrapping quotes, and a trailing
    editorial note -- the model is asked for the paragraph only, but cheap models sometimes
    add one of these anyway."""
    lines = raw.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    for i, ln in enumerate(lines):  # a closing fence ends the paragraph; drop it and anything after
        if ln.strip().startswith("```"):
            lines = lines[:i]
            break
    while lines and _PREFACE_LINE_RE.match(lines[0].strip()):
        lines.pop(0)
    out = "\n".join(lines).strip()
    out = _TRAILING_NOTE_RE.sub("", out).strip()
    if len(out) >= 2 and out[0] in "\"'" and out[-1] == out[0]:
        out = out[1:-1].strip()
    return out


def _has_meta_rewrite_comment(original: str, out: str) -> bool:
    """True when `out` talks *about* rewriting (a model habit, e.g. "I rewrote this to...")
    and the original text never used that word itself."""
    return bool(_META_REWRITE_RE.search(out)) and not _META_REWRITE_RE.search(original)


def _sentence_count(text: str) -> int:
    doc = get_nlp()(text)
    return max(1, sum(1 for _ in doc.sents))


def _propn_set(text: str) -> set[str]:
    doc = get_nlp()(text)
    return {t.text.lower() for t in doc if t.pos_ == "PROPN" and t.is_alpha}


def _fidelity_reject_reason(original: str, out: str, protected: list[Protected]) -> str | None:
    """Every check, in cheapest-first order. Returns a short machine-readable reason key, or
    None when `out` passes every gate."""
    if not out.strip():
        return "empty"
    ratio = len(out) / max(1, len(original))
    if ratio < 0.6:
        return "too_short"
    if ratio > 1.6:
        return "too_long"
    if check_fidelity(protected, out):
        return "missing_protected_span"
    if _has_meta_rewrite_comment(original, out):
        return "meta_comment"
    # sentence-count sanity and "no new named entities" both need the shared parser, so they
    # run last -- only once the cheap string checks above have already passed.
    if _sentence_count(out) < max(1, round(_sentence_count(original) * 0.6)):
        return "too_few_sentences"
    new_propn = _propn_set(out) - _propn_set(original)
    if new_propn:
        return "new_named_entity"
    return None


# -----------------------------------------------------------------------------------------
# usage / cost
# -----------------------------------------------------------------------------------------
_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens",
              "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")


def _usage_from_response(data: dict) -> dict[str, int]:
    usage = data.get("usage") or {}
    return {k: usage[k] for k in _USAGE_KEYS if k in usage}


def usage_cost_usd(usage: dict[str, int]) -> float:
    """Cost in USD for one call's `usage` dict, at the configured (or DeepSeek-default) prices.
    Uses the prompt-cache split when the response carried one (DeepSeek does)."""
    if not usage:
        return 0.0
    price_in, price_out = price_per_million()
    completion = usage.get("completion_tokens", 0) or 0
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    if hit is not None or miss is not None:
        hit = hit or 0
        miss = miss if miss is not None else max(0, (usage.get("prompt_tokens") or 0) - hit)
        cached_price_in = price_in * _DEEPSEEK_CACHE_DISCOUNT if "deepseek" in base_url().lower() else price_in
        prompt_cost = (hit * cached_price_in + miss * price_in) / 1_000_000
    else:
        prompt_cost = (usage.get("prompt_tokens", 0) or 0) * price_in / 1_000_000
    return prompt_cost + completion * price_out / 1_000_000


CHARS_PER_TOKEN = 4  # rough heuristic for English prose
SYSTEM_PROMPT_TOKENS_APPROX = 600  # docs/RESEARCH.md section 4's workload figure


def estimate_cost(text: str) -> dict[str, Any]:
    """A cheap, offline estimate of what rewriting `text` with `--engine llm` would cost, using
    a ~4 chars/token heuristic and the configured (or DeepSeek-default) prices. Does not assume
    any prompt-cache discount -- it is meant as a worst-case number to show before spending."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    n_par = max(1, len(paragraphs))
    body_tokens = round(len(text) / CHARS_PER_TOKEN)
    est_input_tokens = body_tokens + n_par * SYSTEM_PROMPT_TOKENS_APPROX
    est_output_tokens = body_tokens
    price_in, price_out = price_per_million()
    est_usd = (est_input_tokens * price_in + est_output_tokens * price_out) / 1_000_000
    return {
        "paragraphs": n_par,
        "est_input_tokens": est_input_tokens,
        "est_output_tokens": est_output_tokens,
        "est_usd": round(est_usd, 4),
    }


# -----------------------------------------------------------------------------------------
# one paragraph
# -----------------------------------------------------------------------------------------
@dataclass
class LlmParagraphOutcome:
    text: str | None                    # the accepted rewrite, or None if rejected/failed
    rejection: str | None = None        # a _fidelity_reject_reason() key, when text is None
    error: str | None = None            # a network/API error message, when the call itself failed
    usage: dict[str, int] = field(default_factory=dict)


def rewrite_paragraph_llm(paragraph: str, triggers: list[Trigger], profile: ReaderProfile,
                          protected: list[Protected], model: str | None = None) -> LlmParagraphOutcome:
    """Call the model once for one paragraph and run its answer through the fidelity gate."""
    model = model or model_name()
    trig_lines = []
    seen = set()
    for t in triggers:
        if t.kind == "syntax" or t.text.lower() in seen:
            continue
        seen.add(t.text.lower())
        alt = f" (try: {', '.join(t.alternatives[:3])})" if t.alternatives else ""
        trig_lines.append(f"- {t.text}: {t.reason}{alt}")
    vocab = ", ".join(sorted(profile.vocab_set())[:200]) or "(none provided)"

    # Layout: the per-reader block (vocabulary, sentence-length target) is IDENTICAL across
    # every paragraph rewritten for this reader, so it goes first, right after the (also
    # identical) system prompt -- together they form one long stable prefix that DeepSeek's
    # automatic prompt cache can match on every single call, not just the system prompt. The
    # TRIGGERS block is specific to this paragraph and so breaks the cache from that point on,
    # and the paragraph text itself -- the part that changes the most and matters the least for
    # caching -- goes last of all. See docs/RESEARCH.md section 4 for the cache economics.
    user = (
        f"READER VOCABULARY (use these words when possible): {vocab}\n"
        f"MAX SENTENCE WORDS: {profile.max_sentence_words}\n\n"
        "TRIGGERS FOR THIS PARAGRAPH:\n" + ("\n".join(trig_lines) if trig_lines else "- (none)") +
        "\n\nPARAGRAPH:\n" + paragraph
    )
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(max_words=profile.max_sentence_words)},
            {"role": "user", "content": user},
        ],
    }
    try:
        with _client() as c:
            data = _post_with_retries(c, body)
    except Exception as e:  # network / HTTP error after retries are exhausted
        return LlmParagraphOutcome(text=None, error=str(e))

    usage = _usage_from_response(data)
    try:
        raw = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return LlmParagraphOutcome(text=None, rejection="bad_response", usage=usage)

    out = _clean_output(raw)
    reason = _fidelity_reject_reason(paragraph, out, protected)
    if reason:
        return LlmParagraphOutcome(text=None, rejection=reason, usage=usage)
    return LlmParagraphOutcome(text=out, usage=usage)


# -----------------------------------------------------------------------------------------
# many paragraphs, concurrently, order preserved
# -----------------------------------------------------------------------------------------
class ParagraphCacheProtocol:  # pragma: no cover -- documentation only, duck-typed
    """What `rewrite_paragraphs_llm`'s optional `cache` needs: `get` returns a previously
    accepted `LlmParagraphOutcome` for this exact paragraph text (under whatever key the cache
    itself derives from the caller's model/profile/prompt version), or None on a miss; `put`
    stores a freshly accepted one. Only accepted outcomes (`.text is not None`) are ever
    offered to `put` -- a rejection or a network error is never cached."""

    def get(self, paragraph: str) -> LlmParagraphOutcome | None: ...

    def put(self, paragraph: str, outcome: LlmParagraphOutcome) -> None: ...


def rewrite_paragraphs_llm(
    paragraphs: list[tuple[str, list[Trigger], list[Protected]]],
    profile: ReaderProfile,
    model: str | None = None,
    cache: ParagraphCacheProtocol | None = None,
) -> list[LlmParagraphOutcome]:
    """Rewrite every (text, triggers, protected) tuple, checking `cache` first and running the
    rest through a thread pool of `DYSREWRITE_LLM_MAX_CONCURRENCY` workers. Returns one outcome
    per input, in the same order, regardless of which order the network calls complete in."""
    model = model or model_name()
    n = len(paragraphs)
    results: list[LlmParagraphOutcome | None] = [None] * n
    todo: list[int] = []
    for i, (text, _triggers, _protected) in enumerate(paragraphs):
        hit = cache.get(text) if cache is not None else None
        if hit is not None:
            results[i] = hit
        else:
            todo.append(i)

    if todo:
        workers = min(max_concurrency(), len(todo))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {}
            for i in todo:
                text, triggers, protected = paragraphs[i]
                futures[ex.submit(rewrite_paragraph_llm, text, triggers, profile, protected, model)] = i
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except Exception as e:  # pragma: no cover -- rewrite_paragraph_llm already catches
                    results[i] = LlmParagraphOutcome(text=None, error=str(e))
                if cache is not None and results[i].text is not None:
                    cache.put(paragraphs[i][0], results[i])

    return results  # type: ignore[return-value]


# -----------------------------------------------------------------------------------------
# connectivity probe (`dysrewrite llm-check`)
# -----------------------------------------------------------------------------------------
def check_connection(model: str | None = None) -> dict[str, Any]:
    """Send a one-sentence probe to the configured endpoint. Never raises -- failure is
    reported in the returned dict's `ok`/`error` fields."""
    model = model or model_name()
    price_in, price_out = price_per_million()
    probe = "The quick brown fox jumps over the lazy dog."
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Reply with exactly the sentence you are given, unchanged."},
            {"role": "user", "content": probe},
        ],
    }
    t0 = time.monotonic()
    result: dict[str, Any] = {
        "base_url": base_url(), "model": model, "price_in": price_in, "price_out": price_out,
    }
    try:
        with _client() as c:
            data = _post_with_retries(c, body)
        result["latency_ms"] = (time.monotonic() - t0) * 1000
        reply = data["choices"][0]["message"]["content"].strip()
        result["reply"] = reply
        result["sane"] = bool(reply) and len(reply) < 500
        result["ok"] = True
    except Exception as e:
        result["latency_ms"] = (time.monotonic() - t0) * 1000
        result["ok"] = False
        result["sane"] = False
        result["error"] = str(e)
    return result


# -----------------------------------------------------------------------------------------
# diffing (used by the engine to turn an accepted rewrite into displayable segments)
# -----------------------------------------------------------------------------------------
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

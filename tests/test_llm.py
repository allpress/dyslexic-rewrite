"""Tests for the hosted LLM engine (src/dyslexic_rewrite/rewrite/llm.py).

No real network call is ever made: every test installs an in-process OpenAI-compatible mock via
`httpx.MockTransport`, injected through the `llm.DYSREWRITE_LLM_TRANSPORT` test hook.
"""

from __future__ import annotations

import json

import httpx
import pytest

pytest.importorskip("httpx")

from dyslexic_rewrite.profile import ReaderProfile  # noqa: E402
from dyslexic_rewrite.rewrite import llm  # noqa: E402
from dyslexic_rewrite.rewrite.engine import rewrite as _rewrite  # noqa: E402

PROFILE = ReaderProfile(max_sentence_words=12)


def _user_text(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return body["messages"][1]["content"]


def _paragraph_of(user_text: str) -> str:
    # rsplit: "TRIGGERS FOR THIS PARAGRAPH:\n" (the fixed header) also ends in "PARAGRAPH:\n",
    # so the *last* occurrence is the one that actually introduces the paragraph text.
    return user_text.rsplit("PARAGRAPH:\n", 1)[1]


def _reply(text: str, usage: dict | None = None) -> dict:
    body = {"choices": [{"message": {"content": text}}]}
    if usage:
        body["usage"] = usage
    return body


def _install(handler) -> None:
    llm.DYSREWRITE_LLM_TRANSPORT = httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    """A clean env per test, and the transport hook is always cleared afterwards."""
    for k in ("DYSREWRITE_LLM_BASE_URL", "DYSREWRITE_LLM_MODEL", "DYSREWRITE_LLM_API_KEY",
              "DYSREWRITE_LLM_MAX_CONCURRENCY", "DYSREWRITE_LLM_TIMEOUT", "DYSREWRITE_LLM_MAX_RETRIES",
              "DYSREWRITE_LLM_PRICE_IN", "DYSREWRITE_LLM_PRICE_OUT"):
        monkeypatch.delenv(k, raising=False)
    yield
    llm.DYSREWRITE_LLM_TRANSPORT = None


# ---- prompt layout ----------------------------------------------------------------------
def test_reader_block_is_a_stable_prefix_across_paragraphs():
    """The per-reader block (vocabulary, max sentence words) must be byte-identical across
    every paragraph for one reader -- that's what lets DeepSeek's prefix cache match it."""
    seen = []

    def handler(request):
        seen.append(_user_text(request))
        return httpx.Response(200, json=_reply("Whatever, unchanged."))

    _install(handler)
    llm.rewrite_paragraph_llm("First paragraph here.", [], PROFILE, [])
    llm.rewrite_paragraph_llm("A completely different second paragraph.", [], PROFILE, [])
    prefix0 = seen[0].split("\n\nTRIGGERS", 1)[0]
    prefix1 = seen[1].split("\n\nTRIGGERS", 1)[0]
    assert prefix0 == prefix1
    assert seen[0].rsplit("PARAGRAPH:\n", 1)[1] == "First paragraph here."
    assert seen[1].rsplit("PARAGRAPH:\n", 1)[1] == "A completely different second paragraph."


# ---- basic accept / usage ------------------------------------------------------------------
def test_basic_rewrite_is_accepted_with_usage_captured():
    def handler(request):
        return httpx.Response(200, json=_reply(
            "Grandpa wound the clock at 6pm.",
            usage={"prompt_tokens": 640, "completion_tokens": 12},
        ))

    _install(handler)
    outcome = llm.rewrite_paragraph_llm("Grandpa wound the clock at 6pm.", [], PROFILE, [])
    assert outcome.text == "Grandpa wound the clock at 6pm."
    assert outcome.usage == {"prompt_tokens": 640, "completion_tokens": 12}
    assert outcome.rejection is None and outcome.error is None


# ---- output cleanup -----------------------------------------------------------------------
def test_output_cleanup_strips_preface_and_wrapping_quotes():
    raw = 'Here is the rewritten paragraph:\n"Grandpa wound the clock at 6pm."'
    assert llm._clean_output(raw) == "Grandpa wound the clock at 6pm."


def test_output_cleanup_strips_code_fence_and_trailing_note():
    raw = "```\nGrandpa wound the clock at 6pm.\n```\n(note: simplified for clarity)"
    assert llm._clean_output(raw) == "Grandpa wound the clock at 6pm."


# ---- fidelity gate v2 -----------------------------------------------------------------------
def test_missing_protected_span_is_rejected():
    from dyslexic_rewrite.nlp import get_nlp
    from dyslexic_rewrite.protect import find_protected

    original = "She paid 40 dollars for the old clock."
    doc = get_nlp()(original)
    protected = find_protected(doc)

    def handler(request):
        return httpx.Response(200, json=_reply("She paid some money for the old clock."))

    _install(handler)
    outcome = llm.rewrite_paragraph_llm(original, [], PROFILE, protected)
    assert outcome.text is None
    assert outcome.rejection == "missing_protected_span"


def test_meta_comment_about_rewriting_is_rejected_when_original_lacks_the_word():
    original = "Grandpa wound the old clock every night before bed, just as he always had."
    out = "Rewritten: " + original
    assert llm._fidelity_reject_reason(original, out, []) == "meta_comment"


def test_meta_comment_allowed_when_original_already_uses_the_word():
    original = "The museum's exhibit on how scribes used to rewrite manuscripts by hand was fascinating today."
    out = "Rewritten: " + original
    # "rewrite" already appears in the original, so its presence in the output isn't suspicious
    assert llm._fidelity_reject_reason(original, out, []) != "meta_comment"


def test_sentence_count_sanity_rejects_a_collapsed_output():
    original = "Grandpa wound the clock. He went to bed. It was quiet all night."
    out = "Grandpa wound the clock, went to bed, and it was quiet all night."
    assert llm._fidelity_reject_reason(original, out, []) == "too_few_sentences"


def test_new_named_entity_is_rejected():
    original = "The old man wound the clock at 6pm."
    out = "Mr. Higgins wound the clock at 6pm and it chimed."
    assert llm._fidelity_reject_reason(original, out, []) == "new_named_entity"


def test_length_ratio_still_gates():
    original = "Grandpa wound the clock at 6pm, just like every other night that whole long winter."
    assert llm._fidelity_reject_reason(original, "Ok.", []) == "too_short"
    assert llm._fidelity_reject_reason(original, out := original * 3, []) == "too_long"
    del out


# ---- retries ------------------------------------------------------------------------------
def test_retries_after_429_then_succeeds(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_MAX_RETRIES", "2")
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "rate limited"})
        return httpx.Response(200, json=_reply("Grandpa wound the clock at 6pm."))

    _install(handler)
    outcome = llm.rewrite_paragraph_llm("Grandpa wound the clock at 6pm.", [], PROFILE, [])
    assert attempts["n"] == 2
    assert outcome.text == "Grandpa wound the clock at 6pm."


def test_exhausted_retries_surface_as_an_error_outcome(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_MAX_RETRIES", "1")

    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    _install(handler)
    outcome = llm.rewrite_paragraph_llm("Grandpa wound the clock at 6pm.", [], PROFILE, [])
    assert outcome.text is None
    assert outcome.error is not None


# ---- engine-level fallback ------------------------------------------------------------------
def test_engine_falls_back_to_rules_and_records_rejection_reason():
    text = "She paid 40 dollars for the old clock."

    def handler(request):
        return httpx.Response(200, json=_reply("She paid some money for the old clock."))

    _install(handler)
    result = _rewrite(text, PROFILE, engine="llm")
    assert result.stats["llm_paragraphs"] == 0
    assert result.stats["llm_fallbacks"] == 1
    assert result.stats["llm_rejections"].get("missing_protected_span") == 1
    assert "40" in result.text  # the rules-engine fallback never touched the number


def test_engine_aggregates_usage_and_cost(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    text = "Grandpa wound the clock at 6pm.\n\nHe went to bed early that night."

    def handler(request):
        text = _paragraph_of(_user_text(request))
        return httpx.Response(200, json=_reply(text, usage={"prompt_tokens": 700, "completion_tokens": 15}))

    _install(handler)
    result = _rewrite(text, PROFILE, engine="llm")
    assert result.stats["llm_paragraphs"] == 2
    assert result.stats["llm_usage"] == {"prompt_tokens": 1400, "completion_tokens": 30}
    assert result.stats["llm_cost_usd"] > 0


# ---- concurrency + ordering -----------------------------------------------------------------
def test_order_preserved_under_concurrency(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_MAX_CONCURRENCY", "4")
    paragraphs_text = [f"This is paragraph number {i} in the batch of test text." for i in range(8)]

    def handler(request):
        text = _paragraph_of(_user_text(request))
        # deliberately answer out of submission order: the earliest paragraph gets the longest
        # simulated delay, so a naive "first response wins its slot" implementation would fail.
        idx = int(text.split("number ")[1].split(" ")[0])
        import time
        time.sleep(0.01 * (len(paragraphs_text) - idx))
        return httpx.Response(200, json=_reply(text))

    _install(handler)
    jobs = [(t, [], []) for t in paragraphs_text]
    outcomes = llm.rewrite_paragraphs_llm(jobs, PROFILE)
    assert [o.text for o in outcomes] == paragraphs_text


# ---- paragraph cache ------------------------------------------------------------------------
class _FakeCache:
    def __init__(self):
        self.store: dict[str, llm.LlmParagraphOutcome] = {}

    def get(self, paragraph):
        return self.store.get(paragraph)

    def put(self, paragraph, outcome):
        self.store[paragraph] = outcome


def test_cache_hit_avoids_a_second_call():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_reply("Grandpa wound the clock at 6pm."))

    _install(handler)
    fake_cache = _FakeCache()
    jobs = [("Grandpa wound the clock at 6pm.", [], [])]
    r1 = llm.rewrite_paragraphs_llm(jobs, PROFILE, cache=fake_cache)
    r2 = llm.rewrite_paragraphs_llm(jobs, PROFILE, cache=fake_cache)
    assert calls["n"] == 1
    assert r1[0].text == r2[0].text == "Grandpa wound the clock at 6pm."


def test_rejected_outcomes_are_never_cached():
    def handler(request):
        return httpx.Response(200, json=_reply("She paid some money for the old clock."))

    _install(handler)
    from dyslexic_rewrite.nlp import get_nlp
    from dyslexic_rewrite.protect import find_protected

    original = "She paid 40 dollars for the old clock."
    protected = find_protected(get_nlp()(original))
    fake_cache = _FakeCache()
    llm.rewrite_paragraphs_llm([(original, [], protected)], PROFILE, cache=fake_cache)
    assert fake_cache.store == {}


def test_server_llm_cache_key_changes_with_profile(monkeypatch):
    """server/cache.py's key must depend on the profile, not just the paragraph."""
    import sys

    pytest.importorskip("psycopg")  # server/ needs the API extras; the package-only CI job skips this
    sys.path.insert(0, ".")
    from server import cache as server_cache

    p1 = ReaderProfile(max_sentence_words=10)
    p2 = ReaderProfile(max_sentence_words=20)
    k1 = server_cache.llm_cache_key("Grandpa wound the clock.", p1, "deepseek-flash")
    k2 = server_cache.llm_cache_key("Grandpa wound the clock.", p2, "deepseek-flash")
    assert k1 != k2


# ---- cost estimate + connectivity probe ------------------------------------------------------
def test_estimate_cost_uses_configured_prices(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    text = "\n\n".join(["word " * 1000] * 3)
    est = llm.estimate_cost(text)
    assert est["paragraphs"] == 3
    assert est["est_input_tokens"] > 0 and est["est_output_tokens"] > 0
    assert est["est_usd"] > 0


def test_price_defaults_to_deepseek_when_base_url_matches():
    import os

    os.environ["DYSREWRITE_LLM_BASE_URL"] = "https://api.deepseek.com/v1"
    assert llm.price_per_million() == pytest.approx((0.15, 0.60))


def test_price_defaults_to_zero_for_unknown_provider():
    import os

    os.environ["DYSREWRITE_LLM_BASE_URL"] = "https://api.example.com/v1"
    assert llm.price_per_million() == (0.0, 0.0)


def test_usage_cost_uses_deepseek_cache_discount(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    usage = {"prompt_tokens": 1000, "completion_tokens": 100,
              "prompt_cache_hit_tokens": 900, "prompt_cache_miss_tokens": 100}
    cost = llm.usage_cost_usd(usage)
    expected = (900 * 0.15 * 0.02 + 100 * 0.15 + 100 * 0.60) / 1_000_000
    assert cost == pytest.approx(expected)


def test_check_connection_reports_latency_sanity_and_price(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DYSREWRITE_LLM_MODEL", "deepseek-flash")

    def handler(request):
        return httpx.Response(200, json=_reply("The quick brown fox jumps over the lazy dog."))

    _install(handler)
    result = llm.check_connection()
    assert result["ok"] is True
    assert result["sane"] is True
    assert result["model"] == "deepseek-flash"
    assert result["price_in"] == pytest.approx(0.15)
    assert result["price_out"] == pytest.approx(0.60)
    assert result["latency_ms"] >= 0


def test_check_connection_reports_failure_without_raising(monkeypatch):
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "http://localhost:1")

    def handler(request):
        raise httpx.ConnectError("nope", request=request)

    _install(handler)
    result = llm.check_connection()
    assert result["ok"] is False
    assert result["error"]


def test_llm_check_cli_reports_model_and_pricing(monkeypatch):
    from click.testing import CliRunner

    from dyslexic_rewrite.cli import main

    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DYSREWRITE_LLM_MODEL", "deepseek-flash")

    def handler(request):
        return httpx.Response(200, json=_reply("The quick brown fox jumps over the lazy dog."))

    _install(handler)
    runner = CliRunner()
    result = runner.invoke(main, ["llm-check"])
    assert result.exit_code == 0, result.output
    assert "deepseek-flash" in result.output
    assert "0.150" in result.output and "0.600" in result.output


# ---- CLI cost estimate before a big run ------------------------------------------------------
def test_rewrite_cli_prints_estimate_over_20k_chars_on_a_tty(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from dyslexic_rewrite.cli import main

    monkeypatch.setattr("dyslexic_rewrite.cli._is_interactive", lambda: True)

    def handler(request):
        text = _paragraph_of(_user_text(request))
        return httpx.Response(200, json=_reply(text))

    _install(handler)
    big = "Grandpa wound the clock at 6pm. " * 650  # > 20,000 chars, one paragraph
    f = tmp_path / "book.txt"
    f.write_text(big, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["rewrite", str(f), "--engine", "llm", "--yes", "-o", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "Estimated cost" in result.output

# dyslexic-rewrite

**Free, open-source software that rewrites text so a dyslexic reader can read it faster and understand more.**
General first, then tuned by dyslexia type, then tuned to one reader from how they write and speak.

No accounts. No cloud. Runs on your own computer. MIT licensed. Made to help people, not to sell to them.

## Why

For many dyslexic readers the problem is not only *letters* — it is specific *words*. A word that sounds like
another word, or a word that shows up twice nearby with two different meanings (`wind up the clock` … `the wind
blows`), stops the sentence cold. One trigger word can wipe out the rest of the paragraph.

This project finds those triggers and defuses them, and straightens sentence shapes that overload working memory —
while **never destroying the original text**. Every change is reversible and visible on demand, because the
research says silent word swaps do not help on their own but letting the reader see an easier option does.

The plan, in three layers that share one profile format:

| Layer | What it does | Status |
| --- | --- | --- |
| **General** | Detects heteronyms, re-used ambiguous words, misleading phrasal verbs, near-homophone clashes, rare/long words, and heavy sentence shapes. Rewrites what is safe to rewrite; flags the rest with pronunciation cues. | v0.1 — works today |
| **By type** | Built-in profiles that shift the weights: `phonological`, `visual`, `attention`. | v0.1 — first cut |
| **Individual** | `dysrewrite learn` builds a profile from the reader's own writing (or a transcript of their speech): their sentence length, clause depth, passive use, vocabulary. Feedback from the reader view (“this word tripped me”) feeds back in. | v0.1 — first cut |

## The website

The reading-test site lives in this repo too: `server/` (FastAPI, Postgres, email-code sign-in) and `web/`
(React + TypeScript). It runs the same engine and adds the A/B reading test: two matched passages, one
original and one rewritten with your profile, timed, with five questions each, plus "tap the word that
tripped you". Results feed your profile. See `server/API.md` and `web/README.md`. The hosted version lives
at https://unwindwords.com.

```bash
# local dev: Postgres on localhost, then
pip install -e ".[all]" -r server/requirements.txt && python -m spacy download en_core_web_sm
(cd web && npm install && npm run build)
SECURE_COOKIES=0 uvicorn server.app:app --reload     # http://localhost:8000 — sign-in codes print on screen
```

Deploys go to Fly.io from GitHub Actions (`.github/workflows/deploy.yml`); `provision.yml` creates the app,
Postgres and secrets once; `ops.yml` runs any `flyctl` command from the Actions tab.

## Install (command line)

```bash
pip install dyslexic-rewrite            # once published; for now:
git clone https://github.com/allpress/dyslexic-rewrite && cd dyslexic-rewrite
pip install -e ".[all]"
python -m spacy download en_core_web_sm
```

Python 3.10+. Optional extras: `[epub]` for .epub/.html input, `[wordnet]` for synonym lookup
(`python -c "import nltk; nltk.download('wordnet')"`), `[llm]` for the local-model engine, `[speech]` for audio.

## Use

```bash
# 1. See what would trip a reader
dysrewrite analyze chapter.txt
dysrewrite analyze chapter.txt -p attention --show -1

# 2. Rewrite it. You get an HTML reader view, plain text, and a change report.
dysrewrite rewrite chapter.txt -o out/
dysrewrite rewrite book.epub -p visual -o out/

# 3. Make it personal: learn from the reader's own writing (emails, messages, journal, transcript)
dysrewrite learn her_emails.txt her_notes.md -o her.json
dysrewrite rewrite chapter.txt -p her.json -o out/

# 4. Teach the profile from what tripped her (exported from the HTML view), or by hand
dysrewrite profile feedback her.json dysrewrite-feedback.json
dysrewrite profile add her.json -t wind -t tear -r "wind=breeze" -s clock
```

Open `out/chapter.her.html` in any browser. Underlined words were changed — hover or tap to see the original and
why. Dotted words were flagged but kept — hover for a pronunciation cue (`wind: rhymes with 'find'`). Click any
marked word to record that it tripped you, press **Start reading / Finish reading** for a words-per-minute number,
then **Export feedback**. That JSON is what `profile feedback` learns from.

### Phonetic map

A friendly respelling (`in-TEN-shun`, not IPA) shown right over a flagged word — `<ruby>` text with the
respelling as `<rt>` above it — for words a reader might stumble on: heteronyms, words re-used with a different
meaning nearby, personal trigger words, rare or long words, near-homophones. The **Phonetic map** dropdown in the
top bar switches between **off**, **on demand** (hover/tap to reveal; heteronyms, re-used words and personal
triggers always show), and **always** (every respelling visible); it starts at whatever the profile says
(`phonetic_map: "off" | "on_demand" | "always"`, plus `phonetic_map_kinds` / `phonetic_map_always_kinds` to
choose which trigger families get one). Every marked word's tip popover also has a speaker button that reads
just that word aloud, and the top bar has a **Read aloud** button that reads the whole piece, paragraph by
paragraph. Check the table yourself from the command line:

```bash
dysrewrite say intention        # in-TEN-shun
dysrewrite say wind --pos VERB  # WYND (rhymes with 'find')
dysrewrite say read --tag VBD   # RED  (past tense)
```

`dysrewrite rewrite`/`analyze` take `--phonetic-map off|on_demand|always` to override the profile for one run,
and `analyze --show` lists the respelling next to each flagged word. Needs the optional `cmudict` package (a
core dependency); without it, respellings are simply omitted.

### Python

```python
from dyslexic_rewrite import analyze, rewrite, load_profile

profile = load_profile("attention")          # or load_profile("her.json")
report = analyze(text, profile)              # triggers, by kind, with reasons and alternatives
result = rewrite(text, profile)              # result.text, result.all_changes(), result.stats
```

### Optional LLM engine — local, or a cheap hosted tier

`--engine llm` sends each paragraph, its trigger list and the reader's vocabulary to any OpenAI-compatible endpoint,
concurrently (`DYSREWRITE_LLM_MAX_CONCURRENCY`, default 4) with the paragraph order preserved. The default is a
local [Ollama](https://ollama.com) server, so it is free and nothing leaves the machine. Every paragraph the model
returns goes through a fidelity gate — protected spans (names, numbers, quotes) must survive verbatim, the length
must stay in range, the sentence count can't collapse, and no new proper noun can appear — plus an output cleanup
(strips a "Here is..." preface, wrapping quotes, and any meta-comment about "rewriting"). Anything that fails falls
back to the rule engine for that paragraph, and every rejection reason is counted in `result.stats["llm_rejections"]`.

```bash
ollama pull llama3.1:8b
dysrewrite rewrite chapter.txt --engine llm -p her.json
```

#### Cheap hosted engine

The documented cheap option is [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing) `deepseek-flash`,
OpenAI-compatible, about **$0.10 for a 90,000-word book** off-peak with its automatic prompt cache (checked
2026-09-18 — see [docs/RESEARCH.md](docs/RESEARCH.md) §4 for the arithmetic and the other providers we costed).
Nothing about the engine is DeepSeek-specific — the same env vars work with any OpenAI-compatible host.

```bash
export DYSREWRITE_LLM_BASE_URL=https://api.deepseek.com/v1
export DYSREWRITE_LLM_MODEL=deepseek-flash
export DYSREWRITE_LLM_API_KEY=sk-...
dysrewrite llm-check                              # ping the endpoint: model, latency, sane reply, prices in effect
dysrewrite rewrite book.epub --engine llm -p her.json   # prints a cost estimate first for a >20k-char input on a TTY (-y skips it)
```

Config (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DYSREWRITE_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible chat-completions endpoint |
| `DYSREWRITE_LLM_MODEL` | `llama3.1:8b` | Model name sent in the request body |
| `DYSREWRITE_LLM_API_KEY` | `ollama` | Bearer token (Ollama ignores it) |
| `DYSREWRITE_LLM_MAX_CONCURRENCY` | `4` | Paragraphs rewritten in parallel |
| `DYSREWRITE_LLM_TIMEOUT` | `90` | Per-request timeout, seconds |
| `DYSREWRITE_LLM_MAX_RETRIES` | `3` | Retries on 429/5xx/timeout, exponential backoff, honours `Retry-After` |
| `DYSREWRITE_LLM_PRICE_IN` / `_OUT` | DeepSeek off-peak (0.15 / 0.60) if the base URL contains "deepseek", else 0 | $ per 1M tokens, for `stats["llm_cost_usd"]` and the cost estimate |

The stable part of the prompt (the system prompt, plus a fixed per-reader block — vocabulary and the sentence-length
target — placed at the *start* of the user message) is identical across every paragraph rewritten for one reader, so
DeepSeek's automatic prefix cache matches on it every call; the per-paragraph trigger list and the paragraph text
itself (which change every call and matter least for caching) come last. `result.stats` gains `llm_usage` (prompt/
completion tokens, plus DeepSeek's `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` when the response carries
them) and `llm_cost_usd` whenever the model returns usage.

Privacy note: whole books leave the machine with the hosted tier. That's fine for public-domain text and a reader's
own purchases, by their own choice — it is never the default.

## How it works

```
text ──► analyze ──► triggers ──► rewrite ──► render
           │                        │            └─ HTML reader view (originals on hover, hints, feedback export), .txt, .md, .json
           │                        └─ rules engine (deterministic) or LLM engine (fidelity-checked, rules fallback)
           └─ detectors: personal · ambiguity · phrasal · heteronym · phonetic · rare · long · syntax
                         weighted by the reader profile (general → type → individual)
```

**Detectors** (`src/dyslexic_rewrite/triggers/`)

- `heteronym` — one spelling, two pronunciations or meanings (`wind`, `tear`, `lead`, `record` …). Curated table with
  POS-keyed plain alternatives and pronunciation hints in `data/heteronyms.json`.
- `ambiguity` — the same spelling used with a different part of speech within N sentences. This is the
  `wind up / wind blows` case. The occurrence with a safe plain alternative gets rewritten; the other keeps a hint.
- `phrasal` — phrasal verbs whose parts mislead (`wind up` → `end up`), with transitivity checks so
  `wind up the clock` (literal) is left alone.
- `phonetic` — confusable pairs (`from/form`, `quiet/quite`, `their/there`), Metaphone sound-alikes and
  one-edit look-alikes that land close together.
- `rare`, `long` — by word frequency (`wordfreq`) and length; words the reader uses in their own writing are never
  “rare” for them.
- `syntax` — sentence length over the profile's target, three or more clauses, a clause wedged between subject
  and verb, passive voice.

**Phonetic map** (`src/dyslexic_rewrite/pronounce.py`) turns a trigger word into a friendly respelling
(`in-TEN-shun`, not IPA) via `cmudict`, picking the right sense for heteronyms (`wind`/`wind`, `record`/`record`)
from a small routing table keyed by POS and, for tense-based ones like `read`, spaCy's fine-grained tag.

**Rewriter** (`src/dyslexic_rewrite/rewrite/rules.py`) substitutes only where it is safe (personal replacements,
phrasal idioms, ambiguity clashes; rare/long words only with `--simplify-vocab`), then straightens shape:
`X, and Y` → `X. Y.`; `Because X, Y` → `X. So Y.`; `…, which V` → `…. It V`; `Subject, who V1, V2` →
`Subject V1. Subject V2.`; semicolons become full stops. Names, numbers, quotes and URLs are protected spans.

**Profiles** (`src/dyslexic_rewrite/profiles/*.json`) are plain JSON: thresholds, per-family weights, the reader's
trigger words, safe words, replacements, vocabulary, layout, and learned style targets. `dysrewrite profile new me.json`
gives you one to edit.

## What the evidence says (and why the tool behaves the way it does)

- Automatic synonym replacement alone did **not** improve reading speed or comprehension for dyslexic readers, but
  showing easier synonyms *on demand* was rated significantly more readable — Rello et al., *Simplify or help?*, W4A 2013.
  → We keep the original inside every change and show it on hover; plain heteronyms are never silently swapped.
- More frequent words improve readability; shorter words improve understandability — Rello et al., 2013.
  → `rare` and `long` detectors; alternatives are ranked by frequency and by whether the reader already uses them.
- Complex syntax (embedded and relative clauses) is harder for dyslexic readers and tracks attention/working memory
  load — Mazlumi et al., *Dyslexia*, 2026. → sentence-shape rules and the `attention` profile.
- Generic LLM simplification deletes facts readers still need; protected spans and deterministic controls fix
  that — DFT-GEN, arXiv 2026. → fidelity gate on the LLM engine, rules fallback.
- Dyslexia is heterogeneous and the field is moving toward individually tailored tools — Frontiers in Human
  Neuroscience review, 2025. → the general → type → individual ladder.

Sources are listed in [ROADMAP.md](ROADMAP.md).

## Measuring whether it works

The point is reading speed and comprehension, not vibes. The reader view has a built-in timer; export gives you
words-per-minute and the words that tripped the reader. The plan (see the roadmap) is a two-minute A/B check:
same passage, original vs rewritten, time plus five questions, results kept locally and optionally shared.

If you or someone you love has dyslexia and is willing to try this on a chapter and tell us what happened,
that is the most valuable contribution there is. Open an issue.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions: more heteronyms and confusable pairs in
`data/heteronyms.json`, a new language pack, a reader report, a failing test for a sentence the rules mangle.

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT. Free forever. If you build something on it that helps people read, tell us so we can link to it.

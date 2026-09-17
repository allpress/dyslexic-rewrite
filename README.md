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

### Python

```python
from dyslexic_rewrite import analyze, rewrite, load_profile

profile = load_profile("attention")          # or load_profile("her.json")
report = analyze(text, profile)              # triggers, by kind, with reasons and alternatives
result = rewrite(text, profile)              # result.text, result.all_changes(), result.stats
```

### Optional local LLM engine

`--engine llm` sends each paragraph, its trigger list and the reader's vocabulary to any OpenAI-compatible endpoint.
The default is a local [Ollama](https://ollama.com) server, so it is free and nothing leaves the machine.
Every paragraph the model returns is checked: names, numbers and quotes must survive verbatim and the length must
stay in range, otherwise that paragraph falls back to the rule engine.

```bash
ollama pull llama3.1:8b
dysrewrite rewrite chapter.txt --engine llm -p her.json
# or point elsewhere:
DYSREWRITE_LLM_BASE_URL=https://api.example.com/v1 DYSREWRITE_LLM_MODEL=... DYSREWRITE_LLM_API_KEY=... dysrewrite rewrite ...
```

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

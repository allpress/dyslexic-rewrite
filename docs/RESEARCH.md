# Research: dyslexia types, how to spot them, and the cheapest converter for each

Compiled September 2026 for dyslexic-rewrite / unwindwords.com. Everything below was
checked against the cited sources on 2026-09-18; prices in section 4 will drift, so
re-check before quoting them.

The short version:

1. There is no clean set of dyslexia "types". The field has settled on a
   **multiple-deficit model**: a handful of partly independent weaknesses that overlap
   in most people. The four with the best evidence are phonological decoding,
   orthographic (whole-word) knowledge, naming speed / processing rate (RAN), and
   visual attention span (VAS). Attention / working memory is a fifth axis that is
   really ADHD overlap but changes what helps. Visual stress / magnocellular is the
   weakest-evidenced and we should not build around it.
2. We should therefore ship a **profile across axes**, not a single score, and pick
   rewrite levers per axis. A ten-minute browser battery can measure all five axes
   without any audio pipeline, and two more tasks can use the recording feature we
   already have.
3. The **heteronym / re-used word trigger** at the heart of this project has never
   been studied directly in dyslexia. The closest evidence (idiom processing in dyslexic
   adults, syntactic-ambiguity recovery under limited working memory) makes it a
   reasonable hypothesis, not a finding. That makes it the most valuable thing we can
   test — nobody else has the data.
4. The cheapest converter is the one we already have (rules, $0). The next tier is a
   cheap OpenAI-compatible model behind our fidelity gate: **DeepSeek V4.1-Flash costs
   about ten cents per 90,000-word book** with its automatic prompt cache, and about
   half a cent per chapter. Tier three is a small fine-tuned model trained on the pairs
   readers accept, which brings the marginal cost back to $0 and — per the 2026
   benchmarks — likely beats a prompted cheap model on quality.

---

## 1. What the literature says the types are

### 1.1 Phonological (dysphonetic)

The core, best-replicated deficit: mapping letters to sounds is slow and unreliable, so
unfamiliar words and nonwords are hard to decode and reading is effortful. This is the
modal profile in every cohort, and it is what most of the classic simplification
evidence (Rello's frequency and length work) implicitly targets.

### 1.2 Surface / orthographic (dyseidetic)

Whole-word (lexical) recognition is weak while sounding-out is relatively intact.
Irregular words (`yacht`, `colonel`) get "regularised", and spelling errors are
phonetically plausible (`fone`). Developmental surface dyslexia is itself heterogeneous
([Bailey et al., "dyslexia or dyslexias"](https://www.sciencedirect.com/science/article/abs/pii/S0010945218301400)),
and a 2023 lexical-decision study argues some dyslexic adults have a primarily
orthographic, not phonological, deficit
([PMC11178288](https://pmc.ncbi.nlm.nih.gov/articles/PMC11178288/)).

This is the axis where Jennifer's reported trigger (one spelling, two readings) sits
most naturally: if the whole-word route is weak, a spelling that maps to two
pronunciations or two meanings forces a fallback to decoding *and* a meaning lookup
at the same time.

### 1.3 Mixed

In dual-route testing frameworks the largest group has both weaknesses; pure
single-deficit cases are the minority, in children and adults
([PMC3491101](https://pmc.ncbi.nlm.nih.gov/articles/PMC3491101/)). Design consequence:
weights, not categories.

### 1.4 Visual attention span (VAS) — Valdois & Bosse

The number of letters that can be processed in parallel in one glance is reduced,
independently of phonology. Established with a 5-letter partial/whole-report task
([Bosse, Tainturier & Valdois 2007, Cognition](https://www.sciencedirect.com/science/article/abs/pii/S0010027706001272);
method in [Bosse & Valdois 2009](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9817.2008.01387.x);
reviewed in [Valdois 2022](https://onlinelibrary.wiley.com/doi/abs/10.1002/dys.1724)).
The 2007 paper reports that most dyslexic children show a *selective* phonological or
VAS disorder — the two dissociate — but gives no population percentage. Causality is
still argued ([Nature Reviews Neuroscience exchange](https://www.nature.com/articles/nrn3836-c1)).
Levers: shorter words, shorter lines, fewer letters per visual chunk.

### 1.5 Rapid automatized naming (RAN) / double deficit — Wolf & Bowers

Naming speed for digits, letters, colours predicts reading rate independently of
phonological awareness; people with both deficits read slowest and respond least to
treatment ([Wolf & Bowers 1999](https://moodle2.units.it/pluginfile.php/202413/mod_resource/content/0/WolfBowers%201999.pdf);
[Wolf, Bowers & Biddle 2000](https://link.springer.com/article/10.1023/A:1013816320290)).
The pattern persists into adolescence and adulthood
([2015 PubMed 25983024](https://pubmed.ncbi.nlm.nih.gov/25983024/);
[Harrison & Stewart 2019](https://onlinelibrary.wiley.com/doi/abs/10.1002/dys.1638)),
which matters for us: compensated adults often decode fine and are still slow. A 2024
data-driven study of 639 children found rate-only ≈ 14.5 %, accuracy-only ≈ 14.6 %,
double ≈ 8 % of the sample
([Frontiers 2024](https://www.frontiersin.org/journals/language-sciences/articles/10.3389/flang.2024.1390391/full)).
Levers: pacing, chunking, text-to-speech pairing, predictable sentence openings.

### 1.6 Attention / working memory / executive (ADHD overlap)

Comorbidity with ADHD is commonly put at 25–40 %. Pennington's multiple-deficit model
treats both as products of shared risk factors (processing speed, phonology, executive
function) ([Pennington 2006](https://pubmed.ncbi.nlm.nih.gov/16844106/);
[McGrath et al.](https://liberalarts.du.edu/sites/default/files/2021-04/mcgrath2011multipledeficit.pdf);
[Catts & Petscher](https://www.researchgate.net/publication/324742482)).
[Mazlumi et al. 2026](https://onlinelibrary.wiley.com/doi/full/10.1002/dys.70026)
ties complex-syntax comprehension failure in dyslexia to attention, not to syntax
knowledge. Levers: sentence splitting, no centre-embedding, explicit connectives, one
idea per sentence — exactly what our `attention` profile does.

### 1.7 Magnocellular / visual stress — treat as comfort settings only

Stein's magnocellular theory ([Stein 2018](https://pubmed.ncbi.nlm.nih.gov/29588226/))
is an advocacy review with weak, inconsistent effects; coloured overlays show no robust
benefit over placebo ([Griffiths et al. 2016 systematic review](https://www.readwritecenter.org/uploads/1/1/2/8/112870549/colored_overlays-systematic_review_of_literature.pdf);
[Ritchie et al.](https://pubmed.ncbi.nlm.nih.gov/21930551/);
[2020 review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7727967/)). We can offer a
background tint as a preference. We must not claim it helps.

### 1.8 The heteronym / ambiguity question — an evidence gap we can fill

No study was found on heteronym pronunciation selection (`wind`/`wind`,
`tear`/`tear`, `read`/`read`) in dyslexia. Adjacent evidence:

- dyslexic adults recover worse from syntactically ambiguous (garden-path) sentences,
  tied to working-memory limits
  ([Stella & Engelhardt 2019](https://onlinelibrary.wiley.com/doi/10.1002/dys.1613));
- dyslexic adults process idioms through a slower compensatory right-hemisphere route
  ([Kasparian et al. 2019](https://pubmed.ncbi.nlm.nih.gov/30301445/)), which is the
  best support we have for the phrasal-verb detector;
- general ambiguity-resolution models predict a cost when a spelling has to be
  re-mapped ([Rodd 2020](https://journals.sagepub.com/doi/10.1177/1745691619885860)).

So the `heteronym`, `ambiguity` and `phrasal` families are **design hypotheses**. The
site should measure them (section 3, test H) rather than assume them.

---

## 2. What text changes actually help, by axis

| Lever | Evidence | Strength | Axis it serves |
|---|---|---|---|
| Swap rare → frequent words | Improves reading speed ([Rello & Baeza-Yates 2013, INTERACT](https://link.springer.com/chapter/10.1007/978-3-642-40498-6_15)) | Good | phonological, RAN |
| Swap long → short words | Improves comprehension, separately from frequency (same paper) | Good | phonological, VAS |
| Replace vs. annotate the hard word | Readers sometimes prefer the original plus a gloss over a swap ([Simplify or help?](https://www.superarladislexia.org/pdf/2013-Luz%20Rello-w4a.pdf), [CICLing 2013](https://superarladislexia.org/pdf/2013-Luz%20Rello-cicling.pdf)) | Good | all — make it a per-reader toggle |
| Short sentences, no embedding | Dyslexic adults disproportionately hurt by complex sentences ([Annals of Dyslexia](https://link.springer.com/article/10.1007/s11881-009-0028-7); [Reading & Writing](https://link.springer.com/article/10.1007/s11145-004-2661-1); Mazlumi 2026) | Theory strong, A/B thin | attention, RAN |
| Letter/word spacing, line length | Modest and inconsistent ([Annals of Dyslexia 2020](https://link.springer.com/article/10.1007/s11881-020-00194-x)) | Weak-positive | VAS |
| "Dyslexia fonts" | Null ([Kuster et al. 2018](https://link.springer.com/article/10.1007/s11881-017-0154-6); [Rello, Good Fonts](https://dyslexiahelp.umich.edu/wp-content/uploads/2014/02/good_fonts_for_dyslexia_study.pdf)) — plain sans-serif is as good | Null | — |
| Coloured overlays | Null / placebo (section 1.7) | Null | — |
| Text-to-speech | Most consistently positive accommodation in the literature ([Reading & Writing 2025](https://link.springer.com/article/10.1007/s11145-025-10738-5); [5-year follow-up](https://www.tandfonline.com/doi/full/10.1080/17483107.2022.2161647)) | Good | RAN, phonological |
| Avoid heteronyms / re-used spellings | Untested (1.8) | Hypothesis | orthographic, attention |
| LLM rewriting | Works on preference judgments, fails on fidelity without guards ([DFT-GEN 2026](https://arxiv.org/abs/2608.13583); [Dyslexia and AI 2025](https://link.springer.com/chapter/10.1007/978-3-031-98414-3_3)) | Immature | all — only behind the fidelity gate |

Design consequences already reflected in the code: protected spans and the fidelity
check (DFT-GEN's "fidelity-preserving" argument), originals on hover (the
replace-vs-annotate finding), plain sans-serif layout defaults with no font claims.
Two things we should add: a TTS button in the reader (strongest evidence of anything
here) and a per-reader `annotate_instead_of_replace` switch.

---

## 3. A screening battery we can run in the browser

Rules for the battery: no audio pipeline required for the core (audio tasks are
optional and go into the existing `pending_analysis` recording queue), no AI in the
site, every task under two minutes, every task outputs a number that maps to a profile
weight. Total ≈ 10 minutes. The precedent for exactly this shape is Rello's Dytective
— 32 short game tasks, ML-scored, validated on n ≈ 3,600 with ≈ 80 % recall for ages
12+ ([Rello et al. 2020, PLOS ONE](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0241687)).

Timing: use `performance.now()` and `requestAnimationFrame` for every stimulus onset;
never `setTimeout` alone. Stimuli are static JSON served by the API, results are rows
in a `battery_results` table (task, item, response, rt_ms, correct), analysis is
offline in the Python package.

| # | Test | Axis | Stimulus (≈ time) | Score | Maps to profile |
|---|---|---|---|---|---|
| A | Adult checklist | triage | 10 Likert items (BDA / Vinegrad style) (1 min) | weighted sum | onboarding segment only. [Stark 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11632572) found the standard cutoff of 45 under-identifies; use 40 and never gate on it |
| B | Typed spelling dictation | phonological vs orthographic | 20 words played from pre-recorded audio (8 regular, 8 irregular, 4 nonwords) (2 min) | errors classified by rule: phonetically plausible (`fone`) vs implausible (`phne`), plus nonword accuracy | plausible-heavy → raise `heteronym`, `ambiguity`, `phonetic`; implausible-heavy / nonword-poor → raise `rare`, `long`, raise `min_zipf` (more words count as rare). Best-evidenced discriminator we have ([Annals of Dyslexia](https://link.springer.com/article/10.1007/BF02928180); [subgroup parallels](https://link.springer.com/article/10.1023/A:1011122219046)) |
| C | Orthographic choice | orthographic | 24 forced-choice pairs, real vs pseudohomophone (`rain` / `rane`), frequency-matched (1.5 min) | accuracy, median RT | low → orthographic axis; raise `phonetic` window, prefer regular spellings in swaps |
| D | Pseudohomophone decision | phonological | 24 nonword pairs, "which one sounds like a real word?" (`brane` / `brone`) (1.5 min) | accuracy, RT | low → phonological axis; raise `rare`, lower `max_word_length` |
| E | VAS whole report | VAS | 20 trials: 5 consonants flashed 200 ms, type them (1.5 min) | letters correct by position (span) | span < 4 → lower `max_word_length`, `max_line_chars`, raise `word_spacing_em` |
| F | Backward digit span | attention / WM | adaptive, 3 → 8 digits (1.5 min) | longest span | ≤ 4 → raise `syntax`, lower `max_sentence_words`, `clause_depth` target |
| G | RAN digits | rate | 5×10 digit grid read aloud into the existing recorder (30 s) | seconds, scored offline with Whisper word timestamps; silent proxy: click-matching (a different construct — note it) | slow → raise `syntax`, chunked layout, suggest TTS |
| H | **Heteronym probe** (new) | our hypothesis | 24 sentences, self-paced moving window (spacebar per word); 12 contain a heteronym or re-used spelling, 12 matched controls (2 min) | per-word RT on the target and the next two words; regressions (back key) | reliable slowdown → raise `heteronym`, `ambiguity`, `phrasal` weights; no slowdown → leave them at 1.0 and stop rewriting for them |
| I | A/B fluency | outcome | existing passage pairs, original vs rewritten, timer + 5 questions | WPM, comprehension, tripped words | the ground truth every other test is judged against |

What the battery cannot do: eye movements (no eye tracker in a browser), clinical
norms (all the normed instruments — TOWRE-2, GORT-5, WAIS digit span — are
copyrighted), and a diagnosis. We benchmark against our own users, say "screening,
not assessment", and inherit Dytective's caveats (cannot separate ADHD, relies on
self-report as ground truth).

### 3.1 Trial protocol

Within-subject: each reader does the battery once, then the A/B test with at least
six passage pairs across sessions (three pairs is the minimum for a per-person effect;
six gives a stable one). Primary outcome is words per minute on the rewritten passage
minus the original; secondary outcomes are comprehension delta and tripped-word count.
Passage order and which of the pair is rewritten are randomised (already implemented).

The first analysis we want: does the axis profile from B–H predict *which* rewrite
lever produced the WPM gain? That is the whole point of the ladder, and it is the
analysis no published study has run.

### 3.2 Building the item banks cheaply

Item banks for B, C, D and H are the expensive part. Recipe: generate candidates with
the cheap LLM (section 4) from a constrained prompt (frequency band, length, regular
vs irregular), filter with `wordfreq` and the heteronym table, then human-review. A
24-item bank costs cents to draft and an hour to review. Passage pairs for I can be
drafted the same way, but the matched pair needs a human ear; the three pairs we have
were hand-written and that should stay the bar.

---

## 4. Converter tiers and what each costs

Workload used for every figure: one 90,000-word book ≈ 120k input tokens of text +
130k output tokens, rewritten paragraph by paragraph (≈ 1,500 calls) with a 600-token
system prompt each. So ≈ 1.02 M input tokens, of which 900k are the *same* system
prompt repeated. Prompt caching is therefore the biggest lever, bigger than batch
discounts.

### Tier 0 — rules engine (shipped)

`dysrewrite rewrite --engine rules`. $0, runs anywhere, deterministic, every change
reversible. Covers: safe word swaps from the profile and heteronym tables, coordinated
splits, `Because X, Y` → `X. So Y.`, trailing `, which`, subject-relative lift. It
cannot rephrase a sentence that needs a new structure, and it cannot swap a heteronym
whose safe alternative depends on meaning (`tear`/`tear` as two nouns).

### Tier 1 — cheap hosted model behind the fidelity gate

`--engine llm` already speaks OpenAI-compatible chat completions and already throws
away any paragraph that loses a protected span or drifts in length, falling back to
Tier 0 for that paragraph. So a cheap model costs nothing in code — only env vars.
Prices checked 2026-09-18:

| Provider / model | $/M in (miss) | $/M in (cached) | $/M out | Per book | Per chapter | Notes |
|---|---|---|---|---|---|---|
| **DeepSeek `deepseek-flash`** (V4.1-Flash), off-peak | 0.15 | 0.003 | 0.60 | **$0.10** | $0.006 | Automatic prefix cache, 1M context, OpenAI-compatible. Peak (01–04, 06–10 UTC Mon–Fri) is exactly double: $0.20. Uncached $0.23. [pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| Groq Llama-3.1-8B-Instant | 0.05 | – | 0.08 | $0.06 | $0.003 | Cheapest, weakest model. [pricing](https://groq.com/pricing) |
| DeepInfra Qwen3.5-9B | 0.10 | – | 0.15 | $0.12 | $0.007 | [pricing](https://deepinfra.com/blog/qwen-api-pricing-2026-guide) |
| Mistral Small 4 | 0.15 | 0.015 | 0.60 | $0.11 cached / $0.23 | $0.006 | [pricing](https://docs.mistral.ai/inference/pricing) |
| OpenAI GPT-5.6 Luna (cheapest tier) | 0.20 | 0.02 | 1.20 | $0.36 | $0.02 | Cache needs ≥ 1,024-token prefix; our prompt is 600. [pricing](https://developers.openai.com/api/docs/pricing) |
| Gemini 2.5 Flash-Lite | 0.30 | – | 2.50 | $0.63 ($0.32 batch) | $0.035 | [pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| OpenRouter `:free` | 0 | – | 0 | $0 | $0 | 50 req/day (1,000/day after $10 lifetime credit) — a chapter a day, not a book. [limits](https://openrouter.ai/docs/api_reference/limits) |

Arithmetic for the DeepSeek line: 899,400 cached × $0.003/M + 120,600 uncached ×
$0.15/M + 130,000 out × $0.60/M = $0.0027 + $0.0181 + $0.078 ≈ $0.099. Note the model
IDs: `deepseek-chat` and `deepseek-reasoner` were retired 2026-07-24; the current IDs
are `deepseek-flash` and `deepseek-v4-pro` ([changelog](https://api-docs.deepseek.com/updates/)).
The reasoning model costs ≈ 4× and buys us nothing for this task.

To use it today:

```bash
export DYSREWRITE_LLM_BASE_URL=https://api.deepseek.com/v1
export DYSREWRITE_LLM_MODEL=deepseek-flash
export DYSREWRITE_LLM_API_KEY=sk-...
dysrewrite rewrite book.epub --engine llm -p profiles/jenn.json -o book.rewritten.html
```

Privacy note for the hosted tier: whole books leave the machine. That is fine for
public-domain and the reader's own purchases at their choice; it is never the default,
and Jennifer's writing samples never go through it (only the derived profile does).

### Tier 2 — local model ($0, slower)

Ollama on Apple Silicon, Q4 quantised, Qwen3-8B-class: roughly 12 tok/s on an M1
(≈ 3 h per book), 45 tok/s on an M4 Pro (≈ 50 min), 90 tok/s on an M5 Max (≈ 25 min);
4B models run 1.5–2× faster ([community benchmark](https://llmcheck.net/models/qwen-3-8b-on-m2/),
secondary source). Decode only; Ollama does not reuse the system-prompt KV cache across
requests, so real wall clock is higher. This is the private path and the default one
in the CLI. Quality caveat below.

### Tier 3 — small fine-tuned model (the end state)

Two 2025–26 benchmarks change the plan:

- [Redefining Simplicity (2025)](https://arxiv.org/pdf/2502.08281): a 2B model matches
  GPT-4o on *sentence-level* simplification but collapses at document level (SARI 29.6
  vs 42.0). So keep the unit of work a paragraph or a sentence, never a chapter.
- [Simplify-This (2026)](https://arxiv.org/abs/2601.05794): fine-tuned sub-1B
  encoder-decoders (BART/T5) **beat prompted LLMs** on SARI (38.0 vs 27.1 on ASSET) and
  in human preference (46.9 % vs 31.5 %); prompted models often score well on
  faithfulness because they copy the input nearly verbatim.

Plan: log every (original sentence, rewritten sentence, reader verdict) triple the
site and CLI produce — Tier 0 and Tier 1 outputs that readers did not mark as tripped
become positive examples; tripped ones become negatives. A few thousand pairs is enough
to LoRA-tune a 0.5–2B model (Qwen3-1.7B or Flan-T5-base) on top of WikiLarge / ASSET /
[MultiSim](https://huggingface.co/datasets/MichaelR207/MultiSim) pre-training. Existing
starting points: [t5-small text simplification](https://huggingface.co/mrm8488/t5-small-finetuned-text-simplification).
There is **no English dyslexia-specific simplification dataset** on Hugging Face (the
only one found is French primary-school, [dyslexia-french-cp-ce1](https://huggingface.co/datasets/lsadouk1111/dyslexia-french-cp-ce1));
publishing ours — content-free, as sentence pairs from public-domain text — would be
a real contribution. Per-book cost at this tier: $0 and seconds on a laptop.

### 4.1 Per-axis converter recipe

The engine is the same at every tier; what changes per axis is the profile weights
(which triggers get flagged) and, at Tier 1+, a short axis-specific block appended to
the system prompt.

| Axis | Tier 0 rules that carry the load | Tier 1 prompt addition | Layout |
|---|---|---|---|
| Phonological | `rare` → frequent swap, `long` → short swap, `min_zipf` raised | "Prefer short, common, regularly spelled words; avoid words whose spelling does not match their sound" | syllable breaks optional |
| Orthographic | `heteronym`, `ambiguity`, `phonetic` swaps; keep one spelling ↔ one meaning per passage | "Never use the same spelling for two meanings in one paragraph; avoid irregular and homophone-prone spellings" | originals on hover |
| VAS | `long` swap, `max_word_length` ≤ 8 | "Prefer words of eight letters or fewer" | `max_line_chars` 45–55, wider word spacing |
| RAN / rate | syntax splits, subject-first | "Start every sentence with its subject; one clause per sentence" | paragraph breaks every 2–3 sentences, TTS button |
| Attention / WM | syntax family at weight 2, `Because` split, relative lift | "One idea per sentence; make every connective explicit (so, but, then)" | short paragraphs |
| Individual | `personal` triggers, `replacements`, `vocabulary`, style targets from `learn` | reader vocabulary list and sentence-length target injected (already done) | reader's own layout |

The fidelity gate stays on for all of them. A rewrite that changes a fact is a bug at
any price.

---

## 5. What to build next, in order

1. **Test H (heteronym probe) and test B (typed dictation)** on the site. H is the
   experiment only we can run; B is the cheapest validated subtype discriminator.
   Both are static stimuli plus a results table — no AI, no audio.
2. **Weights from battery**: a pure function `battery → ReaderProfile` in the Python
   package, with the mapping in section 3 as the first version. Add
   `dysrewrite assess --from results.json`.
3. **TTS button** in the reader (`speechSynthesis` in the browser is free and offline).
4. **`annotate_instead_of_replace`** profile flag: show the original word with a gloss
   instead of swapping it.
5. **DeepSeek as a documented Tier 1** (env vars above) plus a `--engine llm`
   cost estimate printed before a whole-book run.
6. **Pair logging** for Tier 3: every accepted / tripped sentence pair, content-free
   for private texts (hashes) and full for public-domain ones.
7. C, D, E, F, G in that order; then the first analysis in 3.1 once six readers have
   done six pairs each.

## Sources not linked above

- Friedmann & Coltheart, *Types of developmental dyslexia* (overview of dual-route subtypes). https://www2.crui.it/crui/CNUDD/Beyond_Reading/1_Daniela_Traficante/Friedmann_Coltheart_types_of_developmental_dyslexia.pdf
- Rello et al., *Dytective: diagnosing risk of dyslexia with a game*, PervasiveHealth 2016 / ASSETS. https://www.cs.cmu.edu/~jbigham/pubs/pdfs/2015/dytective_assets.pdf
- Rello et al., *DysWebxia: how to present more readable text for people with dyslexia*, UAIS 2016. https://link.springer.com/article/10.1007/s10209-015-0438-8
- Alva-Manchego et al., *ASSET* dataset. https://huggingface.co/datasets/asset
- British Dyslexia Association adult checklist. https://www.bdadyslexia.org.uk/dyslexia/how-is-dyslexia-diagnosed/dyslexia-checklists

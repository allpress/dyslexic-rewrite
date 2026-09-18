# Roadmap

Four phases. Each is usable on its own; each later phase adds a layer without replacing the one before.

## Principles

1. **Free, forever.** MIT. No accounts, no paid tier. Anything that costs money (hosted LLMs) is optional; the default path runs on a laptop with open models or no model at all.
2. **Local-first.** Profiles, writing samples and the books someone reads stay on their machine. Personal writing is sensitive data.
3. **Never destroy the original.** Every change is reversible and visible on demand. The reader can always see the original word or sentence.
4. **Meaning is protected.** Names, numbers, quotes, dialogue and domain terms are locked spans. A rewrite that changes meaning is a bug.
5. **Measure, don't assume.** Every profile change should be testable with a reading-speed and comprehension check the reader can run in two minutes.
6. **The reader is the expert.** "This word tripped me" is the most valuable signal in the system.
7. **English first, designed for any language.** Trigger lists, phonetic matching and frequency tables are plug-in resources per language.

## Phase 1 — General rewriter (v0.1 shipped, v0.2 next)

Outcome: a CLI that takes a .txt/.md/.html/.epub and produces a rewritten copy plus an HTML reader view with originals on hover.

- [x] Trigger detectors: heteronym, ambiguity (re-used word, different POS), phrasal, phonetic, rare, long, syntax
- [x] Curated heteronym table with POS-keyed alternatives and pronunciation hints (102 words, 56 phrasal verbs, 80 confusable pairs)
- [x] Rule engine: safe substitutions, coordinated-clause split, leading-subordinate split, trailing relative split, subject-relative lift, semicolons
- [x] Protected spans + fidelity check
- [x] Optional LLM engine (Ollama default) with fidelity gate and rules fallback
- [x] HTML reader view: profile-driven layout, originals on hover, hints, tripped-word marking, timer, feedback export
- [x] Profiles: default, phonological, visual, attention
- [x] `learn` from writing samples; `profile feedback` / `profile add`
- [x] 20 tests
- [ ] v0.2: passive → active when the agent is present ("was built by the team" → "the team built")
- [ ] v0.2: coreference-aware pronoun choice when lifting clauses (use "She" for Mrs. Alvarez when the text already does)
- [ ] v0.2: word-sense disambiguation for same-POS heteronyms (`tear`/`tear` both nouns) so more of them can be swapped safely
- [ ] v0.2: EPUB → EPUB output that preserves chapters and formatting
- [ ] v0.2: PyPI release, `pipx install dyslexic-rewrite`
- [ ] Done when: one dyslexic reader reads a chapter in both versions and the tool reports her time and a 5-question comprehension score

## Phase 2 — Dyslexia-type profiles

Outcome: built-in profiles for the main patterns, validated with real readers.
Research and the full test/converter plan: [docs/RESEARCH.md](docs/RESEARCH.md).

- [ ] Browser screening battery on unwindwords.com (≈10 min, static stimuli, no AI): heteronym probe (H) and typed spelling dictation (B) first, then orthographic choice, pseudohomophone decision, VAS whole report, backward digit span, RAN via the recorder
- [ ] `dysrewrite assess --from results.json`: battery scores → profile weights (mapping in RESEARCH.md §3)
- [ ] Axes instead of types: phonological, orthographic, VAS, RAN/rate, attention — weights, not categories
- [x] Text-to-speech button in the reader (strongest-evidenced accommodation in the literature)
- [x] Phonetic map: friendly respellings (`WYND` / `WIND`, `in-TEN-shun`) over trigger words, off / on demand / always, in the CLI reader and on the site; the A/B test records the mode so it can be measured as its own lever
- [ ] `annotate_instead_of_replace` profile flag (Rello's "simplify or help?" finding)
- [ ] Documented cheap hosted tier: DeepSeek `deepseek-flash` behind the fidelity gate (~$0.10 per book), cost estimate printed before a whole-book run
- [ ] Layout controls per profile: chunking, syllable breaks, line length, colour (comfort only — no overlay/font claims)
- [ ] Done when: the axis profile from the battery predicts which rewrite lever produced a reader's speed gain, across at least six readers × six passage pairs

## Phase 3 — Individual tuning

Outcome: a profile learned from the reader's own writing and speech that beats the type profile for that reader.

- [ ] Richer style extraction: preferred constructions (how they start sentences, how they join clauses), connective words they use, their own frequent bigrams
- [ ] Rewrite *toward* the reader's style: choose among candidate rewrites by similarity to their sentences
- [ ] Speech input via local Whisper (`--audio`) — speaking is often closer to how a dyslexic person thinks than their writing is
- [ ] Feedback loop tightened: tripped words raise the weight of the whole trigger family they belong to, not just the word
- [ ] Log (original sentence, rewritten sentence, reader verdict) pairs; LoRA-tune a 0.5–2B model on them once there are a few thousand — fine-tuned small models beat prompted cheap LLMs on simplification (RESEARCH.md §4, Tier 3)
- [ ] Done when: the personal profile measurably beats the type profile for that reader

## Phase 4 — Measurement and community

- [ ] Built-in A/B reading test: same passage, original vs rewritten, timer + 5 questions, results stored locally
- [ ] Opt-in anonymised result sharing so the project can publish what actually helps
- [ ] Browser extension that rewrites the page you are on
- [ ] E-reader export (EPUB/Kindle) and a simple web UI
- [ ] Language packs (Spanish first — the largest body of dyslexia + simplification research is in Spanish)
- [ ] Done when: published results and external contributors merging PRs

## Sources

- Rello, Baeza-Yates, Bott, Saggion. *Simplify or help? Text simplification strategies for people with dyslexia.* W4A 2013. https://www.superarladislexia.org/pdf/2013-Luz%20Rello-w4a.pdf
- Rello, Baeza-Yates, Saggion. *The impact of lexical simplification by verbal paraphrases for people with and without dyslexia.* CICLing 2013. https://superarladislexia.org/pdf/2013-Luz%20Rello-cicling.pdf
- Rello, Baeza-Yates, Dempere-Marco, Saggion. *Frequent words improve readability and short words improve understandability for people with dyslexia.* INTERACT 2013. https://link.springer.com/chapter/10.1007/978-3-642-40498-6_15
- *Phonological, orthographic, and semantic processing during sentence reading in adults with dyslexia.* Brain and Cognition, 2025. https://pubmed.ncbi.nlm.nih.gov/40619103/
- Mazlumi et al. *Linking attention deficits to difficulties in the comprehension of complex syntax in dyslexia.* Dyslexia, 2026. https://onlinelibrary.wiley.com/doi/full/10.1002/dys.70026
- *Beyond Simplification: DFT-GEN for fidelity-preserving visual accessibility in dyslexia-friendly educational texts.* arXiv, 2026. https://arxiv.org/abs/2608.13583
- *Emerging technologies and neuroscience-based approaches in dyslexia: a narrative review toward integrative and personalized solutions.* Frontiers in Human Neuroscience, 2025. https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2025.1683924/full
- *Automated text simplification: a survey.* ACM Computing Surveys 54(2), 2021. https://dl.acm.org/doi/10.1145/3442695

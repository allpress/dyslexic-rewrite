# Contributing

Thank you. This project exists to help people with dyslexia read, and it is free forever.

## Ways to help

**If you have dyslexia, or read with someone who does:** the most valuable thing you can do is try it on a real
chapter and tell us what happened. Which words tripped you? Did a rewrite change the meaning? Was the reader view
comfortable? Open an issue with the passage (or a similar one) and what you saw. Export feedback from the HTML
view and attach it if you are comfortable doing so.

**Words and data** (`src/dyslexic_rewrite/data/heteronyms.json`):
- Add heteronyms and multi-sense words. Keep alternatives common, short and meaning-preserving. If a part of speech
  still has two senses (`tear` the noun: rip or teardrop), leave its list empty and add a `_hint` instead — an empty
  list means "flag it, never auto-swap it".
- Add confusable pairs you or your readers actually mix up.
- Add phrasal verbs with an `object` value: `no` if the idiom only works without a direct object (`wind up` = end up),
  `yes` if it only works with one, `any` otherwise.

**Rules** (`src/dyslexic_rewrite/rewrite/rules.py`): every shape rule must keep meaning. Add a test in `tests/`
with the sentence before and after. If you find a sentence the rules mangle, a failing test is a great contribution
on its own.

**Language packs:** trigger tables, phonetic matching and frequency data are per-language. Spanish is the first
target; open an issue before starting so we can agree on the layout.

## Ground rules

- Free and local by default. Nothing may require an account, a key, or a network call to work.
- Never silently change meaning. Names, numbers, quotes and terminology are protected. When in doubt, flag instead of swap.
- Keep the reader's dignity: no childish rewrites, same register as the source.
- Personal profiles and writing samples are private data. Never log them, never upload them, never commit them.

## Dev setup

```bash
git clone https://github.com/allpress/dyslexic-rewrite && cd dyslexic-rewrite
pip install -e ".[all]"
python -m spacy download en_core_web_sm
pytest
```

Style: `ruff check src tests`. Python 3.10+. Small PRs with a test beat big ones without.

## Code of conduct

Be kind. Many contributors here will be people who found reading hard for most of their lives; the tone of every
comment should assume that.

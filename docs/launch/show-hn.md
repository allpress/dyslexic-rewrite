# Show HN

Post between 08:00 and 09:00 ET, Tuesday–Thursday. Title under 80 characters. Link to the
repo, not the site (HN prefers source; the README's first line points at the site). Reply to
every comment in the first two hours — that is what keeps it on the front page.

## Title

Show HN: Unwind Words – open-source tool that rewrites books for dyslexic readers

## First comment (post it yourself immediately after submitting)

I built this for my wife. She's dyslexic, and the thing that stops her reading isn't letters
— it's specific words. "Wind" as in "wind up the clock" followed by "the wind blows" two lines
later stops the whole paragraph. Same spelling, different word, and her brain has to go back
and re-decide.

So the engine finds those (heteronyms, the same spelling re-used with a different meaning,
phrasal verbs that mislead, near-homophones landing close together, rare and long words,
sentence shapes that overload working memory), rewrites what it can safely rewrite, and marks
the rest with a friendly respelling above the word (WYND vs WIND). Every change is reversible
— the original is one hover away — because the research (Rello 2013) says silent swaps don't
help but showing an easier option does. Names, numbers and quotes are locked; a rewrite that
changes meaning is a bug.

It's Python (spaCy + CMUdict + a rules engine) with an optional LLM tier behind a fidelity
gate; the CLI and the engine are MIT. The website adds a 10-minute screening that gives a
five-axis profile (the literature's multiple-deficit model, not a "type"), A/B reading tests
that time you on original vs rewritten passages, and a library that turns an EPUB/PDF into a
dyslexia-friendly EPUB you can send to a Kindle. The library is the paid bit ($5/mo) and
pays for hosting; everything a single reader needs for a page is free.

The part I find most interesting: nobody has studied heteronyms in dyslexia. The closest work
is idiom processing and garden-path recovery. So the site includes a self-paced reading probe
with matched control sentences, and I'll publish whatever the data says, including a null.

Repo: https://github.com/allpress/dyslexic-rewrite — try it on a sample chapter at
https://unwindwords.com/read?sample=wind-in-the-willows

Happy to answer anything about the trigger detection, the respelling rules, or the fidelity
gate.

## Likely questions and honest answers

- *Is there evidence this works?* Word frequency and length substitution: yes (Rello &
  Baeza-Yates 2013). Sentence simplification: theory strong, direct A/B thin. Heteronym
  avoidance: our hypothesis, being measured. Fonts and overlays: no, and we don't claim it.
- *Why not just TTS?* TTS is the best-evidenced accommodation and it's built in. Rewriting is
  for when you want to read, not listen.
- *Doesn't rewriting change the book?* The rules engine only swaps where the meaning is
  unambiguous and keeps the original one hover away. The LLM tier rejects any paragraph that
  loses a name, number or quote, drifts in length, or invents a proper noun.
- *Privacy?* Profiles and books stay on the server you signed into; nothing is sold; there's
  a delete-account button; no third-party scripts. The CLI runs entirely offline.

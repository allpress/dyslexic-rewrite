"""Command-line interface: dysrewrite"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .analyze import analyze
from .io import read_text, write_epub
from .profile import BUILTIN_PROFILES, load_profile
from .pronounce import respell
from .render import write_outputs
from .rewrite.engine import rewrite as _rewrite

_PHONETIC_MAP_CHOICES = ["off", "on_demand", "always"]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="dysrewrite")
def main():
    """Rewrite text so dyslexic readers can read it faster. Free, local, open source.

    Typical flow:

      dysrewrite analyze chapter.txt                 # see what would trip a reader

      dysrewrite rewrite chapter.txt -o out/         # HTML reader view + plain text

      dysrewrite learn my_emails.txt -o me.json      # build a personal profile

      dysrewrite rewrite chapter.txt -p me.json      # rewrite for *me*
    """


# --------------------------------------------------------------------------------------
@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("-p", "--profile", "profile_name", default="default", show_default=True,
              help=f"Built-in profile {BUILTIN_PROFILES} or path to a profile .json")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output")
@click.option("--show", type=int, default=25, show_default=True, help="How many triggers to list (0 = none, -1 = all)")
@click.option("--phonetic-map", "phonetic_map", type=click.Choice(_PHONETIC_MAP_CHOICES), default=None,
              help="Override the profile's phonetic map mode for this run")
def analyze_cmd(file, profile_name, as_json, show, phonetic_map):
    """Find the words and sentence shapes that would trip a reader."""
    profile = load_profile(profile_name)
    if phonetic_map:
        profile.phonetic_map = phonetic_map
    text = read_text(file)
    report = analyze(text, profile)
    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return
    click.echo(report.summary())
    if show:
        click.echo("\nTriggers:")
        items = report.triggers if show < 0 else report.triggers[:show]
        for t in items:
            alts = f"  → {', '.join(t.alternatives[:3])}" if t.alternatives else ""
            hint = f"  [{t.hint}]" if t.hint else ""
            r = respell(t.text, pos=t.pos or None, tag=getattr(t, "tag", "") or None)
            say = f"  (say: {r.respell})" if r else ""
            txt = t.text if len(t.text) <= 40 else t.text[:37] + "..."
            click.echo(f"  {t.kind:<9} s{t.sent_index:<4} {txt!r:44} {t.reason}{alts}{hint}{say}")
        if 0 < show < len(report.triggers):
            click.echo(f"  ... {len(report.triggers) - show} more (use --show -1)")


main.add_command(analyze_cmd, name="analyze")


# --------------------------------------------------------------------------------------
@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("-p", "--profile", "profile_name", default="default", show_default=True)
@click.option("-o", "--out", "out_dir", type=click.Path(file_okay=False), default="dysrewrite_out", show_default=True)
@click.option("-e", "--engine", type=click.Choice(["rules", "llm"]), default="rules", show_default=True,
              help="rules = deterministic, no model. llm = local Ollama or any OpenAI-compatible API, with fidelity checks and rules fallback.")
@click.option("-f", "--format", "formats", multiple=True, default=("html", "txt", "md"),
              type=click.Choice(["html", "txt", "md", "json"]), show_default=True)
@click.option("--simplify-vocab", is_flag=True, help="Also swap rare/long words for plain ones when a safe one is known")
@click.option("--phonetic-map", "phonetic_map", type=click.Choice(_PHONETIC_MAP_CHOICES), default=None,
              help="Override the profile's phonetic map mode (off/on_demand/always) for this run")
@click.option("--epub", "want_epub", is_flag=True,
              help="Also write an EPUB (automatic when the input file is itself .epub)")
@click.option("-v", "--verbose", is_flag=True)
def rewrite(file, profile_name, out_dir, engine, formats, simplify_vocab, phonetic_map, want_epub, verbose):
    """Rewrite a .txt/.md/.html/.epub file and write an HTML reader view next to plain text."""
    profile = load_profile(profile_name)
    if phonetic_map:
        profile.phonetic_map = phonetic_map
    text = read_text(file)
    if not text.strip():
        raise click.ClickException("No text found in the file.")
    report = analyze(text, profile)
    result = _rewrite(text, profile, engine=engine, simplify_vocab=simplify_vocab, report=report, verbose=verbose)
    stem = Path(file).stem + f".{profile.name}"
    written = write_outputs(result, profile, Path(out_dir), stem, tuple(formats))
    st = result.stats
    click.echo(f"{st['sentences']} sentences, {st['sentences_changed']} changed, {st['changes']} word changes "
               f"({', '.join(f'{k} {v}' for k, v in st['changes_by_kind'].items()) or 'none'})")
    click.echo(f"reading load {st['load_before']} → {st.get('load_after', '?')} per 100 words")
    if engine == "llm":
        click.echo(f"llm paragraphs {st['llm_paragraphs']}, fell back to rules {st['llm_fallbacks']}")
    for p in written:
        click.echo(f"wrote {p}")
    if want_epub or Path(file).suffix.lower() == ".epub":
        epub_path = write_epub(result, Path(out_dir) / f"{stem}.epub", title=Path(file).stem, profile=profile)
        click.echo(f"wrote {epub_path}")


# --------------------------------------------------------------------------------------
@main.command()
@click.argument("samples", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", "out_path", default="personal.json", show_default=True)
@click.option("-b", "--base", default="default", show_default=True, help="Profile to start from")
@click.option("-n", "--name", default="personal", show_default=True)
@click.option("--audio", is_flag=True, help="Treat the samples as audio files and transcribe them locally first")
@click.option("-r", "--report", "report_path", default=None,
              help="Also write a style report (aggregate metadata only, no content) to this JSON path")
def learn(samples, out_path, base, name, audio, report_path):
    """Build a personal profile from the reader's own writing (or speech).

    Reads .txt/.md/.html/.epub, or a .json export of posts (see scripts/export_facebook_posts.js).
    Stores only aggregate metadata — never a sentence from the sample — so the raw sample
    can be deleted afterwards.
    """
    from .learn import analyze_style, learn_profile, transcribe
    texts = []
    for s in samples:
        texts.append(transcribe(s) if audio else read_text(s))
    report = analyze_style(texts)
    profile = learn_profile(texts, base=base, name=name, report=report)
    profile.save(out_path)
    if report_path:
        Path(report_path).write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    r = report
    click.echo(f"learned from {r.sample_words} words, {r.sample_sentences} sentences, {r.sample_paragraphs} paragraphs")
    click.echo(f"sentences: median {r.sentence_words_median:.0f} words, p75 {r.sentence_words_p75:.0f}, p90 {r.sentence_words_p90:.0f}; "
               f"short {r.short_sentence_rate:.0%}, long {r.long_sentence_rate:.0%}, fragments {r.fragment_rate:.0%}")
    click.echo(f"shape: {r.clauses_per_sentence:.2f} clauses/sentence, passive {r.passive_rate:.0%}, "
               f"subject-first {r.subject_first_rate:.0%}, centre-embedded {r.centre_embedded_rate:.1%}, "
               f"{r.comma_per_sentence:.2f} commas/sentence")
    click.echo(f"words: mean {r.word_length_mean:.1f} letters, median frequency {r.word_zipf_median:.2f}, "
               f"rare {r.rare_word_rate:.1%}, long {r.long_word_rate:.1%}, first-person {r.first_person_rate:.1f}/100")
    click.echo(f"voice: exclamations {r.exclamation_rate:.0%} (multi {r.multi_exclaim_rate:.0%}), questions {r.question_rate:.0%}, "
               f"ellipses {r.ellipsis_rate:.0%}, parentheses {r.parenthetical_rate:.0%}, emoji {r.emoji_per_sentence:.2f}/sentence, "
               f"contractions {r.contraction_rate:.2f}/sentence")
    top = ", ".join(f"{w} {c}" for w, c in list(r.sentence_starters.items())[:8])
    click.echo(f"starts sentences with: {top}")
    click.echo(f"connectives: {', '.join(f'{w} {c}' for w, c in list(r.connectives.items())[:8])}")
    click.echo(f"targets: max_sentence_words={profile.max_sentence_words}, min_zipf={profile.min_zipf}, "
               f"vocabulary={len(profile.vocabulary)} words, safe heteronyms={len(profile.safe_words)}")
    click.echo(f"wrote {out_path}" + (f" and {report_path}" if report_path else ""))
    click.echo("The profile holds aggregate metadata only. You can delete the raw sample file(s) now:")
    for s in samples:
        click.echo(f"  rm {s}")


# --------------------------------------------------------------------------------------
@main.group()
def profile():
    """Show, create, and teach reader profiles."""


@profile.command("list")
def profile_list():
    """List built-in profiles."""
    for n in BUILTIN_PROFILES:
        p = load_profile(n)
        click.echo(f"{n:<13} {p.description}")


@profile.command("show")
@click.argument("name_or_path", default="default")
def profile_show(name_or_path):
    """Print a profile as JSON."""
    click.echo(json.dumps(load_profile(name_or_path).to_dict(), indent=2, ensure_ascii=False))


@profile.command("new")
@click.argument("out_path")
@click.option("-b", "--base", default="default", show_default=True)
@click.option("-n", "--name", default=None)
def profile_new(out_path, base, name):
    """Copy a built-in profile to a file you can edit."""
    p = load_profile(base)
    p.name = name or Path(out_path).stem
    p.save(out_path)
    click.echo(f"wrote {out_path}")


@profile.command("feedback")
@click.argument("profile_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("feedback_files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
def profile_feedback(profile_path, feedback_files):
    """Fold exported reader feedback (from the HTML view) into a profile."""
    p = load_profile(profile_path)
    added = 0
    for f in feedback_files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        before = len(p.trigger_words)
        p.add_feedback(data.get("tripped", []), data.get("safe", []), data.get("replacements", {}))
        added += len(p.trigger_words) - before
        if data.get("wpm"):
            click.echo(f"{f}: {data['wpm']} wpm over {data.get('words')} words")
    p.save(profile_path)
    click.echo(f"added {added} trigger words → {len(p.trigger_words)} total; wrote {profile_path}")


@profile.command("add")
@click.argument("profile_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-t", "--trigger", multiple=True, help="Word that trips the reader (repeatable)")
@click.option("-s", "--safe", multiple=True, help="Word to always leave alone (repeatable)")
@click.option("-r", "--replace", multiple=True, metavar="WORD=REPLACEMENT", help="Always swap WORD for REPLACEMENT")
def profile_add(profile_path, trigger, safe, replace):
    """Add trigger words, safe words, or fixed replacements to a profile."""
    p = load_profile(profile_path)
    repl = {}
    for r in replace:
        if "=" not in r:
            raise click.BadParameter("use WORD=REPLACEMENT", param_hint="--replace")
        k, v = r.split("=", 1)
        repl[k] = v
    p.add_feedback(list(trigger), list(safe), repl)
    p.save(profile_path)
    click.echo(f"wrote {profile_path}: {len(p.trigger_words)} triggers, {len(p.safe_words)} safe, {len(p.replacements)} replacements")


# --------------------------------------------------------------------------------------
@main.command()
@click.argument("word")
@click.option("--pos", default=None, help="Coarse POS to pick a sense: VERB, NOUN, ADJ, ADV")
@click.option("--tag", default=None, help="Fine-grained spaCy tag (e.g. VBD/VBP) for tense-based words like 'read'")
def say(word, pos, tag):
    """Print the friendly respelling for a word (handy for checking the phoneme table)."""
    r = respell(word, pos=pos, tag=tag)
    if r is None:
        raise click.ClickException(
            f"No pronunciation found for {word!r}. Is the 'cmudict' package installed, "
            "and is this an English word?"
        )
    click.echo(r.respell)
    if r.hint:
        click.echo(f"hint: {r.hint}")
    if r.ambiguous:
        click.echo("(ambiguous: this word has more than one pronunciation; pass --pos or --tag to pick one)")


# --------------------------------------------------------------------------------------
@main.command()
def demo():
    """Rewrite the bundled example and open nothing — just show what happens."""
    sample = Path(__file__).parent / "data" / "sample.txt"
    text = sample.read_text(encoding="utf-8")
    for name in ("default", "attention"):
        p = load_profile(name)
        r = _rewrite(text, p)
        click.echo(f"\n=== {name} ===\n{r.text}\n{r.stats}")


# --------------------------------------------------------------------------------------
@main.command()
@click.option("--from", "results_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Raw battery results JSON (see server/API.md, 'which kind of reader am I?')")
@click.option("-p", "--profile", "profile_name", default="default", show_default=True,
              help=f"Base profile to fold the result onto: {BUILTIN_PROFILES} or a path to a profile .json")
@click.option("-o", "--out", "out_path", default="profile.json", show_default=True)
def assess(results_path, profile_name, out_path):
    """Score a browser-battery result file into axes, and write a reader profile.

    A first cut, not a validated instrument (docs/RESEARCH.md, section 3) -- this reports axes,
    never a diagnosis.
    """
    from .assess import AXIS_LABELS, profile_from_scores, score_battery
    raw = json.loads(Path(results_path).read_text(encoding="utf-8"))
    scores = score_battery(raw)
    base = load_profile(profile_name)
    profile = profile_from_scores(scores, base)
    profile.save(out_path)

    click.echo("Axes (0 = no extra support needed, 100 = a lot):\n")
    for axis_id in ("phonological", "orthographic", "rate", "vas", "attention"):
        axis = scores.axis(axis_id)
        bar_len = round(axis.support / 100 * 30)
        bar = "#" * bar_len + "-" * (30 - bar_len)
        low = "  (low confidence -- this task was skipped)" if axis.confidence == "low" else ""
        click.echo(f"  {AXIS_LABELS[axis_id]:<32} [{bar}] {axis.support:5.1f}{low}")

    click.echo(f"\n  {'Visual comfort (self-report only)':<32} [{'#' * round(scores.comfort.support / 100 * 30):-<30}] {scores.comfort.support:5.1f}")

    h = scores.heteronym
    if h.reliable:
        click.echo(f"\nTricky-word slowdown: {h.slowdown_ms:.0f}ms ({h.slowdown_ratio:.0%} slower) over "
                    f"{h.pairs_scored} matched pairs -- reliable.")
    elif h.slowdown_ms is not None:
        click.echo(f"\nTricky-word slowdown: {h.slowdown_ms:.0f}ms over {h.pairs_scored} matched pairs "
                    "-- not reliable enough to act on.")
    else:
        click.echo("\nTricky-word slowdown: not measured (task H was skipped).")

    click.echo(f"\nwrote {out_path}")


main.add_command(assess, name="assess")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""Command-line interface: dysrewrite"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .analyze import analyze
from .io import read_text
from .profile import BUILTIN_PROFILES, load_profile
from .render import write_outputs
from .rewrite.engine import rewrite as _rewrite


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
def analyze_cmd(file, profile_name, as_json, show):
    """Find the words and sentence shapes that would trip a reader."""
    profile = load_profile(profile_name)
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
            txt = t.text if len(t.text) <= 40 else t.text[:37] + "..."
            click.echo(f"  {t.kind:<9} s{t.sent_index:<4} {txt!r:44} {t.reason}{alts}{hint}")
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
@click.option("-v", "--verbose", is_flag=True)
def rewrite(file, profile_name, out_dir, engine, formats, simplify_vocab, verbose):
    """Rewrite a .txt/.md/.html/.epub file and write an HTML reader view next to plain text."""
    profile = load_profile(profile_name)
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


# --------------------------------------------------------------------------------------
@main.command()
@click.argument("samples", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", "out_path", default="personal.json", show_default=True)
@click.option("-b", "--base", default="default", show_default=True, help="Profile to start from")
@click.option("-n", "--name", default="personal", show_default=True)
@click.option("--audio", is_flag=True, help="Treat the samples as audio files and transcribe them locally first")
def learn(samples, out_path, base, name, audio):
    """Build a personal profile from the reader's own writing (or speech)."""
    from .learn import learn_profile, transcribe
    texts = []
    for s in samples:
        texts.append(transcribe(s) if audio else read_text(s))
    profile = learn_profile(texts, base=base, name=name)
    profile.save(out_path)
    st = profile.style
    click.echo(f"learned from {st.sample_words} words: median sentence {st.median_sentence_words:.0f} words, "
               f"p75 {st.p75_sentence_words:.0f}, clause depth {st.clause_depth:.2f}, passive rate {st.passive_rate:.0%}, "
               f"median word frequency {st.median_zipf:.2f}")
    click.echo(f"targets: max_sentence_words={profile.max_sentence_words}, min_zipf={profile.min_zipf}, "
               f"vocabulary={len(profile.vocabulary)} words")
    click.echo(f"wrote {out_path}")


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
def demo():
    """Rewrite the bundled example and open nothing — just show what happens."""
    sample = Path(__file__).parent / "data" / "sample.txt"
    text = sample.read_text(encoding="utf-8")
    for name in ("default", "attention"):
        p = load_profile(name)
        r = _rewrite(text, p)
        click.echo(f"\n=== {name} ===\n{r.text}\n{r.stats}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

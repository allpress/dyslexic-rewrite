"""Renderers: plain text, markdown diff, and the HTML reader view.

The HTML reader is the main product for now. It is one self-contained file, no network,
no tracking. It gives the reader:
  - dyslexia-friendly layout driven by the profile (size, spacing, line length)
  - every changed word underlined; hover or tap shows the original and why it changed
  - flagged-but-unchanged words get a dotted underline with a pronunciation hint
  - a "this word tripped me" toggle on any word, plus a reading timer
  - an Export feedback button that saves a JSON file the profile can learn from
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .profile import ReaderProfile
from .pronounce import respell
from .rewrite.model import RewriteResult
from .triggers.base import Trigger

_CSS = """
:root {{
  --bg: {background}; --fg: {text}; --muted: #6b6f76; --accent: #1f6f8b; --note: #8a6d1f;
  --fs: {font_size_px}px; --lh: {line_height}; --ls: {letter_spacing_em}em; --ws: {word_spacing_em}em;
  --maxw: {max_line_chars}ch; --pgap: {paragraph_gap_em}em;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #17191c; --fg: #e8e6e1; --muted: #9aa0a6; --accent: #7cc4de; --note: #d6b35a; }}
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--fg); }}
body {{ font-family: "Atkinson Hyperlegible", "OpenDyslexic", "Lexend", Verdana, "Trebuchet MS", Arial, sans-serif;
  font-size: var(--fs); line-height: var(--lh); letter-spacing: var(--ls); word-spacing: var(--ws); }}
header {{ position: sticky; top: 0; background: var(--bg); border-bottom: 1px solid #0002; padding: 10px 16px;
  display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; font-size: 0.72em; letter-spacing: 0; z-index: 2; }}
header b {{ font-weight: 600; }}
header button, header label {{ font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid #0003; background: transparent; color: inherit; cursor: pointer; }}
header button:hover {{ background: #0001; }}
main {{ max-width: var(--maxw); margin: 0 auto; padding: 28px 16px 120px; }}
p {{ margin: 0 0 var(--pgap); text-align: left; hyphens: none; }}
h2 {{ font-size: 1.15em; margin: 1.6em 0 0.6em; }}
.w {{ cursor: pointer; border-radius: 3px; }}
.w:hover {{ background: #1f6f8b18; }}
.w.tripped {{ background: #d9534f33; outline: 2px solid #d9534f88; }}
.chg {{ border-bottom: 2px solid var(--accent); }}
.note {{ border-bottom: 2px dotted var(--note); }}
body.plain .chg, body.plain .note {{ border-bottom: none; }}
body.showorig .chg::after {{ content: " (" attr(data-orig) ")"; color: var(--muted); font-size: 0.8em; }}
ruby {{ ruby-position: over; }}
rt {{ display: none; font-size: 0.58em; font-weight: 700; color: var(--accent); letter-spacing: 0; word-spacing: 0; }}
.w.always rt {{ display: ruby-text; display: inline; }}
.w:hover rt, .w:focus rt, .w.open rt {{ display: ruby-text; display: inline; }}
body.pm-off rt {{ display: none !important; }}
body.pm-always rt {{ display: ruby-text; display: inline !important; }}
#tip {{ position: fixed; max-width: 34ch; background: #222; color: #fff; padding: 10px 12px; border-radius: 10px;
  font-size: 0.7em; line-height: 1.5; letter-spacing: 0; word-spacing: 0; pointer-events: auto; display: none; z-index: 5; }}
#tip b {{ color: #ffd58a; }}
#tip .speak-btn {{ font: inherit; margin-top: 4px; padding: 4px 8px; border-radius: 6px; border: 1px solid #fff5;
  background: #fff2; color: #fff; cursor: pointer; }}
#tip .speak-btn:hover {{ background: #fff3; }}
.s {{ }}
footer {{ max-width: var(--maxw); margin: 40px auto; padding: 0 16px; color: var(--muted); font-size: 0.7em; letter-spacing: 0; }}
"""

_JS = """
(function(){
  const tip = document.getElementById('tip');
  const tripped = new Set();
  const phoneticShown = new Set();
  const state = { started: null, finished: null };
  function wordOf(el){ return (el.dataset.orig || el.textContent).trim().toLowerCase(); }
  function show(e, el){
    let h = '';
    if (el.dataset.orig) h += '<b>Original:</b> ' + esc(el.dataset.orig) + '<br>';
    if (el.dataset.why)  h += esc(el.dataset.why) + '<br>';
    if (el.dataset.hint) h += '<b>Say it:</b> ' + esc(el.dataset.hint) + '<br>';
    if (el.dataset.respell) {
      h += '<b>Sounds like:</b> ' + esc(el.dataset.respell) + '<br>';
      phoneticShown.add(wordOf(el));
    }
    if (el.dataset.alts) h += '<b>Other words:</b> ' + esc(el.dataset.alts) + '<br>';
    if ('speechSynthesis' in window) {
      h += '<button type="button" class="speak-btn" data-say="' + esc(wordOf(el)) + '">&#128266; Say it aloud</button><br>';
    }
    h += '<i>Click the word to mark "this word tripped me"</i>';
    tip.innerHTML = h; tip.style.display = 'block';
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 10);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 18) + 'px';
  }
  function esc(s){ return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  function speak(text, rate){
    if (!('speechSynthesis' in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = rate || 0.85;
    speechSynthesis.speak(u);
    return u;
  }
  tip.addEventListener('click', (e) => {
    const btn = e.target.closest('.speak-btn');
    if (!btn) return;
    e.stopPropagation();
    speak(btn.dataset.say, 0.85);
  });
  document.querySelectorAll('.w').forEach(el => {
    el.addEventListener('mousemove', e => show(e, el));
    el.addEventListener('focus', e => show(e, el));
    el.addEventListener('mouseleave', () => tip.style.display = 'none');
    el.addEventListener('click', () => {
      el.classList.toggle('open');
      const w = wordOf(el);
      if (el.classList.toggle('tripped')) tripped.add(w); else tripped.delete(w);
      document.getElementById('count').textContent = tripped.size;
    });
  });
  document.getElementById('toggleOrig').onclick = () => document.body.classList.toggle('showorig');
  document.getElementById('togglePlain').onclick = () => document.body.classList.toggle('plain');
  const pmSelect = document.getElementById('pmToggle');
  if (pmSelect) {
    function applyPM(v){
      document.body.classList.remove('pm-off', 'pm-on_demand', 'pm-always');
      document.body.classList.add('pm-' + v);
    }
    pmSelect.value = PHONETIC_MAP_MODE;
    applyPM(PHONETIC_MAP_MODE);
    pmSelect.onchange = () => applyPM(pmSelect.value);
  }
  const readBtn = document.getElementById('readAloud');
  let reading = false;
  readBtn.onclick = () => {
    if (reading) {
      speechSynthesis.cancel(); reading = false; readBtn.textContent = 'Read aloud';
      return;
    }
    if (!('speechSynthesis' in window)) return;
    const paras = [...document.querySelectorAll('main p, main h2')].map(p => p.textContent.trim()).filter(Boolean);
    let i = 0;
    reading = true; readBtn.textContent = 'Stop reading';
    function next(){
      if (!reading || i >= paras.length) { reading = false; readBtn.textContent = 'Read aloud'; return; }
      const u = speak(paras[i++], 0.85);
      if (u) u.onend = next; else next();
    }
    next();
  };
  const timerBtn = document.getElementById('timer');
  timerBtn.onclick = () => {
    if (!state.started) { state.started = Date.now(); timerBtn.textContent = 'Finish reading'; }
    else if (!state.finished) {
      state.finished = Date.now();
      const mins = (state.finished - state.started) / 60000;
      const wpm = Math.round(WORDS / mins);
      timerBtn.textContent = 'Done: ' + wpm + ' wpm';
      state.wpm = wpm;
    }
  };
  document.getElementById('export').onclick = () => {
    const data = { tripped: [...tripped], profile: PROFILE, engine: ENGINE, words: WORDS,
                   phonetic_map_shown: [...phoneticShown],
                   seconds: state.finished && state.started ? Math.round((state.finished - state.started)/1000) : null,
                   wpm: state.wpm || null, exported: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'dysrewrite-feedback.json'; a.click();
  };
})();
"""


def _attrs(**kw) -> str:
    return "".join(f' data-{k}="{html.escape(str(v), quote=True)}"' for k, v in kw.items() if v)


def _phonetic_for_trigger(t: Trigger, profile: ReaderProfile) -> tuple[str, bool] | None:
    """(respell, always) for a flagged-but-kept word, or None if the phonetic map is off
    for this profile/kind/word. Mirrors the filtering `pronounce.phonetic_map()` does, but
    works straight off the Trigger objects already carried by the rewrite result so it
    stays exactly in step with what the reader view renders.
    """
    if profile.phonetic_map == "off":
        return None
    lw = t.text.lower()
    if lw in {w.lower() for w in profile.safe_words}:
        return None
    is_personal = t.kind == "personal" and lw in {w.lower() for w in profile.trigger_words}
    if t.kind not in set(profile.phonetic_map_kinds) and not is_personal:
        return None
    r = respell(t.text, pos=t.pos or None, tag=getattr(t, "tag", "") or None)
    if r is None:
        return None
    always = profile.phonetic_map == "always" or t.kind in set(profile.phonetic_map_always_kinds) or is_personal
    return r.respell, always


def to_html(result: RewriteResult, profile: ReaderProfile, title: str = "Rewritten text") -> str:
    parts = []
    words = 0
    for para in result.paragraphs:
        tag = "h2" if para.heading else "p"
        buf = []
        for s in para.sentences:
            buf.append('<span class="s">')
            for kind, val in s.segments:
                if kind == "text":
                    buf.append(html.escape(val))
                    words += len(val.split())
                elif kind == "change":
                    words += len(val.replacement.split())
                    buf.append(
                        f'<span class="w chg"{_attrs(orig=val.original, why=val.reason, alts=", ".join(val.alternatives[1:4]))}>'
                        f'{html.escape(val.replacement)}</span>'
                    )
                elif kind == "note":
                    words += 1
                    phon = _phonetic_for_trigger(val, profile)
                    cls = "w note always" if phon and phon[1] else "w note"
                    word_html = html.escape(val.text)
                    if phon:
                        word_html = f'<ruby>{word_html}<rt>{html.escape(phon[0])}</rt></ruby>'
                    buf.append(
                        f'<span class="{cls}"{_attrs(why=val.reason, hint=val.hint, respell=phon[0] if phon else "", alts=", ".join(val.alternatives[:3]))}>'
                        f'{word_html}</span>'
                    )
                elif kind == "break":
                    pass
            buf.append("</span> ")
        parts.append(f"<{tag}>{''.join(buf).strip()}</{tag}>")

    lay = dict(profile.layout)
    css = _CSS.format(**lay)
    st = result.stats
    return f"""<!doctype html>
<html lang="{profile.language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{css}</style>
</head>
<body>
<header>
  <b>{html.escape(title)}</b>
  <span>profile: {html.escape(profile.name)}</span>
  <span>{st.get('changes', 0)} changes · {st.get('sentences_changed', 0)}/{st.get('sentences', 0)} sentences · load {st.get('load_before', '?')} → {st.get('load_after', '?')}</span>
  <button id="toggleOrig">Show originals inline</button>
  <button id="togglePlain">Hide markings</button>
  <label>Phonetic map:
    <select id="pmToggle">
      <option value="off">off</option>
      <option value="on_demand">on demand</option>
      <option value="always">always</option>
    </select>
  </label>
  <button id="readAloud">Read aloud</button>
  <button id="timer">Start reading</button>
  <button id="export">Export feedback (<span id="count">0</span> marked)</button>
</header>
<main>
{chr(10).join(parts)}
</main>
<footer>Underlined words were changed — hover or tap to see the original. Dotted words were flagged but kept; hover for a pronunciation cue,
and a small "ᴬᴮᶜ" respelling above the word when the phonetic map is on. Click any marked word to record that it tripped you, then Export
feedback and run <code>dysrewrite profile feedback</code> to teach your profile.
Made with dyslexic-rewrite (free, open source, runs on your own computer).</footer>
<div id="tip"></div>
<script>
const WORDS = {words}; const PROFILE = {json.dumps(profile.name)}; const ENGINE = {json.dumps(result.engine)};
const PHONETIC_MAP_MODE = {json.dumps(profile.phonetic_map)};
{_JS}
</script>
</body>
</html>
"""


def to_markdown_diff(result: RewriteResult) -> str:
    """Side-by-side-ish markdown: each changed sentence as original -> rewritten."""
    lines = [f"# Rewrite report (profile: {result.profile_name}, engine: {result.engine})", ""]
    for k, v in result.stats.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    for para in result.paragraphs:
        for s in para.sentences:
            if not s.changed:
                continue
            lines.append(f"**Original:** {s.original.strip()}")
            lines.append("")
            lines.append(f"**Rewritten:** {s.text.strip()}")
            for c in s.changes:
                lines.append(f"  - `{c.original}` → `{c.replacement}` ({c.kind}: {c.reason})")
            lines.append("")
    return "\n".join(lines)


def write_outputs(result: RewriteResult, profile: ReaderProfile, out_dir: Path, stem: str,
                  formats: tuple[str, ...] = ("html", "txt", "md")) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    if "html" in formats:
        p = out_dir / f"{stem}.html"
        p.write_text(to_html(result, profile, title=stem.replace("_", " ")), encoding="utf-8")
        written.append(p)
    if "txt" in formats:
        p = out_dir / f"{stem}.txt"
        p.write_text(result.text + "\n", encoding="utf-8")
        written.append(p)
    if "md" in formats:
        p = out_dir / f"{stem}.changes.md"
        p.write_text(to_markdown_diff(result) + "\n", encoding="utf-8")
        written.append(p)
    if "json" in formats:
        p = out_dir / f"{stem}.json"
        p.write_text(json.dumps({
            "profile": profile.name, "engine": result.engine, "stats": result.stats,
            "paragraphs": [
                {"heading": para.heading, "sentences": [
                    {"original": s.original, "rewritten": s.text,
                     "changes": [c.__dict__ for c in s.changes]} for s in para.sentences]}
                for para in result.paragraphs],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(p)
    return written

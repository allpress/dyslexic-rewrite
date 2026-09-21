"""Read/write .txt / .md / .html / .epub files.

`read_text` (above) flattens a whole document into one blob, for the CLI's single-shot
`rewrite`/`analyze` commands. `read_chapters` and `write_epub` (below) work at the
chapter level, for "Your library": upload a book, rewrite each chapter separately (so
progress, caching and per-chapter fidelity checks all work the way they do for any other
paragraph), and get a real EPUB back.
"""

from __future__ import annotations

import html
import re
import uuid
from pathlib import Path
from typing import Any


def read_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return _read_epub(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".json":
        return _json_to_text(raw)
    if suffix in (".html", ".htm"):
        return _html_to_text(raw)
    if suffix == ".md":
        raw = re.sub(r"^#{1,6}\s*", "", raw, flags=re.M)      # headings -> plain lines
        raw = re.sub(r"[*_`]{1,3}", "", raw)                    # emphasis markers
    return _normalise(raw)


_TEXT_KEYS = ("body", "text", "message", "content", "post")


def _json_to_text(raw: str) -> str:
    """A JSON writing-sample export: a list of posts, or {"items": [...]}, each with a text field.

    This is the shape `scripts/export_facebook_posts.md` describes, and also works for plain
    lists of strings. Every post becomes one paragraph.
    """
    import json

    data = json.loads(raw)
    if isinstance(data, dict):
        for k in ("items", "posts", "messages", "entries", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    paras = []
    for item in data:
        if isinstance(item, str):
            txt = item
        elif isinstance(item, dict):
            txt = next((item[k] for k in _TEXT_KEYS if isinstance(item.get(k), str)), "")
        else:
            continue
        lines = [ln.strip() for ln in txt.strip().split("\n")]
        # drop trailing audience / timestamp lines that social-media exports leave behind
        while lines and (_AUDIENCE_RE.match(lines[-1]) or _TIME_RE.match(lines[-1])):
            lines.pop()
        txt = "\n".join(lines).strip()
        if txt:
            paras.append(txt)
    return _normalise("\n\n".join(paras))


_AUDIENCE_RE = re.compile(r"^(Public|Friends|Friends of friends|Only me|Custom|Shared with.*|Friends except.*|"
                          r"Specific friends|Close Friends)$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}[\s  ]?(AM|PM)$")


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # join hard-wrapped lines inside a paragraph, keep blank lines as paragraph breaks
    paras = re.split(r"\n\s*\n", text)
    out = []
    for p in paras:
        lines = [ln.strip() for ln in p.split("\n") if ln.strip()]
        if not lines:
            continue
        out.append(" ".join(lines))
    return "\n\n".join(out)


def _html_to_text(raw: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover
        raise SystemExit("HTML/EPUB input needs beautifulsoup4: pip install 'dyslexic-rewrite[epub]'") from e
    soup = BeautifulSoup(raw, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    blocks = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        txt = el.get_text(" ", strip=True)
        if txt:
            blocks.append(txt)
    if not blocks:
        blocks = [soup.get_text("\n", strip=True)]
    return _normalise("\n\n".join(blocks))


def _read_epub(path: Path) -> str:
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError as e:  # pragma: no cover
        raise SystemExit("EPUB input needs ebooklib: pip install 'dyslexic-rewrite[epub]'") from e
    book = epub.read_epub(str(path))
    chunks = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        chunks.append(_html_to_text(item.get_content().decode("utf-8", errors="replace")))
    return "\n\n".join(c for c in chunks if c.strip())


# =========================================================================================
# Chapters: read_chapters() / write_epub() -- "Your library" (upload a book, get it back
# rewritten, read it on the site or on a Kindle).
# =========================================================================================

CHUNK_WORDS = 8_000

_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_CHAPTER_LINE_RE = re.compile(r"^\s*chapter\s+\S+.*$", re.I | re.M)


def _clean_md_text(raw: str) -> str:
    raw = re.sub(r"^#{1,6}\s*", "", raw, flags=re.M)
    raw = re.sub(r"[*_`]{1,3}", "", raw)
    return _normalise(raw)


def _chunk_chapter(text: str, chunk_words: int = CHUNK_WORDS) -> list[dict[str, str]]:
    """Split one big chapter into ~chunk_words-word pieces on paragraph boundaries."""
    if len(text.split()) <= chunk_words:
        return [{"title": "Chapter 1", "text": text}] if text.strip() else []
    paras = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_words = 0
    for p in paras:
        pw = len(p.split())
        if cur and cur_words + pw > chunk_words:
            chunks.append("\n\n".join(cur))
            cur, cur_words = [], 0
        cur.append(p)
        cur_words += pw
    if cur:
        chunks.append("\n\n".join(cur))
    return [{"title": f"Chapter {i + 1}", "text": c} for i, c in enumerate(chunks)]


def _split_text_chapters(raw: str, is_md: bool) -> list[dict[str, str]]:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    def _sections(matches: list[re.Match], titler) -> list[dict[str, str]]:
        out = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            body = raw[start:end]
            text = _clean_md_text(body) if is_md else _normalise(body)
            if text.strip():
                out.append({"title": titler(m), "text": text})
        return out

    if is_md:
        md = list(_MD_HEADING_RE.finditer(raw))
        if md:
            sections = _sections(md, lambda m: m.group(1).strip())
            if sections:
                return sections

    ch = list(_CHAPTER_LINE_RE.finditer(raw))
    if ch:
        sections = _sections(ch, lambda m: m.group(0).strip())
        if sections:
            return sections

    whole = _clean_md_text(raw) if is_md else _normalise(raw)
    return _chunk_chapter(whole)


def _first_heading(raw_html: str) -> str | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        return None
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in ("h1", "h2", "h3"):
        el = soup.find(tag)
        if el:
            txt = el.get_text(" ", strip=True)
            if txt:
                return txt
    return None


def _read_epub_chapters(path: Path) -> list[dict[str, str]]:
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError as e:  # pragma: no cover
        raise SystemExit("EPUB input needs ebooklib: pip install 'dyslexic-rewrite[epub]'") from e
    book = epub.read_epub(str(path))
    chapters: list[dict[str, str]] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        raw_html = item.get_content().decode("utf-8", errors="replace")
        text = _html_to_text(raw_html)
        if not text.strip():
            continue
        title = _first_heading(raw_html) or f"Chapter {len(chapters) + 1}"
        chapters.append({"title": title, "text": text})
    if not chapters:
        chapters = _chunk_chapter(_read_epub(path))
    return chapters


def _read_pdf_chapters(path: Path) -> list[dict[str, str]]:
    """`.pdf`: extract each page's text with `pypdf` and split it the same way `.txt` is split
    (Markdown-style headings never appear in a PDF's extracted text, so this only ever tries the
    "Chapter N" line pattern, then falls back to ~8,000-word chunks). A PDF with no extractable
    text at all -- a straight image scan -- raises a `ValueError` with a clear message, since
    OCR is out of scope here."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise SystemExit("PDF input needs pypdf: pip install 'dyslexic-rewrite[docs]'") from e
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # a single malformed page must not sink the whole import
            pages.append("")
    raw = "\n\n".join(pages)
    if not raw.strip():
        raise ValueError("This PDF is a scan — OCR isn't supported yet.")
    return _split_text_chapters(raw, is_md=False)


def _read_docx_chapters(path: Path) -> list[dict[str, str]]:
    """`.docx`: a paragraph styled "Heading *" starts a new chapter, titled from that heading's
    text; everything before the first heading (if any) becomes "Chapter 1". A document with no
    headings at all is treated like a headingless `.txt` file -- one chapter, chunked into
    ~8,000-word pieces if it's long."""
    try:
        import docx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("DOCX input needs python-docx: pip install 'dyslexic-rewrite[docs]'") from e
    document = docx.Document(str(path))
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    any_heading = False
    for para in document.paragraphs:
        style_name = (para.style.name if para.style else "") or ""
        text = para.text.strip()
        if not text:
            continue
        if style_name.lower().startswith("heading"):
            any_heading = True
            sections.append((text, []))
        else:
            sections[-1][1].append(text)

    if not any_heading:
        whole = _normalise("\n\n".join(p for _, paras in sections for p in paras))
        return _chunk_chapter(whole)

    chapters = []
    for title, paras in sections:
        text = _normalise("\n\n".join(paras))
        if text.strip():
            chapters.append({"title": title or f"Chapter {len(chapters) + 1}", "text": text})
    return chapters


def read_chapters(path: str | Path) -> list[dict[str, str]]:
    """Split a book into `[{"title": str, "text": str}, ...]`, one entry per chapter.

    `.epub`: walks the spine in order, one chapter per spine document, titled from its
    first `<h1>`/`<h2>`/`<h3>` (falling back to "Chapter N").

    `.pdf`: extracts text per page with `pypdf`, then splits like `.txt` below. Raises
    `ValueError` if the PDF has no extractable text (a scan -- OCR is out of scope).

    `.docx`: paragraphs styled "Heading *" split it into chapters, titled from the heading text.

    `.txt`/`.md`: splits on Markdown headings (`.md` only) or lines like "Chapter 3" /
    "CHAPTER III"; if neither pattern is found, the whole file is one chapter, further cut
    into ~8,000-word chunks (on paragraph boundaries) so a single huge chapter still
    rewrites and renders in reasonable pieces.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return _read_epub_chapters(path)
    if suffix == ".pdf":
        return _read_pdf_chapters(path)
    if suffix == ".docx":
        return _read_docx_chapters(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    return _split_text_chapters(raw, is_md=(suffix == ".md"))


_EPUB_CSS = """
body {{ font-family: "Atkinson Hyperlegible", "OpenDyslexic", serif; font-size: {font_size_px}px;
  line-height: {line_height}; letter-spacing: {letter_spacing_em}em; word-spacing: {word_spacing_em}em;
  margin: 0 auto; max-width: {max_line_chars}ch; padding: 1em; background: {background}; color: {text}; }}
p {{ margin: 0 0 {paragraph_gap_em}em; }}
h1, h2 {{ line-height: 1.3; margin: 1em 0 0.6em; }}
ruby {{ ruby-position: over; }}
rt {{ font-size: 0.6em; }}
span.orig {{ border-bottom: 1px dotted currentColor; }}
"""

_FRONT_MATTER_TEMPLATE = (
    "<h1>{title}</h1>"
    "<p>Rewritten for easier reading by Unwind Words &mdash; every change is reversible; "
    "the original text is unchanged.</p>"
)


def _paragraphs_of(result_or_paragraphs: Any) -> list:
    """A RewriteResult's `.paragraphs`, or a bare list of Paragraph objects."""
    return getattr(result_or_paragraphs, "paragraphs", result_or_paragraphs)


def _chapter_body_html(paragraphs: list, profile) -> str:
    """Body-inner XHTML for one chapter (ebooklib wraps this in <html><head>...<body>)."""
    from .render import _phonetic_for_trigger

    show_phonetic = getattr(profile, "phonetic_map", "off") != "off"
    parts = []
    for para in paragraphs:
        tag = "h2" if getattr(para, "heading", False) else "p"
        buf = []
        for s in para.sentences:
            for kind, val in s.segments:
                if kind == "text":
                    if val:
                        buf.append(html.escape(val))
                elif kind == "change":
                    buf.append(
                        f'<span class="orig" title="{html.escape(val.original, quote=True)}">'
                        f"{html.escape(val.replacement)}</span>"
                    )
                elif kind == "note":
                    word_html = html.escape(val.text)
                    if show_phonetic:
                        phon = _phonetic_for_trigger(val, profile)
                        if phon:
                            word_html = f"<ruby>{word_html}<rt>{html.escape(phon[0])}</rt></ruby>"
                    buf.append(word_html)
                # "break" segments are sentence boundaries the rewriter inserted; nothing to render.
            buf.append(" ")
        text = "".join(buf).strip()
        if text:
            parts.append(f"<{tag}>{text}</{tag}>")
    return "\n".join(parts)


def write_epub(
    result_or_paragraphs: Any,
    path: str | Path,
    title: str,
    author: str | None = None,
    chapters: list[Any] | None = None,
    profile: Any = None,
) -> Path:
    """Write a valid EPUB 3 file with `ebooklib`.

    One-chapter book: pass a `RewriteResult` (or a bare list of `Paragraph`) as
    `result_or_paragraphs`. Multi-chapter book: pass `chapters`, a list of either
    `(chapter_title, RewriteResult)` tuples or `{"title": ..., "result": ...}` dicts;
    `result_or_paragraphs` is then ignored (pass `None`). A chapter dict may instead carry
    `{"title": ..., "html": "<p>...</p>"}` -- ready-made body-inner XHTML, used by the server
    (`server/library.py`), which already has each chapter's rewrite as JSON segments rather
    than `Paragraph` objects.

    `profile` (a `ReaderProfile`) drives the reader-friendly CSS (font size, line height,
    letter/word spacing, max line width) and whether flagged-but-kept words get an inline
    `<ruby>` phonetic map (Kindle renders `<ruby>`/`<rt>`) -- included whenever
    `profile.phonetic_map != "off"`. Changed words keep their original inline, cheaply, as
    a `title` attribute (`<span class="orig" title="...">`). Defaults to `ReaderProfile()`
    when omitted.

    A short front-matter page is written before the first chapter, saying the rewrite is
    reversible and the original text is untouched.
    """
    try:
        from ebooklib import epub
    except ImportError as e:  # pragma: no cover
        raise SystemExit("EPUB output needs ebooklib: pip install 'dyslexic-rewrite[epub]'") from e
    from .profile import ReaderProfile

    profile = profile or ReaderProfile()

    if chapters is None:
        chapter_list = [{"title": title, "paragraphs": _paragraphs_of(result_or_paragraphs)}]
    else:
        chapter_list = []
        for ch in chapters:
            if isinstance(ch, dict):
                ch_title = ch.get("title") or f"Chapter {len(chapter_list) + 1}"
                if "html" in ch:
                    chapter_list.append({"title": ch_title, "html": ch["html"]})
                    continue
                ch_paras = _paragraphs_of(ch.get("result", ch.get("paragraphs")))
            else:
                ch_title, ch_result = ch
                ch_paras = _paragraphs_of(ch_result)
            chapter_list.append({"title": ch_title, "paragraphs": ch_paras})

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(getattr(profile, "language", "en") or "en")
    if author:
        book.add_author(author)

    css = epub.EpubItem(
        uid="style_main", file_name="style/main.css", media_type="text/css",
        content=_EPUB_CSS.format(**dict(profile.layout)).encode("utf-8"),
    )
    book.add_item(css)

    front = epub.EpubHtml(title="About this edition", file_name="front.xhtml", lang=profile.language)
    front.content = _FRONT_MATTER_TEMPLATE.format(title=html.escape(title))
    front.add_item(css)
    book.add_item(front)

    spine_items: list = [front]
    toc: list = [front]
    for i, ch in enumerate(chapter_list):
        page = epub.EpubHtml(title=ch["title"], file_name=f"chap_{i + 1:03d}.xhtml", lang=profile.language)
        page.content = ch["html"] if "html" in ch else _chapter_body_html(ch["paragraphs"], profile)
        page.add_item(css)
        book.add_item(page)
        spine_items.append(page)
        toc.append(page)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [nav, *spine_items]

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_path), book)
    return out_path

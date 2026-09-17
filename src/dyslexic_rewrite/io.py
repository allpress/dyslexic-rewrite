"""Read text from .txt / .md / .html / .epub files."""

from __future__ import annotations

import re
from pathlib import Path


def read_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return _read_epub(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        return _html_to_text(raw)
    if suffix == ".md":
        raw = re.sub(r"^#{1,6}\s*", "", raw, flags=re.M)      # headings -> plain lines
        raw = re.sub(r"[*_`]{1,3}", "", raw)                    # emphasis markers
    return _normalise(raw)


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

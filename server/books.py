"""Server-rendered book pages (v0.5 marketing surface): plain HTML, not the SPA, so crawlers get
real text on first load. Reuses the same rewrite cache the JSON API uses
(`GET /api/samples/{slug}`), so the first crawler or visitor to hit a page pays nothing -- the
sample books are pre-warmed at startup (server/app.py's lifespan hook).

Registered in server/app.py *before* the SPA's catch-all `/{path:path}` route, so these paths are
never shadowed by it.
"""

from __future__ import annotations

import html
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from dyslexic_rewrite import load_profile

from . import cache, marketing, samples, service

router = APIRouter()

SITE_URL = os.environ.get("SITE_URL", "https://unwindwords.com").rstrip("/")
APP_NAME = os.environ.get("APP_NAME", "Unwind Words")
EXCERPT_WORD_TARGET = 600

_PAGE_CSS = """
body{background:#fbf8f1;color:#1f2328;font-family:'Atkinson Hyperlegible',Verdana,Arial,sans-serif;
  font-size:20px;line-height:1.9;letter-spacing:0.02em;margin:0}
main{max-width:640px;margin:0 auto;padding:28px 20px 96px}
h1{font-size:1.7rem;line-height:1.3;margin:0 0 0.4em}
h2{font-size:1.2rem;margin:1.4em 0 0.5em}
p{margin:0 0 1.1em}
.muted{color:#55606b;font-size:0.9rem}
a{color:#1c5d4a}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:52px;padding:12px 26px;
  border:2px solid #1c5d4a;border-radius:10px;background:#1c5d4a;color:#fff;font-weight:700;
  text-decoration:none;margin:1.2em 0}
ruby rt{font-size:0.6em;color:#55606b}
.excerpt{border-top:2px solid #ded5c2;border-bottom:2px solid #ded5c2;padding:8px 0;margin:1.4em 0}
nav a{color:#1c5d4a;text-decoration:none;font-weight:700}
@media (prefers-color-scheme: dark){
  body{background:#14171a;color:#e8e4dc}
  .muted{color:#a8b0b8}
  a,nav a{color:#6fd3b0}
  .btn{background:#6fd3b0;border-color:#6fd3b0;color:#10221c}
  .excerpt{border-color:#38404a}
  ruby rt{color:#a8b0b8}
}
"""


def _render_ruby(text: str, entries: list[dict[str, Any]]) -> str:
    """Escape `text` and wrap the word span of each entry (offsets into `text`) in <ruby>."""
    ordered = sorted((e for e in entries if 0 <= e["start"] < e["end"] <= len(text)), key=lambda e: e["start"])
    out: list[str] = []
    pos = 0
    for e in ordered:
        if e["start"] < pos:
            continue  # defensive: skip anything that overlaps the previous entry
        out.append(html.escape(text[pos:e["start"]]))
        word = html.escape(text[e["start"]:e["end"]])
        respell = html.escape(str(e.get("respell") or ""))
        out.append(f"<ruby>{word}<rt>{respell}</rt></ruby>" if respell else word)
        pos = e["end"]
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _excerpt(text: str, phonetic_map: list[dict[str, Any]], target_words: int = EXCERPT_WORD_TARGET) -> str:
    """First ~`target_words` words of `text`, whole paragraphs only, as ruby-annotated HTML."""
    paragraphs = text.split("\n\n")
    included: list[str] = []
    words = 0
    for p in paragraphs:
        included.append(p)
        words += len(p.split())
        if words >= target_words:
            break
    excerpt_text = "\n\n".join(included)
    cutoff = len(excerpt_text)
    entries = [e for e in phonetic_map if e["end"] <= cutoff]
    rendered = _render_ruby(excerpt_text, entries)
    paras = [p.replace("\n", " ").strip() for p in rendered.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paras)


def _base_page(title: str, description: str, canonical: str, body: str, jsonld: dict | None = None) -> str:
    jsonld_tag = (
        f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld is not None else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{html.escape(canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{html.escape(canonical)}">
<meta property="og:site_name" content="{html.escape(APP_NAME)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<style>{_PAGE_CSS}</style>
{jsonld_tag}
</head>
<body>
<main>
<nav><a href="/">&larr; {html.escape(APP_NAME)}</a></nav>
{body}
</main>
</body>
</html>"""


def _track(request: Request, path: str) -> None:
    try:
        marketing.record_page_view(path, marketing.referrer_host(request))
    except Exception:  # tracking must never break a page render
        pass


@router.get("/books", response_class=HTMLResponse)
def books_index(request: Request):
    _track(request, "/books")
    items = samples.list_samples()
    cards = "".join(
        f'<li><h2><a href="/books/{html.escape(s["slug"])}">{html.escape(s["title"], quote=False)}</a></h2>'
        f'<p class="muted">{html.escape(s["author"], quote=False)}, {s["year"]} &mdash; '
        f'{html.escape(s["blurb"], quote=False)}</p></li>'
        for s in items
    )
    body = (
        "<h1>Free, dyslexia-friendly classics</h1>"
        "<p>Public-domain books, rewritten so trigger words are defused and long sentences are "
        "straightened. Read a chapter free, no sign-in needed.</p>"
        f'<ul style="list-style:none;padding:0">{cards}</ul>'
    )
    canonical = f"{SITE_URL}/books"
    return HTMLResponse(_base_page(
        f"Free dyslexia-friendly classics | {APP_NAME}",
        "Public-domain books rewritten to defuse trigger words and straighten long sentences. "
        "Read a chapter free.",
        canonical, body,
    ))


@router.get("/books/{slug}", response_class=HTMLResponse)
def book_page(slug: str, request: Request):
    s = samples.get_sample(slug)
    if not s:
        raise HTTPException(404, "No such book.")
    _track(request, f"/books/{slug}")

    profile = load_profile("default")
    segs, _stats, phonetic_map, _cached = cache.cached_rewrite(s["text"], profile, "always", sample_slug=slug)
    served = service.served_text(segs)
    excerpt_html = _excerpt(served, phonetic_map)

    title = f"Read {s['title']}, dyslexia-friendly | {APP_NAME}"
    description = (
        f"{s['title']} by {s['author']} ({s['year']}), rewritten so trigger words are defused and "
        "sentences are straightened. Free to read, open source, no sign-in needed."
    )
    canonical = f"{SITE_URL}/books/{slug}"
    read_url = f"/read?sample={slug}"

    body = (
        f"<h1>{html.escape(s['title'], quote=False)}</h1>"
        f'<p class="muted">{html.escape(s["author"], quote=False)}, {s["year"]} &middot; '
        f'{html.escape(s["chapter"], quote=False)} &mdash; rewritten by {APP_NAME}</p>'
        f'<div class="excerpt">{excerpt_html}</div>'
        f'<a class="btn" href="{html.escape(read_url)}">Continue reading &rarr;</a>'
        f'<p class="muted">Public domain, from <a href="{html.escape(s["source"])}" rel="noopener">'
        "Project Gutenberg</a>. Rewritten text is free to read and reuse under the same terms as the "
        "original.</p>"
    )

    jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Book",
                "name": s["title"],
                "author": {"@type": "Person", "name": s["author"]},
                "datePublished": str(s["year"]),
                "url": canonical,
                "sameAs": s["source"],
            },
            {
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical,
                "isPartOf": {"@type": "WebSite", "name": APP_NAME, "url": SITE_URL},
            },
        ],
    }
    return HTMLResponse(_base_page(title, description, canonical, body, jsonld))


@router.get("/sitemap.xml")
def sitemap(request: Request):
    paths = ["/", "/pricing", "/read", "/assess", "/books"] + [
        f"/books/{s['slug']}" for s in samples.list_samples()
    ]
    urls = "".join(f"<url><loc>{html.escape(SITE_URL + p)}</loc></url>" for p in paths)
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(content=body, media_type="application/xml")


@router.get("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")

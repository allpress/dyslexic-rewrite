/**
 * Extract the article text from the current page for POST /api/rewrite.
 *
 * Primary path: Mozilla's own Readability library (vendored via npm, bundled into content.js —
 * the same de-clutter engine behind Firefox Reader View), run against a *clone* of the
 * document, since Readability mutates the DOM it's given.
 *
 * Fallback chain, in order, for pages Readability can't parse (paywalled markup, an SPA that
 * renders nothing server-side-shaped, a non-article page): the reader's current text selection,
 * then the whole page's visible text (`document.body.innerText`). Both are trimmed to `maxChars`
 * so a giant page never blows past the API's paste quota before the server even gets to enforce
 * its own limit.
 */

import { Readability } from '@mozilla/readability';

export interface ExtractedArticle {
  title: string;
  text: string;
  /** Which path produced this text, surfaced in the overlay so a fallback is never silent. */
  source: 'readability' | 'selection' | 'body-text';
}

const MIN_READABILITY_CHARS = 200;

/** Pure enough to unit-test: takes a Document (real or JSDOM-parsed) instead of always reading
 * `window.document`, and a `selectionText` instead of always reading `window.getSelection()`. */
export function extractArticle(doc: Document, selectionText: string, maxChars: number): ExtractedArticle {
  const readabilityResult = tryReadability(doc);
  if (readabilityResult && readabilityResult.text.trim().length >= MIN_READABILITY_CHARS) {
    return {
      title: readabilityResult.title,
      text: truncate(readabilityResult.text, maxChars),
      source: 'readability',
    };
  }

  const selection = selectionText.trim();
  if (selection.length > 0) {
    return { title: doc.title || 'Selection', text: truncate(selection, maxChars), source: 'selection' };
  }

  const bodyText = (doc.body?.innerText ?? doc.body?.textContent ?? '').trim();
  return { title: doc.title || 'This page', text: truncate(bodyText, maxChars), source: 'body-text' };
}

function tryReadability(doc: Document): { title: string; text: string } | null {
  try {
    // Readability mutates the document it's given, so hand it a clone rather than the live page.
    const clone = doc.cloneNode(true) as Document;
    const article = new Readability(clone).parse();
    if (!article || !article.textContent) return null;
    return { title: article.title || doc.title || '', text: article.textContent };
  } catch {
    return null;
  }
}

function truncate(text: string, maxChars: number): string {
  const collapsed = text.replace(/\n{3,}/g, '\n\n').trim();
  if (collapsed.length <= maxChars) return collapsed;
  return collapsed.slice(0, maxChars);
}

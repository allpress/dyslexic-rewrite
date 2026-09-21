import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { extractArticle } from '../src/content/extract';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixtureHtml = readFileSync(join(__dirname, 'fixtures/article.html'), 'utf-8');

function parse(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

describe('extractArticle', () => {
  it('extracts the article body via Readability, dropping nav/sidebar/footer clutter', () => {
    const doc = parse(fixtureHtml);
    const result = extractArticle(doc, '', 100_000);

    expect(result.source).toBe('readability');
    expect(result.title).toContain("Grandpa's Clock");
    expect(result.text).toContain('Every evening, Grandpa would wind the old clock');
    expect(result.text).toContain('the new owners found the clock still');

    // The nav, sidebar ad/related links and footer boilerplate should not survive.
    expect(result.text).not.toContain('Subscribe now for $5/month');
    expect(result.text).not.toContain('Buy our newsletter subscription');
    expect(result.text).not.toContain('All rights reserved');
  });

  it('truncates to maxChars', () => {
    const doc = parse(fixtureHtml);
    const result = extractArticle(doc, '', 50);
    expect(result.text.length).toBeLessThanOrEqual(50);
  });

  it('falls back to the current selection when Readability finds too little content', () => {
    const doc = parse('<html><head><title>Empty</title></head><body><div id="app"></div></body></html>');
    const selection = 'The paragraph a reader had selected before opening the extension.';
    const result = extractArticle(doc, selection, 100_000);

    expect(result.source).toBe('selection');
    expect(result.text).toBe(selection);
  });

  it('falls back to the page body text when there is no article and no selection', () => {
    const doc = parse('<html><head><title>Bare page</title></head><body><p>Just some plain body text here.</p></body></html>');
    const result = extractArticle(doc, '', 100_000);

    expect(result.source).toBe('body-text');
    expect(result.text).toContain('Just some plain body text here.');
  });

  it('never throws on a pathological document', () => {
    const doc = parse('<html><body></body></html>');
    expect(() => extractArticle(doc, '', 1000)).not.toThrow();
  });
});

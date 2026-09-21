/**
 * Loads the optional reading-settings fonts on demand — never up front, and never claimed to
 * help (see docs/RESEARCH.md §2; the panel's own copy says as much). Atkinson Hyperlegible and
 * Lexend come from Google Fonts via a `<link>`; OpenDyslexic ships its OFL font files in the
 * `@fontsource/opendyslexic` npm package (see web/public/fonts/LICENSES.md) and is pulled in via
 * a dynamic import so its ~200KB of woff2 never lands in the main bundle.
 */
import type { ReaderFontFamily } from '../api';

const GOOGLE_FONT_HREFS: Partial<Record<ReaderFontFamily, string>> = {
  atkinson:
    'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700&display=swap',
  lexend: 'https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;700&display=swap',
};

/** CSS `font-family` stacks for each option, always ending in a plain generic fallback so a
 * blocked font load (or the family simply not having loaded yet) never leaves the reader with
 * no font at all. */
export const FONT_STACKS: Record<ReaderFontFamily, string> = {
  system: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  atkinson: "'Atkinson Hyperlegible', -apple-system, BlinkMacSystemFont, sans-serif",
  lexend: "'Lexend', -apple-system, BlinkMacSystemFont, sans-serif",
  opendyslexic: "'OpenDyslexic', -apple-system, BlinkMacSystemFont, sans-serif",
  mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
};

export const FONT_LABELS: Record<ReaderFontFamily, string> = {
  system: 'System sans (default)',
  atkinson: 'Atkinson Hyperlegible',
  lexend: 'Lexend',
  opendyslexic: 'OpenDyslexic',
  mono: 'Monospace',
};

const loaded = new Set<ReaderFontFamily>();

/**
 * Makes sure `family`'s font files are on the page. Safe to call every time the reader picks a
 * font — it only ever injects once per family per session — and never throws: a blocked network
 * or strict CSP just means that family falls back to its stack's next entry, not a broken page.
 */
export function ensureFontLoaded(family: ReaderFontFamily): void {
  if (loaded.has(family)) return;
  try {
    const href = GOOGLE_FONT_HREFS[family];
    if (href) {
      loaded.add(family);
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      link.setAttribute('data-reader-font', family);
      document.head.appendChild(link);
    } else if (family === 'opendyslexic') {
      loaded.add(family);
      void import('@fontsource/opendyslexic');
    }
  } catch {
    // Comfort setting, not a requirement — the reader still gets the fallback stack.
  }
}

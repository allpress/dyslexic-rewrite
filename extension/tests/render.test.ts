import { describe, expect, it } from 'vitest';
import { cleanWord, paragraphTexts, renderSegments, servedTextSpans, toBlocks } from '../src/content/render';
import type { PhoneticMapEntry, Segment } from '../src/lib/types';

describe('cleanWord', () => {
  it('strips surrounding punctuation and lowercases', () => {
    expect(cleanWord('Clock,')).toBe('clock');
    expect(cleanWord('"Wind!"')).toBe('wind');
    expect(cleanWord('  ')).toBe('');
  });
});

describe('toBlocks / paragraphTexts', () => {
  const segments: Segment[] = [
    { t: 'heading', s: 'Chapter One' },
    { t: 'text', s: 'The ' },
    { t: 'change', s: 'clock', orig: 'timepiece', why: 'more common word', alts: [] },
    { t: 'text', s: ' ticked.' },
    { t: 'para' },
    { t: 'text', s: 'Second paragraph.' },
  ];

  it('groups segments into heading/paragraph blocks on para/heading boundaries', () => {
    const blocks = toBlocks(segments);
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toEqual({ kind: 'heading', text: 'Chapter One' });
    expect(blocks[1].kind).toBe('para');
    expect(blocks[2].kind).toBe('para');
  });

  it('produces one plain-text string per block, in order, for the read-aloud queue', () => {
    const texts = paragraphTexts(segments);
    expect(texts).toEqual(['Chapter One', 'The clock ticked.', 'Second paragraph.']);
  });
});

describe('servedTextSpans', () => {
  it('matches server.service.served_text: para breaks count as two newlines', () => {
    const segments: Segment[] = [
      { t: 'text', s: 'ab' },
      { t: 'para' },
      { t: 'text', s: 'cd' },
    ];
    const spans = servedTextSpans(segments);
    expect(spans).toEqual([
      { segIndex: 0, start: 0, end: 2 },
      { segIndex: 2, start: 4, end: 6 },
    ]);
  });

  it('skips para segments and gives headings a span too', () => {
    const segments: Segment[] = [{ t: 'heading', s: 'Hi' }, { t: 'text', s: 'x' }];
    expect(servedTextSpans(segments)).toEqual([
      { segIndex: 0, start: 0, end: 2 },
      { segIndex: 1, start: 2, end: 3 },
    ]);
  });
});

describe('renderSegments', () => {
  function container(): HTMLDivElement {
    const div = document.createElement('div');
    document.body.appendChild(div);
    return div;
  }

  it('renders a heading as an h2 and text as a paragraph of word buttons', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'heading', s: 'Title' }, { t: 'text', s: 'a b' }];
    renderSegments(el, segments, { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: false });

    expect(el.querySelector('h2.uw-heading')?.textContent).toBe('Title');
    const words = el.querySelectorAll('button.uw-word');
    expect(words).toHaveLength(2);
    expect(words[0].textContent).toBe('a');
    expect(words[1].textContent).toBe('b');
  });

  it('marks a change segment with the change class and a title tooltip with the original', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'change', s: 'clock', orig: 'timepiece', why: 'plainer word', alts: [] }];
    renderSegments(el, segments, { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: false });

    const btn = el.querySelector('button.uw-word--change') as HTMLButtonElement;
    expect(btn).not.toBeNull();
    expect(btn.textContent).toBe('clock');
    expect(btn.title).toContain('timepiece');
    expect(btn.title).toContain('plainer word');
  });

  it('marks a note segment with the note class', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'note', s: 'wind', why: 'heteronym', hint: "rhymes with 'find'" }];
    renderSegments(el, segments, { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: false });

    const btn = el.querySelector('button.uw-word--note') as HTMLButtonElement;
    expect(btn).not.toBeNull();
    expect(btn.title).toContain("rhymes with 'find'");
  });

  it('appends the bracketed original after a change when showOriginalInline is on', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'change', s: 'clock', orig: 'timepiece', why: '', alts: [] }];
    renderSegments(el, segments, { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: true });

    expect(el.querySelector('.uw-inline-orig')?.textContent).toBe(' [was: timepiece]');
  });

  it('renders a <ruby>/<rt> for a word covered by a phonetic-map entry, in on_demand mode', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'text', s: 'intention matters' }];
    const entry: PhoneticMapEntry = {
      start: 0,
      end: 9,
      word: 'intention',
      respell: 'in-TEN-shun',
      hint: null,
      kind: 'long',
      always: false,
    };
    renderSegments(el, segments, { phoneticMap: [entry], phoneticMapMode: 'on_demand', showOriginalInline: false });

    const ruby = el.querySelector('ruby');
    expect(ruby).not.toBeNull();
    const rt = ruby?.querySelector('rt');
    expect(rt?.textContent).toBe('in-TEN-shun');
    expect(rt?.classList.contains('uw-rt--always')).toBe(false);

    // "matters" has no entry, so it renders as plain text with no ruby.
    const words = Array.from(el.querySelectorAll('button.uw-word'));
    const mattersBtn = words.find((w) => w.textContent === 'matters');
    expect(mattersBtn?.querySelector('ruby')).toBeNull();
  });

  it('marks every covered word "always visible" in always mode, regardless of the entry.always flag', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'text', s: 'intention' }];
    const entry: PhoneticMapEntry = {
      start: 0,
      end: 9,
      word: 'intention',
      respell: 'in-TEN-shun',
      hint: null,
      kind: 'long',
      always: false, // server said "on demand", but the extension's local mode overrides display
    };
    renderSegments(el, segments, { phoneticMap: [entry], phoneticMapMode: 'always', showOriginalInline: false });

    const rt = el.querySelector('rt');
    expect(rt?.classList.contains('uw-rt--always')).toBe(true);
  });

  it('renders no ruby elements at all when phoneticMapMode is off, even with entries present', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'text', s: 'intention' }];
    const entry: PhoneticMapEntry = {
      start: 0,
      end: 9,
      word: 'intention',
      respell: 'in-TEN-shun',
      hint: null,
      kind: 'long',
      always: true,
    };
    renderSegments(el, segments, { phoneticMap: [entry], phoneticMapMode: 'off', showOriginalInline: false });

    expect(el.querySelector('ruby')).toBeNull();
  });

  it('calls onToggleWord with a stable id and the cleaned word on click', () => {
    const el = container();
    const segments: Segment[] = [{ t: 'text', s: 'Clock,' }];
    const clicks: [string, string][] = [];
    renderSegments(el, segments, {
      phoneticMap: [],
      phoneticMapMode: 'off',
      showOriginalInline: false,
      onToggleWord: (id, word) => clicks.push([id, word]),
    });

    const btn = el.querySelector('button.uw-word') as HTMLButtonElement;
    btn.click();
    expect(clicks).toEqual([['0:0', 'clock']]);
  });

  it('clears previous content on re-render', () => {
    const el = container();
    renderSegments(el, [{ t: 'text', s: 'first' }], { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: false });
    renderSegments(el, [{ t: 'text', s: 'second' }], { phoneticMap: [], phoneticMapMode: 'off', showOriginalInline: false });

    expect(el.textContent?.trim()).toBe('second');
  });
});

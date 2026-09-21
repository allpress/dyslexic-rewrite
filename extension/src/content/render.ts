/**
 * Segment list → DOM, the extension's equivalent of web/src/components/Reader.tsx. Plain DOM
 * (no framework) so it can run inside a shadow root injected into an arbitrary page. The
 * offset math (`servedTextSpans`) is copied from Reader.tsx on purpose: it has to match
 * `server.service.served_text` exactly so a server-computed phonetic-map offset lands on the
 * right word here too.
 */

import type { PhoneticMapEntry, PhoneticMapMode, Segment } from '../lib/types';

/** Strip surrounding punctuation and case, same rule the web app uses. */
export function cleanWord(raw: string): string {
  return raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '').toLowerCase();
}

type Block = { kind: 'para'; parts: { seg: Segment; segIndex: number }[] } | { kind: 'heading'; text: string };

export function toBlocks(segments: Segment[]): Block[] {
  const blocks: Block[] = [];
  let current: { seg: Segment; segIndex: number }[] = [];
  const flush = () => {
    if (current.length) blocks.push({ kind: 'para', parts: current });
    current = [];
  };
  segments.forEach((seg, segIndex) => {
    if (seg.t === 'para') {
      flush();
    } else if (seg.t === 'heading') {
      flush();
      blocks.push({ kind: 'heading', text: seg.s });
    } else {
      current.push({ seg, segIndex });
    }
  });
  flush();
  return blocks;
}

/** One paragraph (or heading) of plain text per block, in reading order — the read-aloud queue. */
export function paragraphTexts(segments: Segment[]): string[] {
  return toBlocks(segments).map((block) =>
    block.kind === 'heading'
      ? block.text
      : block.parts.map((p) => (p.seg.t === 'text' || p.seg.t === 'change' || p.seg.t === 'note' ? p.seg.s : '')).join(''),
  );
}

interface SegmentSpan {
  segIndex: number;
  start: number;
  end: number;
}

/** Character range each segment occupies in the "served text" (every segment's `s` joined in
 * order, each `para` break counted as two newlines) — matches server.service.served_text. */
export function servedTextSpans(segments: Segment[]): SegmentSpan[] {
  const spans: SegmentSpan[] = [];
  let pos = 0;
  segments.forEach((seg, segIndex) => {
    if (seg.t === 'para') {
      pos += 2;
      return;
    }
    const text = seg.t === 'heading' || seg.t === 'text' || seg.t === 'change' || seg.t === 'note' ? seg.s : '';
    spans.push({ segIndex, start: pos, end: pos + text.length });
    pos += text.length;
  });
  return spans;
}

interface LocalEntry {
  start: number;
  end: number;
  entry: PhoneticMapEntry;
}

export interface RenderOptions {
  phoneticMap: PhoneticMapEntry[];
  phoneticMapMode: PhoneticMapMode;
  /** Reader-mode toggle: print the original word inline (in brackets) after each change,
   * instead of only on hover. */
  showOriginalInline: boolean;
  onToggleWord?: (id: string, word: string) => void;
}

/**
 * Render `segments` into `container` (cleared first). Returns the block/paragraph elements in
 * reading order so the caller (the read-aloud loop) can highlight the paragraph and word
 * currently being spoken without re-walking the DOM.
 */
export function renderSegments(container: HTMLElement, segments: Segment[], opts: RenderOptions): HTMLElement[] {
  container.innerHTML = '';
  const blocks = toBlocks(segments);
  const spans = servedTextSpans(segments);

  const entriesBySegment = new Map<number, LocalEntry[]>();
  if (opts.phoneticMapMode !== 'off' && opts.phoneticMap.length > 0) {
    for (const span of spans) {
      const local: LocalEntry[] = [];
      for (const e of opts.phoneticMap) {
        if (e.start >= span.start && e.end <= span.end && e.end > e.start) {
          local.push({ start: e.start - span.start, end: e.end - span.start, entry: e });
        }
      }
      if (local.length) entriesBySegment.set(span.segIndex, local);
    }
  }

  const paragraphEls: HTMLElement[] = [];

  blocks.forEach((block) => {
    if (block.kind === 'heading') {
      const h = document.createElement('h2');
      h.className = 'uw-heading';
      h.textContent = block.text;
      container.appendChild(h);
      paragraphEls.push(h);
      return;
    }
    const p = document.createElement('p');
    p.className = 'uw-para';
    block.parts.forEach(({ seg, segIndex }) => {
      renderSegmentInto(p, seg, segIndex, entriesBySegment.get(segIndex) ?? [], opts);
    });
    container.appendChild(p);
    paragraphEls.push(p);
  });

  return paragraphEls;
}

function renderSegmentInto(
  parent: HTMLElement,
  seg: Segment,
  segIndex: number,
  localEntries: LocalEntry[],
  opts: RenderOptions,
): void {
  if (seg.t === 'para' || seg.t === 'heading') return;

  const marked = seg.t === 'change' ? 'change' : seg.t === 'note' ? 'note' : null;
  const chunks = seg.s.split(/(\s+)/);
  let charPos = 0;

  chunks.forEach((chunk, i) => {
    if (chunk === '') return;
    if (/^\s+$/.test(chunk)) {
      parent.appendChild(document.createTextNode(chunk));
      charPos += chunk.length;
      return;
    }

    const chunkStart = charPos;
    const chunkEnd = charPos + chunk.length;
    charPos = chunkEnd;

    const phonLocal = localEntries.find((le) => le.start >= chunkStart && le.end <= chunkEnd);
    const showPhon = opts.phoneticMapMode !== 'off' && !!phonLocal;
    // Unlike the website (which only pins the server's `always` subset visible), the extension's
    // phonetic-map mode is a purely local rendering choice -- the server always computes entries
    // for the account's own saved mode (or "on_demand" when anonymous), so "always" here means
    // "reveal every entry this response included", regardless of each entry's own `always` flag.
    const alwaysVisible = opts.phoneticMapMode === 'always' && showPhon;

    const id = `${segIndex}:${i}`;
    const word = cleanWord(chunk);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = ['uw-word', marked ? `uw-word--${marked}` : ''].filter(Boolean).join(' ');
    btn.dataset.segStart = String(chunkStart);
    btn.dataset.segEnd = String(chunkEnd);
    btn.dataset.segIndex = String(segIndex);

    if (seg.t === 'change') {
      btn.title = `Was: ${seg.orig}${seg.why ? ` — ${seg.why}` : ''}`;
    } else if (seg.t === 'note') {
      btn.title = `${seg.why}${seg.hint ? ` — ${seg.hint}` : ''}`;
    }

    if (showPhon && phonLocal) {
      const ruby = document.createElement('ruby');
      ruby.appendChild(document.createTextNode(chunk));
      const rt = document.createElement('rt');
      rt.className = ['uw-rt', alwaysVisible ? 'uw-rt--always' : ''].filter(Boolean).join(' ');
      rt.textContent = phonLocal.entry.respell;
      ruby.appendChild(rt);
      btn.appendChild(ruby);
    } else {
      btn.textContent = chunk;
    }

    if (word && opts.onToggleWord) {
      btn.addEventListener('click', () => opts.onToggleWord?.(id, word));
    }

    parent.appendChild(btn);

    if (opts.showOriginalInline && seg.t === 'change' && /\S/.test(chunk)) {
      const orig = document.createElement('span');
      orig.className = 'uw-inline-orig';
      orig.textContent = ` [was: ${seg.orig}]`;
      parent.appendChild(orig);
    }
  });
}

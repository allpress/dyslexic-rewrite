import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { PhoneticMapEntry, PhoneticMapMode, Segment } from '../api';
import { speak } from '../lib/speech';

/** Strip surrounding punctuation and case so "Clock," and "clock" count as one word. */
export function cleanWord(raw: string): string {
  return raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '').toLowerCase();
}

export interface ReaderProps {
  segments: Segment[];
  /** Underline changes and notes. Off during a reading test so the condition stays hidden. */
  showMarks: boolean;
  /** Read-anything only: print the original word in brackets after each change. */
  showOriginalInline?: boolean;
  /** Word-instance ids currently marked as tripped. */
  tripped: ReadonlySet<string>;
  onToggleWord: (id: string, word: string) => void;
  /** Phonetic-map entries for this passage's served text (offsets per `servedTextSpans`). */
  phoneticMap?: PhoneticMapEntry[];
  /** 'off' renders nothing; 'on_demand'/'always' render <ruby>/<rt>. Defaults to 'off'. */
  phoneticMapMode?: PhoneticMapMode;
}

type Tip = { id: string; top: number; left: number; content: ReactNode };

type Block = { kind: 'para'; parts: Part[] } | { kind: 'heading'; text: string };
type Part = { seg: Segment; segIndex: number };

/** Split the flat segment list into paragraphs and headings. */
export function toBlocks(segments: Segment[]): Block[] {
  const blocks: Block[] = [];
  let current: Part[] = [];

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

/** One paragraph (or heading) of plain text per block, in reading order — for read-aloud. */
export function paragraphTexts(segments: Segment[]): string[] {
  return toBlocks(segments).map((block) =>
    block.kind === 'heading'
      ? block.text
      : block.parts.map((p) => (p.seg.t === 'text' || p.seg.t === 'change' || p.seg.t === 'note' ? p.seg.s : ''))
          .join(''),
  );
}

interface SegmentSpan {
  segIndex: number;
  start: number;
  end: number;
}

/**
 * The character range each segment occupies in the "served text": every segment's `s`
 * concatenated in order, with each `para` break counted as two newlines. Matches
 * `server.service.served_text` exactly, so a server-computed phonetic-map offset lands on the
 * right segment here.
 */
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

export default function Reader({
  segments,
  showMarks,
  showOriginalInline = false,
  tripped,
  onToggleWord,
  phoneticMap = [],
  phoneticMapMode = 'off',
}: ReaderProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const pendingTip = useRef<{ id: string; el: HTMLElement; content: ReactNode } | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Position the tooltip relative to the reader box after it is known.
  useLayoutEffect(() => {
    const p = pendingTip.current;
    if (!p || !wrapRef.current) return;
    const box = wrapRef.current.getBoundingClientRect();
    const word = p.el.getBoundingClientRect();
    setTip({
      id: p.id,
      top: word.bottom - box.top + 8,
      left: Math.max(0, Math.min(word.left - box.left, Math.max(0, box.width - 300))),
      content: p.content,
    });
    pendingTip.current = null;
  });

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const openTip = useCallback(
    (id: string, el: HTMLElement, content: ReactNode) => {
      cancelClose();
      pendingTip.current = { id, el, content };
      setTip((t) => (t?.id === id ? t : { id, top: -9999, left: 0, content }));
    },
    [cancelClose],
  );

  const closeTip = useCallback((id: string) => {
    setTip((t) => (t?.id === id ? null : t));
  }, []);

  // Closing is deferred a tick so that moving the pointer or focus from a word into its own
  // tip (e.g. to press the speaker button) can cancel the close instead of the tip vanishing
  // out from under the click.
  const scheduleClose = useCallback(
    (id: string) => {
      cancelClose();
      closeTimer.current = setTimeout(() => {
        closeTimer.current = null;
        closeTip(id);
      }, 0);
    },
    [cancelClose, closeTip],
  );

  const blocks = toBlocks(segments);

  // Phonetic-map entries, grouped by segment and re-based to offsets local to that segment's `s`.
  const entriesBySegment = useMemo(() => {
    const map = new Map<number, LocalEntry[]>();
    if (phoneticMapMode === 'off' || phoneticMap.length === 0) return map;
    const spans = servedTextSpans(segments);
    for (const span of spans) {
      const local: LocalEntry[] = [];
      for (const e of phoneticMap) {
        if (e.start >= span.start && e.end <= span.end && e.end > e.start) {
          local.push({ start: e.start - span.start, end: e.end - span.start, entry: e });
        }
      }
      if (local.length) map.set(span.segIndex, local);
    }
    return map;
  }, [segments, phoneticMap, phoneticMapMode]);

  const renderSegment = (seg: Segment, segIndex: number): ReactNode => {
    if (seg.t === 'para' || seg.t === 'heading') return null;

    const marked = seg.t === 'change' ? 'change' : seg.t === 'note' ? 'note' : null;

    let marksTip: ReactNode = null;
    if (seg.t === 'change') {
      marksTip = (
        <>
          <p>
            <span className="tip__label">Was:</span> {seg.orig}
          </p>
          <p>{seg.why}</p>
          {seg.alts.length > 0 && (
            <p>
              <span className="tip__label">Other options:</span> {seg.alts.join(', ')}
            </p>
          )}
        </>
      );
    } else if (seg.t === 'note') {
      marksTip = (
        <>
          <p>{seg.why}</p>
          <p>{seg.hint}</p>
        </>
      );
    }

    const localEntries = entriesBySegment.get(segIndex) ?? [];

    // Keep the whitespace so the paragraph still reads as running text.
    const chunks = seg.s.split(/(\s+)/);

    const nodes: ReactNode[] = [];
    let charPos = 0;
    chunks.forEach((chunk, i) => {
      if (chunk === '') return;
      if (/^\s+$/.test(chunk)) {
        nodes.push(<span key={`${segIndex}-s${i}`}>{chunk}</span>);
        charPos += chunk.length;
        return;
      }

      const chunkStart = charPos;
      const chunkEnd = charPos + chunk.length;
      charPos = chunkEnd;

      const phonLocal = localEntries.find((le) => le.start >= chunkStart && le.end <= chunkEnd);
      const phonEntry = phonLocal?.entry;
      const showPhon = phoneticMapMode !== 'off' && !!phonEntry;
      const alwaysVisible = phoneticMapMode === 'always' && !!phonEntry?.always;

      const id = `${segIndex}:${i}`;
      const word = cleanWord(chunk);
      const isTripped = tripped.has(id);
      const tipId = `tip-${segIndex}-${i}`;
      const showMarksTip = showMarks && marksTip !== null;

      const tipParts: ReactNode[] = [];
      if (showMarksTip) tipParts.push(<span key="marks">{marksTip}</span>);
      if (showPhon && phonEntry) {
        tipParts.push(
          <p className="tip__phon" key="phon">
            <span className="tip__label">Say it:</span> {phonEntry.respell}
            {phonEntry.hint ? <> — {phonEntry.hint}</> : null}
            <button
              type="button"
              className="tip__speak"
              aria-label={`Hear "${phonEntry.word}"`}
              onClick={() => speak(phonEntry.word)}
            >
              🔊
            </button>
          </p>,
        );
      }
      const tipContent = tipParts.length ? <>{tipParts}</> : null;
      const showTip = tipContent !== null;
      // On-demand entries are hidden until this word's tip is open (tapped/hovered/focused);
      // an "always" entry (in always mode) stays visible regardless.
      const revealed = showPhon && tip?.id === tipId;
      const rtClassName = ['rt', alwaysVisible ? 'rt--always' : '', revealed ? 'rt--revealed' : '']
        .filter(Boolean)
        .join(' ');

      const displayed: ReactNode = showPhon ? (
        <ruby>
          {chunk}
          <rt className={rtClassName}>{phonEntry!.respell}</rt>
        </ruby>
      ) : (
        chunk
      );

      nodes.push(
        <button
          key={id}
          type="button"
          className={[
            'word',
            isTripped ? 'word--tripped' : '',
            marked && showMarks ? `word--${marked}` : '',
          ]
            .filter(Boolean)
            .join(' ')}
          aria-pressed={isTripped}
          aria-label={`${chunk} — ${isTripped ? 'tripped me, tap to clear' : 'tap if this word trips you up'}`}
          aria-describedby={showTip && tip?.id === tipId ? tipId : undefined}
          onClick={() => word && onToggleWord(id, word)}
          onMouseEnter={(e) => showTip && openTip(tipId, e.currentTarget, tipContent)}
          onMouseLeave={() => showTip && scheduleClose(tipId)}
          onFocus={(e) => showTip && openTip(tipId, e.currentTarget, tipContent)}
          onBlur={() => showTip && scheduleClose(tipId)}
        >
          {displayed}
        </button>,
      );
    });

    if (showOriginalInline && seg.t === 'change') {
      nodes.push(
        <span key={`${segIndex}-orig`} className="reader__inline-orig">
          {' '}
          [was: {seg.orig}]
        </span>,
      );
    }

    return <span key={`seg-${segIndex}`}>{nodes}</span>;
  };

  const className = [
    'reader',
    'reader__text',
    showMarks ? 'marks' : '',
    phoneticMapMode === 'always' ? 'reader__text--always' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={className} style={{ position: 'relative' }} ref={wrapRef}>
      {blocks.map((block, i) =>
        block.kind === 'heading' ? (
          <h2 key={`b${i}`}>{block.text}</h2>
        ) : (
          <p key={`b${i}`}>{block.parts.map((p) => renderSegment(p.seg, p.segIndex))}</p>
        ),
      )}
      {tip && (
        <div
          className="tip"
          role="tooltip"
          id={tip.id}
          style={{ top: tip.top, left: tip.left }}
          // Clicking inside the tip (e.g. its speaker button) must not steal focus from the
          // word button, or a resulting blur could close the tip before the click registers.
          onMouseDown={(e) => e.preventDefault()}
          onMouseEnter={cancelClose}
          onMouseLeave={() => scheduleClose(tip.id)}
          onFocus={cancelClose}
          onBlur={() => scheduleClose(tip.id)}
        >
          {tip.content}
        </div>
      )}
    </div>
  );
}

import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { Segment } from '../api';

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

export default function Reader({
  segments,
  showMarks,
  showOriginalInline = false,
  tripped,
  onToggleWord,
}: ReaderProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const pendingTip = useRef<{ id: string; el: HTMLElement; content: ReactNode } | null>(null);

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

  const openTip = useCallback((id: string, el: HTMLElement, content: ReactNode) => {
    pendingTip.current = { id, el, content };
    setTip((t) => (t?.id === id ? t : { id, top: -9999, left: 0, content }));
  }, []);

  const closeTip = useCallback((id: string) => {
    setTip((t) => (t?.id === id ? null : t));
  }, []);

  const blocks = toBlocks(segments);

  const renderSegment = (seg: Segment, segIndex: number): ReactNode => {
    if (seg.t === 'para' || seg.t === 'heading') return null;

    const marked = seg.t === 'change' ? 'change' : seg.t === 'note' ? 'note' : null;

    let tipContent: ReactNode = null;
    if (seg.t === 'change') {
      tipContent = (
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
      tipContent = (
        <>
          <p>{seg.why}</p>
          <p>{seg.hint}</p>
        </>
      );
    }

    // Keep the whitespace so the paragraph still reads as running text.
    const chunks = seg.s.split(/(\s+)/);

    const nodes: ReactNode[] = [];
    chunks.forEach((chunk, i) => {
      if (chunk === '') return;
      if (/^\s+$/.test(chunk)) {
        nodes.push(<span key={`${segIndex}-s${i}`}>{chunk}</span>);
        return;
      }
      const id = `${segIndex}:${i}`;
      const word = cleanWord(chunk);
      const isTripped = tripped.has(id);
      const tipId = `tip-${segIndex}-${i}`;
      const showTip = showMarks && tipContent !== null;

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
          onMouseLeave={() => showTip && closeTip(tipId)}
          onFocus={(e) => showTip && openTip(tipId, e.currentTarget, tipContent)}
          onBlur={() => showTip && closeTip(tipId)}
        >
          {chunk}
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

  return (
    <div className={`reader${showMarks ? ' marks' : ''}`} style={{ position: 'relative' }} ref={wrapRef}>
      {blocks.map((block, i) =>
        block.kind === 'heading' ? (
          <h2 key={`b${i}`}>{block.text}</h2>
        ) : (
          <p key={`b${i}`}>{block.parts.map((p) => renderSegment(p.seg, p.segIndex))}</p>
        ),
      )}
      {tip && (
        <div className="tip" role="tooltip" id={tip.id} style={{ top: tip.top, left: tip.left }}>
          {tip.content}
        </div>
      )}
    </div>
  );
}

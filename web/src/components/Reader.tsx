import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import type { PhoneticMapEntry, PhoneticMapMode, Segment } from '../api';
import { speak, speakBlocks, type SpeakBlocksHandle } from '../lib/speech';
import { FONT_STACKS } from '../lib/fonts';
import {
  prefersReducedMotion,
  readerCssVars,
  readerPrefsStore,
  ttsModeStore,
  useReaderPrefs,
  useTtsMode,
} from '../lib/readerPrefs';

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

interface WordSpan {
  /** Same `${segIndex}:${chunkIndex}` scheme as each word button's own `id` below, so a
   * text-to-speech char offset can be turned straight into "which word button is this". */
  id: string;
  start: number;
  end: number;
}

/**
 * Per block (paragraph/heading), the character range each word occupies in that block's own
 * plain text (i.e. `paragraphTexts(segments)[blockIndex]`) — read-aloud's `onboundary` events
 * report offsets into exactly that text, one utterance per block. Headings get `[]`: they render
 * as plain text with no per-word buttons to highlight.
 */
export function blockWordSpans(blocks: Block[]): WordSpan[][] {
  return blocks.map((block) => {
    if (block.kind === 'heading') return [];
    const spans: WordSpan[] = [];
    let pos = 0;
    block.parts.forEach(({ seg, segIndex }) => {
      const raw = seg.t === 'text' || seg.t === 'change' || seg.t === 'note' ? seg.s : '';
      raw.split(/(\s+)/).forEach((chunk, i) => {
        if (chunk === '') return;
        if (!/^\s+$/.test(chunk)) spans.push({ id: `${segIndex}:${i}`, start: pos, end: pos + chunk.length });
        pos += chunk.length;
      });
    });
    return spans;
  });
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
  const blockTexts = useMemo(() => paragraphTexts(segments), [segments]);
  const wordSpans = useMemo(() => blockWordSpans(blocks), [blocks]);

  /* ------------------------------------------------------------ reading settings ("Aa" panel)
   * Comfort settings only (docs/RESEARCH.md §2) -- font, spacing, theme, reading ruler,
   * spotlight, auto-scroll and text-to-speech. Read from the shared store `ReaderSettingsPanel`
   * (mounted elsewhere on the page) writes to, so this component re-renders live as the reader
   * adjusts anything. See lib/readerPrefs.ts and lib/speech.ts. */
  const prefs = useReaderPrefs();
  const ttsMode = useTtsMode();
  const reducedMotion = prefersReducedMotion();

  const cssVars = readerCssVars(prefs, FONT_STACKS[prefs.font_family]) as unknown as CSSProperties;

  // ---- reading ruler: a dimmed page with a lit band that follows the pointer/finger/arrows.
  const [rulerY, setRulerY] = useState<number | null>(null);
  const handleRulerMove = useCallback(
    (clientY: number) => {
      if (!prefs.ruler_enabled || !wrapRef.current) return;
      const box = wrapRef.current.getBoundingClientRect();
      setRulerY(Math.max(0, Math.min(clientY - box.top, box.height)));
    },
    [prefs.ruler_enabled],
  );
  // Give the ruler a starting position as soon as it's turned on, rather than waiting for the
  // first pointer move (or never appearing at all on a keyboard-only toggle via "R").
  useEffect(() => {
    if (!prefs.ruler_enabled) {
      setRulerY(null);
    } else if (rulerY === null && wrapRef.current) {
      setRulerY(wrapRef.current.getBoundingClientRect().height / 2);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.ruler_enabled]);

  // ---- spotlight: dims every paragraph but the current one; ↑/↓ or a click move it.
  const [spotlightIndex, setSpotlightIndex] = useState(0);
  useEffect(() => {
    if (spotlightIndex > blocks.length - 1) setSpotlightIndex(Math.max(0, blocks.length - 1));
  }, [blocks.length, spotlightIndex]);

  // ---- text-to-speech: per-word highlighting when the browser's onboundary gives word offsets,
  // a whole-paragraph fallback (via onBlockStart) when it never does (e.g. some Safari voices).
  const [speakingBlock, setSpeakingBlock] = useState<number | null>(null);
  const [speakingIds, setSpeakingIds] = useState<ReadonlySet<string>>(new Set());
  const [ttsPlaying, setTtsPlaying] = useState(false);
  const speechRef = useRef<SpeakBlocksHandle | null>(null);
  const pausedRef = useRef(false);

  const stopReading = useCallback(() => {
    speechRef.current?.stop();
    speechRef.current = null;
    pausedRef.current = false;
    setTtsPlaying(false);
    setSpeakingBlock(null);
    setSpeakingIds(new Set());
  }, []);

  const startReadingFrom = useCallback(
    (blockIndex: number) => {
      speechRef.current?.stop();
      pausedRef.current = false;
      setTtsPlaying(true);
      speechRef.current = speakBlocks(blockTexts, blockIndex, {
        rate: prefs.tts_rate,
        pitch: prefs.tts_pitch,
        voiceURI: prefs.tts_voice || null,
        onBlockStart: (i) => {
          setSpeakingBlock(i);
          // Whole-block fallback highlight, replaced by a single word as soon as (if) a real
          // word boundary arrives for this block.
          setSpeakingIds(new Set((wordSpans[i] ?? []).map((w) => w.id)));
        },
        onBoundary: (i, boundary) => {
          const spans = wordSpans[i] ?? [];
          if (boundary.isWord) {
            const hit = spans.find((s) => boundary.charIndex >= s.start && boundary.charIndex < s.end);
            if (hit) setSpeakingIds(new Set([hit.id]));
            return;
          }
          // Sentence-level (or unnamed, non-word) boundary: highlight every word it spans.
          const end = boundary.charIndex + Math.max(boundary.charLength, 1);
          const ids = spans.filter((s) => s.start < end && s.end > boundary.charIndex).map((s) => s.id);
          if (ids.length) setSpeakingIds(new Set(ids));
        },
        onDone: stopReading,
      });
    },
    [blockTexts, wordSpans, prefs.tts_rate, prefs.tts_pitch, prefs.tts_voice, stopReading],
  );

  const toggleReadingPlayPause = useCallback(() => {
    if (!speechRef.current) {
      startReadingFrom(0);
      return;
    }
    if (pausedRef.current) {
      speechRef.current.resume();
      pausedRef.current = false;
      setTtsPlaying(true);
    } else {
      speechRef.current.pause();
      pausedRef.current = true;
      setTtsPlaying(false);
    }
  }, [startReadingFrom]);

  // Never keep talking after the passage changes or this reader unmounts.
  useEffect(() => stopReading, [segments, stopReading]);

  // ---- auto-scroll: 1-5 lines/second, paused on hover/tap, skipped under reduced motion.
  const [autoscrollPaused, setAutoscrollPaused] = useState(false);
  useEffect(() => {
    if (prefs.autoscroll_speed <= 0 || reducedMotion || autoscrollPaused) return;
    const pxPerSecond = prefs.autoscroll_speed * prefs.font_size_px * prefs.line_height;
    let raf = 0;
    let last = performance.now();
    let carry = 0;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      carry += pxPerSecond * dt;
      if (carry >= 1) {
        window.scrollBy(0, Math.floor(carry));
        carry -= Math.floor(carry);
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [prefs.autoscroll_speed, prefs.font_size_px, prefs.line_height, reducedMotion, autoscrollPaused]);

  // ---- keyboard: R toggles the ruler, S toggles spotlight, ↑/↓ move whichever is on, Space
  // plays/pauses read-aloud once TTS mode is turned on in the settings panel. Ignored while
  // typing anywhere else on the page.
  useEffect(() => {
    function isTypingTarget(target: EventTarget | null): boolean {
      const el = target as HTMLElement | null;
      if (!el) return false;
      return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable;
    }
    function onKeyDown(e: KeyboardEvent) {
      if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'r' || e.key === 'R') {
        readerPrefsStore.set({ ruler_enabled: !readerPrefsStore.get().ruler_enabled });
      } else if (e.key === 's' || e.key === 'S') {
        readerPrefsStore.set({ spotlight_enabled: !readerPrefsStore.get().spotlight_enabled });
      } else if (e.key === 'ArrowDown') {
        if (readerPrefsStore.get().spotlight_enabled) {
          e.preventDefault();
          setSpotlightIndex((v) => Math.min(v + 1, Math.max(0, blocks.length - 1)));
        }
        if (readerPrefsStore.get().ruler_enabled) setRulerY((v) => (v ?? 0) + 24);
      } else if (e.key === 'ArrowUp') {
        if (readerPrefsStore.get().spotlight_enabled) {
          e.preventDefault();
          setSpotlightIndex((v) => Math.max(v - 1, 0));
        }
        if (readerPrefsStore.get().ruler_enabled) setRulerY((v) => Math.max((v ?? 0) - 24, 0));
      } else if (e.key === ' ' && ttsModeStore.get()) {
        e.preventDefault();
        toggleReadingPlayPause();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [blocks.length, toggleReadingPlayPause]);

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
            speakingIds.has(id) ? 'word--speaking' : '',
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
    prefs.ruler_enabled ? 'reader--ruler-on' : '',
    prefs.spotlight_enabled ? 'reader--spotlight-on' : '',
    reducedMotion ? 'reader--reduced-motion' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={className}
      style={{ position: 'relative', ...cssVars }}
      ref={wrapRef}
      data-theme={prefs.theme}
      onMouseMove={(e) => handleRulerMove(e.clientY)}
      onTouchMove={(e) => {
        const t = e.touches[0];
        if (t) handleRulerMove(t.clientY);
      }}
      onMouseEnter={() => setAutoscrollPaused(true)}
      onMouseLeave={() => setAutoscrollPaused(false)}
      onTouchStart={() => setAutoscrollPaused(true)}
      onTouchEnd={() => setAutoscrollPaused(false)}
    >
      {prefs.ruler_enabled && rulerY !== null && (
        <div
          className="reader__ruler"
          aria-hidden="true"
          style={{ top: rulerY - prefs.ruler_height_px / 2, height: prefs.ruler_height_px }}
        />
      )}
      {blocks.map((block, i) => {
        const dimmed = prefs.spotlight_enabled && i !== spotlightIndex;
        const active = prefs.spotlight_enabled && i === spotlightIndex;
        return (
          <div
            key={`b${i}`}
            className={[
              'reader__block',
              dimmed ? 'reader__block--dim' : '',
              active ? 'reader__block--active' : '',
              i === speakingBlock ? 'reader__block--speaking' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => prefs.spotlight_enabled && setSpotlightIndex(i)}
          >
            {ttsMode && (
              <button
                type="button"
                className="reader__read-from"
                aria-label={`Read from here${block.kind === 'heading' ? '' : `, paragraph ${i + 1}`}`}
                aria-pressed={ttsPlaying && speakingBlock === i}
                onClick={(e) => {
                  e.stopPropagation();
                  startReadingFrom(i);
                }}
              >
                <span aria-hidden="true">▶</span>
              </button>
            )}
            {block.kind === 'heading' ? (
              <h2>{block.text}</h2>
            ) : (
              <p>{block.parts.map((p) => renderSegment(p.seg, p.segIndex))}</p>
            )}
          </div>
        );
      })}
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

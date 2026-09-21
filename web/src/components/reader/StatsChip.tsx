import type { Segment } from '../../api';
import { paragraphTexts } from '../Reader';

/** What a page can tell the stats chip about the passage it's showing. Everything but
 * `segments` is optional — the chip still shows a sensible reading-time estimate without it. */
export interface ReaderStatsInput {
  segments: Segment[];
  /** From `RewriteStats.sentences`, when the page already computed one server-side. Falls back
   * to counting sentence-ending punctuation in the passage text. */
  sentences?: number;
  /** `RewriteStats.load_before` / `load_after` — shown as "reading load N → M" when both are given. */
  loadBefore?: number;
  loadAfter?: number;
  /** The reader's own last measured words-per-minute (e.g. `ItemResult.wpm` from an earlier
   * passage in the same test), when the host page has one to hand. Falls back to 200 wpm. */
  wpm?: number;
}

const DEFAULT_WPM = 200;
const WORD_RE = /[\p{L}\p{N}]+/gu;
const SENTENCE_END_RE = /[.!?]+(?:\s|$)/g;

export interface ReaderStats {
  words: number;
  sentences: number;
  minutes: number;
  wpm: number;
  loadBefore?: number;
  loadAfter?: number;
}

/** Pure computation, exported so it (and the chip's rendering) can be tested separately. */
export function computeReaderStats(input: ReaderStatsInput): ReaderStats {
  const text = paragraphTexts(input.segments).join(' ');
  const words = text.match(WORD_RE)?.length ?? 0;
  const countedSentences = text.match(SENTENCE_END_RE)?.length ?? 0;
  const sentences = input.sentences ?? (countedSentences || (words > 0 ? 1 : 0));
  const wpm = input.wpm && input.wpm > 0 ? input.wpm : DEFAULT_WPM;
  return { words, sentences, minutes: words / wpm, wpm, loadBefore: input.loadBefore, loadAfter: input.loadAfter };
}

function formatMinutes(minutes: number): string {
  if (minutes <= 0) return '0 min read';
  if (minutes < 1) return '< 1 min read';
  return `${Math.round(minutes)} min read`;
}

/** A small pill row: word count, estimated reading time, sentence count, and (when the page
 * has them) the passage's reading-load before/after a rewrite. */
export default function StatsChip({ stats }: { stats: ReaderStatsInput }) {
  const s = computeReaderStats(stats);
  const hasLoad = s.loadBefore !== undefined && s.loadAfter !== undefined;
  return (
    <div className="reader-stats" role="status">
      <span className="reader-stats__item">
        {s.words} word{s.words === 1 ? '' : 's'}
      </span>
      <span className="reader-stats__item">{formatMinutes(s.minutes)}</span>
      <span className="reader-stats__item">
        {s.sentences} sentence{s.sentences === 1 ? '' : 's'}
      </span>
      {hasLoad && (
        <span className="reader-stats__item">
          Reading load {Math.round(s.loadBefore!)} &rarr; {Math.round(s.loadAfter!)}
        </span>
      )}
    </div>
  );
}

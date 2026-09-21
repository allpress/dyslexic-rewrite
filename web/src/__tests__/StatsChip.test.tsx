import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatsChip, { computeReaderStats } from '../components/reader/StatsChip';
import type { Segment } from '../api';

const SEGMENTS: Segment[] = [{ t: 'text', s: 'One two three four five six seven eight nine ten.' }];

describe('computeReaderStats', () => {
  it('counts words and sentences and estimates reading time at 200 wpm by default', () => {
    const stats = computeReaderStats({ segments: SEGMENTS });
    expect(stats.words).toBe(10);
    expect(stats.sentences).toBe(1);
    expect(stats.wpm).toBe(200);
    expect(stats.minutes).toBeCloseTo(10 / 200);
  });

  it('uses the reader’s own last measured wpm instead of the 200 default when given one', () => {
    const stats = computeReaderStats({ segments: SEGMENTS, wpm: 100 });
    expect(stats.wpm).toBe(100);
    expect(stats.minutes).toBeCloseTo(10 / 100);
  });

  it('falls back to 200 wpm when a wpm of 0 is given (nothing measured yet)', () => {
    const stats = computeReaderStats({ segments: SEGMENTS, wpm: 0 });
    expect(stats.wpm).toBe(200);
  });

  it('prefers a supplied sentence count over counting punctuation', () => {
    const stats = computeReaderStats({ segments: SEGMENTS, sentences: 3 });
    expect(stats.sentences).toBe(3);
  });

  it('carries reading-load before/after through untouched', () => {
    const stats = computeReaderStats({ segments: SEGMENTS, loadBefore: 42.4, loadAfter: 18.1 });
    expect(stats.loadBefore).toBeCloseTo(42.4);
    expect(stats.loadAfter).toBeCloseTo(18.1);
  });
});

describe('StatsChip', () => {
  it('renders word count, reading time, sentence count and reading load', () => {
    render(<StatsChip stats={{ segments: SEGMENTS, loadBefore: 40, loadAfter: 20 }} />);
    expect(screen.getByText('10 words')).toBeInTheDocument();
    expect(screen.getByText('< 1 min read')).toBeInTheDocument();
    expect(screen.getByText('1 sentence')).toBeInTheDocument();
    expect(screen.getByText('Reading load 40 → 20')).toBeInTheDocument();
  });

  it('omits the reading-load item when the page has no RewriteStats to give it', () => {
    render(<StatsChip stats={{ segments: SEGMENTS }} />);
    expect(screen.queryByText(/Reading load/)).not.toBeInTheDocument();
  });
});

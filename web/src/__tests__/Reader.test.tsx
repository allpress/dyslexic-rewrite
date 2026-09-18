import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Reader, { cleanWord, servedTextSpans, toBlocks } from '../components/Reader';
import type { PhoneticMapEntry, Segment } from '../api';

const SEGMENTS: Segment[] = [
  { t: 'heading', s: 'The clock' },
  { t: 'text', s: 'Every night Grandpa would wind the ' },
  {
    t: 'change',
    s: 'clock',
    orig: 'chronometer',
    why: 'Shorter and more common.',
    alts: ['timepiece', 'watch'],
  },
  { t: 'text', s: ' before bed.' },
  { t: 'para' },
  { t: 'note', s: 'The house went quiet.', why: 'Long sentence split.', hint: 'Take a breath here.' },
];

function Harness({ showMarks = false }: { showMarks?: boolean }) {
  const [tripped, setTripped] = useState<Map<string, string>>(new Map());
  return (
    <>
      <Reader
        segments={SEGMENTS}
        showMarks={showMarks}
        tripped={new Set(tripped.keys())}
        onToggleWord={(id, word) =>
          setTripped((prev) => {
            const next = new Map(prev);
            if (next.has(id)) next.delete(id);
            else next.set(id, word);
            return next;
          })
        }
      />
      <output data-testid="tripped">{Array.from(new Set(tripped.values())).join(',')}</output>
    </>
  );
}

describe('Reader', () => {
  it('renders headings, paragraphs and every word as a button', () => {
    render(<Harness />);

    expect(screen.getByRole('heading', { level: 2, name: 'The clock' })).toBeInTheDocument();
    // Two paragraphs: one before the `para` break, one after.
    expect(document.querySelectorAll('.reader p')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /^Grandpa/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^clock/ })).toBeInTheDocument();
  });

  it('toggles a word as tripped and back again', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const word = screen.getByRole('button', { name: /^Grandpa/ });
    expect(word).toHaveAttribute('aria-pressed', 'false');

    await user.click(word);
    expect(word).toHaveAttribute('aria-pressed', 'true');
    expect(word.className).toContain('word--tripped');
    expect(screen.getByTestId('tripped')).toHaveTextContent('grandpa');

    await user.click(word);
    expect(word).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('tripped').textContent).toBe('');
  });

  it('hides change marks by default and shows them when asked', () => {
    const { rerender } = render(<Harness showMarks={false} />);
    expect(screen.getByRole('button', { name: /^clock/ }).className).not.toContain('word--change');

    rerender(<Harness showMarks />);
    expect(screen.getByRole('button', { name: /^clock/ }).className).toContain('word--change');
  });

  it('shows the original word and the reason in a tooltip when marks are on', async () => {
    const user = userEvent.setup();
    render(<Harness showMarks />);

    await user.hover(screen.getByRole('button', { name: /^clock/ }));

    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent('chronometer');
    expect(tip).toHaveTextContent('Shorter and more common.');
    expect(tip).toHaveTextContent('timepiece');
  });

  it('splits segments into blocks and normalises words', () => {
    const blocks = toBlocks(SEGMENTS);
    expect(blocks.map((b) => b.kind)).toEqual(['heading', 'para', 'para']);
    expect(cleanWord('Clock,')).toBe('clock');
    expect(cleanWord('“quiet.”')).toBe('quiet');
  });
});

/* ------------------------------------------------------- phonetic map */

const PHON_SEGMENTS: Segment[] = [
  { t: 'text', s: 'Every night Grandpa would wind the ' },
  {
    t: 'change',
    s: 'clock',
    orig: 'chronometer',
    why: 'Shorter and more common.',
    alts: [],
  },
  { t: 'text', s: ' before bed.' },
];

function entryFor(word: string, respell: string, always: boolean): PhoneticMapEntry {
  const spans = servedTextSpans(PHON_SEGMENTS);
  for (const span of spans) {
    const seg = PHON_SEGMENTS[span.segIndex];
    const text = seg.t === 'text' || seg.t === 'change' || seg.t === 'note' ? seg.s : '';
    const at = text.indexOf(word);
    if (at >= 0) {
      return { start: span.start + at, end: span.start + at + word.length, word, respell, hint: null, kind: 'phonetic', always };
    }
  }
  throw new Error(`word "${word}" not found in fixture`);
}

const ON_DEMAND_ENTRY = entryFor('Grandpa', 'GRAN-pa', false);
const ALWAYS_ENTRY = entryFor('clock', 'KLOK', true);
const PHON_ENTRIES = [ON_DEMAND_ENTRY, ALWAYS_ENTRY];

function PhonHarness({ mode }: { mode: 'off' | 'on_demand' | 'always' }) {
  return (
    <Reader
      segments={PHON_SEGMENTS}
      showMarks={false}
      tripped={new Set()}
      onToggleWord={() => {}}
      phoneticMap={PHON_ENTRIES}
      phoneticMapMode={mode}
    />
  );
}

describe('Reader phonetic map', () => {
  it('renders no <ruby>/<rt> at all when the mode is off', () => {
    const { container } = render(<PhonHarness mode="off" />);
    expect(container.querySelectorAll('ruby')).toHaveLength(0);
    expect(container.querySelectorAll('rt')).toHaveLength(0);
  });

  it('on_demand: renders <ruby>/<rt> hidden, then reveals on click', async () => {
    const user = userEvent.setup();
    const { container } = render(<PhonHarness mode="on_demand" />);

    const rubies = container.querySelectorAll('ruby');
    expect(rubies.length).toBeGreaterThan(0);

    const grandpaButton = screen.getByRole('button', { name: /^Grandpa/ });
    const rt = grandpaButton.querySelector('rt')!;
    expect(rt).toHaveTextContent('GRAN-pa');
    expect(rt.className).not.toContain('rt--revealed');
    expect(rt.className).not.toContain('rt--always');

    await user.click(grandpaButton);
    expect(rt.className).toContain('rt--revealed');

    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent('GRAN-pa');
  });

  it('always: shows <rt> only for entries marked always', () => {
    render(<PhonHarness mode="always" />);

    const clockButton = screen.getByRole('button', { name: /^clock/ });
    const clockRt = clockButton.querySelector('rt')!;
    expect(clockRt.className).toContain('rt--always');

    const grandpaButton = screen.getByRole('button', { name: /^Grandpa/ });
    const grandpaRt = grandpaButton.querySelector('rt')!;
    expect(grandpaRt.className).not.toContain('rt--always');
    expect(grandpaRt.className).not.toContain('rt--revealed');
  });

  it('the tip has a speaker button that calls speechSynthesis', async () => {
    const speak = vi.fn();
    const cancel = vi.fn();
    vi.stubGlobal('speechSynthesis', { speak, cancel });
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      vi.fn().mockImplementation((text: string) => ({ text, rate: 1 })),
    );

    const user = userEvent.setup();
    render(<PhonHarness mode="on_demand" />);

    await user.click(screen.getByRole('button', { name: /^Grandpa/ }));
    const speakButton = await screen.findByRole('button', { name: /Hear "Grandpa"/ });
    await user.click(speakButton);

    expect(speak).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalled();

    vi.unstubAllGlobals();
  });
});

import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Reader, { cleanWord, toBlocks } from '../components/Reader';
import type { Segment } from '../api';

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

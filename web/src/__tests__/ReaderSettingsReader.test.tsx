import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Reader, { blockWordSpans, paragraphTexts, toBlocks } from '../components/Reader';
import { DEFAULT_READER_PREFS, readerPrefsStore, ttsModeStore } from '../lib/readerPrefs';
import type { Segment } from '../api';

const SEGMENTS: Segment[] = [
  { t: 'heading', s: 'The clock' },
  { t: 'text', s: 'Every night Grandpa would wind the clock before bed.' },
  { t: 'para' },
  { t: 'text', s: 'The house went quiet after that.' },
];

function noop() {}

beforeEach(() => {
  // These are read from a shared, module-level store (see lib/readerPrefs.ts) so every test
  // needs a clean slate, or one test's toggles would leak into the next.
  readerPrefsStore.replace({ ...DEFAULT_READER_PREFS });
  ttsModeStore.set(false);
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Reader: reading ruler', () => {
  it('is off by default and toggles on with the "R" key', () => {
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    const reader = container.querySelector('.reader')!;
    expect(reader.className).not.toContain('reader--ruler-on');

    fireEvent.keyDown(window, { key: 'r' });
    expect(reader.className).toContain('reader--ruler-on');
    expect(container.querySelector('.reader__ruler')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'r' });
    expect(reader.className).not.toContain('reader--ruler-on');
  });

  it('ignores the "r" key while the reader is typing in a form field elsewhere on the page', () => {
    render(
      <>
        <input aria-label="elsewhere" defaultValue="" />
        <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />
      </>,
    );
    screen.getByLabelText('elsewhere').focus();
    fireEvent.keyDown(screen.getByLabelText('elsewhere'), { key: 'r' });
    expect(readerPrefsStore.get().ruler_enabled).toBe(false);
  });
});

describe('Reader: spotlight', () => {
  it('dims every paragraph but the current one, and "↓" moves it forward', () => {
    act(() => readerPrefsStore.set({ spotlight_enabled: true }));
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    const blocks = container.querySelectorAll('.reader__block');
    expect(blocks).toHaveLength(3); // heading + 2 paragraphs

    expect(blocks[0].className).toContain('reader__block--active');
    expect(blocks[1].className).toContain('reader__block--dim');
    expect(blocks[2].className).toContain('reader__block--dim');

    fireEvent.keyDown(window, { key: 'ArrowDown' });

    expect(blocks[0].className).toContain('reader__block--dim');
    expect(blocks[1].className).toContain('reader__block--active');
    expect(blocks[2].className).toContain('reader__block--dim');
  });

  it('toggles on with the "S" key', () => {
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    expect(container.querySelector('.reader__block--dim')).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: 's' });
    expect(container.querySelector('.reader__block--dim')).toBeInTheDocument();
  });

  it('moves to a clicked paragraph', async () => {
    const user = userEvent.setup();
    act(() => readerPrefsStore.set({ spotlight_enabled: true }));
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    const blocks = container.querySelectorAll('.reader__block');
    await user.click(screen.getByRole('button', { name: /^house/ }));
    expect(blocks[2].className).toContain('reader__block--active');
  });
});

describe('Reader: colour theme', () => {
  it('sets data-theme on the reader container and reacts to a theme change', () => {
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    const reader = container.querySelector('.reader')!;
    expect(reader).toHaveAttribute('data-theme', 'light');

    act(() => readerPrefsStore.set({ theme: 'dark' }));
    expect(reader).toHaveAttribute('data-theme', 'dark');
  });
});

describe('Reader: settings drive CSS custom properties on the container', () => {
  it('reflects font size onto --reader-font-size', () => {
    const { container } = render(
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />,
    );
    const reader = container.querySelector('.reader') as HTMLElement;
    expect(reader.style.getPropertyValue('--reader-font-size')).toBe('20px');

    act(() => readerPrefsStore.set({ font_size_px: 28 }));
    expect(reader.style.getPropertyValue('--reader-font-size')).toBe('28px');
  });
});

/* ------------------------------------------------------------------- text-to-speech */

class FakeUtterance {
  static instances: FakeUtterance[] = [];
  text: string;
  rate = 1;
  pitch = 1;
  voice: unknown = null;
  onboundary: ((e: { charIndex: number; charLength?: number; name?: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
    FakeUtterance.instances.push(this);
  }
}

describe('Reader: text-to-speech word highlighting', () => {
  beforeEach(() => {
    FakeUtterance.instances = [];
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance);
    vi.stubGlobal('speechSynthesis', {
      speak: vi.fn(),
      cancel: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      getVoices: vi.fn(() => []),
    });
  });

  it('highlights the word a mocked onboundary event points at', async () => {
    const user = userEvent.setup();
    ttsModeStore.set(true);
    render(<Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />);

    // "Read from here" on the first paragraph starts speaking blockTexts[1] (index 1: the
    // heading is block 0).
    await user.click(screen.getByRole('button', { name: /Read from here, paragraph 2/ }));
    expect(FakeUtterance.instances).toHaveLength(1);

    const text = paragraphTexts(SEGMENTS)[1];
    const spans = blockWordSpans(toBlocks(SEGMENTS))[1];
    const grandpaSpan = spans.find((s) => text.slice(s.start, s.end) === 'Grandpa')!;
    expect(grandpaSpan).toBeDefined();

    act(() => {
      FakeUtterance.instances[0].onboundary?.({
        charIndex: grandpaSpan.start,
        charLength: grandpaSpan.end - grandpaSpan.start,
        name: 'word',
      });
    });

    const grandpaButton = screen.getByRole('button', { name: /^Grandpa/ });
    expect(grandpaButton.className).toContain('word--speaking');

    const clockButton = screen.getByRole('button', { name: /^clock/ });
    expect(clockButton.className).not.toContain('word--speaking');
  });

  it('falls back to highlighting a whole sentence when the boundary event has no word info', async () => {
    const user = userEvent.setup();
    ttsModeStore.set(true);
    render(<Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />);

    await user.click(screen.getByRole('button', { name: /Read from here, paragraph 2/ }));
    const text = paragraphTexts(SEGMENTS)[1];

    act(() => {
      FakeUtterance.instances[0].onboundary?.({
        charIndex: 0,
        charLength: text.length,
        name: 'sentence',
      });
    });

    expect(screen.getByRole('button', { name: /^Every/ }).className).toContain('word--speaking');
    expect(screen.getByRole('button', { name: /^Grandpa/ }).className).toContain('word--speaking');
  });

  it('does not render "read from here" controls when TTS mode is off', () => {
    render(<Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={noop} />);
    expect(screen.queryByRole('button', { name: /Read from here/ })).not.toBeInTheDocument();
  });
});

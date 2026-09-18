import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ReadAnything from '../pages/Read';
import { MeProvider } from '../useMe';
import type { SampleInfo, SampleResponse } from '../api';

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

const SAMPLE_LIST: SampleInfo[] = [
  {
    slug: 'wind-in-the-willows',
    title: 'The Wind in the Willows',
    author: 'Kenneth Grahame',
    year: 1908,
    chapter: 'Chapter 1: The River Bank',
    source: 'https://www.gutenberg.org/ebooks/289',
    blurb: 'Mole meets the River for the first time.',
    words: 693,
  },
  {
    slug: 'alice-in-wonderland',
    title: "Alice's Adventures in Wonderland",
    author: 'Lewis Carroll',
    year: 1865,
    chapter: 'Chapter 1: Down the Rabbit-Hole',
    source: 'https://www.gutenberg.org/ebooks/11',
    blurb: 'Alice follows a White Rabbit down a hole.',
    words: 454,
  },
  {
    slug: 'red-headed-league',
    title: 'The Adventures of Sherlock Holmes',
    author: 'Arthur Conan Doyle',
    year: 1892,
    chapter: 'The Red-Headed League (opening)',
    source: 'https://www.gutenberg.org/ebooks/1661',
    blurb: 'Watson walks in on a client with fiery red hair.',
    words: 607,
  },
  {
    slug: 'treasure-island',
    title: 'Treasure Island',
    author: 'Robert Louis Stevenson',
    year: 1883,
    chapter: 'Chapter I: The Old Sea-dog at the Admiral Benbow',
    source: 'https://www.gutenberg.org/ebooks/120',
    blurb: 'An old seaman takes a room at the inn.',
    words: 498,
  },
];

function sampleResponse(slug: string): SampleResponse {
  const info = SAMPLE_LIST.find((s) => s.slug === slug)!;
  return {
    segments: [{ t: 'text', s: 'Some rewritten passage text.' }],
    stats: { sentences: 1, sentences_changed: 0, changes: 0, load_before: 1, load_after: 1 },
    phonetic_map: [],
    cached: false,
    title: info.title,
    author: info.author,
    year: info.year,
    chapter: info.chapter,
    source: info.source,
  };
}

describe('Read anything — sample books', () => {
  let calls: { url: string; method: string }[] = [];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        calls.push({ url, method });

        if (url === '/api/me' && method === 'GET') return reply(401, { error: 'Please sign in.' });
        if (url === '/api/samples' && method === 'GET') return reply(200, SAMPLE_LIST);
        const sampleMatch = url.match(/^\/api\/samples\/([\w-]+)$/);
        if (sampleMatch && method === 'GET') return reply(200, sampleResponse(sampleMatch[1]));
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows all four samples in the picker and loads one with its attribution', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/read']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MeProvider>
          <ReadAnything />
        </MeProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Show me an example' }));

    const dialog = await screen.findByRole('dialog', { name: 'Choose a sample book' });
    for (const s of SAMPLE_LIST) {
      expect(await screen.findByRole('heading', { name: s.title })).toBeInTheDocument();
    }

    const windCard = (await screen.findByRole('heading', { name: 'The Wind in the Willows' })).closest('li')!;
    await user.click(
      within(windCard).getByRole('button', { name: 'Read this' }),
    );

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await waitFor(() => {
      const attribution = document.querySelector('.sample-attribution');
      expect(attribution?.textContent).toMatch(/From\s*The Wind in the Willows\s*by Kenneth Grahame, 1908/);
    });
    expect(calls.some((c) => c.url === '/api/samples/wind-in-the-willows')).toBe(true);
  });

  it('loads the sample named in ?sample= directly, without opening the picker', async () => {
    render(
      <MemoryRouter
        initialEntries={['/read?sample=alice-in-wonderland']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <MeProvider>
          <ReadAnything />
        </MeProvider>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(calls.some((c) => c.url === '/api/samples/alice-in-wonderland')).toBe(true),
    );
    await waitFor(() => {
      const attribution = document.querySelector('.sample-attribution');
      expect(attribution?.textContent).toMatch(/From\s*Alice's Adventures in Wonderland\s*by Lewis Carroll, 1865/);
    });
    expect(screen.queryByRole('dialog', { name: 'Choose a sample book' })).not.toBeInTheDocument();
  });
});

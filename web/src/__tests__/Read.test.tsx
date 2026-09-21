import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ReadAnything from '../pages/Read';
import { MeProvider } from '../useMe';
import type { PlanSummary, RewriteResponse, SampleInfo, SampleResponse, User } from '../api';

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

// ===========================================================================================
// v0.6: import from a web page, dictionary "define on select", and AI summaries
// ===========================================================================================
function userWith(plan: PlanSummary): User {
  return {
    id: 'u1',
    email: 'doug@example.com',
    name: 'Doug',
    base_profile: 'default',
    onboarded: true,
    has_personal_profile: false,
    phonetic_map: 'on_demand',
    kindle_email: null,
    plan,
    created_at: '2026-09-17T10:00:00Z',
  };
}

const FREE_PLAN: PlanSummary = { plan: 'free', pro: false, plan_until: null, cancel_at_period_end: false, manageable: false };
const PRO_PLAN: PlanSummary = { plan: 'pro', pro: true, plan_until: null, cancel_at_period_end: false, manageable: true };

const REWRITE_RESULT: RewriteResponse = {
  segments: [{ t: 'text', s: 'The clock struck noon.' }],
  stats: { sentences: 1, sentences_changed: 0, changes: 0, load_before: 1, load_after: 1 },
  phonetic_map: [],
  cached: false,
};

describe('Read anything — import from a web page (v0.6)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        if (url === '/api/me' && method === 'GET') return reply(401, { error: 'Please sign in.' });
        if (url === '/api/import/url' && method === 'POST') {
          return reply(200, {
            title: 'A Test Article',
            byline: 'By Someone',
            text: 'The imported article text goes here.',
            words: 6,
            source_url: 'https://example.com/article',
            note: null,
          });
        }
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('imports a URL into the paste box on the "From a web page" tab', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/read']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MeProvider>
          <ReadAnything />
        </MeProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('tab', { name: 'From a web page' }));
    const urlInput = await screen.findByPlaceholderText('https://example.com/an-article');
    await user.type(urlInput, 'https://example.com/article');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    const textarea = (await screen.findByLabelText(
      'Paste anything: an email, an article, a chapter',
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe('The imported article text goes here.'));
  });
});

describe('Read anything — Summary (v0.6, Pro)', () => {
  function stubFetch(user: User | null) {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        if (url === '/api/me' && method === 'GET') {
          return user ? reply(200, { user, profile: null }) : reply(401, { error: 'Please sign in.' });
        }
        if (url === '/api/rewrite' && method === 'POST') return reply(200, REWRITE_RESULT);
        if (url === '/api/summaries' && method === 'POST') {
          return reply(200, { bullets: ['The clock struck noon.'], summary: '- The clock struck noon.' });
        }
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function rewriteSomething() {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/read']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MeProvider>
          <ReadAnything />
        </MeProvider>
      </MemoryRouter>,
    );
    const textarea = await screen.findByLabelText('Paste anything: an email, an article, a chapter');
    await user.type(textarea, 'The clock struck noon.');
    await user.click(screen.getByRole('button', { name: 'Rewrite it' }));
    await screen.findByText(/sentences changed/);
    return user;
  }

  it('shows an upgrade nudge instead of a working Summary button for a free reader', async () => {
    stubFetch(userWith(FREE_PLAN));
    await rewriteSomething();
    expect(screen.queryByRole('button', { name: 'Summary' })).not.toBeInTheDocument();
  });

  it('does not offer Summary at all for an anonymous reader', async () => {
    stubFetch(null);
    await rewriteSomething();
    expect(screen.queryByRole('button', { name: 'Summary' })).not.toBeInTheDocument();
    expect(screen.queryByText(/AI summaries are part of Unwind Words Pro/)).not.toBeInTheDocument();
  });

  it('lets a Pro reader generate and see a labelled AI summary', async () => {
    stubFetch(userWith(PRO_PLAN));
    const user = await rewriteSomething();
    await user.click(await screen.findByRole('button', { name: 'Summary' }));
    expect(await screen.findByText('The clock struck noon.')).toBeInTheDocument();
    expect(screen.getByText(/AI summary — read the text for the details/)).toBeInTheDocument();
  });
});

describe('Read anything — define a selected word (v0.6)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        if (url === '/api/me' && method === 'GET') return reply(401, { error: 'Please sign in.' });
        if (url === '/api/rewrite' && method === 'POST') return reply(200, REWRITE_RESULT);
        if (url.startsWith('/api/define')) {
          return reply(200, {
            word: 'clock', phonetic: '/klɒk/',
            meanings: [{ pos: 'noun', definition: 'A device that measures and shows time.', example: null }],
            audio_url: null,
          });
        }
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows a Define chip when a single word is selected, and shows the definition on click', async () => {
    const user = userEvent.setup();
    // jsdom implements no layout at all, so Range has no getBoundingClientRect of its own; give
    // it a plausible on-screen size so the component doesn't treat the selection as empty.
    Range.prototype.getBoundingClientRect = () =>
      ({ top: 100, bottom: 120, left: 40, right: 80, width: 40, height: 20, x: 40, y: 100, toJSON: () => ({}) }) as DOMRect;

    render(
      <MemoryRouter initialEntries={['/read']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MeProvider>
          <ReadAnything />
        </MeProvider>
      </MemoryRouter>,
    );
    const textarea = await screen.findByLabelText('Paste anything: an email, an article, a chapter');
    await user.type(textarea, 'The clock struck noon.');
    await user.click(screen.getByRole('button', { name: 'Rewrite it' }));
    await screen.findByText(/sentences changed/);

    const wordButton = await screen.findByRole('button', { name: /^clock/ });
    const textNode = wordButton.firstChild as Text;
    const range = document.createRange();
    range.setStart(textNode, 0);
    range.setEnd(textNode, textNode.length);
    const selection = window.getSelection()!;
    act(() => {
      selection.removeAllRanges();
      selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    });

    const chip = await screen.findByRole('button', { name: 'Define “clock”' });
    await user.click(chip);

    expect(await screen.findByText('A device that measures and shows time.')).toBeInTheDocument();
    expect(screen.getByText('/klɒk/')).toBeInTheDocument();
  });
});

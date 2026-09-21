import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Landing from '../pages/Landing';
import type { SampleResponse } from '../api';

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

const SAMPLE: SampleResponse = {
  segments: [
    { t: 'text', s: 'Every night, Grandpa would wind up the clock before bed' },
    { t: 'change', s: '. The', orig: ', and', why: 'long sentence', alts: [] },
    { t: 'text', s: ' house would go quiet.' },
    { t: 'para' },
    { t: 'text', s: 'A second paragraph that should not appear in the strip.' },
  ],
  stats: { sentences: 2, sentences_changed: 1, changes: 1, load_before: 4, load_after: 2 },
  phonetic_map: [],
  cached: true,
  title: 'The Wind in the Willows',
  author: 'Kenneth Grahame',
  year: 1908,
  chapter: 'Chapter 1: The River Bank',
  source: 'https://www.gutenberg.org/ebooks/289',
};

describe('Landing', () => {
  let calls: { url: string; method: string; body: unknown }[] = [];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        calls.push({ url, method, body });

        if (url === '/api/samples/wind-in-the-willows' && method === 'GET') return reply(200, SAMPLE);
        if (url === '/api/newsletter' && method === 'POST') return reply(200, { ok: true });
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the hero pitch and both CTAs', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Landing />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: /rewritten so you can actually read them/i }),
    ).toBeInTheDocument();

    const sampleCta = screen.getByRole('link', { name: 'Try it on a sample book' });
    expect(sampleCta).toHaveAttribute('href', '/read?sample=wind-in-the-willows');

    const assessCta = screen.getByRole('link', { name: 'Which kind of reader am I?' });
    expect(assessCta).toHaveAttribute('href', '/assess');

    // Let the in-flight sample fetch settle so its state update isn't left dangling.
    await waitFor(() =>
      expect(calls.some((c) => c.url === '/api/samples/wind-in-the-willows')).toBe(true),
    );
  });

  it('loads the live before/after strip from the sample API and marks the changed words', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Landing />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(calls.some((c) => c.url === '/api/samples/wind-in-the-willows')).toBe(true),
    );

    // The original wording survives in "Before" and the rewritten wording in "After".
    await screen.findByText(', and');
    expect(screen.getByText('. The')).toBeInTheDocument();
    expect(screen.getAllByText(/Every night, Grandpa would wind up the clock before bed/)).toHaveLength(2);
    // Only the first paragraph (up to the `para` break) is shown.
    expect(screen.queryByText(/second paragraph/)).not.toBeInTheDocument();
  });

  it('posts an email to the newsletter endpoint', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Landing />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText('Your email'), 'reader@example.com');
    await user.click(screen.getByRole('button', { name: 'Notify me' }));

    await waitFor(() => expect(calls.some((c) => c.url === '/api/newsletter')).toBe(true));
    const call = calls.find((c) => c.url === '/api/newsletter')!;
    expect(call.body).toEqual({ email: 'reader@example.com', source: 'landing' });

    await screen.findByText("You're on the list. Thank you.");
  });
});

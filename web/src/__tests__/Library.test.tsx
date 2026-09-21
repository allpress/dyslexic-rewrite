import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Library from '../pages/Library';
import { MeProvider } from '../useMe';
import type { Book, User } from '../api';

const USER: User = {
  id: 'u1',
  email: 'doug@example.com',
  name: 'Doug',
  base_profile: 'default',
  onboarded: true,
  has_personal_profile: false,
  phonetic_map: 'on_demand',
  kindle_email: null,
  created_at: '2026-09-17T10:00:00Z',
};

function book(overrides: Partial<Book>): Book {
  return {
    id: 'b1',
    title: 'Treasure Island',
    author: 'Robert Louis Stevenson',
    source_name: 'treasure-island.txt',
    source_kind: 'txt',
    words: 1200,
    chapters: 3,
    status: 'ready',
    engine: 'rules',
    progress: 3,
    error: null,
    created_at: '2026-09-17T10:00:00Z',
    finished_at: '2026-09-17T10:01:00Z',
    last_opened_at: null,
    kindle_sent_at: null,
    ...overrides,
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={['/library']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MeProvider>
        <Library />
      </MeProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Library — listing', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/me') return reply(200, { user: USER, profile: null });
        if (url === '/api/books') return reply(200, [book({})]);
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  it('renders the reader’s books with status and word count', async () => {
    renderLibrary();

    expect(await screen.findByRole('heading', { name: 'Treasure Island' })).toBeInTheDocument();
    expect(screen.getByText('Robert Louis Stevenson')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText(/1,200 words/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Read' })).toHaveAttribute('href', '/library/b1');
  });

  it('shows a progress bar for a book still being rewritten', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/me') return reply(200, { user: USER, profile: null });
        if (url === '/api/books') {
          return reply(200, [book({ status: 'processing', progress: 1, chapters: 4 })]);
        }
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
    renderLibrary();

    expect(await screen.findByText('Rewriting…')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
  });
});

describe('Library — upload quota', () => {
  class FakeXHR {
    static instances: FakeXHR[] = [];
    method = '';
    url = '';
    status = 402;
    responseText = '';
    withCredentials = false;
    upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;

    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }

    send() {
      FakeXHR.instances.push(this);
      this.responseText = JSON.stringify({
        error: 'Your first book is free. Upgrade to Unwind Words Pro to add more books to your library.',
      });
      setTimeout(() => this.onload?.(), 0);
    }
  }

  beforeEach(() => {
    FakeXHR.instances = [];
    vi.stubGlobal('XMLHttpRequest', FakeXHR as unknown as typeof XMLHttpRequest);
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/me') return reply(200, { user: USER, profile: null });
        if (url === '/api/books') return reply(200, []);
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  it('shows the upgrade nudge linking to /pricing when the free-tier quota is used', async () => {
    const user = userEvent.setup();
    renderLibrary();

    await screen.findByText(/No books yet/);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['hello'], 'book.txt', { type: 'text/plain' });
    await user.upload(input, file);

    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1));
    expect(await screen.findByText(/Upgrade to Unwind Words Pro/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See Unwind Words Pro' })).toHaveAttribute('href', '/pricing');
  });
});

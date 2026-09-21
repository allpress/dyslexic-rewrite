import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Profile from '../pages/Profile';
import ReadAloudButton from '../components/ReadAloudButton';
import { MeProvider } from '../useMe';
import type { PlanSummary, ProfileSummary, User } from '../api';

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

const FREE_PLAN: PlanSummary = {
  plan: 'free',
  pro: false,
  plan_until: null,
  cancel_at_period_end: false,
  manageable: false,
};

const BASE_USER: User = {
  id: 'u1',
  email: 'doug@example.com',
  name: 'Doug',
  base_profile: 'default',
  onboarded: true,
  has_personal_profile: false,
  phonetic_map: 'on_demand',
  created_at: '2026-09-17T10:00:00Z',
  plan: FREE_PLAN,
};

const PROFILE: ProfileSummary = {
  name: 'default',
  base_profile: 'default',
  max_sentence_words: 20,
  min_zipf: 3.3,
  trigger_words: [],
  safe_words: [],
  vocabulary_size: 0,
  style: {
    median_sentence_words: 14,
    p75_sentence_words: 20,
    passive_rate: 0.05,
    clause_depth: 1.2,
    median_zipf: 4.6,
    sample_words: 0,
  },
};

describe('Profile phonetic-map mode selector', () => {
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

        if (url === '/api/me' && method === 'GET') {
          return reply(200, { user: BASE_USER, profile: PROFILE, plan: FREE_PLAN });
        }
        if (url === '/api/me' && method === 'PATCH') {
          const nextUser = { ...BASE_USER, ...(body as object) };
          return reply(200, { user: nextUser });
        }
        return reply(404, { error: `unexpected ${method} ${url}` });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the reader\'s saved mode and saves a new one via PATCH /api/me', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MeProvider>
          <Profile />
        </MeProvider>
      </MemoryRouter>,
    );

    const select = (await screen.findByRole('combobox', { name: 'Phonetic map' })) as HTMLSelectElement;
    expect(select.value).toBe('on_demand');

    await user.selectOptions(select, 'always');

    await waitFor(() => {
      const patch = calls.find((c) => c.url === '/api/me' && c.method === 'PATCH');
      expect(patch?.body).toEqual({ phonetic_map: 'always' });
    });
    expect(select.value).toBe('always');
  });
});

describe('ReadAloudButton', () => {
  class FakeUtterance {
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    rate = 1;
    constructor(public text: string) {}
  }

  let speak: ReturnType<typeof vi.fn>;
  let cancel: ReturnType<typeof vi.fn>;
  let instances: FakeUtterance[];

  beforeEach(() => {
    instances = [];
    speak = vi.fn((u: FakeUtterance) => instances.push(u));
    cancel = vi.fn();
    vi.stubGlobal('speechSynthesis', { speak, cancel });
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      vi.fn().mockImplementation((text: string) => new FakeUtterance(text)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads paragraphs one after another and stops on a second click', async () => {
    const user = userEvent.setup();
    const onFirstUse = vi.fn();
    render(<ReadAloudButton paragraphs={['First paragraph.', 'Second paragraph.']} onFirstUse={onFirstUse} />);

    const button = screen.getByRole('button', { name: 'Read aloud' });
    await user.click(button);

    expect(onFirstUse).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Stop reading aloud' })).toHaveAttribute('aria-pressed', 'true');
    expect(speak).toHaveBeenCalledTimes(1);
    expect(instances[0].text).toBe('First paragraph.');

    // Finishing the first paragraph moves on to the second automatically.
    instances[0].onend?.();
    expect(speak).toHaveBeenCalledTimes(2);
    expect(instances[1].text).toBe('Second paragraph.');

    // A second click stops it and cancels speech; using it again does not re-fire onFirstUse.
    await user.click(screen.getByRole('button', { name: 'Stop reading aloud' }));
    expect(cancel).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Read aloud' })).toHaveAttribute('aria-pressed', 'false');

    await user.click(screen.getByRole('button', { name: 'Read aloud' }));
    expect(onFirstUse).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when the browser has no speech synthesis', () => {
    vi.unstubAllGlobals();
    const { container } = render(<ReadAloudButton paragraphs={['Hello.']} />);
    expect(container).toBeEmptyDOMElement();
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import FeedbackWidget from '../components/FeedbackWidget';
import { MeProvider } from '../useMe';
import type { User } from '../api';

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

const USER: User = {
  id: 'u1',
  email: 'doug@example.com',
  name: 'Doug',
  base_profile: 'default',
  onboarded: true,
  has_personal_profile: false,
  phonetic_map: 'on_demand',
  kindle_email: null,
  plan: { plan: 'free', pro: false, plan_until: null, cancel_at_period_end: false, manageable: false },
  created_at: '2026-09-17T10:00:00Z',
};

let calls: { url: string; method: string; body: unknown }[];

function stubFetch(meResponse: { status: number; body: unknown }) {
  calls = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ url, method, body });
      if (url === '/api/me') return reply(meResponse.status, meResponse.body);
      if (url === '/api/feedback/submit' && method === 'POST') return reply(201, { id: 'f1' });
      return reply(404, { error: `unexpected ${method} ${url}` });
    }),
  );
}

function renderWidget(initialEntry = '/read') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MeProvider>
        <FeedbackWidget />
      </MeProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('FeedbackWidget', () => {
  beforeEach(() => {
    stubFetch({ status: 401, body: { error: 'Please sign in.' } });
  });

  it('is hidden on the timed /test route', () => {
    renderWidget('/test');
    expect(screen.queryByRole('button', { name: 'Feedback' })).not.toBeInTheDocument();
  });

  it('opens the panel and shows the kind chips, message box and rating scale', async () => {
    const user = userEvent.setup();
    renderWidget();

    await user.click(await screen.findByRole('button', { name: 'Feedback' }));

    expect(screen.getByRole('dialog', { name: 'Send feedback' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Bug' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Idea' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Praise' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Question' })).toBeInTheDocument();
    expect(screen.getByLabelText(/What.s on your mind/)).toBeInTheDocument();
    expect(screen.getByLabelText('Your email (optional, if you’d like a reply)')).toBeInTheDocument();
  });

  it('requires a message before sending', async () => {
    const user = userEvent.setup();
    renderWidget();
    await user.click(await screen.findByRole('button', { name: 'Feedback' }));

    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/say a little/i);
    expect(calls.some((c) => c.url === '/api/feedback/submit')).toBe(false);
  });

  it('submits with kind, message, rating, page and context, and shows the thanks message', async () => {
    const user = userEvent.setup();
    renderWidget('/read');
    await user.click(await screen.findByRole('button', { name: 'Feedback' }));

    await user.click(screen.getByRole('radio', { name: 'Idea' }));
    await user.type(screen.getByLabelText(/What.s on your mind/), 'A dark mode would help a lot');
    await user.click(screen.getByRole('button', { name: '4' }));
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(calls.some((c) => c.url === '/api/feedback/submit')).toBe(true));
    const call = calls.find((c) => c.url === '/api/feedback/submit')!;
    const body = call.body as {
      kind: string;
      message: string;
      rating: number;
      page: string;
      context: Record<string, unknown>;
    };
    expect(body.kind).toBe('idea');
    expect(body.message).toBe('A dark mode would help a lot');
    expect(body.rating).toBe(4);
    expect(body.page).toBe('/read');
    expect(body.context).toHaveProperty('app_version');
    expect(body.context).toHaveProperty('viewport');
    expect(body.context).toHaveProperty('user_agent');

    expect(await screen.findByText('Thanks — we read every one.')).toBeInTheDocument();
  });

  it('does not ask for an email when signed in', async () => {
    stubFetch({ status: 200, body: { user: USER, profile: null } });
    const user = userEvent.setup();
    renderWidget();

    await user.click(await screen.findByRole('button', { name: 'Feedback' }));

    expect(screen.queryByLabelText(/Your email/)).not.toBeInTheDocument();
  });
});

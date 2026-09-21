import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Profile from '../pages/Profile';
import { MeProvider } from '../useMe';
import type { PlanSummary, ProfileSummary, User } from '../api';

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

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
    created_at: '2026-09-17T10:00:00Z',
    plan,
  };
}

const FREE_PLAN: PlanSummary = {
  plan: 'free',
  pro: false,
  plan_until: null,
  cancel_at_period_end: false,
  manageable: false,
};

const PRO_PLAN: PlanSummary = {
  plan: 'pro',
  pro: true,
  plan_until: '2026-11-01T00:00:00Z',
  cancel_at_period_end: false,
  manageable: true,
};

let currentUser: User;

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/me') return reply(200, { user: currentUser, profile: PROFILE, plan: currentUser.plan });
      if (url === '/api/battery/latest') return reply(200, { run: null });
      return reply(404, { error: `unexpected ${url}` });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderProfile(initialEntry = '/profile') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MeProvider>
        <Profile />
      </MeProvider>
    </MemoryRouter>,
  );
}

describe('Profile: Account & plan', () => {
  it('shows Free with an upgrade link when the reader has no plan', async () => {
    currentUser = userWith(FREE_PLAN);
    renderProfile();

    expect(await screen.findByRole('heading', { name: 'Account & plan' })).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upgrade to Pro' })).toHaveAttribute('href', '/pricing');
  });

  it('shows Pro with a renewal date and a manage-billing button', async () => {
    currentUser = userWith(PRO_PLAN);
    renderProfile();

    expect(await screen.findByText('Pro')).toBeInTheDocument();
    expect(screen.getByText('Renews')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Manage billing' })).toBeInTheDocument();
  });

  it('shows a thank-you banner after ?upgraded=1 and clears it from the URL', async () => {
    currentUser = userWith(PRO_PLAN);
    renderProfile('/profile?upgraded=1');

    expect(await screen.findByRole('status')).toHaveTextContent('Thanks for upgrading to Pro');
  });
});

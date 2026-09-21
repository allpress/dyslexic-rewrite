import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Pricing from '../pages/Pricing';
import { MeProvider } from '../useMe';
import type { PlanSummary, User } from '../api';

const FREE_PLAN: PlanSummary = {
  plan: 'free',
  pro: false,
  plan_until: null,
  cancel_at_period_end: false,
  manageable: false,
};

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
  plan: FREE_PLAN,
};

const PLANS_BODY = {
  monthly: { price_id: 'price_monthly_test', amount: 500, currency: 'usd', interval: 'month' },
  yearly: { price_id: 'price_yearly_test', amount: 3900, currency: 'usd', interval: 'year' },
  configured: true,
};

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

let calls: { url: string; method: string; body: unknown }[] = [];
let meStatus = 401;

beforeEach(() => {
  calls = [];
  meStatus = 401;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ url, method, body });

      if (url === '/api/me' && method === 'GET') {
        return meStatus === 200
          ? reply(200, { user: USER, profile: null, plan: FREE_PLAN })
          : reply(401, { error: 'Not signed in' });
      }
      if (url === '/api/billing/plans' && method === 'GET') return reply(200, PLANS_BODY);
      if (url === '/api/billing/checkout' && method === 'POST') {
        return reply(200, { url: 'https://checkout.stripe.com/test-session' });
      }
      return reply(404, { error: `unexpected ${method} ${url}` });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPricing() {
  return render(
    <MemoryRouter initialEntries={['/pricing']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MeProvider>
        <Routes>
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/signin" element={<h1>Sign in</h1>} />
        </Routes>
      </MeProvider>
    </MemoryRouter>,
  );
}

describe('Pricing page', () => {
  it('renders both plan cards with amounts from /api/billing/plans and toggles interval', async () => {
    renderPricing();

    expect(await screen.findByRole('heading', { name: 'Free' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pro' })).toBeInTheDocument();

    // Monthly is the default toggle state.
    expect(await screen.findByText('$5')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Yearly' }));

    expect(await screen.findByText('$39')).toBeInTheDocument();
  });

  it('sends a signed-out visitor to sign in with a return trip back to /pricing', async () => {
    renderPricing();
    await screen.findByText('$5');

    const goPro = screen.getByRole('link', { name: 'Go Pro' });
    expect(goPro).toHaveAttribute('href', '/signin?next=/pricing');
  });

  it('starts checkout for a signed-in visitor', async () => {
    meStatus = 200;
    // jsdom doesn't implement navigation; swallow the assignment so the test doesn't crash.
    Object.defineProperty(window, 'location', { value: { href: '' }, writable: true });
    renderPricing();
    await screen.findByText('$5');

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Go Pro' }));

    await waitFor(() => {
      const checkout = calls.find((c) => c.url === '/api/billing/checkout');
      expect(checkout?.body).toEqual({ interval: 'monthly' });
    });
    expect(window.location.href).toBe('https://checkout.stripe.com/test-session');
  });
});

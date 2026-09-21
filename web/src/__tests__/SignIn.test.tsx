import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SignIn from '../pages/SignIn';
import { MeProvider } from '../useMe';
import type { User } from '../api';

const USER: User = {
  id: 'u1',
  email: 'doug@example.com',
  name: '',
  base_profile: 'default',
  onboarded: false,
  has_personal_profile: false,
  phonetic_map: 'on_demand',
  kindle_email: null,
  created_at: '2026-09-17T10:00:00Z',
};

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

let calls: { url: string; body: unknown }[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });

      if (url === '/api/me') return reply(401, { error: 'Not signed in' });
      if (url === '/api/auth/request-code') return reply(200, { ok: true, dev_code: '314159' });
      if (url === '/api/auth/verify') {
        const body = JSON.parse(String(init?.body ?? '{}'));
        if (body.code !== '314159') return reply(400, { error: 'That code has expired.' });
        return reply(200, { user: USER });
      }
      return reply(404, { error: `unexpected ${url}` });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSignIn() {
  return render(
    <MemoryRouter
      initialEntries={['/signin']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <MeProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/onboarding" element={<h1>Onboarding</h1>} />
          <Route path="/test" element={<h1>Reading test</h1>} />
        </Routes>
      </MeProvider>
    </MemoryRouter>,
  );
}

describe('sign-in code flow', () => {
  it('asks for a code, shows the dev code, then verifies and moves on', async () => {
    const user = userEvent.setup();
    renderSignIn();

    await user.type(screen.getByLabelText('Your email'), 'doug@example.com');
    await user.click(screen.getByRole('button', { name: 'Send me a code' }));

    // Dev-only code is shown inline because the response carried dev_code.
    expect(await screen.findByText('314159')).toBeInTheDocument();
    expect(calls.find((c) => c.url === '/api/auth/request-code')?.body).toEqual({
      email: 'doug@example.com',
    });

    await user.type(screen.getByLabelText('Your 6-digit code'), '314159');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    // user.onboarded is false, so the app goes to onboarding.
    expect(await screen.findByRole('heading', { name: 'Onboarding' })).toBeInTheDocument();
  });

  it('shows the server error when the code is wrong', async () => {
    const user = userEvent.setup();
    renderSignIn();

    await user.type(screen.getByLabelText('Your email'), 'doug@example.com');
    await user.click(screen.getByRole('button', { name: 'Send me a code' }));
    await user.type(await screen.findByLabelText('Your 6-digit code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('That code has expired.');
  });
});

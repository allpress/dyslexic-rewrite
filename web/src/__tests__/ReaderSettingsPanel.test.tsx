import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Reader from '../components/Reader';
import ReaderSettingsPanel from '../components/reader/ReaderSettingsPanel';
import { MeProvider } from '../useMe';
import { DEFAULT_READER_PREFS, readerPrefsStore } from '../lib/readerPrefs';
import type { PlanSummary, Segment, User } from '../api';

const SEGMENTS: Segment[] = [{ t: 'text', s: 'Every night Grandpa would wind the clock before bed.' }];

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

const PLAN: PlanSummary = { plan: 'free', pro: false, plan_until: null, cancel_at_period_end: false, manageable: false };

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
  plan: PLAN,
};

beforeEach(() => {
  readerPrefsStore.replace({ ...DEFAULT_READER_PREFS });
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanelAndReader() {
  return render(
    <MeProvider>
      <ReaderSettingsPanel variant="profile" />
      <Reader segments={SEGMENTS} showMarks={false} tripped={new Set()} onToggleWord={() => {}} />
    </MeProvider>,
  );
}

describe('ReaderSettingsPanel (signed out)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => reply(401, { error: 'Please sign in.' })));
  });

  it('changes a CSS variable on the reader container and stores the change in localStorage', async () => {
    const { container } = renderPanelAndReader();
    await screen.findByLabelText('Text size');

    const reader = container.querySelector('.reader') as HTMLElement;
    expect(reader.style.getPropertyValue('--reader-font-size')).toBe('20px');

    const slider = screen.getByLabelText('Text size') as HTMLInputElement;
    fireChange(slider, '28');

    expect(reader.style.getPropertyValue('--reader-font-size')).toBe('28px');

    const stored = JSON.parse(localStorage.getItem('reader:prefs:v1') || '{}');
    expect(stored.font_size_px).toBe(28);
  });

  it('never calls PUT /api/me/layout while signed out', async () => {
    renderPanelAndReader();
    await screen.findByLabelText('Text size');
    const slider = screen.getByLabelText('Text size') as HTMLInputElement;
    fireChange(slider, '24');

    await new Promise((r) => setTimeout(r, 500));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    const putCalls = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'PUT');
    expect(putCalls).toHaveLength(0);
  });
});

describe('ReaderSettingsPanel (signed in)', () => {
  let putBodies: unknown[];

  beforeEach(() => {
    putBodies = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === '/api/me') return reply(200, { user: USER, profile: null, plan: PLAN });
        if (url === '/api/me/layout' && (!init || init.method === undefined)) return reply(200, { layout: {} });
        if (url === '/api/me/layout' && init?.method === 'PUT') {
          putBodies.push(JSON.parse(String(init.body)));
          return reply(200, { layout: { ...DEFAULT_READER_PREFS, ...JSON.parse(String(init.body)) } });
        }
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  it('saves a changed setting to the profile via PUT /api/me/layout, debounced', async () => {
    renderPanelAndReader();
    await screen.findByLabelText('Text size');

    const slider = screen.getByLabelText('Text size') as HTMLInputElement;
    fireChange(slider, '26');

    await waitFor(() => expect(putBodies.length).toBeGreaterThan(0));
    expect(putBodies[0]).toMatchObject({ font_size_px: 26 });
  });

  it('hydrates from the signed-in reader’s saved layout on mount', async () => {
    (window.fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/me') return reply(200, { user: USER, profile: null, plan: PLAN });
        if (url === '/api/me/layout') return reply(200, { layout: { font_size_px: 30, theme: 'sepia' } });
        return reply(404, { error: `unexpected ${url}` });
      },
    );
    const { container } = renderPanelAndReader();

    await waitFor(() => {
      const reader = container.querySelector('.reader') as HTMLElement;
      expect(reader.style.getPropertyValue('--reader-font-size')).toBe('30px');
    });
    expect(container.querySelector('.reader')).toHaveAttribute('data-theme', 'sepia');
  });
});

/** `userEvent.clear`+`type` doesn't work well on `<input type="range">`; drive it directly. */
function fireChange(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

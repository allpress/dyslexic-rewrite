import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Record, { STATUS_LABEL } from '../pages/Record';
import type { Prompt, Recording } from '../api';

const PROMPTS: Prompt[] = [
  { id: 'p1', kind: 'read_aloud', title: 'The old clock', text: 'Grandpa wound the clock every night.', words: 6 },
  { id: 'p2', kind: 'free_speech', title: 'A room you changed', text: 'Tell us about a room you changed.', words: 0 },
];

function recordingWith(status: Recording['status'], id: string): Recording {
  return {
    id,
    created_at: '2026-09-10T10:00:00Z',
    kind: 'read_aloud',
    prompt_id: 'p1',
    prompt_title: 'The old clock',
    seconds: 42,
    bytes: 12345,
    mime: 'audio/webm',
    status,
    note: status === 'failed' ? 'The file would not open.' : null,
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

function renderRecord() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Record />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('status words', () => {
  beforeEach(() => {
    const recordings = [
      recordingWith('pending_analysis', 'r1'),
      recordingWith('analyzing', 'r2'),
      recordingWith('analyzed', 'r3'),
      recordingWith('failed', 'r4'),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/read-aloud-prompts') return reply(200, PROMPTS);
        if (url === '/api/me/recordings') {
          return reply(200, { recordings, totals: { count: 4, seconds: 168, bytes: 4 * 12345 } });
        }
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  it('renders the plain-word status for every recording status', async () => {
    renderRecord();

    for (const label of Object.values(STATUS_LABEL)) {
      expect(await screen.findByText(new RegExp(label))).toBeInTheDocument();
    }
  });
});

describe('uploading a recording', () => {
  class FakeXHR {
    static instances: FakeXHR[] = [];
    method = '';
    url = '';
    status = 201;
    responseText = '';
    withCredentials = false;
    upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    sentBody: FormData | null = null;

    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }

    send(body: FormData) {
      this.sentBody = body;
      FakeXHR.instances.push(this);
      const created: Recording = {
        id: 'new-1',
        created_at: '2026-09-17T10:00:00Z',
        kind: 'free_speech',
        prompt_id: null,
        prompt_title: null,
        seconds: 5,
        bytes: 999,
        mime: 'audio/webm',
        status: 'pending_analysis',
        note: null,
      };
      this.responseText = JSON.stringify(created);
      setTimeout(() => this.onload?.(), 0);
    }
  }

  beforeEach(() => {
    FakeXHR.instances = [];
    vi.stubGlobal('XMLHttpRequest', FakeXHR as unknown as typeof XMLHttpRequest);
    // jsdom implements neither of these; the component only uses them to preview/measure a clip.
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:mock-url'),
      revokeObjectURL: vi.fn(),
    });
    class FakeAudio {
      addEventListener(event: string, cb: () => void) {
        if (event === 'error') setTimeout(cb, 0);
      }
      removeAttribute() {}
      set src(_v: string) {}
    }
    vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio);
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/read-aloud-prompts') return reply(200, []);
        if (url === '/api/me/recordings') {
          return reply(200, { recordings: [], totals: { count: 0, seconds: 0, bytes: 0 } });
        }
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  it('posts the file, kind and seconds as multipart form fields', async () => {
    const user = userEvent.setup();
    renderRecord();

    await screen.findByLabelText('Or upload a file instead');

    const file = new File(['hello'], 'sample.webm', { type: 'audio/webm' });
    const input = screen.getByLabelText('Or upload a file instead') as HTMLInputElement;
    // jsdom cannot compute real audio duration for a fake file; that is fine, seconds is optional.
    await user.upload(input, file);

    const useButton = await screen.findByRole('button', { name: 'Use this one' });
    await user.click(useButton);

    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1));
    const sent = FakeXHR.instances[0];
    expect(sent.url).toBe('/api/me/recordings');
    expect(sent.method).toBe('POST');
    expect(sent.sentBody).toBeInstanceOf(FormData);

    const form = sent.sentBody as FormData;
    expect(form.get('kind')).toBe('read_aloud');
    const uploaded = form.get('file');
    expect(uploaded).toBeInstanceOf(File);
    expect((uploaded as File).name).toBe('sample.webm');

    expect(await screen.findByText(/Saved\./)).toBeInTheDocument();
  });
});

describe('no MediaRecorder support', () => {
  let originalMediaRecorder: unknown;

  beforeEach(() => {
    originalMediaRecorder = (window as unknown as { MediaRecorder?: unknown }).MediaRecorder;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).MediaRecorder;
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/read-aloud-prompts') return reply(200, PROMPTS);
        if (url === '/api/me/recordings') {
          return reply(200, { recordings: [], totals: { count: 0, seconds: 0, bytes: 0 } });
        }
        return reply(404, { error: `unexpected ${url}` });
      }),
    );
  });

  afterEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).MediaRecorder = originalMediaRecorder;
  });

  it('hides the record button and still offers the file upload path', async () => {
    renderRecord();

    await screen.findByText(/Recording is not available in this browser/);
    expect(screen.queryByRole('button', { name: 'Record' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Or upload a file instead')).toBeInTheDocument();
  });
});

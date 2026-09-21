import { afterEach, describe, expect, it, vi } from 'vitest';
import { authHeaders, mapError, RewriteApiError, rewrite } from '../src/lib/api';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('authHeaders', () => {
  it('omits Authorization when there is no token', () => {
    expect(authHeaders(null)).toEqual({ 'Content-Type': 'application/json' });
    expect(authHeaders('')).toEqual({ 'Content-Type': 'application/json' });
    expect(authHeaders('   ')).toEqual({ 'Content-Type': 'application/json' });
  });

  it('sends Bearer uw_... when a token is set', () => {
    expect(authHeaders('uw_abc123')).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer uw_abc123',
    });
  });

  it('trims whitespace around a pasted token', () => {
    expect(authHeaders('  uw_abc123  ').Authorization).toBe('Bearer uw_abc123');
  });
});

describe('mapError', () => {
  it('maps 402 (pro_required) to a quota error linking to the upgrade path', () => {
    const info = mapError('https://unwindwords.com', 402, {
      error: 'pro_required',
      message: 'This feature is part of Unwind Words Pro.',
      upgrade: '/pricing',
    });
    expect(info.kind).toBe('quota');
    expect(info.message).toBe('This feature is part of Unwind Words Pro.');
    expect(info.actionUrl).toBe('https://unwindwords.com/pricing');
  });

  it('maps 413 to a quota error even with no body', () => {
    const info = mapError('https://unwindwords.com/', 413, null);
    expect(info.kind).toBe('quota');
    expect(info.actionUrl).toBe('https://unwindwords.com/pricing');
  });

  it('maps a 400 paste-limit message to quota, not generic', () => {
    const info = mapError('https://unwindwords.com', 400, {
      error: "That's a lot at once — try up to 20,000 characters.",
    });
    expect(info.kind).toBe('quota');
    expect(info.actionUrl).toBe('https://unwindwords.com/pricing');
  });

  it('maps a plain 400 to generic', () => {
    const info = mapError('https://unwindwords.com', 400, { error: 'Paste some text first.' });
    expect(info.kind).toBe('generic');
    expect(info.message).toBe('Paste some text first.');
  });

  it('maps 401 to auth', () => {
    expect(mapError('https://unwindwords.com', 401, null).kind).toBe('auth');
  });

  it('maps status 0 to network', () => {
    expect(mapError('https://unwindwords.com', 0, null).kind).toBe('network');
  });

  it('maps 5xx to server', () => {
    expect(mapError('https://unwindwords.com', 500, null).kind).toBe('server');
    expect(mapError('https://unwindwords.com', 503, null).kind).toBe('server');
  });
});

describe('rewrite', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the Authorization header and returns the parsed response on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { segments: [{ t: 'text', s: 'hi' }], stats: {}, phonetic_map: [], cached: false }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await rewrite({ apiBase: 'https://unwindwords.com', token: 'uw_xyz', text: 'hi' });

    expect(result.segments).toEqual([{ t: 'text', s: 'hi' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://unwindwords.com/api/rewrite');
    expect(init.headers.Authorization).toBe('Bearer uw_xyz');
    expect(JSON.parse(init.body)).toEqual({ text: 'hi' });
  });

  it('omits Authorization when there is no token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], stats: {}, phonetic_map: [], cached: false }));
    vi.stubGlobal('fetch', fetchMock);

    await rewrite({ apiBase: 'https://unwindwords.com', token: null, text: 'hi' });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it('strips a trailing slash from apiBase', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], stats: {}, phonetic_map: [], cached: false }));
    vi.stubGlobal('fetch', fetchMock);

    await rewrite({ apiBase: 'https://unwindwords.com/', token: null, text: 'hi' });

    expect(fetchMock.mock.calls[0][0]).toBe('https://unwindwords.com/api/rewrite');
  });

  it('throws a RewriteApiError with the mapped error on a non-2xx response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { error: 'nope' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(rewrite({ apiBase: 'https://unwindwords.com', token: 'bad', text: 'hi' })).rejects.toMatchObject({
      status: 401,
      info: { kind: 'auth' },
    });
  });

  it('throws a network RewriteApiError when fetch itself rejects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    );

    let caught: unknown;
    try {
      await rewrite({ apiBase: 'https://unwindwords.com', token: null, text: 'hi' });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(RewriteApiError);
    expect((caught as RewriteApiError).info.kind).toBe('network');
  });

  it('re-throws AbortError instead of mapping it to a network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')),
    );

    await expect(rewrite({ apiBase: 'https://unwindwords.com', token: null, text: 'hi' })).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});

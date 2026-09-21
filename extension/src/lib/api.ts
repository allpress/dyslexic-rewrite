/**
 * Thin client for POST /api/rewrite (see server/API.md), used by the content script.
 *
 * Unlike web/src/api.ts, this never sends cookies — the extension runs on a third-party page's
 * origin, which has no unwindwords.com session cookie to send anyway. It authenticates with a
 * personal token (server/tokens.py, server/API.md "API tokens (v0.6)") sent as
 * `Authorization: Bearer uw_...` when the reader has pasted one into the popup; with no token,
 * `/api/rewrite` still works anonymously under the free quota.
 */

import type { RewriteResponse } from './types';

export type ApiErrorKind = 'quota' | 'auth' | 'network' | 'server' | 'generic';

export interface ApiErrorInfo {
  kind: ApiErrorKind;
  message: string;
  /** Present for `quota` errors: a page on the API's own site worth linking to. */
  actionUrl?: string;
  actionLabel?: string;
}

export class RewriteApiError extends Error {
  status: number;
  info: ApiErrorInfo;
  constructor(status: number, info: ApiErrorInfo) {
    super(info.message);
    this.name = 'RewriteApiError';
    this.status = status;
    this.info = info;
  }
}

/** Build the request headers for an authenticated call. Exported so tests can assert on it
 * directly without needing to intercept a real fetch. */
export function authHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token && token.trim()) headers.Authorization = `Bearer ${token.trim()}`;
  return headers;
}

function normaliseBase(apiBase: string): string {
  return apiBase.trim().replace(/\/+$/, '');
}

/**
 * Turn a non-2xx response (or a thrown network error) into one of a small set of kinds the
 * overlay knows how to explain plainly. `apiBase` is used to build the /pricing link for a
 * quota-exceeded response, since that page lives on the API's own host, not the extension's.
 */
export function mapError(apiBase: string, status: number, body: unknown): ApiErrorInfo {
  const base = normaliseBase(apiBase);
  const bodyMessage =
    body && typeof body === 'object' && 'message' in body && typeof (body as { message: unknown }).message === 'string'
      ? (body as { message: string }).message
      : body && typeof body === 'object' && 'error' in body && typeof (body as { error: unknown }).error === 'string'
        ? (body as { error: string }).error
        : null;

  if (status === 402 || status === 413) {
    const upgrade =
      body && typeof body === 'object' && 'upgrade' in body && typeof (body as { upgrade: unknown }).upgrade === 'string'
        ? (body as { upgrade: string }).upgrade
        : '/pricing';
    return {
      kind: 'quota',
      message: bodyMessage || "That's more than the free plan allows at once.",
      actionUrl: `${base}${upgrade}`,
      actionLabel: 'See Unwind Words Pro',
    };
  }
  if (status === 400 && bodyMessage && /characters|a lot at once/i.test(bodyMessage)) {
    return {
      kind: 'quota',
      message: bodyMessage,
      actionUrl: `${base}/pricing`,
      actionLabel: 'See Unwind Words Pro',
    };
  }
  if (status === 401) {
    return {
      kind: 'auth',
      message: 'That token was not accepted. Check it in the extension settings, or remove it to use the free plan.',
    };
  }
  if (status === 0) {
    return {
      kind: 'network',
      message: "Couldn't reach Unwind Words. Check your connection and try again.",
    };
  }
  if (status >= 500) {
    return {
      kind: 'server',
      message: 'Unwind Words is having trouble right now. Try again in a moment.',
    };
  }
  return {
    kind: 'generic',
    message: bodyMessage || `Something went wrong (${status}).`,
  };
}

export interface RewriteRequest {
  apiBase: string;
  token: string | null;
  text: string;
  /** Aborts the underlying fetch, e.g. if the reader closes the overlay mid-request. */
  signal?: AbortSignal;
}

export async function rewrite({ apiBase, token, text, signal }: RewriteRequest): Promise<RewriteResponse> {
  const base = normaliseBase(apiBase);
  let res: Response;
  try {
    res = await fetch(`${base}/api/rewrite`, {
      method: 'POST',
      headers: authHeaders(token),
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new RewriteApiError(0, mapError(apiBase, 0, null));
  }

  let payload: unknown = null;
  try {
    const raw = await res.text();
    payload = raw ? JSON.parse(raw) : null;
  } catch {
    payload = null;
  }

  if (!res.ok) {
    throw new RewriteApiError(res.status, mapError(apiBase, res.status, payload));
  }
  return payload as RewriteResponse;
}

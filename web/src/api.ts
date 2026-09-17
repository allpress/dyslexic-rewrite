/**
 * Typed client for the JSON API described in ../../server/API.md.
 *
 * Base: same origin, prefix `/api`. Auth is a signed `session` cookie set by
 * POST /api/auth/verify, so every request sends credentials.
 * Errors come back as {"error": "message"} with a 4xx status.
 */

export type BaseProfile = 'default' | 'phonological' | 'visual' | 'attention';

export interface User {
  id: string;
  email: string;
  name: string;
  base_profile: BaseProfile;
  onboarded: boolean;
  has_personal_profile: boolean;
  created_at: string;
}

export interface StyleNumbers {
  median_sentence_words: number;
  p75_sentence_words: number;
  passive_rate: number;
  clause_depth: number;
  median_zipf: number;
  sample_words: number;
}

export interface ProfileSummary {
  name: string;
  base_profile: BaseProfile;
  max_sentence_words: number;
  min_zipf: number;
  trigger_words: string[];
  safe_words: string[];
  vocabulary_size: number;
  style: StyleNumbers;
}

/**
 * StyleReport is "the JSON of dyslexic_rewrite.learn.StyleReport (all numeric
 * rates + small word-count maps)" — the exact key set is not pinned by API.md,
 * so it is typed loosely and rendered by looking for known keys.
 */
export type StyleReport = Record<string, number | Record<string, number> | string | null>;

export interface PassageInfo {
  id: string;
  slug: string;
  title: string;
  words: number;
  level: string;
  pair: string;
}

export type Segment =
  | { t: 'text'; s: string }
  | { t: 'change'; s: string; orig: string; why: string; alts: string[] }
  | { t: 'note'; s: string; why: string; hint: string }
  | { t: 'para' }
  | { t: 'heading'; s: string };

export interface Question {
  id: string;
  prompt: string;
  options: string[];
}

export interface ItemResult {
  seconds: number;
  wpm: number;
  correct: number;
  total: number;
  ease: number;
  tripped: string[];
  recorded_at: string;
}

export type Condition = 'original' | 'rewritten';

export interface TestItem {
  index: 0 | 1;
  passage_id: string;
  title: string;
  condition: Condition;
  words: number;
  segments: Segment[];
  questions: Question[];
  result: ItemResult | null;
}

export interface Test {
  id: string;
  pair: string;
  created_at: string;
  completed: boolean;
  items: TestItem[];
}

export interface TestSummaryItem {
  condition: Condition;
  title: string;
  wpm: number;
  correct: number;
  total: number;
  ease: number;
}

export interface TestSummary {
  id: string;
  pair: string;
  created_at: string;
  completed: boolean;
  items: TestSummaryItem[];
}

export interface ConditionTotals {
  wpm: number;
  comprehension: number;
  n: number;
}

export interface ResultsResponse {
  tests: TestSummary[];
  totals: { original: ConditionTotals; rewritten: ConditionTotals };
}

export interface RewriteStats {
  sentences: number;
  sentences_changed: number;
  changes: number;
  load_before: number;
  load_after: number;
}

export interface RewriteResponse {
  segments: Segment[];
  stats: RewriteStats;
}

export interface MeResponse {
  user: User;
  profile: ProfileSummary | null;
}

export interface FinishBody {
  seconds: number;
  answers: Record<string, number>;
  tripped: string[];
  ease: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

/** Fires whenever any request comes back 401, so the app can bounce to /signin. */
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  onUnauthorized = fn;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
  });

  let payload: unknown = null;
  const raw = await res.text();
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = null;
    }
  }

  if (!res.ok) {
    const message =
      (payload && typeof payload === 'object' && 'error' in payload
        ? String((payload as { error: unknown }).error)
        : '') || `Something went wrong (${res.status}).`;
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, message);
  }

  return payload as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

/* ---------------------------------------------------------------- auth */

export const requestCode = (email: string) =>
  post<{ ok: true; dev_code?: string }>('/auth/request-code', { email });

export const verifyCode = (email: string, code: string) =>
  post<{ user: User }>('/auth/verify', { email, code });

export const logout = () => post<{ ok: true }>('/auth/logout');

/* ------------------------------------------------------------------ me */

export const getMe = () => request<MeResponse>('/me');

export const patchMe = (patch: { name?: string; base_profile?: BaseProfile; onboarded?: boolean }) =>
  request<{ user: User }>('/me', { method: 'PATCH', body: JSON.stringify(patch) });

export const postWritingSample = (text: string) =>
  post<{ style: StyleReport; profile: ProfileSummary }>('/me/writing-sample', { text });

export const postTriggers = (body: { add?: string[]; remove?: string[]; safe?: string[] }) =>
  post<{ profile: ProfileSummary }>('/me/triggers', body);

export const deleteMe = () => request<{ ok: true }>('/me', { method: 'DELETE' });

/* ------------------------------------------------------------ passages */

export const getPassages = () => request<PassageInfo[]>('/passages');

/* --------------------------------------------------------------- tests */

export const createTest = (pair?: string) => post<Test>('/tests', pair ? { pair } : {});

export const getTest = (id: string) => request<Test>(`/tests/${encodeURIComponent(id)}`);

export const startItem = (testId: string, index: number) =>
  post<{ started_at: string }>(`/tests/${encodeURIComponent(testId)}/items/${index}/start`);

export const finishItem = (testId: string, index: number, body: FinishBody) =>
  post<ItemResult>(`/tests/${encodeURIComponent(testId)}/items/${index}/finish`, body);

export const getResults = () => request<ResultsResponse>('/results');

/* ------------------------------------------------------- read anything */

export const rewrite = (text: string) => post<RewriteResponse>('/rewrite', { text });

export const postFeedback = (body: { tripped: string[]; safe?: string[] }) =>
  post<{ profile: ProfileSummary }>('/feedback', body);

/* -------------------------------------------------------------- health */

export const getHealth = () => request<{ ok: true; version: string }>('/health');

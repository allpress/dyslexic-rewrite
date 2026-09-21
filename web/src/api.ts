/**
 * Typed client for the JSON API described in ../../server/API.md.
 *
 * Base: same origin, prefix `/api`. Auth is a signed `session` cookie set by
 * POST /api/auth/verify, so every request sends credentials.
 * Errors come back as {"error": "message"} with a 4xx status.
 */

export type BaseProfile = 'default' | 'phonological' | 'visual' | 'attention';

/**
 * Reader's phonetic-map preference: 'off' never shows a respelling, 'on_demand' shows one only
 * once the word is tapped/hovered/focused, 'always' pins the profile's "always" entries visible
 * and leaves the rest on-demand.
 */
export type PhoneticMapMode = 'off' | 'on_demand' | 'always';

export interface User {
  id: string;
  email: string;
  name: string;
  base_profile: BaseProfile;
  onboarded: boolean;
  has_personal_profile: boolean;
  phonetic_map: PhoneticMapMode;
  /** Where "Send to Kindle" (see Library, v0.5) emails a book's EPUB. Null until set. */
  kindle_email: string | null;
  created_at: string;
  /** Billing (v0.5) -- see PlanSummary below. */
  plan: PlanSummary;
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

/**
 * A respelling for one word (e.g. "in-TEN-shun", "WYND" vs "WIND"). `start`/`end` are character
 * offsets into the *served* text — every segment's `s` concatenated in order, with each `para`
 * break counted as two newlines. See `servedTextSpans` in components/Reader.tsx.
 */
export interface PhoneticMapEntry {
  start: number;
  end: number;
  word: string;
  respell: string;
  hint: string | null;
  kind: string;
  always: boolean;
}

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
  /** The reader's phonetic-map mode at the moment this attempt was recorded. */
  phonetic_map: PhoneticMapMode;
  /** Whether the reader turned on read-aloud during this attempt. */
  read_aloud: boolean;
}

export type Condition = 'original' | 'rewritten';

export interface TestItem {
  index: 0 | 1;
  passage_id: string;
  title: string;
  condition: Condition;
  words: number;
  segments: Segment[];
  phonetic_map: PhoneticMapEntry[];
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
  phonetic_map: PhoneticMapEntry[];
  /** Whether this came from the rewrite cache instead of being freshly computed. */
  cached: boolean;
}

/** A public-domain excerpt listed by GET /api/samples ("Show me an example"). */
export interface SampleInfo {
  slug: string;
  title: string;
  author: string;
  year: number;
  chapter: string;
  /** The Project Gutenberg ebook page for this title. */
  source: string;
  blurb: string;
  words: number;
}

export interface SampleResponse extends RewriteResponse {
  title: string;
  author: string;
  year: number;
  chapter: string;
  source: string;
}

export interface MeResponse {
  user: User;
  profile: ProfileSummary | null;
  /** Same value as `user.plan` -- kept at the top level too since that's how server/API.md
   * documents `GET /api/me`'s billing addition. Optional here (unlike on `User`) so call sites
   * that only ever had `{user, profile}` to hand -- after a PATCH, not a fresh GET -- don't need
   * a `plan` of their own; read `user.plan` instead, which is always present. */
  plan?: PlanSummary;
}

export interface FinishBody {
  seconds: number;
  answers: Record<string, number>;
  tripped: string[];
  ease: number;
  /** Set true when the reader turned on read-aloud during this attempt. */
  read_aloud?: boolean;
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

export const patchMe = (patch: {
  name?: string;
  base_profile?: BaseProfile;
  onboarded?: boolean;
  phonetic_map?: PhoneticMapMode;
  kindle_email?: string;
}) => request<{ user: User }>('/me', { method: 'PATCH', body: JSON.stringify(patch) });

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

/* -------------------------------------------------------------- sample books */

export const getSamples = () => request<SampleInfo[]>('/samples');

export const getSample = (slug: string) => request<SampleResponse>(`/samples/${encodeURIComponent(slug)}`);

/* ------------------------------------------------------ voice recordings */

export type RecordingKind = 'read_aloud' | 'free_speech';

export interface Prompt {
  id: string;
  kind: RecordingKind;
  title: string;
  text: string;
  words: number;
}

export type RecordingStatus = 'pending_analysis' | 'analyzing' | 'analyzed' | 'failed';

export interface Recording {
  id: string;
  created_at: string;
  kind: RecordingKind;
  prompt_id: string | null;
  prompt_title: string | null;
  seconds: number | null;
  bytes: number;
  mime: string;
  status: RecordingStatus;
  note: string | null;
}

export interface RecordingTotals {
  count: number;
  seconds: number;
  bytes: number;
}

export interface RecordingsResponse {
  recordings: Recording[];
  totals: RecordingTotals;
}

export const getReadAloudPrompts = () => request<Prompt[]>('/read-aloud-prompts');

export const getRecordings = () => request<RecordingsResponse>('/me/recordings');

export const deleteRecording = (id: string) =>
  request<{ ok: true }>(`/me/recordings/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Own recordings only; the browser sends the session cookie along with an <audio> request. */
export function recordingAudioUrl(id: string): string {
  return `/api/me/recordings/${encodeURIComponent(id)}/audio`;
}

export interface UploadRecordingBody {
  file: Blob;
  filename: string;
  kind: RecordingKind;
  prompt_id?: string;
  seconds?: number;
}

/**
 * POST /api/me/recordings as multipart form data, via XHR so we get real upload
 * progress (fetch cannot report request-body progress). onProgress gets a 0..1 fraction.
 */
export function uploadRecording(
  body: UploadRecordingBody,
  onProgress?: (fraction: number) => void,
): Promise<Recording> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', body.file, body.filename);
    form.append('kind', body.kind);
    if (body.prompt_id) form.append('prompt_id', body.prompt_id);
    if (body.seconds !== undefined) form.append('seconds', String(Math.round(body.seconds)));

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/me/recordings');
    xhr.withCredentials = true;

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
    }

    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as Recording);
        return;
      }
      const message =
        (payload && typeof payload === 'object' && 'error' in payload
          ? String((payload as { error: unknown }).error)
          : '') || `Something went wrong (${xhr.status}).`;
      if (xhr.status === 401 && onUnauthorized) onUnauthorized();
      reject(new ApiError(xhr.status, message));
    };

    xhr.onerror = () => {
      reject(new ApiError(0, 'The upload failed. Check your connection and try again.'));
    };

    xhr.send(form);
  });
}

/* -------------------------------------------------------------- health */

export const getHealth = () => request<{ ok: true; version: string }>('/health');

/* --------------------------------------------------- "which kind of reader am I?" battery */
// See server/API.md, "which kind of reader am I? battery (v0.4)".

export interface BatteryChecklist {
  scale: string[];
  items: { id: string; axis: string; prompt: string }[];
  comfort_items: { id: string; prompt: string }[];
}

export interface BatterySpellingItem {
  id: string;
  word: string;
  kind: 'regular' | 'irregular' | 'nonword';
}

export interface BatterySpelling {
  speech_rate: number;
  items: BatterySpellingItem[];
}

export interface BatteryChoiceItem {
  id: string;
  left: string;
  right: string;
  correct: 'left' | 'right';
}

export interface BatteryVasTrial {
  id: string;
  letters: string[];
  practice: boolean;
}

export interface BatteryDigitTrial {
  id: string;
  length: number;
  digits: number[];
}

export interface BatteryHeteronymQuestion {
  prompt: string;
  answer: boolean;
}

export interface BatteryHeteronymItem {
  id: string;
  pair_id: string;
  condition: 'target' | 'control';
  words: string[];
  critical_index: number;
  question: BatteryHeteronymQuestion | null;
}

export interface BatteryItems {
  checklist: BatteryChecklist;
  spelling: BatterySpelling;
  orthographic_choice: BatteryChoiceItem[];
  pseudohomophone: BatteryChoiceItem[];
  vas: BatteryVasTrial[];
  digit_span: BatteryDigitTrial[];
  heteronym: BatteryHeteronymItem[];
}

export interface BatteryChoiceTrial {
  id: string;
  correct: boolean;
  rt_ms: number;
}

/** One task's raw result. Every key is optional -- a reader can skip any task. */
export interface BatteryRaw {
  checklist?: { answers: Record<string, number>; comfort: Record<string, number> };
  spelling?: { trials: { id: string; word: string; kind: string; response: string }[] };
  orthographic_choice?: { trials: BatteryChoiceTrial[] };
  pseudohomophone?: { trials: BatteryChoiceTrial[] };
  vas?: { trials: { id: string; correct_letters: number; practice: boolean }[] };
  digit_span?: { span: number };
  heteronym?: {
    trials: {
      id: string;
      pair_id: string;
      condition: 'target' | 'control';
      critical_index: number;
      word_rts: number[];
    }[];
  };
}

export interface BatteryAxisScore {
  id: string;
  label: string;
  support: number;
  confidence: 'low' | 'normal';
  detail: Record<string, unknown>;
}

export interface BatteryHeteronymResult {
  slowdown_ms: number | null;
  slowdown_ratio: number | null;
  reliable: boolean;
  pairs_scored: number;
}

export interface BatteryResult {
  axes: BatteryAxisScore[];
  comfort: { support: number; confidence: 'low' | 'normal'; detail: Record<string, unknown> };
  heteronym: BatteryHeteronymResult;
}

export interface BatteryRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  raw: BatteryRaw;
  scores: BatteryResult | null;
}

export const getBatteryItems = () => request<BatteryItems>('/battery/items');

/** Score a raw result set without saving it -- how an anonymous reader sees their radar. */
export const scoreBattery = (raw: BatteryRaw) => post<BatteryResult>('/battery/score', { raw });

export const createBatteryRun = () => post<BatteryRun>('/battery/runs');

export const getBatteryRun = (id: string) => request<BatteryRun>(`/battery/runs/${encodeURIComponent(id)}`);

export const patchBatteryRun = (id: string, patch: BatteryRaw) =>
  request<BatteryRun>(`/battery/runs/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });

export const finishBatteryRun = (id: string) => post<BatteryRun>(`/battery/runs/${encodeURIComponent(id)}/finish`);

export const applyBatteryRun = (id: string) =>
  post<{ profile: ProfileSummary }>(`/battery/runs/${encodeURIComponent(id)}/apply`);

export const getLatestBatteryRun = () => request<{ run: BatteryRun | null }>('/battery/latest');

/* ------------------------------------------------------------------ billing (v0.5) */
// See server/API.md, "Billing (v0.5)". The engine itself stays free and open source;
// "Pro" is a convenience the site sells on top of it.

export type BillingInterval = 'monthly' | 'yearly';

/** One priced plan as GET /api/billing/plans reports it -- amount is in the smallest unit of
 * `currency` (e.g. cents for USD), matching Stripe's own Price objects. */
export interface PlanPrice {
  price_id: string | null;
  amount: number;
  currency: string;
  interval: string;
}

export interface PlansResponse {
  monthly: PlanPrice;
  yearly: PlanPrice;
  /** false when Stripe isn't set up yet -- the amounts above are then placeholders. */
  configured: boolean;
}

/** The reader's own plan state, from `GET /api/me` (`user.plan`/top-level `plan`) or
 * `GET /api/billing/status`. */
export interface PlanSummary {
  plan: 'free' | 'pro';
  pro: boolean;
  plan_until: string | null;
  cancel_at_period_end: boolean;
  /** true once there's a Stripe customer to open a billing portal session for. */
  manageable: boolean;
}

export const getPlans = () => request<PlansResponse>('/billing/plans');

export const getBillingStatus = () => request<PlanSummary>('/billing/status');

/** Starts a Stripe Checkout session for the given interval and returns its URL to redirect to. */
export const startCheckout = (interval: BillingInterval) =>
  post<{ url: string }>('/billing/checkout', { interval });

/** Opens a Stripe Billing Portal session (manage or cancel an existing subscription). */
export const openPortal = () => post<{ url: string }>('/billing/portal');
/* ------------------------------------------------------ "Your library" (v0.5) */
// See server/API.md, "Library (v0.5)". Upload a book, get it back rewritten, read it on the
// site or send it to a Kindle.

export type BookStatus = 'queued' | 'processing' | 'ready' | 'failed';
export type BookSourceKind = 'epub' | 'txt' | 'md';
export type BookEngine = 'rules' | 'llm';

export interface Book {
  id: string;
  title: string;
  author: string | null;
  source_name: string;
  source_kind: BookSourceKind;
  words: number;
  /** Total chapter count once known (0 until the upload has been read). */
  chapters: number;
  status: BookStatus;
  engine: BookEngine;
  /** Chapters rewritten so far, out of `chapters` — poll while `status` is queued/processing. */
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  last_opened_at: string | null;
  kindle_sent_at: string | null;
}

/** GET /api/books/{id}/read?chapter=n — same shape as RewriteResponse, plus the chapter itself. */
export interface BookChapterResponse extends RewriteResponse {
  chapter: number;
  chapters: number;
  title: string;
}

export const getBooks = () => request<Book[]>('/books');

export const getBook = (id: string) => request<Book>(`/books/${encodeURIComponent(id)}`);

export const getBookChapter = (id: string, chapter: number) =>
  request<BookChapterResponse>(`/books/${encodeURIComponent(id)}/read?chapter=${encodeURIComponent(chapter)}`);

export const rerunBook = (id: string) => post<Book>(`/books/${encodeURIComponent(id)}/rerun`);

export const sendToKindle = (id: string) => post<{ ok: true }>(`/books/${encodeURIComponent(id)}/kindle`);

export const deleteBook = (id: string) =>
  request<{ ok: true }>(`/books/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Own books only; the browser sends the session cookie along with the download navigation. */
export function downloadBookUrl(id: string): string {
  return `/api/books/${encodeURIComponent(id)}/download`;
}

export interface UploadBookBody {
  file: File;
  title?: string;
  author?: string;
  engine?: BookEngine;
}

/** POST /api/books as multipart form data, via XHR so we get real upload progress. */
export function uploadBook(body: UploadBookBody, onProgress?: (fraction: number) => void): Promise<Book> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', body.file, body.file.name);
    if (body.title) form.append('title', body.title);
    if (body.author) form.append('author', body.author);
    if (body.engine) form.append('engine', body.engine);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/books');
    xhr.withCredentials = true;

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
    }

    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as Book);
        return;
      }
      const message =
        (payload && typeof payload === 'object' && 'error' in payload
          ? String((payload as { error: unknown }).error)
          : '') || `Something went wrong (${xhr.status}).`;
      if (xhr.status === 401 && onUnauthorized) onUnauthorized();
      reject(new ApiError(xhr.status, message));
    };

    xhr.onerror = () => {
      reject(new ApiError(0, 'The upload failed. Check your connection and try again.'));
    };

    xhr.send(form);
  });
}

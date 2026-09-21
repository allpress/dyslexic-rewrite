# Reading-test site — API contract

Base: same origin, prefix `/api`. JSON in, JSON out. Auth = signed `session` cookie set by `/api/auth/verify`.
Errors: `{"error": "message"}` with a 4xx status. All timestamps ISO-8601 UTC.

Privacy rules the server enforces:
- A writing sample sent to `/api/me/writing-sample` is processed in memory and discarded. Only the
  `StyleReport` (aggregate metadata) and the derived profile are stored.
- Passage texts are the project's own. A user's free-form text sent to `/api/rewrite` is never stored.
- `DELETE /api/me` removes the user and every row that references them.

## Auth

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/auth/request-code` | `{email}` | `{ok: true, dev_code?: string}` — `dev_code` only when no email provider is configured |
| POST | `/api/auth/verify` | `{email, code}` | `{user}` and sets the cookie |
| POST | `/api/auth/logout` | — | `{ok: true}` |

## Me

`User` = `{id, email, name, base_profile: "default"|"phonological"|"visual"|"attention", onboarded: bool, has_personal_profile: bool, phonetic_map: "off"|"on_demand"|"always", created_at, plan: PlanSummary}`
(`plan` is billing's addition -- see "Billing (v0.5)" below for `PlanSummary`.)
`User` = `{id, email, name, base_profile: "default"|"phonological"|"visual"|"attention", onboarded: bool, has_personal_profile: bool, phonetic_map: "off"|"on_demand"|"always", kindle_email: string|null, created_at}`

`kindle_email` (v0.5, "Your library") is where `POST /api/books/{id}/kindle` emails a book's
EPUB. Null until the reader sets it via `PATCH /api/me {kindle_email}`.

`phonetic_map` is the reader's phonetic-map preference (see v0.3 below). It defaults to `on_demand`
and lives directly on the user row, the same way `base_profile` does.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/api/me` | — | `{user, profile: ProfileSummary | null, plan: PlanSummary}` (401 when signed out; `plan` is billing's addition, see "Billing (v0.5)") |
| PATCH | `/api/me` | `{name?, base_profile?, onboarded?, phonetic_map?}` | `{user}` |
| GET | `/api/me` | — | `{user, profile: ProfileSummary | null}` (401 when signed out) |
| PATCH | `/api/me` | `{name?, base_profile?, onboarded?, phonetic_map?, kindle_email?}` | `{user}` |
| POST | `/api/me/writing-sample` | `{text}` (>= 150 words) | `{style: StyleReport, profile: ProfileSummary}` |
| POST | `/api/me/triggers` | `{add?: [word], remove?: [word], safe?: [word]}` | `{profile: ProfileSummary}` |
| DELETE | `/api/me` | — | `{ok: true}` |

`ProfileSummary` = `{name, base_profile, max_sentence_words, min_zipf, trigger_words: [..], safe_words: [..], vocabulary_size, style: {median_sentence_words, p75_sentence_words, passive_rate, clause_depth, median_zipf, sample_words}}`

`StyleReport` = the JSON of `dyslexic_rewrite.learn.StyleReport` (all numeric rates + small word-count maps).

## Passages

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/passages` | `[{id, slug, title, words, level, pair}]` — `pair` groups two matched passages |

## Reading tests (the A/B framework)

A test = two matched passages. One is shown as the original, the other rewritten with the user's
profile; which one is rewritten is randomised per test. The reader never sees the same text twice.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/tests` | `{pair?: string}` (omit = next unused pair) | `Test` |
| GET | `/api/tests/{id}` | — | `Test` |
| POST | `/api/tests/{id}/items/{index}/start` | — | `{started_at}` (server clock, for the timer) |
| POST | `/api/tests/{id}/items/{index}/finish` | `{seconds, answers: {question_id: option_index}, tripped: [word], ease: 1..5}` | `ItemResult` |
| GET | `/api/results` | — | `{tests: [TestSummary], totals: {original: {wpm, comprehension, n}, rewritten: {...}}}` |

`Test` = `{id, pair, created_at, completed: bool, items: [TestItem]}`
`TestItem` = `{index: 0|1, passage_id, title, condition: "original"|"rewritten", words, segments: [Segment], questions: [Question], result: ItemResult | null}`
`Segment` = `{t: "text", s: string}` | `{t: "change", s: string, orig: string, why: string, alts: [string]}` | `{t: "note", s: string, why: string, hint: string}` | `{t: "para"}` | `{t: "heading", s: string}`
`Question` = `{id, prompt, options: [string x4]}` (correct answer never sent to the client)
`ItemResult` = `{seconds, wpm, correct, total, ease, tripped: [word], recorded_at}`
`TestSummary` = `{id, pair, created_at, completed, items: [{condition, title, wpm, correct, total, ease}]}`

## Read anything

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/rewrite` | `{text}` (<= 20k chars free / 200k chars Pro -- `billing.quota(u)["paste_chars"]`, v0.5) | `{segments: [Segment], stats: {sentences, sentences_changed, changes, load_before, load_after}}` — uses the caller's profile when signed in, `default` otherwise; text is not stored |
| POST | `/api/feedback` | `{tripped: [word], safe?: [word]}` | `{profile: ProfileSummary}` — from the read-anything view, signed in only |

## Health

`GET /api/health` → `{ok: true, version}`

---

# Voice recordings (v0.2)

People speak more naturally than they write, so a spoken sample is often a truer picture of how
someone's language works than their typing is. The site therefore lets a signed-in reader record or
upload audio. **The site does no analysis.** Every upload lands in `pending_analysis` and stays there
until an offline pipeline (built separately) picks it up. No transcription, no model, no background job.

Privacy: audio is a person's voice, so it is theirs. It is stored only against their own account, only
they can play it back, `DELETE` removes the row and the file, and deleting the account deletes every
recording and file with it.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/api/read-aloud-prompts` | — | `[Prompt]` — short passages to read aloud, plus free-speech suggestions |
| POST | `/api/me/recordings` | multipart: `file` (audio), `kind`, `prompt_id?`, `seconds?` | `Recording` (201) |
| GET | `/api/me/recordings` | — | `{recordings: [Recording], totals: {count, seconds, bytes}}` |
| GET | `/api/me/recordings/{id}/audio` | — | the audio bytes (`Content-Type` as uploaded), own recordings only |
| DELETE | `/api/me/recordings/{id}` | — | `{ok: true}` |

`Prompt` = `{id, kind: "read_aloud"|"free_speech", title, text, words}`
 - `read_aloud`: a passage to read out; `text` is the passage.
 - `free_speech`: a question to answer in their own words (e.g. "Tell us about a room you changed");
   `text` is the question, `words` is 0.

`Recording` = `{id, created_at, kind, prompt_id|null, prompt_title|null, seconds|null, bytes, mime,
status: "pending_analysis"|"analyzing"|"analyzed"|"failed", note|null}`

Rules the server enforces:
- Signed in only. A reader may only list, play and delete their own recordings.
- `kind` must be `read_aloud` or `free_speech`; `prompt_id` must exist when given.
- Accepted types: `audio/webm`, `audio/ogg`, `audio/mp4`, `audio/mpeg`, `audio/wav`, `audio/x-m4a`,
  `audio/aac`, `audio/flac` (extension is derived from the type).
- At most 25 MB and 15 minutes per recording; at most 50 recordings per account.
- `status` is always `pending_analysis` on create. Nothing in the web app ever changes it; the offline
  pipeline does that directly in the database.

Storage: files are written to `AUDIO_DIR` (default `./data/recordings`), one file per recording named
`<user_id>/<uuid>.<ext>`. On Fly that directory lives on a mounted volume. Nothing else reads it.

---

# Phonetic map & read-aloud (v0.3)

A friendly respelling (`in-TEN-shun`, `WYND` vs `WIND`) shown over words a reader might struggle
with, computed with `dyslexic_rewrite.pronounce.phonetic_map` over the reader's own profile. If
that module isn't installed, every `phonetic_map` field below is simply `[]` — nothing else
changes.

`PhoneticMapEntry` = `{start, end, word, respell, hint: string|null, kind, always: bool}`
 - `start`/`end` are character offsets into the **served text**: every segment's `s` concatenated
   in order, with each `{t: "para"}` break counted as two newlines (`"\n\n"`). This is the same
   text the reader renders, so a client maps an entry back onto its segments by walking that same
   concatenation.
 - `always` marks entries a client should surface without interaction. It's `true` for every
   entry when the reader's mode (below) is `"always"`, and also for a handful of kinds (true
   heteronyms, personal trigger words) even outside that mode — so a client just checks
   `always` and doesn't need to know the reader's mode to decide.

Every place a passage body (original or rewritten) is served now also returns a `phonetic_map:
[PhoneticMapEntry]` field, computed with the same profile used to build its `segments`:
 - `TestItem.phonetic_map` (`POST /api/tests`, `GET /api/tests/{id}`)
 - `POST /api/rewrite` → `{segments, stats, phonetic_map}`

The reader's own display mode is `User.phonetic_map`, one of:
 - `"off"` — never show a respelling.
 - `"on_demand"` (default) — show a respelling only once the reader taps/hovers/focuses the word.
 - `"always"` — show respellings for `always: true` entries all the time; the rest stay on-demand.

It is read from `GET /api/me` and set with `PATCH /api/me {phonetic_map}`; signed-out readers of
`/api/rewrite` get entries computed as if their mode were `"on_demand"`.

`FinishIn` (`POST /api/tests/{id}/items/{index}/finish`) gains an optional `read_aloud: bool`
(default `false`) — set it when the reader turned on read-aloud during that attempt. `ItemResult`
gains `phonetic_map` (the mode that was active for the reader at the moment they finished) and
`read_aloud`, so later analysis can compare outcomes across modes.

Migration: `server/migrations/003_phonetic_map.sql` adds `users.phonetic_map` (`TEXT NOT NULL
DEFAULT 'on_demand'`) and `test_items.phonetic_map` / `test_items.read_aloud`.

---

# Sample books & rewrite cache (v0.4)

## Sample books ("Show me an example")

Four short, public-domain excerpts a visitor can load straight into the read-anything view
without pasting anything in, defined in `server/data/samples/index.json` (metadata) plus one
`.txt` file per excerpt (`server/samples.py` loads both once, at import).

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/samples` | `[SampleInfo]` |
| GET | `/api/samples/{slug}` | same shape as `POST /api/rewrite`, plus `{title, author, year, chapter, source}` (404 if `slug` is unknown) |

`SampleInfo` = `{slug, title, author, year, chapter, source, blurb, words}` — `source` is the
Project Gutenberg ebook page for that title.

`GET /api/samples/{slug}` rewrites the excerpt with the caller's own profile when signed in,
the `default` profile otherwise (anonymous is allowed, exactly like `/api/rewrite`), and returns
`{segments, stats, phonetic_map, cached, title, author, year, chapter, source}`.

## Rewrite cache

`POST /api/rewrite` and `GET /api/samples/{slug}` share a cache (`server/cache.py`,
`server/migrations/004_rewrite_cache.sql`) so re-rewriting the same text under the same profile
does no analysis/rewrite/phonetic-map work a second time. Both now also return `cached: bool`,
so a caller can see whether it was served from cache.

The cache key is `sha256(package_version | engine | profile_fingerprint | text)`, where
`profile_fingerprint` is a sha256 of the canonical (sorted-key) JSON of every `ReaderProfile`
field that can change a rewrite or map -- everything except `name`, `description` and `layout`.
Sample-book entries use the same key, prefixed `sample:`, so the four samples are never subject
to eviction.

The stored `phonetic_map` is always computed as if the profile's mode were `"always"` (the full
entry list, each entry carrying its `kind`); the server re-derives the `always` flag for the
caller's real mode on every read (`off` -> `[]`, `on_demand` -> `always` only for entries whose
`kind` is in the profile's always-kinds or is `"personal"`, `always` -> every entry), so one row
serves every reader regardless of their `phonetic_map` preference. Behaviour for a caller is
identical to computing the map fresh each time.

Bounds: `/api/rewrite` only caches text of 20,000 characters or fewer (its own existing limit,
so in practice always). On every insert there's a 1-in-50 chance of an opportunistic cleanup
that deletes non-sample rows whose `last_hit` is older than 90 days, then trims the oldest
(by `last_hit`) non-sample rows until the table is back under 5,000 rows.

The four samples are pre-rewritten for the `default` profile in a background thread at startup
(`server/app.py`'s lifespan hook), so the first visitor to open one doesn't pay for it; a failure
there is logged and never blocks startup.

Migration: `server/migrations/004_rewrite_cache.sql` adds `rewrite_cache (key, engine,
package_version, segments, stats, phonetic_map, created_at, last_hit, hits)`.

# "Which kind of reader am I?" battery (v0.4)

A ~10-minute, keyboard/mouse-only screening battery (docs/RESEARCH.md, section 3) that gives a
reader a plain-language profile across five axes, drawn as a radar chart -- never a label, never a
diagnosis. No AI anywhere: every stimulus is static content from `server/battery_items.py`, and
every score comes from deterministic arithmetic in `dyslexic_rewrite.assess`.

Axes (`phonological`, `orthographic`, `rate`, `vas`, `attention`) each get a `support` (0-100,
higher = more support would help) and a `confidence` (`"low"` when the task behind that axis was
skipped). `comfort` (visual comfort) is scored the same way but shown as a separate note, never as
an axis or folded into the profile (RESEARCH.md section 1.7). The project's own hypothesis --
whether a reused spelling/heteronym costs extra reading time -- is reported separately as
`heteronym: {slowdown_ms, slowdown_ratio, reliable, pairs_scored}`.

**Every anchor these scores are built from is a documented first cut, not a validated instrument**
-- see the module docstring in `src/dyslexic_rewrite/assess.py`. Every raw per-task result is
stored (`battery_runs.raw`) specifically so the anchors can be re-scored later against real
outcomes (RESEARCH.md section 3.1), without losing any attempt.

Tasks A-F and H are implemented; **test G (RAN, read aloud into the existing recorder) is a TODO**
for a later pass -- it needs the offline audio pipeline this battery deliberately avoids depending
on. Test I (the A/B fluency test) already exists as the reading-tests flow above.

| Method | Path | Body | Auth | Returns |
| --- | --- | --- | --- | --- |
| GET | `/api/battery/items` | -- | none | `BatteryItems` -- all stimuli, randomised per call |
| POST | `/api/battery/score` | `{raw: BatteryRaw}` | none | `BatteryResult` -- scores a result set without saving it (how an anonymous reader sees their radar) |
| POST | `/api/battery/runs` | -- | signed in | `BatteryRun` (started, empty `raw`) |
| GET | `/api/battery/runs/{id}` | -- | signed in, own run | `BatteryRun` |
| PATCH | `/api/battery/runs/{id}` | `{<task>: <task's raw result>}` -- any subset of the `BatteryRaw` keys | signed in, own run | `BatteryRun` (merged) |
| POST | `/api/battery/runs/{id}/finish` | -- | signed in, own run | `BatteryRun` with `scores` filled in and `finished_at` set |
| POST | `/api/battery/runs/{id}/apply` | -- | signed in, own run, already finished | `{profile: ProfileSummary}` -- merges `profile_from_scores` into the reader's stored profile, keeping their trigger words, vocabulary and style targets |
| GET | `/api/battery/latest` | -- | signed in | `{run: BatteryRun \| null}` -- the reader's most recently *finished* run |

An anonymous reader can call every route above except the four that need a saved run
(`POST /api/battery/runs` and the three under it) -- they take the whole battery client-side and
score it with `POST /api/battery/score`, but cannot save or apply a result until they sign in. The
web app runs the same stepper either way and only asks for sign-in at the "use these settings"
step.

`BatteryItems` = `{checklist: {scale: [string x4], items: [{id, axis, prompt}], comfort_items:
[{id, prompt}]}, spelling: {speech_rate, items: [{id, word, kind: "regular"|"irregular"|"nonword"}]},
orthographic_choice: [{id, left, right, correct: "left"|"right"}], pseudohomophone: [{id, left,
right, correct: "left"|"right"}], vas: [{id, letters: [string x5], practice: bool}], digit_span:
[{id, length, digits: [int]}], heteronym: [{id, pair_id, condition: "target"|"control", words:
[string], critical_index, question: {prompt, answer: bool} | null}]}`

`BatteryRaw` (every key optional -- a reader can skip any task) = `{checklist: {answers: {item_id:
1..4}, comfort: {item_id: 1..4}}, spelling: {trials: [{id, word, kind, response}]},
orthographic_choice: {trials: [{id, correct, rt_ms}]}, pseudohomophone: {trials: [{id, correct,
rt_ms}]}, vas: {trials: [{id, correct_letters, practice}]}, digit_span: {span: int}, heteronym:
{trials: [{id, pair_id, condition, critical_index, word_rts: [number]}]}}`. `word_rts` is one
reading time (ms) per word revealed in that sentence's moving window, in order.

`BatteryResult` = `{axes: [{id, label, support, confidence: "low"|"normal", detail}], comfort:
{support, confidence, detail}, heteronym: {slowdown_ms, slowdown_ratio, reliable, pairs_scored}}`

`BatteryRun` = `{id, started_at, finished_at: string | null, raw: BatteryRaw, scores: BatteryResult
| null}`

Privacy: unlike a writing sample or free-form text, a battery run's raw data is fixed, single-word
or numeric responses to the project's own stimuli (item ids, one typed word per spelling item,
correctness, timings, Likert answers), kept on purpose so the scoring anchors in
`dyslexic_rewrite.assess` can be re-checked against real outcomes later (RESEARCH.md section 3.1).
`DELETE /api/me` removes every `battery_runs` row for that user, like everything else.

---

# Billing (v0.5)

`dyslexic_rewrite` (the rewriting engine) stays MIT-licensed and free to run yourself, forever.
"Pro" is a convenience the site sells on top of it -- unlimited book conversions, a bigger paste
limit, and (once it exists) priority use of the higher-quality LLM rewrite tier. There is no
trial and no time limit on the free tier. All of this lives in `server/billing.py`.

`users.plan` (`"free"` | `"pro"`) and `users.plan_until` are the single source of truth
`billing.is_pro()` reads: `pro` and (`plan_until` is null or in the future). Nothing else --
not a live Stripe subscription, not a cached flag -- decides it, so a plan set by hand (see the
CLI below) behaves identically to one Stripe set through the webhook.

**If `STRIPE_SECRET_KEY` is not set**, every route below except `GET /api/billing/plans` returns
503 `{"error": "Billing is not set up yet"}`, and `is_pro`/`plan_summary`/`quota` all still work
off whatever is already in the database -- so gifting Pro to a tester never needs Stripe at all:

```
python -m server.billing grant EMAIL [--months N]   # N omitted = no expiry, until revoked
python -m server.billing revoke EMAIL
```

## Config (env)

| Variable | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY` | Stripe secret key. Unset = billing routes are 503 (see above). |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for the endpoint added in the Stripe dashboard. |
| `STRIPE_PRICE_MONTHLY` / `STRIPE_PRICE_YEARLY` | Price ids for the two Pro intervals. |
| `PUBLIC_BASE_URL` | Used to build Checkout/Portal return URLs. Default `https://unwindwords.com`. |
| `DYSREWRITE_LLM_BASE_URL` | Already the engine's own LLM-tier switch (`src/dyslexic_rewrite/rewrite/llm.py`); `billing.quota()`'s `llm_tier` is `true` only when this is set *and* the reader is Pro. |

## Routes

| Method | Path | Body | Auth | Returns |
| --- | --- | --- | --- | --- |
| GET | `/api/billing/plans` | -- | none | `Plans` -- always 200, even unconfigured |
| POST | `/api/billing/checkout` | `{interval: "monthly"\|"yearly"}` | signed in | `{url}` -- redirect the browser here |
| POST | `/api/billing/portal` | -- | signed in | `{url}` -- Stripe Billing Portal session |
| POST | `/api/billing/webhook` | raw Stripe event + `Stripe-Signature` header | Stripe only | `{ok: true, duplicate?: true}` |
| GET | `/api/billing/status` | -- | signed in | `PlanSummary` |

`Plans` = `{monthly: PlanPrice, yearly: PlanPrice, configured: bool}`
`PlanPrice` = `{price_id: string|null, amount: int, currency: string, interval: string}` --
`amount` is in the smallest currency unit (cents for USD), read straight from the Stripe `Price`
objects and cached in-process for an hour. Unconfigured (or a failed Stripe call) falls back to
placeholder amounts (500 / 3900, i.e. $5.00 / $39.00) with `configured: false`, so `/pricing`
always has something to render.

`PlanSummary` = `{plan: "free"|"pro", pro: bool, plan_until: string|null, cancel_at_period_end: bool,
manageable: bool}` -- `manageable` is `true` once there's a Stripe customer to open a Portal
session for (so a Pro plan granted by hand has nothing to "manage" here).

`GET /api/me` gains a `plan: PlanSummary` field, both at the top level and on `user.plan`
(`User.plan` in `web/src/api.ts`).

`POST /api/billing/checkout` creates or looks up the caller's Stripe customer (by email), then a
Checkout Session in `mode: "subscription"` with `success_url` =
`{PUBLIC_BASE_URL}/profile?upgraded=1`, `cancel_url` = `{PUBLIC_BASE_URL}/pricing`,
`allow_promotion_codes: true`, and `client_reference_id` = the user's id.

`POST /api/billing/webhook` verifies the signature against the raw body, records the Stripe
event id in `billing_events` before acting on it (a replay of the same id is a no-op), and
handles: `checkout.session.completed` (associates the Checkout customer with the user who
started it), `customer.subscription.created`/`.updated` (sets `plan`/`plan_until` and upserts
`subscriptions`), `customer.subscription.deleted` (back to `free`), `invoice.paid` (extends
`plan_until`), and `invoice.payment_failed` (marks the subscription `past_due` -- does not itself
downgrade; the grace period below covers a slow retry, and Stripe's own follow-up
`customer.subscription.updated` is what actually acts).

`plan_until` is always set to `current_period_end + 3 days` (`billing.GRACE_PERIOD`), so a
webhook delay or a slow card retry never cuts a paying reader off mid-read.

## Gating (for other modules, e.g. the book library)

```python
from server import billing

billing.require_pro(user)          # raises HTTP 402 {"error": "pro_required", "message", "upgrade": "/pricing"}
q = billing.quota(user)             # {"books_total": 1 | None, "paste_chars": 20_000 | 200_000, "llm_tier": bool}
```

`quota(user)` (`user` may be `None` for an anonymous caller, always free): free is one book ever
(`books_total: 1`) and a 20,000-character paste limit; Pro is unlimited books (`books_total:
None`) and 200,000 characters. `POST /api/rewrite` enforces `quota(u)["paste_chars"]` (anonymous
callers get the free limit).

## Migration

`server/migrations/006_billing.sql` adds `users.plan` / `users.plan_until` /
`users.stripe_customer_id`, plus `subscriptions` (one row per Stripe subscription) and
`billing_events` (webhook idempotency, keyed on the Stripe event id).
# Your library (v0.5)

Upload a book, get it back rewritten, read it on the site or a Kindle. All routes below require
sign-in. Files (the original upload and the rewritten EPUB) are written to `BOOKS_DIR` (default
`./data/books`; on Fly, `/data/books`, the same mounted volume `AUDIO_DIR` uses), one subfolder
per user, using the same traversal-safe key pattern as voice recordings.

Processing runs on a single background worker thread with a queue, started from the app's
lifespan hook (`server/library.py`). A book left `queued`/`processing` by a restart re-queues
itself at startup.

`Book` = `{id, title, author: string|null, source_name, source_kind: "epub"|"txt"|"md", words,
chapters, status: "queued"|"processing"|"ready"|"failed", engine: "rules"|"llm", progress,
error: string|null, created_at, finished_at: string|null, last_opened_at: string|null,
kindle_sent_at: string|null}`

- `chapters` is the total chapter count once the upload has been read (0 only for an instant
  before that finishes); `progress` is how many of those chapters have been rewritten so far --
  poll `GET /api/books/{id}` (or list) roughly every 3 seconds while `status` is `queued` or
  `processing`.
- `engine` is `"rules"` unless the upload asked for `"llm"` *and* the reader is Pro *and* the
  server has an LLM configured (`DYSREWRITE_LLM_BASE_URL`/`DYSREWRITE_LLM_API_KEY`) -- otherwise
  it's silently downgraded to `"rules"`.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/books` | multipart: `file` (.epub/.txt/.md), `title?`, `author?`, `engine?` | `Book` (201) |
| GET | `/api/books` | -- | `[Book]`, newest first |
| GET | `/api/books/{id}` | -- | `Book` -- poll this for status/progress |
| GET | `/api/books/{id}/read?chapter=n` | -- | same shape as `POST /api/rewrite`, plus `{chapter, chapters, title}` -- 409 until `status == "ready"` |
| GET | `/api/books/{id}/download` | -- | the rewritten EPUB, `Content-Disposition: attachment` -- 409 until ready |
| POST | `/api/books/{id}/kindle` | -- | `{ok: true}` -- emails the EPUB to `users.kindle_email`; 400 if that isn't set yet |
| POST | `/api/books/{id}/rerun` | -- | `Book` -- re-rewrites with the reader's *current* profile; **Pro only** (402 otherwise) |
| DELETE | `/api/books/{id}` | -- | `{ok: true}` -- removes the row and its files |

Rules the server enforces:
- **Upload limits**: at most 25 MB; `.epub`/.txt`/`.md` only; at most 300,000 words for anyone,
  and at most 60,000 words for a free reader (a longer book needs Pro). Rejections come back as
  400 (bad file/too long outright) or 402 (fixable by upgrading).
- **Book quota**: `billing.quota(user).books_total` -- a free reader gets exactly one book, ever;
  a second upload is a 402 that says so. Pro is unlimited (`books_total: null`).
- A book's chapters come from `dyslexic_rewrite.io.read_chapters` (EPUB spine order with heading
  detection; `.txt`/`.md` split on headings or "Chapter N" lines, falling back to ~8,000-word
  chunks of the whole file). Each chapter is rewritten with `dyslexic_rewrite.rewrite.engine.rewrite`
  under the reader's own profile, going through the same rewrite cache as `/api/rewrite`
  (`server/cache.py`) -- so `POST /api/books/{id}/rerun` under an unchanged profile is instant.
- **Send to Kindle** emails the EPUB as a base64 attachment via Resend (reusing `auth.py`'s
  client/env), from `LOGIN_FROM_EMAIL`, to `users.kindle_email`. The reader must add that sending
  address to Amazon's **Approved Personal Document E-mail List** (on amazon.com: Manage Your
  Content and Devices > Preferences > Personal Document Settings) or the book is silently
  dropped -- the web app shows this instruction whenever it asks for the address. Without
  `RESEND_API_KEY` configured (local dev), the send is a logged no-op, same spirit as
  `DEV_CODE_FALLBACK` for sign-in codes.
- `PATCH /api/me` gains `kindle_email?: string` (cleared with `""`); `User` gains
  `kindle_email: string | null`.
- `DELETE /api/me` also deletes every book row (cascade) and every book file for that user.

Migration: `server/migrations/007_library.sql` adds `books (id, user_id, title, author,
source_name, source_kind, words, chapters, status, engine, profile_fingerprint, error,
source_key, output_key, progress, created_at, finished_at, last_opened_at, kindle_sent_at)` and
`users.kindle_email`.

Env vars: `BOOKS_DIR` (default `./data/books`), plus the LLM engine's existing
`DYSREWRITE_LLM_BASE_URL`/`DYSREWRITE_LLM_API_KEY` (see `src/dyslexic_rewrite/rewrite/llm.py`) to
allow Pro readers the `"llm"` engine.
# Marketing (v0.5)

The launch marketing surface: server-rendered SEO book pages (real HTML, not the SPA), a
newsletter, a cookie-free page-view counter, and an admin stats endpoint. Implementation:
`server/books.py` (pages) and `server/marketing.py` (newsletter/track/admin), registered in
`server/app.py` *before* the SPA's catch-all route so neither the static mount nor the SPA
fallback can shadow them.

## Server-rendered book pages

Plain HTML (not the React app) so crawlers see real content on first load, built from the same
sample books and rewrite cache as `GET /api/samples/{slug}` (v0.4) -- a page costs nothing to
render because the samples are pre-warmed at startup.

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/books` | HTML index of every sample book, linking to its page |
| GET | `/books/{slug}` | HTML page for one sample: title `Read <Title>, dyslexia-friendly \| Unwind Words`, the first ~600 words of the rewritten text with a `<ruby>` phonetic map, a "Continue reading" link into `/read?sample=<slug>`, Gutenberg attribution, canonical link, OpenGraph/Twitter tags, and `Book`/`WebPage` JSON-LD (404 for an unknown slug) |
| GET | `/sitemap.xml` | XML sitemap: `/`, `/pricing`, `/read`, `/assess`, `/books`, and `/books/<slug>` for every sample |
| GET | `/robots.txt` | `Allow: /` plus the sitemap URL |

Each book-page view is recorded through the same counter as `POST /api/track` below.

## Newsletter

Single opt-in for v1 (no confirmation email) -- signing up takes effect immediately. If
`RESEND_API_KEY` is set (see `server/auth.py`), a one-line welcome email is sent with an
unsubscribe link; otherwise signup still succeeds silently. Rate-limited in-process to 5 requests
per minute per client IP.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/newsletter` | `{email, source?}` | `{ok: true}` (400 invalid email, 429 rate-limited) |
| GET | `/api/newsletter/unsubscribe?token=` | -- | `{ok: true, email}` -- `token` is an itsdangerous-signed email from the welcome email's unsubscribe link (400 if it doesn't verify) |

`source` is a short free-text tag (e.g. `"landing"`, `"footer"`) for telling signups apart later;
never required. Signing up again with the same address keeps the first-seen `source` and clears
`unsubscribed_at`.

Migration `server/migrations/008_marketing.sql` adds `newsletter_signups (email PK, source,
created_at, confirmed_at, unsubscribed_at)`. `confirmed_at` is unused in v1 (reserved for a future
double opt-in) and `DELETE /api/me` does not touch this table, since a newsletter signup does not
require an account.

## Page-view counter

Cookie-free, IP-free: only a day, a path, and the referring site's hostname (never the full
referrer URL) are kept, as a running count. Called once per route change from the SPA
(`web/src/App.tsx`) and once per view from the server-rendered book pages above.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/track` | `{path}` | `{ok: true}` |

Migration `008_marketing.sql` adds `page_views (day, path, referrer_host, count)`, primary keyed on
`(day, path, referrer_host)` with `referrer_host` defaulting to `''` (not `NULL`) when there was no
referrer.

## Admin stats

404s outright when `ADMIN_KEY` is not set in the environment, or when the given `key` doesn't
match it -- the route is invisible by default, not just unauthorized.

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/admin/stats?key=` | `{signups, page_views_30d: [{path, count}], users, pro_users, books, generated_at}` |

`pro_users` (from `users.plan`, added by the billing migration) and `books` (from the `books`
table, added by the library migration) are `null` when that column/table doesn't exist yet --
guarded by a try/rollback per query, so this endpoint works whether or not those migrations have
landed.

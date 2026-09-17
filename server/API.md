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

`User` = `{id, email, name, base_profile: "default"|"phonological"|"visual"|"attention", onboarded: bool, has_personal_profile: bool, created_at}`

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/api/me` | — | `{user, profile: ProfileSummary | null}` (401 when signed out) |
| PATCH | `/api/me` | `{name?, base_profile?, onboarded?}` | `{user}` |
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
| POST | `/api/rewrite` | `{text}` (<= 20k chars) | `{segments: [Segment], stats: {sentences, sentences_changed, changes, load_before, load_after}}` — uses the caller's profile when signed in, `default` otherwise; text is not stored |
| POST | `/api/feedback` | `{tripped: [word], safe?: [word]}` | `{profile: ProfileSummary}` — from the read-anything view, signed in only |

## Health

`GET /api/health` → `{ok: true, version}`

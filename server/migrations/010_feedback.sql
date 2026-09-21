-- User feedback (v0.6): a lightweight inbox that a Claude skill rolls up weekly into work.
--
-- Anonymous submissions are allowed -- both `user_id` and `email` are nullable -- and a signed-in
-- submitter's `user_id` is attached automatically by `server/feedback.py`. `user_id` uses
-- ON DELETE SET NULL (not CASCADE, unlike most other tables): a reader's account can be deleted
-- without erasing the feedback itself, since that's exactly the record the weekly rollup needs;
-- deleting the account just detaches it from who sent it, the same spirit as `page_views` never
-- storing an identity to begin with.
--
-- `context` is a small JSONB grab-bag of whatever the web app could gather at submission time --
-- profile name, plan, phonetic-map mode, book id, passage/test id, user agent, viewport, app
-- version -- never anything sensitive. `kind = 'tripped'` rows are written automatically by the
-- existing `POST /api/feedback` (reader taps a word that trips them up); the other four kinds
-- come from the floating feedback widget and the inline post-test/post-conversion prompt.
CREATE TABLE IF NOT EXISTS feedback (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
  email       TEXT,
  kind        TEXT NOT NULL CHECK (kind IN ('bug', 'idea', 'praise', 'question', 'tripped')),
  message     TEXT NOT NULL,
  rating      SMALLINT CHECK (rating BETWEEN 1 AND 5),
  page        TEXT,
  context     JSONB NOT NULL DEFAULT '{}'::jsonb,
  status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'triaged', 'planned', 'done', 'wontfix')),
  tags        TEXT[] NOT NULL DEFAULT '{}',
  admin_note  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS feedback_status_created_idx ON feedback (status, created_at DESC);

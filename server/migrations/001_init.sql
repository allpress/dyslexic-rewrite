-- Reading-test site schema. Applied in order by server/db.py at startup.

CREATE TABLE IF NOT EXISTS schema_migrations (
  name TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id           BIGSERIAL PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  name         TEXT,
  base_profile TEXT NOT NULL DEFAULT 'default',
  onboarded    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one-time sign-in codes (hashed), short lived
CREATE TABLE IF NOT EXISTS login_codes (
  id         BIGSERIAL PRIMARY KEY,
  email      TEXT NOT NULL,
  code_hash  TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS login_codes_email_idx ON login_codes (email, created_at DESC);

-- the reader profile: aggregate metadata ONLY (dyslexic_rewrite.ReaderProfile as JSON)
CREATE TABLE IF NOT EXISTS profiles (
  user_id     BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  profile     JSONB NOT NULL,
  style       JSONB,            -- StyleReport from the last writing sample, or null
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS passages (
  id         BIGSERIAL PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  pair       TEXT NOT NULL,          -- two passages share a pair key
  title      TEXT NOT NULL,
  level      TEXT NOT NULL DEFAULT 'general',
  words      INT NOT NULL,
  body       TEXT NOT NULL,
  questions  JSONB NOT NULL          -- [{id, prompt, options[4], answer}]
);
CREATE INDEX IF NOT EXISTS passages_pair_idx ON passages (pair);

CREATE TABLE IF NOT EXISTS tests (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pair         TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS test_items (
  test_id     BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
  idx         SMALLINT NOT NULL,
  passage_id  BIGINT NOT NULL REFERENCES passages(id),
  condition   TEXT NOT NULL,          -- original | rewritten
  words       INT NOT NULL,           -- words as shown (rewritten may differ)
  started_at  TIMESTAMPTZ,
  seconds     REAL,
  wpm         REAL,
  correct     SMALLINT,
  total       SMALLINT,
  ease        SMALLINT,
  tripped     JSONB,                  -- [word] — the reader's own marks
  answers     JSONB,                  -- {question_id: option_index}
  recorded_at TIMESTAMPTZ,
  PRIMARY KEY (test_id, idx)
);

CREATE INDEX IF NOT EXISTS tests_user_idx ON tests (user_id, created_at DESC);

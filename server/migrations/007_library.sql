-- "Your library" (v0.5): upload a book, get it back rewritten, read it on the site or a Kindle.
--
-- One row per uploaded book. Files (the original upload and the rewritten EPUB) live under
-- `BOOKS_DIR` (server/library.py), keyed by `source_key`/`output_key`, the same traversal-safe
-- pattern server/storage.py already uses for recordings.
CREATE TABLE IF NOT EXISTS books (
  id                  BIGSERIAL PRIMARY KEY,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title               TEXT NOT NULL,
  author              TEXT,
  source_name         TEXT NOT NULL,             -- the uploaded file's own name
  source_kind         TEXT NOT NULL CHECK (source_kind IN ('epub', 'txt', 'md')),
  words               INT NOT NULL DEFAULT 0,
  chapters            INT NOT NULL DEFAULT 0,
  status              TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
  engine              TEXT NOT NULL DEFAULT 'rules',
  profile_fingerprint TEXT,                       -- server/cache.py fingerprint the book was built with
  error               TEXT,
  source_key          TEXT NOT NULL,
  output_key          TEXT,                       -- set once the rewritten EPUB is written
  progress            INT NOT NULL DEFAULT 0,     -- chapters done, 0..chapters
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  last_opened_at      TIMESTAMPTZ,
  kindle_sent_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS books_user_idx ON books (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS books_status_idx ON books (status) WHERE status IN ('queued', 'processing');

-- Where to email a book's EPUB for "Send to Kindle". The reader must add this address to
-- Amazon's "Approved Personal Document E-mail List" for the email to actually arrive.
ALTER TABLE users ADD COLUMN IF NOT EXISTS kindle_email TEXT;

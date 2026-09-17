-- Voice recordings. The site only stores them; analysis happens offline and updates `status`.

CREATE TABLE IF NOT EXISTS recordings (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL DEFAULT 'free_speech',   -- read_aloud | free_speech
  prompt_id    TEXT,                                  -- which prompt they were given, if any
  seconds      REAL,                                  -- client-reported duration
  bytes        BIGINT NOT NULL,
  mime         TEXT NOT NULL,
  storage_key  TEXT NOT NULL UNIQUE,                  -- path under AUDIO_DIR
  status       TEXT NOT NULL DEFAULT 'pending_analysis',
  note         TEXT,                                  -- set by the offline pipeline
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  analyzed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS recordings_user_idx ON recordings (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS recordings_status_idx ON recordings (status) WHERE status = 'pending_analysis';

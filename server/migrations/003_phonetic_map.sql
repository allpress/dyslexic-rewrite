-- Phonetic map (v0.3): a friendly respelling shown over words the reader might struggle with.

-- Reader preference: off | on_demand | always. Lives alongside the other per-user reading
-- settings (base_profile, onboarded) that already sit directly on `users`.
ALTER TABLE users ADD COLUMN IF NOT EXISTS phonetic_map TEXT NOT NULL DEFAULT 'on_demand'
  CHECK (phonetic_map IN ('off', 'on_demand', 'always'));

-- Record which mode was active, and whether read-aloud was used, on each test attempt so the
-- A/B analysis can compare across modes later.
ALTER TABLE test_items ADD COLUMN IF NOT EXISTS phonetic_map TEXT
  CHECK (phonetic_map IS NULL OR phonetic_map IN ('off', 'on_demand', 'always'));
ALTER TABLE test_items ADD COLUMN IF NOT EXISTS read_aloud BOOLEAN NOT NULL DEFAULT FALSE;

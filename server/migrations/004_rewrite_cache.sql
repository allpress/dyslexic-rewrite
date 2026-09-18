-- Rewrite cache (v0.4): avoid re-running analyze/rewrite/phonetic-map for text + profile
-- combinations we have already seen. `key` is a sha256 of (package_version | engine |
-- profile_fingerprint | text); sample-book entries are additionally prefixed "sample:" so the
-- opportunistic cleanup below can leave them alone.

CREATE TABLE IF NOT EXISTS rewrite_cache (
  key             TEXT PRIMARY KEY,
  engine          TEXT NOT NULL,
  package_version TEXT NOT NULL,
  segments        JSONB NOT NULL,
  stats           JSONB NOT NULL,
  phonetic_map    JSONB NOT NULL,   -- stored as if phonetic_map mode == "always"; each entry
                                    -- carries its own `kind` so the server can recompute the
                                    -- `always` flag per request without recomputing the map.
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_hit        TIMESTAMPTZ,
  hits            INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS rewrite_cache_last_hit_idx ON rewrite_cache (last_hit);

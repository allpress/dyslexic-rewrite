-- Paragraph-level cache for the hosted LLM tier (docs/RESEARCH.md section 4, tier 1;
-- src/dyslexic_rewrite/rewrite/llm.py). Keyed on sha256(model | prompt version | profile
-- fingerprint | paragraph) in server/cache.py, so a small profile tweak, or the same
-- public-domain book rewritten for two readers who happen to share a profile, costs nothing to
-- re-run. Unlike `rewrite_cache` (004_rewrite_cache.sql) this table only ever stores the LLM
-- engine's output, and only an accepted (fidelity-gate-passing) rewrite is ever inserted -- a
-- rejection or a network error is never cached.
CREATE TABLE IF NOT EXISTS llm_cache (
  key         TEXT PRIMARY KEY,
  model       TEXT NOT NULL,
  output      TEXT NOT NULL,
  usage       JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  hits        INT NOT NULL DEFAULT 0
);

-- Per-book cost/usage visibility and a note for the reader when part of a book fell back to
-- the rules engine (server/library.py: more than 30% of a chapter's paragraphs did).
ALTER TABLE books ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10,6);
ALTER TABLE books ADD COLUMN IF NOT EXISTS llm_usage JSONB;
ALTER TABLE books ADD COLUMN IF NOT EXISTS engine_note TEXT;

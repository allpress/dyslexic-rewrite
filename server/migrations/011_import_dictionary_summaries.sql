-- v0.6: import from a web page (server/importer.py), dictionary lookups (server/dictionary.py)
-- and AI summaries (server/summaries.py). Also relaxes the `books.source_kind` CHECK constraint
-- from 007_library.sql to allow the new PDF/DOCX upload kinds (src/dyslexic_rewrite/io.py).

-- Postgres has no "ALTER CHECK", so the original (unnamed -> auto-named) constraint is dropped
-- and re-added with the wider list. Safe to run even if a checkout somehow already has the
-- wider constraint (IF EXISTS on the drop; the add is idempotent in effect since it always
-- re-creates the same definition).
ALTER TABLE books DROP CONSTRAINT IF EXISTS books_source_kind_check;
ALTER TABLE books ADD CONSTRAINT books_source_kind_check
  CHECK (source_kind IN ('epub', 'txt', 'md', 'pdf', 'docx'));

-- Dictionary lookups (server/dictionary.py): a cache of api.dictionaryapi.dev responses, keyed
-- on the lowercased word, so a repeated lookup -- a common word, several readers -- never re-hits
-- the upstream API. A definite "not found" is cached too (as {"_missing": true}, handled in
-- server/dictionary.py), so a typo doesn't hammer the upstream service either.
CREATE TABLE IF NOT EXISTS definitions (
  word        TEXT PRIMARY KEY,
  payload     JSONB NOT NULL,
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AI summaries (server/summaries.py, Pro only): keyed on sha256(model | prompt version |
-- profile fingerprint | max_sentence_words | text) in server/summaries.py, the same spirit as
-- `llm_cache` (009_llm_cache.sql) -- re-summarising the same text under an unchanged profile
-- costs nothing to run again. `text` stores the bullets as a JSON array.
CREATE TABLE IF NOT EXISTS summaries (
  key         TEXT PRIMARY KEY,
  text        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

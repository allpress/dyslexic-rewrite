-- "Which kind of reader am I?" screening battery (docs/RESEARCH.md, section 3).
--
-- One row per attempt. `raw` accumulates task-by-task as the reader works through the battery
-- (PATCH /api/battery/runs/{id}); `scores` is filled in once, by `POST /api/battery/runs/{id}/finish`,
-- from `dyslexic_rewrite.assess.score_battery(raw)`. Both are kept (not just the final `scores`) so
-- the provisional scoring anchors in assess.py can be re-run against real data later.
--
-- `user_id` is nullable: an anonymous reader can run the whole battery and see their radar, they
-- just cannot save or apply the result (server/app.py enforces sign-in on start/apply, not on the
-- stimuli or the scoring itself).
CREATE TABLE IF NOT EXISTS battery_runs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  raw         JSONB NOT NULL DEFAULT '{}'::jsonb,
  scores      JSONB
);

CREATE INDEX IF NOT EXISTS battery_runs_user_idx ON battery_runs (user_id, started_at DESC);

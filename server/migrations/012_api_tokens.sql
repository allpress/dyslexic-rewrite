-- Personal API tokens (v0.6): lets the browser extension ("Unwind this page") call the API
-- without a cookie. A token authenticates exactly like the session cookie (see the
-- `current_user`/`optional_user` change in server/app.py) but is meant to live in
-- `chrome.storage.local` on a device the reader controls, so it can be revoked independently
-- of signing out everywhere else.
--
-- Only the SHA-256 hash of the token is stored -- never the plaintext, which is shown to the
-- reader exactly once, at creation, by `POST /api/me/tokens`. `prefix` is the token's first
-- few characters (after the `uw_` marker), kept in the clear so the list view can show readers
-- which token is which without ever re-displaying the secret.
CREATE TABLE IF NOT EXISTS api_tokens (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,
  prefix        TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at  TIMESTAMPTZ,
  revoked_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS api_tokens_user_idx ON api_tokens (user_id, created_at DESC);

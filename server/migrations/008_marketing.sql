-- Marketing surface (v0.5): newsletter signups and a cookie-free page-view counter.
--
-- `newsletter_signups` is a plain email list -- no double opt-in in v1 (see server/marketing.py),
-- so `confirmed_at` stays NULL until we add one; `unsubscribed_at` is set by the one-click
-- unsubscribe link and cleared again if the same address signs up a second time.
--
-- `page_views` is a daily counter keyed by path and referrer host only: no cookies, no IP
-- address, no per-visitor identity of any kind. `referrer_host` is '' (not NULL) when there was
-- no referrer, so the triple stays a valid primary key.
CREATE TABLE IF NOT EXISTS newsletter_signups (
  email           TEXT PRIMARY KEY,
  source          TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_at    TIMESTAMPTZ,
  unsubscribed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS page_views (
  day           DATE NOT NULL DEFAULT CURRENT_DATE,
  path          TEXT NOT NULL,
  referrer_host TEXT NOT NULL DEFAULT '',
  count         INT NOT NULL DEFAULT 0,
  PRIMARY KEY (day, path, referrer_host)
);

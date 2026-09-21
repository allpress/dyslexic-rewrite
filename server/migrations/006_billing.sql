-- Billing (v0.5): a free tier that always works, plus a Stripe-backed "Pro" tier for
-- convenience. See server/billing.py for how these columns are read and written --
-- `users.plan`/`plan_until` is the single source of truth `is_pro()` reads, whether it was
-- set by the webhook or by hand (the grant/revoke CLI), so Pro can be gifted with no Stripe
-- involved at all.

ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_until TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE;

-- One row per Stripe subscription, mirroring what the webhook last saw. `user_id` is kept even
-- though `stripe_customer_id` already maps to a user, so a lookup never has to round-trip
-- through the customer id.
CREATE TABLE IF NOT EXISTS subscriptions (
  id                     BIGSERIAL PRIMARY KEY,
  user_id                BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stripe_subscription_id TEXT NOT NULL UNIQUE,
  status                 TEXT NOT NULL,
  price_id               TEXT,
  current_period_end     TIMESTAMPTZ,
  cancel_at_period_end   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS subscriptions_user_idx ON subscriptions (user_id);

-- Webhook idempotency: Stripe retries deliveries, so every event id is recorded before it is
-- acted on, and a replay is a no-op (server/billing.py's handle_webhook checks this first).
CREATE TABLE IF NOT EXISTS billing_events (
  stripe_event_id TEXT PRIMARY KEY,
  type            TEXT NOT NULL,
  received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

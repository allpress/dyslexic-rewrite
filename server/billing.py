"""Billing: a free tier that always works, and a Stripe-backed "Pro" tier for convenience.

The `dyslexic_rewrite` engine stays MIT-licensed and works with no billing at all; this module
only gates the *site's* convenience features (unlimited book conversions, a bigger paste limit,
the higher-quality LLM engine tier). `users.plan` / `users.plan_until` is the single source of
truth `is_pro()` reads, so a plan set by hand (the `grant`/`revoke` CLI below) works identically
to one Stripe sets through the webhook -- useful for gifting Pro to testers without touching
Stripe at all.

If `STRIPE_SECRET_KEY` isn't set, every route below returns 503 `{"error": "Billing is not set
up yet"}`, and `is_pro()` / `plan_summary()` / `quota()` still work off whatever is already in
the database.

CLI (works with no Stripe configured -- Postgres only):
    python -m server.billing grant EMAIL [--months N]   # N omitted = no expiry, until revoked
    python -m server.billing revoke EMAIL
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import auth, db

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "")
STRIPE_PRICE_YEARLY = os.environ.get("STRIPE_PRICE_YEARLY", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://unwindwords.com").rstrip("/")

stripe.api_key = STRIPE_SECRET_KEY

# A lapsed payment doesn't cut a reader off mid-read: Pro stays live for a few days past the
# period Stripe told us about, so a slow card retry or a webhook delay never bites a real payer.
GRACE_PERIOD = timedelta(days=3)

# Shown on /pricing when Stripe isn't configured yet, so the page still renders sensibly.
PLACEHOLDER_MONTHLY_CENTS = 500
PLACEHOLDER_YEARLY_CENTS = 3900

# Free-tier limits (server/API.md, "Billing (v0.5)"); Pro lifts all three.
FREE_BOOKS_TOTAL = 1
FREE_PASTE_CHARS = 20_000
PRO_PASTE_CHARS = 200_000

# A subscription in one of these statuses counts as paying; the others count as lapsed.
_PRO_STATUSES = {"active", "trialing", "past_due"}
_INACTIVE_STATUSES = {"canceled", "unpaid", "incomplete_expired"}

BILLING_NOT_SET_UP = "Billing is not set up yet"


def configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


# ---------------------------------------------------------------------------------------
# plan state -- reads only `users.plan` / `users.plan_until`, never touches Stripe
# ---------------------------------------------------------------------------------------
def is_pro(user_row: dict | None) -> bool:
    """True if this user currently has Pro -- works with no Stripe configured at all, since
    it only ever reads the two columns a human (via the CLI) or the webhook can set."""
    if not user_row or user_row.get("plan") != "pro":
        return False
    until = user_row.get("plan_until")
    return until is None or until > datetime.now(timezone.utc)


def plan_summary(user_row: dict) -> dict[str, Any]:
    with db.conn() as c:
        sub = c.execute(
            "SELECT cancel_at_period_end FROM subscriptions WHERE user_id = %s "
            "ORDER BY updated_at DESC LIMIT 1", (user_row["id"],),
        ).fetchone()
    plan_until = user_row.get("plan_until")
    return {
        "plan": user_row.get("plan", "free"),
        "pro": is_pro(user_row),
        "plan_until": plan_until.isoformat() if plan_until else None,
        "cancel_at_period_end": bool(sub["cancel_at_period_end"]) if sub else False,
        "manageable": bool(user_row.get("stripe_customer_id")),
    }


def quota(user_row: dict | None) -> dict[str, Any]:
    """Free-tier limits for `user_row` (`None` = anonymous, always free)."""
    pro = is_pro(user_row)
    return {
        "books_total": None if pro else FREE_BOOKS_TOTAL,
        "paste_chars": PRO_PASTE_CHARS if pro else FREE_PASTE_CHARS,
        "llm_tier": pro and bool(os.environ.get("DYSREWRITE_LLM_BASE_URL")),
    }


class ProRequiredError(HTTPException):
    """A distinct HTTPException subclass so `server/app.py` can register a handler for it that
    returns the flat `{"error": "pro_required", ...}` shape (not the generic `{"error": <str>}`
    every other route gets) without changing that generic handler at all."""

    def __init__(self, message: str) -> None:
        super().__init__(402, {"error": "pro_required", "message": message, "upgrade": "/pricing"})


def require_pro(user_row: dict, message: str | None = None) -> None:
    """Raise 402 unless `user_row` currently has Pro. For other modules (e.g. the book library)
    to gate a Pro-only feature without depending on this module's Stripe internals."""
    if not is_pro(user_row):
        raise ProRequiredError(message or "This feature is part of Unwind Words Pro.")


# ---------------------------------------------------------------------------------------
# plans -- public, cached in-process for an hour so /pricing never waits on Stripe
# ---------------------------------------------------------------------------------------
_plans_lock = threading.Lock()
_plans_cache: dict[str, Any] | None = None
_plans_cache_at: float = 0.0
PLANS_CACHE_SECONDS = 3600


def _placeholder_plans(configured_flag: bool) -> dict[str, Any]:
    return {
        "monthly": {"price_id": STRIPE_PRICE_MONTHLY or None, "amount": PLACEHOLDER_MONTHLY_CENTS,
                    "currency": "usd", "interval": "month"},
        "yearly": {"price_id": STRIPE_PRICE_YEARLY or None, "amount": PLACEHOLDER_YEARLY_CENTS,
                   "currency": "usd", "interval": "year"},
        "configured": configured_flag,
    }


def get_plans() -> dict[str, Any]:
    global _plans_cache, _plans_cache_at
    with _plans_lock:
        now = time.monotonic()
        if _plans_cache is not None and (now - _plans_cache_at) < PLANS_CACHE_SECONDS:
            return _plans_cache
        if not configured():
            result = _placeholder_plans(False)
        else:
            try:
                monthly = stripe.Price.retrieve(STRIPE_PRICE_MONTHLY)
                yearly = stripe.Price.retrieve(STRIPE_PRICE_YEARLY)
                result = {
                    "monthly": {"price_id": monthly["id"], "amount": monthly["unit_amount"],
                                "currency": monthly["currency"], "interval": monthly["recurring"]["interval"]},
                    "yearly": {"price_id": yearly["id"], "amount": yearly["unit_amount"],
                               "currency": yearly["currency"], "interval": yearly["recurring"]["interval"]},
                    "configured": True,
                }
            except Exception as e:  # Stripe down, bad price id, no network in dev ...
                print(f"[billing] failed to fetch Stripe prices: {e}")
                result = _placeholder_plans(False)
        _plans_cache, _plans_cache_at = result, now
        return result


# ---------------------------------------------------------------------------------------
# Stripe customer + Checkout + portal
# ---------------------------------------------------------------------------------------
def _get_or_create_customer(user_row: dict) -> str:
    if user_row.get("stripe_customer_id"):
        return user_row["stripe_customer_id"]
    existing = stripe.Customer.list(email=user_row["email"], limit=1).get("data") or []
    customer = existing[0] if existing else stripe.Customer.create(
        email=user_row["email"], metadata={"user_id": str(user_row["id"])},
    )
    with db.conn() as c:
        c.execute("UPDATE users SET stripe_customer_id = %s WHERE id = %s", (customer["id"], user_row["id"]))
        c.commit()
    return customer["id"]


def create_checkout_session(user_row: dict, interval: str) -> str:
    if interval not in ("monthly", "yearly"):
        raise HTTPException(400, "interval must be 'monthly' or 'yearly'.")
    price_id = STRIPE_PRICE_MONTHLY if interval == "monthly" else STRIPE_PRICE_YEARLY
    if not price_id:
        raise HTTPException(503, BILLING_NOT_SET_UP)
    customer_id = _get_or_create_customer(user_row)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{PUBLIC_BASE_URL}/profile?upgraded=1",
        cancel_url=f"{PUBLIC_BASE_URL}/pricing",
        allow_promotion_codes=True,
        client_reference_id=str(user_row["id"]),
    )
    return session["url"]


def create_portal_session(user_row: dict) -> str:
    if not user_row.get("stripe_customer_id"):
        raise HTTPException(400, "Start a checkout first -- there's no billing account yet.")
    session = stripe.billing_portal.Session.create(
        customer=user_row["stripe_customer_id"], return_url=f"{PUBLIC_BASE_URL}/profile",
    )
    return session["url"]


# ---------------------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------------------
def _to_dt(ts: Any) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def _price_id_of(sub: dict) -> str | None:
    try:
        return sub["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return sub.get("price_id")  # flat fallback, for simpler hand-built test payloads


def _user_by_customer(customer_id: str | None) -> dict | None:
    if not customer_id:
        return None
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE stripe_customer_id = %s", (customer_id,)).fetchone()


def _set_plan(user_id: int, plan: str, plan_until: datetime | None) -> None:
    with db.conn() as c:
        c.execute("UPDATE users SET plan = %s, plan_until = %s WHERE id = %s", (plan, plan_until, user_id))
        c.commit()


def _upsert_subscription(user_id: int, sub: dict) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO subscriptions (user_id, stripe_subscription_id, status, price_id, "
            "current_period_end, cancel_at_period_end, updated_at) VALUES (%s, %s, %s, %s, %s, %s, now()) "
            "ON CONFLICT (stripe_subscription_id) DO UPDATE SET status = EXCLUDED.status, "
            "price_id = EXCLUDED.price_id, current_period_end = EXCLUDED.current_period_end, "
            "cancel_at_period_end = EXCLUDED.cancel_at_period_end, updated_at = now()",
            (user_id, sub["id"], sub.get("status", ""), _price_id_of(sub),
             _to_dt(sub.get("current_period_end")), bool(sub.get("cancel_at_period_end", False))),
        )
        c.commit()


def _apply_checkout_completed(obj: dict) -> None:
    """Associate the Checkout customer with the signed-in user who started it. The subscription
    itself (status, period end, price) arrives moments later as its own `customer.subscription.*`
    event, which is what actually flips `users.plan` -- this just closes the loop for a customer
    the checkout created that our own `_get_or_create_customer` didn't already know about."""
    ref = obj.get("client_reference_id")
    customer_id = obj.get("customer")
    if not ref or not customer_id:
        return
    with db.conn() as c:
        c.execute(
            "UPDATE users SET stripe_customer_id = %s WHERE id = %s AND stripe_customer_id IS NULL",
            (customer_id, int(ref)),
        )
        c.commit()


def _apply_subscription(obj: dict) -> None:
    user = _user_by_customer(obj.get("customer"))
    if not user:
        return
    _upsert_subscription(user["id"], obj)
    status = obj.get("status", "")
    if status in _PRO_STATUSES:
        period_end = _to_dt(obj.get("current_period_end"))
        plan_until = (period_end + GRACE_PERIOD) if period_end else None
        _set_plan(user["id"], "pro", plan_until)
    elif status in _INACTIVE_STATUSES:
        _set_plan(user["id"], "free", None)


def _apply_subscription_deleted(obj: dict) -> None:
    user = _user_by_customer(obj.get("customer"))
    if not user:
        return
    canceled = {**obj, "status": "canceled"}
    _upsert_subscription(user["id"], canceled)
    _set_plan(user["id"], "free", None)


def _apply_invoice_paid(obj: dict) -> None:
    user = _user_by_customer(obj.get("customer"))
    if not user:
        return
    period_end = _to_dt(obj.get("period_end"))
    plan_until = (period_end + GRACE_PERIOD) if period_end else user.get("plan_until")
    _set_plan(user["id"], "pro", plan_until)
    sub_id = obj.get("subscription")
    if sub_id and period_end:
        with db.conn() as c:
            c.execute(
                "UPDATE subscriptions SET current_period_end = %s, status = 'active', updated_at = now() "
                "WHERE stripe_subscription_id = %s", (period_end, sub_id),
            )
            c.commit()


def _apply_invoice_failed(obj: dict) -> None:
    """Doesn't downgrade on its own -- the grace period covers a slow retry, and Stripe's own
    later `customer.subscription.updated` (status `past_due`/`unpaid`) is what actually acts."""
    sub_id = obj.get("subscription")
    if not sub_id:
        return
    with db.conn() as c:
        c.execute(
            "UPDATE subscriptions SET status = 'past_due', updated_at = now() "
            "WHERE stripe_subscription_id = %s", (sub_id,),
        )
        c.commit()


_WEBHOOK_HANDLERS = {
    "checkout.session.completed": _apply_checkout_completed,
    "customer.subscription.created": _apply_subscription,
    "customer.subscription.updated": _apply_subscription,
    "customer.subscription.deleted": _apply_subscription_deleted,
    "invoice.paid": _apply_invoice_paid,
    "invoice.payment_failed": _apply_invoice_failed,
}


def handle_webhook(payload: bytes, sig_header: str | None) -> dict[str, Any]:
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, BILLING_NOT_SET_UP)
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(400, "Invalid webhook signature.") from e

    event_id, event_type = event["id"], event["type"]
    with db.conn() as c:
        inserted = c.execute(
            "INSERT INTO billing_events (stripe_event_id, type) VALUES (%s, %s) "
            "ON CONFLICT (stripe_event_id) DO NOTHING RETURNING stripe_event_id",
            (event_id, event_type),
        ).fetchone()
        c.commit()
    if not inserted:
        return {"ok": True, "duplicate": True}  # already processed -- a Stripe retry, no-op

    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler:
        handler(event["data"]["object"])
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------------------
def _user_row(user_id: int) -> dict | None:
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def _current_user(request: Request) -> dict:
    """A private copy of `server.app.current_user` -- kept local so this module has no import
    dependency on `server.app` (which imports this module)."""
    uid = auth.read_session(request.cookies.get(auth.COOKIE))
    u = _user_row(uid) if uid else None
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def _require_configured() -> None:
    if not configured():
        raise HTTPException(503, BILLING_NOT_SET_UP)


class CheckoutIn(BaseModel):
    interval: str


router = APIRouter(prefix="/api/billing")


@router.get("/plans")
def plans_route():
    return get_plans()


@router.post("/checkout")
def checkout_route(body: CheckoutIn, u: dict = Depends(_current_user)):
    _require_configured()
    return {"url": create_checkout_session(u, body.interval)}


@router.post("/portal")
def portal_route(u: dict = Depends(_current_user)):
    _require_configured()
    return {"url": create_portal_session(u)}


@router.post("/webhook")
async def webhook_route(request: Request):
    _require_configured()
    payload = await request.body()
    return handle_webhook(payload, request.headers.get("stripe-signature"))


@router.get("/status")
def status_route(u: dict = Depends(_current_user)):
    return plan_summary(u)


# ---------------------------------------------------------------------------------------
# CLI: grant/revoke Pro by hand -- Postgres only, no Stripe needed
# ---------------------------------------------------------------------------------------
def _cli_grant(email: str, months: int) -> None:
    email = email.strip().lower()
    with db.conn() as c:
        row = c.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if not row:
            print(f"No such user: {email}", file=sys.stderr)
            raise SystemExit(1)
        plan_until = datetime.now(timezone.utc) + timedelta(days=30 * months) if months else None
        c.execute("UPDATE users SET plan = 'pro', plan_until = %s WHERE id = %s", (plan_until, row["id"]))
        c.commit()
    until_str = plan_until.isoformat() if plan_until else "no expiry (until revoked)"
    print(f"Granted Pro to {email} -- {until_str}")


def _cli_revoke(email: str) -> None:
    email = email.strip().lower()
    with db.conn() as c:
        row = c.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if not row:
            print(f"No such user: {email}", file=sys.stderr)
            raise SystemExit(1)
        c.execute("UPDATE users SET plan = 'free', plan_until = NULL WHERE id = %s", (row["id"],))
        c.commit()
    print(f"Revoked Pro from {email}")


def _cli_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m server.billing",
        description="Grant or revoke Pro by hand. Works with no Stripe configured -- Postgres only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    grant_p = sub.add_parser("grant", help="Grant Pro to a user by email.")
    grant_p.add_argument("email")
    grant_p.add_argument("--months", type=int, default=0, help="Expire after N months (default: no expiry).")

    revoke_p = sub.add_parser("revoke", help="Revoke Pro from a user by email.")
    revoke_p.add_argument("email")

    args = parser.parse_args(argv)
    if args.command == "grant":
        _cli_grant(args.email, args.months)
    elif args.command == "revoke":
        _cli_revoke(args.email)


if __name__ == "__main__":  # pragma: no cover
    _cli_main()

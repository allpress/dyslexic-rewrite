"""Billing tests. Need a Postgres at DATABASE_URL (or TEST_DATABASE_URL); skipped otherwise.

Stripe itself is never called: the plan/quota logic is tested directly, the webhook is tested by
monkeypatching `stripe.Webhook.construct_event` with a hand-built event (real signature
verification is Stripe's own well-tested code, not ours), and "unconfigured" is simply this
process's real state -- no STRIPE_SECRET_KEY is set anywhere in the test environment.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")

os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dysrewrite"))
os.environ["SECURE_COOKIES"] = "0"
os.environ.pop("RESEND_API_KEY", None)

try:
    import psycopg
    psycopg.connect(os.environ["DATABASE_URL"]).close()
except Exception as e:  # pragma: no cover
    pytest.skip(f"no Postgres for billing tests: {e}", allow_module_level=True)

import stripe  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server import billing, db  # noqa: E402
from server.app import app  # noqa: E402


def _clear_billing_test_state() -> None:
    """`billing_events`/`subscriptions` are real Postgres state that outlives one pytest run
    (unlike the fake in-memory Stripe calls), so webhook tests start from a known-clean slate
    rather than assuming their event ids have never been seen before."""
    with db.conn() as c:
        c.execute("DELETE FROM billing_events WHERE stripe_event_id LIKE 'evt_test%'")
        c.execute("DELETE FROM subscriptions WHERE stripe_subscription_id LIKE 'sub_test%' "
                  "OR stripe_subscription_id LIKE 'sub_new%'")
        c.commit()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs migrations, incl. 006_billing.sql
        _clear_billing_test_state()
        yield c


def _make_user(c: TestClient, email: str) -> int:
    r = c.post("/api/auth/request-code", json={"email": email}).json()
    ok = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"]})
    assert ok.status_code == 200
    return int(ok.json()["user"]["id"])


def _delete_user(email: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM users WHERE email = %s", (email,))
        c.execute("DELETE FROM login_codes WHERE email = %s", (email,))
        c.commit()


def _row(user_id: int) -> dict:
    with db.conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


# ---------------------------------------------------------------------------------------
# is_pro: pure logic, no Stripe, no route
# ---------------------------------------------------------------------------------------
def test_is_pro_truth_table():
    now = datetime.now(timezone.utc)
    assert billing.is_pro(None) is False
    assert billing.is_pro({"plan": "free", "plan_until": None}) is False
    assert billing.is_pro({"plan": "free", "plan_until": now + timedelta(days=30)}) is False
    assert billing.is_pro({"plan": "pro", "plan_until": None}) is True  # no expiry -> pro forever
    assert billing.is_pro({"plan": "pro", "plan_until": now + timedelta(days=1)}) is True
    assert billing.is_pro({"plan": "pro", "plan_until": now - timedelta(seconds=1)}) is False  # just expired
    # the grace period itself is baked into plan_until by the webhook (current_period_end + 3
    # days) -- is_pro just compares against "now", so a plan_until still inside the grace window
    # reads as pro, and one past it does not.
    assert billing.is_pro({"plan": "pro", "plan_until": now + timedelta(days=2, hours=23)}) is True
    assert billing.is_pro({"plan": "pro", "plan_until": now - timedelta(days=4)}) is False


def test_quota_free_vs_pro(monkeypatch):
    monkeypatch.delenv("DYSREWRITE_LLM_BASE_URL", raising=False)
    free = billing.quota(None)
    assert free == {"books_total": 1, "paste_chars": 20_000, "llm_tier": False}
    pro_row = {"plan": "pro", "plan_until": None}
    pro = billing.quota(pro_row)
    assert pro["books_total"] is None and pro["paste_chars"] == 200_000
    assert pro["llm_tier"] is False  # no DYSREWRITE_LLM_BASE_URL set
    monkeypatch.setenv("DYSREWRITE_LLM_BASE_URL", "http://localhost:11434")
    assert billing.quota(pro_row)["llm_tier"] is True
    assert billing.quota(None)["llm_tier"] is False  # free never gets the LLM tier


def test_require_pro_raises_402_for_free_users():
    with pytest.raises(HTTPException) as exc:
        billing.require_pro({"plan": "free", "plan_until": None})
    assert exc.value.status_code == 402
    assert exc.value.detail["error"] == "pro_required"
    assert exc.value.detail["upgrade"] == "/pricing"
    billing.require_pro({"plan": "pro", "plan_until": None})  # does not raise


# ---------------------------------------------------------------------------------------
# unconfigured server: no STRIPE_SECRET_KEY anywhere in this test environment
# ---------------------------------------------------------------------------------------
def test_unconfigured_plans_are_placeholders(client):
    assert billing.configured() is False
    body = client.get("/api/billing/plans").json()
    assert body["configured"] is False
    assert body["monthly"]["amount"] == 500 and body["monthly"]["currency"] == "usd"
    assert body["yearly"]["amount"] == 3900


def test_unconfigured_checkout_and_portal_and_webhook_503(client):
    email = "pytest-billing-unconfigured@example.com"
    _make_user(client, email)
    try:
        r = client.post("/api/billing/checkout", json={"interval": "monthly"})
        assert r.status_code == 503 and r.json()["error"] == "Billing is not set up yet"
        r = client.post("/api/billing/portal")
        assert r.status_code == 503 and r.json()["error"] == "Billing is not set up yet"
        r = client.post("/api/billing/webhook", content=b"{}")
        assert r.status_code == 503 and r.json()["error"] == "Billing is not set up yet"
    finally:
        client.delete("/api/me")
        _delete_user(email)


def test_billing_status_and_me_work_with_no_stripe_configured(client):
    email = "pytest-billing-status@example.com"
    _make_user(client, email)
    try:
        status = client.get("/api/billing/status").json()
        assert status == {"plan": "free", "pro": False, "plan_until": None,
                           "cancel_at_period_end": False, "manageable": False}
        me = client.get("/api/me").json()
        assert me["plan"] == status
        assert me["user"]["plan"] == status
    finally:
        client.delete("/api/me")
        _delete_user(email)


# ---------------------------------------------------------------------------------------
# webhook: hand-built events, no network, idempotent by event id
# ---------------------------------------------------------------------------------------
class _FakeEvents:
    """Queues one fake stripe Event dict per call to construct_event, ignoring signature checks
    entirely -- the payload/sig_header/secret this hands to Stripe's real code are never touched,
    since it's Stripe's own signature verification we're not re-testing here."""

    def __init__(self):
        self._next: dict | None = None

    def push(self, event_id: str, event_type: str, obj: dict) -> None:
        self._next = {"id": event_id, "type": event_type, "data": {"object": obj}}

    def construct_event(self, payload, sig_header, secret):
        assert self._next is not None, "no fake event queued"
        return self._next


@pytest.fixture
def fake_stripe(monkeypatch):
    events = _FakeEvents()
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(stripe.Webhook, "construct_event", events.construct_event)
    return events


@pytest.fixture
def billing_user(client):
    email = "pytest-billing-webhook@example.com"
    uid = _make_user(client, email)
    with db.conn() as c:
        c.execute("UPDATE users SET stripe_customer_id = %s WHERE id = %s", ("cus_test_1", uid))
        c.commit()
    yield uid
    client.delete("/api/me")
    _delete_user(email)


def test_webhook_subscription_updated_flips_plan_to_pro_and_is_idempotent(fake_stripe, billing_user):
    period_end = datetime.now(timezone.utc) + timedelta(days=27)
    sub = {
        "id": "sub_test_1", "customer": "cus_test_1", "status": "active",
        "current_period_end": int(period_end.timestamp()), "cancel_at_period_end": False,
        "price_id": "price_test_monthly",
    }
    fake_stripe.push("evt_test_1", "customer.subscription.updated", sub)
    result = billing.handle_webhook(b"{}", "sig")
    assert result == {"ok": True}

    row = _row(billing_user)
    assert row["plan"] == "pro"
    assert abs((row["plan_until"] - (period_end + billing.GRACE_PERIOD)).total_seconds()) < 2

    with db.conn() as c:
        subrow = c.execute(
            "SELECT * FROM subscriptions WHERE stripe_subscription_id = %s", ("sub_test_1",),
        ).fetchone()
    assert subrow["status"] == "active" and subrow["price_id"] == "price_test_monthly"

    # Replay the exact same event (Stripe retries deliveries): dedup by event id means this must
    # be a pure no-op, not just "harmless" -- prove it by flipping the plan by hand first.
    with db.conn() as c:
        c.execute("UPDATE users SET plan = 'free', plan_until = NULL WHERE id = %s", (billing_user,))
        c.commit()
    fake_stripe.push("evt_test_1", "customer.subscription.updated", sub)  # same event id
    replay = billing.handle_webhook(b"{}", "sig")
    assert replay == {"ok": True, "duplicate": True}
    assert _row(billing_user)["plan"] == "free"  # untouched by the replay


def test_webhook_subscription_deleted_and_invoice_payment_failed(fake_stripe, billing_user):
    period_end = datetime.now(timezone.utc) + timedelta(days=27)
    sub = {
        "id": "sub_test_2", "customer": "cus_test_1", "status": "active",
        "current_period_end": int(period_end.timestamp()),
    }
    fake_stripe.push("evt_test_2", "customer.subscription.created", sub)
    billing.handle_webhook(b"{}", "sig")
    assert _row(billing_user)["plan"] == "pro"

    fake_stripe.push("evt_test_3", "invoice.payment_failed", {"customer": "cus_test_1", "subscription": "sub_test_2"})
    billing.handle_webhook(b"{}", "sig")
    with db.conn() as c:
        subrow = c.execute(
            "SELECT status FROM subscriptions WHERE stripe_subscription_id = %s", ("sub_test_2",),
        ).fetchone()
    assert subrow["status"] == "past_due"

    fake_stripe.push("evt_test_4", "customer.subscription.deleted", {**sub, "status": "canceled"})
    billing.handle_webhook(b"{}", "sig")
    row = _row(billing_user)
    assert row["plan"] == "free" and row["plan_until"] is None


def test_webhook_checkout_completed_sets_customer_id(fake_stripe, client):
    email = "pytest-billing-checkout@example.com"
    uid = _make_user(client, email)
    try:
        assert _row(uid)["stripe_customer_id"] is None
        fake_stripe.push("evt_test_checkout_1", "checkout.session.completed", {
            "customer": "cus_new_1", "client_reference_id": str(uid), "subscription": "sub_new_1",
        })
        billing.handle_webhook(b"{}", "sig")
        assert _row(uid)["stripe_customer_id"] == "cus_new_1"
    finally:
        client.delete("/api/me")
        _delete_user(email)


def test_webhook_bad_signature_is_400(monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "whsec_test")

    def _boom(payload, sig_header, secret):
        raise stripe.SignatureVerificationError("bad sig", sig_header)

    monkeypatch.setattr(stripe.Webhook, "construct_event", _boom)
    with pytest.raises(HTTPException) as exc:
        billing.handle_webhook(b"{}", "sig")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------------------
# grant/revoke CLI -- works with no Stripe at all
# ---------------------------------------------------------------------------------------
def test_grant_and_revoke_cli(client):
    email = "pytest-billing-cli@example.com"
    uid = _make_user(client, email)
    try:
        assert billing.is_pro(_row(uid)) is False

        billing._cli_main(["grant", email, "--months", "1"])
        row = _row(uid)
        assert row["plan"] == "pro"
        assert row["plan_until"] is not None
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert abs((row["plan_until"] - expected).total_seconds()) < 60
        assert billing.is_pro(row) is True

        billing._cli_main(["grant", email])  # no --months -> no expiry
        row = _row(uid)
        assert row["plan"] == "pro" and row["plan_until"] is None

        billing._cli_main(["revoke", email])
        row = _row(uid)
        assert row["plan"] == "free" and row["plan_until"] is None
        assert billing.is_pro(row) is False
    finally:
        client.delete("/api/me")
        _delete_user(email)


def test_grant_unknown_email_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        billing._cli_main(["grant", "not-a-real-user@example.com"])
    assert exc.value.code == 1

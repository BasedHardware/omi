"""Tests that one invalid Stripe price ID doesn't hide all plans.

Exercises the real get_available_plans_endpoint() from routers/payment.py
with mocked Stripe, so a regression in the per-price try/except blocks
would be caught.
"""

from unittest.mock import MagicMock

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import users as users_db
from routers import payment as payment_router

# Real Stripe dev price IDs
UNLIM_MONTHLY = "price_1RrxXL1F8wnoWYvwIddzR902"
UNLIM_ANNUAL = "price_1RrxXL1F8wnoWYvw3kDbWmjs"
ARCH_MONTHLY = "price_1TAznX1F8wnoWYvwyaSVQbZW"
ARCH_ANNUAL = "price_1TAznX1F8wnoWYvwN8YmzbiC"


@pytest.fixture(scope="module")
def ctx():
    """Build the real router under test with its DB/Stripe seams patched.

    ``routers.payment`` imports cleanly now (Tier-1 import purity done for its
    chain), so the sanctioned seam is ``monkeypatch.setattr`` on the real
    ``database.users`` singletons the endpoint calls at request time, plus the
    real ``stripe`` module attributes. No ``sys.modules`` mutation.
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", UNLIM_MONTHLY)
    mp.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", UNLIM_ANNUAL)
    mp.setenv("STRIPE_ARCHITECT_MONTHLY_PRICE_ID", ARCH_MONTHLY)
    mp.setenv("STRIPE_ARCHITECT_ANNUAL_PRICE_ID", ARCH_ANNUAL)

    # DB helpers the endpoint reaches at request time. Tests reconfigure
    # ``return_value`` per-case via these persistent MagicMock objects.
    get_user_subscription = MagicMock(return_value=None)
    get_stripe_customer_id = MagicMock(return_value=None)
    mp.setattr(users_db, "get_user_subscription", get_user_subscription)
    mp.setattr(users_db, "get_stripe_customer_id", get_stripe_customer_id)

    mp.setattr(stripe, "api_key", "sk_test_fake")

    app = FastAPI()
    app.include_router(payment_router.router)
    app.dependency_overrides[payment_router.auth.get_current_user_uid_no_byok_validation] = lambda: "test-user"
    client = TestClient(app)

    yield {
        "client": client,
        "get_user_subscription": get_user_subscription,
        "get_stripe_customer_id": get_stripe_customer_id,
    }
    mp.undo()


def _make_stripe_price(price_id, amount, interval):
    """Return a MagicMock mimicking a stripe.Price object."""
    price = MagicMock()
    price.id = price_id
    price.unit_amount = amount
    price.recurring = MagicMock()
    price.recurring.interval = interval
    return price


def test_invalid_architect_price_skips_architect_but_unlimited_remains(ctx):
    """When stripe.Price.retrieve fails for Architect prices, only Unlimited plans are returned."""
    ctx["get_user_subscription"].return_value = None

    def _mock_retrieve(price_id):
        if price_id in (ARCH_MONTHLY, ARCH_ANNUAL):
            raise Exception(f"No such price: {price_id}")
        if price_id == UNLIM_MONTHLY:
            return _make_stripe_price(price_id, 1900, "month")
        if price_id == UNLIM_ANNUAL:
            return _make_stripe_price(price_id, 18000, "year")
        raise Exception(f"Unexpected price_id: {price_id}")

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = ctx["client"].get("/v1/payments/available-plans")

    assert response.status_code == 200
    data = response.json()
    plans = data["plans"]

    # Unlimited monthly + annual should be present
    plan_ids = {p["id"] for p in plans}
    assert UNLIM_MONTHLY in plan_ids
    assert UNLIM_ANNUAL in plan_ids

    # Architect prices should be absent (their retrieval failed)
    assert ARCH_MONTHLY not in plan_ids
    assert ARCH_ANNUAL not in plan_ids

    assert len(plans) == 2


def test_all_valid_prices_returns_all_plans(ctx):
    """When all Stripe prices are valid, all four pricing options are returned."""
    ctx["get_user_subscription"].return_value = None

    def _mock_retrieve(price_id):
        intervals = {UNLIM_MONTHLY: "month", UNLIM_ANNUAL: "year", ARCH_MONTHLY: "month", ARCH_ANNUAL: "year"}
        amounts = {UNLIM_MONTHLY: 1900, UNLIM_ANNUAL: 18000, ARCH_MONTHLY: 990, ARCH_ANNUAL: 9900}
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = ctx["client"].get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]
    plan_ids = {p["id"] for p in plans}
    assert plan_ids == {UNLIM_MONTHLY, UNLIM_ANNUAL, ARCH_MONTHLY, ARCH_ANNUAL}
    assert len(plans) == 4


def test_legacy_unlimited_subscriber_sees_is_active(ctx):
    """Legacy Unlimited subscriber gets their plan with is_active=True in catalog."""
    from models.users import Subscription, SubscriptionStatus, PlanType

    sub = Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_legacy_123",
        cancel_at_period_end=False,
    )
    ctx["get_user_subscription"].return_value = sub

    # Mock Stripe subscription retrieval to return the monthly price
    stripe_sub = MagicMock()
    stripe_sub.to_dict.return_value = {
        "items": {"data": [{"price": {"id": UNLIM_MONTHLY}}]},
        "customer": "cus_123",
    }
    stripe.Subscription.retrieve = MagicMock(return_value=stripe_sub)
    stripe.SubscriptionSchedule.list = MagicMock(return_value=MagicMock(data=[]))

    def _mock_retrieve(price_id):
        intervals = {UNLIM_MONTHLY: "month", UNLIM_ANNUAL: "year", ARCH_MONTHLY: "month", ARCH_ANNUAL: "year"}
        amounts = {UNLIM_MONTHLY: 1900, UNLIM_ANNUAL: 18000, ARCH_MONTHLY: 990, ARCH_ANNUAL: 9900}
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = ctx["client"].get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]

    # Legacy unlimited subscriber should have their monthly plan marked active
    active_plans = [p for p in plans if p["is_active"]]
    assert len(active_plans) == 1
    assert active_plans[0]["id"] == UNLIM_MONTHLY
    assert active_plans[0]["interval"] == "month"


def test_operator_subscriber_on_old_client_gets_remapped_is_active(ctx, monkeypatch):
    """Operator subscriber on old client (no platform header) gets price remapped to Unlimited."""
    from models.users import Subscription, SubscriptionStatus, PlanType

    OP_MONTHLY = "price_operator_monthly_test"
    monkeypatch.setenv("STRIPE_OPERATOR_MONTHLY_PRICE_ID", OP_MONTHLY)

    sub = Subscription(
        plan=PlanType.operator,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_operator_123",
        cancel_at_period_end=False,
    )
    ctx["get_user_subscription"].return_value = sub

    stripe_sub = MagicMock()
    stripe_sub.to_dict.return_value = {
        "items": {"data": [{"price": {"id": OP_MONTHLY}}]},
        "customer": "cus_456",
    }
    stripe.Subscription.retrieve = MagicMock(return_value=stripe_sub)
    stripe.SubscriptionSchedule.list = MagicMock(return_value=MagicMock(data=[]))

    def _mock_retrieve(price_id):
        intervals = {UNLIM_MONTHLY: "month", UNLIM_ANNUAL: "year", ARCH_MONTHLY: "month", ARCH_ANNUAL: "year"}
        amounts = {UNLIM_MONTHLY: 1900, UNLIM_ANNUAL: 18000, ARCH_MONTHLY: 990, ARCH_ANNUAL: 9900}
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    # No platform header → old client → adapt_plans_for_legacy_client + price remap
    response = ctx["client"].get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]

    # Operator price should be remapped to Unlimited monthly, so is_active is set
    active_plans = [p for p in plans if p["is_active"]]
    assert len(active_plans) == 1
    assert active_plans[0]["id"] == UNLIM_MONTHLY
    assert active_plans[0]["interval"] == "month"


def test_all_prices_fail_returns_500(ctx):
    """When every stripe.Price.retrieve call fails, endpoint returns HTTP 500."""
    ctx["get_user_subscription"].return_value = None
    stripe.Price.retrieve = MagicMock(side_effect=Exception("Stripe is down"))

    response = ctx["client"].get("/v1/payments/available-plans")

    assert response.status_code == 500

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
# Omi Pro (unlimited_v2) — the single plan a header-less new buyer may see
# under the 2026-10-24 ruling.
PRO_MONTHLY = "price_unlimited_v2_monthly_test"
PRO_ANNUAL = "price_unlimited_v2_annual_test"


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
    mp.setenv("STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID", PRO_MONTHLY)
    mp.setenv("STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID", PRO_ANNUAL)

    # DB helpers the endpoint reaches at request time. Tests reconfigure
    # ``return_value`` per-case via these persistent MagicMock objects.
    get_user_subscription = MagicMock(return_value=None)
    get_user_valid_subscription = MagicMock(return_value=None)
    get_stripe_customer_id = MagicMock(return_value=None)
    mp.setattr(users_db, "get_user_subscription", get_user_subscription)
    mp.setattr(users_db, "get_user_valid_subscription", get_user_valid_subscription)
    mp.setattr(users_db, "get_stripe_customer_id", get_stripe_customer_id)

    mp.setattr(stripe, "api_key", "sk_test_fake")

    app = FastAPI()
    app.include_router(payment_router.router)
    app.dependency_overrides[payment_router.auth.get_current_user_uid_no_byok_validation] = lambda: "test-user"
    client = TestClient(app)

    yield {
        "client": client,
        "get_user_subscription": get_user_subscription,
        "get_user_valid_subscription": get_user_valid_subscription,
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


def test_invalid_architect_price_skips_architect_but_unlimited_remains(ctx, monkeypatch):
    """When stripe.Price.retrieve fails for Architect prices, only Unlimited plans are returned.

    The multi-plan shape needs the pre-ruling catalog, so this runs with the
    new-buyer single-plan kill switch off; the ruling's own catalog shape is
    pinned in test_new_buyer_headerless_gets_single_plan_catalog below."""
    ctx["get_user_subscription"].return_value = None
    monkeypatch.setenv("NEW_BUYER_SINGLE_PLAN_ENABLED", "false")

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


def test_all_valid_prices_returns_all_plans(ctx, monkeypatch):
    """When all Stripe prices are valid, all four pricing options are returned.

    The four-option shape is the pre-ruling catalog; the kill switch keeps that
    path testable (the ruling's single-plan shape has its own test below)."""
    ctx["get_user_subscription"].return_value = None
    monkeypatch.setenv("NEW_BUYER_SINGLE_PLAN_ENABLED", "false")

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
    descriptions = {p["id"]: p["description"] for p in plans}
    assert "chat questions per month" in descriptions[UNLIM_MONTHLY]
    assert "Power-user AI" in descriptions[ARCH_MONTHLY]


def _all_price_retrieve_mock():
    def _mock_retrieve(price_id):
        intervals = {
            UNLIM_MONTHLY: "month",
            UNLIM_ANNUAL: "year",
            ARCH_MONTHLY: "month",
            ARCH_ANNUAL: "year",
            PRO_MONTHLY: "month",
            PRO_ANNUAL: "year",
        }
        amounts = {
            UNLIM_MONTHLY: 1900,
            UNLIM_ANNUAL: 18000,
            ARCH_MONTHLY: 990,
            ARCH_ANNUAL: 9900,
            PRO_MONTHLY: 2999,
            PRO_ANNUAL: 26991,
        }
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    return MagicMock(side_effect=_mock_retrieve)


_ALL_SIX_PRICES = {
    UNLIM_MONTHLY,
    UNLIM_ANNUAL,
    ARCH_MONTHLY,
    ARCH_ANNUAL,
    PRO_MONTHLY,
    PRO_ANNUAL,
}


def test_new_buyer_explicit_platforms_get_single_plan_catalog(ctx, monkeypatch):
    """2026-10-24 ruling: a buyer with no current paid subscription on an
    explicit non-desktop platform (mobile or web) is offered only Omi Pro
    (`unlimited_v2`) — both intervals, and nothing else, even though Neo and
    Architect prices are configured and retrievable. A missing or unknown
    platform header keeps the pre-ruling full catalog (desktop compatibility
    outranks closing the header-less direct-API gap)."""
    ctx["get_user_subscription"].return_value = None
    ctx["get_user_valid_subscription"].return_value = None
    monkeypatch.delenv("NEW_BUYER_SINGLE_PLAN_ENABLED", raising=False)
    stripe.Price.retrieve = _all_price_retrieve_mock()

    for platform in ("ios", "android", "web"):
        response = ctx["client"].get("/v1/payments/available-plans", headers={"X-App-Platform": platform})
        assert response.status_code == 200, platform
        plans = response.json()["plans"]
        assert {p["id"] for p in plans} == {PRO_MONTHLY, PRO_ANNUAL}, platform
        assert {p["plan_id"] for p in plans} == {"unlimited_v2"}, platform

    # Missing header and unrecognized values keep the pre-ruling catalog.
    for headers in ({}, {"X-App-Platform": "not-a-platform"}):
        response = ctx["client"].get("/v1/payments/available-plans", headers=headers)
        assert response.status_code == 200, headers
        assert {p["id"] for p in response.json()["plans"]} == _ALL_SIX_PRICES, headers


def test_expired_desktop_tier_subscriber_on_mobile_is_offered_omi_pro(ctx, monkeypatch):
    """Catalog filtering keys off the period-valid plan, like checkout: a
    lapsed Operator record keeps its stored plan after the paid period ends,
    and the mobile manage-only fast path must not reduce that user to their
    expired desktop SKU — they are a basic buyer and get the Omi Pro offer."""
    from models.users import Subscription, SubscriptionStatus, PlanType

    ctx["get_user_subscription"].return_value = Subscription(
        plan=PlanType.operator,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_operator_expired",
        cancel_at_period_end=False,
        current_period_end=1_000,  # long past
    )
    # The same period-valid lookup checkout uses sees a lapsed paid plan as basic.
    from utils.subscription import get_default_basic_subscription

    ctx["get_user_valid_subscription"].return_value = get_default_basic_subscription()
    monkeypatch.delenv("NEW_BUYER_SINGLE_PLAN_ENABLED", raising=False)
    stripe.Price.retrieve = _all_price_retrieve_mock()
    stripe.Subscription.retrieve = MagicMock()
    stripe.SubscriptionSchedule.list = MagicMock(return_value=MagicMock(data=[]))

    response = ctx["client"].get("/v1/payments/available-plans", headers={"X-App-Platform": "ios"})
    assert response.status_code == 200
    plans = response.json()["plans"]
    assert {p["id"] for p in plans} == {PRO_MONTHLY, PRO_ANNUAL}
    assert {p["plan_id"] for p in plans} == {"unlimited_v2"}


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

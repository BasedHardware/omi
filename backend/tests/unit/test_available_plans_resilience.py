"""Tests that one invalid Stripe price ID doesn't hide all plans.

Exercises the real get_available_plans_endpoint() from routers/payment.py
with mocked Stripe, so a regression in the per-price try/except blocks
would be caught.
"""

import os
import sys
import types
from unittest.mock import MagicMock

# --- env vars needed at import time ---
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
# Real Stripe dev price IDs
UNLIM_MONTHLY = "price_1RrxXL1F8wnoWYvwIddzR902"
UNLIM_ANNUAL = "price_1RrxXL1F8wnoWYvw3kDbWmjs"
ARCH_MONTHLY = "price_1TAznX1F8wnoWYvwyaSVQbZW"
ARCH_ANNUAL = "price_1TAznX1F8wnoWYvwN8YmzbiC"

os.environ["STRIPE_UNLIMITED_MONTHLY_PRICE_ID"] = UNLIM_MONTHLY
os.environ["STRIPE_UNLIMITED_ANNUAL_PRICE_ID"] = UNLIM_ANNUAL
os.environ["STRIPE_ARCHITECT_MONTHLY_PRICE_ID"] = ARCH_MONTHLY
os.environ["STRIPE_ARCHITECT_ANNUAL_PRICE_ID"] = ARCH_ANNUAL

# --- Stub heavy infrastructure before importing any project modules ---

# Firestore client
_mock_client = types.ModuleType("database._client")
_mock_client.db = MagicMock()
sys.modules["database._client"] = _mock_client

# Firebase admin
_fb_admin = types.ModuleType("firebase_admin")
_fb_admin.auth = MagicMock()
sys.modules["firebase_admin"] = _fb_admin
sys.modules["firebase_admin.auth"] = _fb_admin.auth

# Database submodules
_db_mod = types.ModuleType("database")
sys.modules.setdefault("database", _db_mod)

for _name in [
    "database.users",
    "database.notifications",
    "database.conversations",
    "database.memories",
    "database.action_items",
    "database.redis_db",
    "database.user_usage",
    "database.cache",
    "database.announcements",
]:
    _m = types.ModuleType(_name)
    sys.modules[_name] = _m
    # Set as attribute on database package so `from database import X` works
    setattr(_db_mod, _name.split(".")[-1], _m)

# database.announcements needs _compare_versions for should_show_new_plans()
_announcements_mod = sys.modules["database.announcements"]


def _compare_versions(a, b):
    a_parts = [int(x) for x in a.split('.')]
    b_parts = [int(x) for x in b.split('.')]
    for x, y in zip(a_parts, b_parts):
        if x != y:
            return 1 if x > y else -1
    return len(a_parts) - len(b_parts)


_announcements_mod._compare_versions = _compare_versions
_announcements_mod.compare_versions = _compare_versions

# database.users needs the functions payment.py imports by name
_users_mod = sys.modules["database.users"]
for _attr in [
    "get_user_subscription",
    "get_user_valid_subscription",
    "update_user_subscription",
    "get_stripe_connect_account_id",
    "set_stripe_connect_account_id",
    "set_paypal_payment_details",
    "get_default_payment_method",
    "set_default_payment_method",
    "get_paypal_payment_details",
]:
    setattr(_users_mod, _attr, MagicMock())

# database.redis_db
_redis_mod = sys.modules["database.redis_db"]
_redis_mod.set_credits_invalidation_signal = MagicMock()
_redis_mod.r = MagicMock()

# Utils stubs for heavy external deps
for _name in [
    "utils.fair_use",
    "utils.notifications",
    "utils.apps",
    "utils.stripe",
    "utils.other",
    "utils.other.endpoints",
    "utils.other.storage",
]:
    _m = types.ModuleType(_name)
    sys.modules[_name] = _m

sys.modules["utils.fair_use"].clear_fair_use_on_upgrade = MagicMock()

_notif_mod = sys.modules["utils.notifications"]
_notif_mod.send_notification = MagicMock()
_notif_mod.send_subscription_paid_personalized_notification = MagicMock()

_apps_mod = sys.modules["utils.apps"]
for _attr in ["find_app_subscription", "get_is_user_paid_app", "paid_app", "set_user_app_sub_customer_id"]:
    setattr(_apps_mod, _attr, MagicMock())

_stripe_utils = sys.modules["utils.stripe"]
_stripe_utils.base_url = "http://test"
_stripe_utils.create_connect_account = MagicMock()
_stripe_utils.refresh_connect_account_link = MagicMock()
_stripe_utils.is_onboarding_complete = MagicMock()
_stripe_utils.create_subscription_checkout_session = MagicMock()

_endpoints_mod = sys.modules["utils.other.endpoints"]
_endpoints_mod.get_current_user_uid = lambda: "test-user"
_endpoints_mod.get_current_user_uid_no_byok_validation = lambda: "test-user"

# Ensure utils.other has endpoints attr for `from utils.other import endpoints`
sys.modules["utils.other"].endpoints = _endpoints_mod

# Stripe — use real module but we'll mock Price.retrieve per-test
import stripe

stripe.api_key = "sk_test_fake"

# --- Import the real router under test ---
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import payment as payment_router

app = FastAPI()
app.include_router(payment_router.router)
app.dependency_overrides[payment_router.auth.get_current_user_uid] = lambda: "test-user"
client = TestClient(app)


def _make_stripe_price(price_id, amount, interval):
    """Return a MagicMock mimicking a stripe.Price object."""
    price = MagicMock()
    price.id = price_id
    price.unit_amount = amount
    price.recurring = MagicMock()
    price.recurring.interval = interval
    return price


def test_invalid_architect_price_skips_architect_but_unlimited_remains():
    """When stripe.Price.retrieve fails for Architect prices, only Unlimited plans are returned."""
    _users_mod.get_user_subscription.return_value = None

    def _mock_retrieve(price_id):
        if price_id in (ARCH_MONTHLY, ARCH_ANNUAL):
            raise Exception(f"No such price: {price_id}")
        if price_id == UNLIM_MONTHLY:
            return _make_stripe_price(price_id, 1900, "month")
        if price_id == UNLIM_ANNUAL:
            return _make_stripe_price(price_id, 18000, "year")
        raise Exception(f"Unexpected price_id: {price_id}")

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = client.get("/v1/payments/available-plans")

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


def test_all_valid_prices_returns_all_plans():
    """When all Stripe prices are valid, all four pricing options are returned."""
    _users_mod.get_user_subscription.return_value = None

    def _mock_retrieve(price_id):
        intervals = {UNLIM_MONTHLY: "month", UNLIM_ANNUAL: "year", ARCH_MONTHLY: "month", ARCH_ANNUAL: "year"}
        amounts = {UNLIM_MONTHLY: 1900, UNLIM_ANNUAL: 18000, ARCH_MONTHLY: 990, ARCH_ANNUAL: 9900}
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]
    plan_ids = {p["id"] for p in plans}
    assert plan_ids == {UNLIM_MONTHLY, UNLIM_ANNUAL, ARCH_MONTHLY, ARCH_ANNUAL}
    assert len(plans) == 4


def test_legacy_unlimited_subscriber_sees_is_active():
    """Legacy Unlimited subscriber gets their plan with is_active=True in catalog."""
    from models.users import Subscription, SubscriptionStatus, PlanType

    sub = Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_legacy_123",
        cancel_at_period_end=False,
    )
    _users_mod.get_user_subscription.return_value = sub

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

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]

    # Legacy unlimited subscriber should have their monthly plan marked active
    active_plans = [p for p in plans if p["is_active"]]
    assert len(active_plans) == 1
    assert active_plans[0]["id"] == UNLIM_MONTHLY
    assert active_plans[0]["interval"] == "month"


def test_operator_subscriber_on_old_client_gets_remapped_is_active(monkeypatch):
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
    _users_mod.get_user_subscription.return_value = sub

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
    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]

    # Operator price should be remapped to Unlimited monthly, so is_active is set
    active_plans = [p for p in plans if p["is_active"]]
    assert len(active_plans) == 1
    assert active_plans[0]["id"] == UNLIM_MONTHLY
    assert active_plans[0]["interval"] == "month"


def test_all_prices_fail_returns_500():
    """When every stripe.Price.retrieve call fails, endpoint returns HTTP 500."""
    _users_mod.get_user_subscription.return_value = None
    stripe.Price.retrieve = MagicMock(side_effect=Exception("Stripe is down"))

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 500


def _make_subscription(price_id=UNLIM_MONTHLY, cancel_at_period_end=False):
    from models.users import PlanType, Subscription, SubscriptionStatus

    return Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_test_123",
        cancel_at_period_end=cancel_at_period_end,
    )


def _make_stripe_subscription(price_id=UNLIM_MONTHLY, customer="cus_test_123"):
    stripe_sub = MagicMock()
    stripe_sub.to_dict.return_value = {
        "id": "sub_test_123",
        "customer": customer,
        "status": "active",
        "current_period_start": 1_700_000_000,
        "current_period_end": 1_700_086_400,
        "cancel_at_period_end": False,
        "items": {"data": [{"id": "si_test_123", "price": {"id": price_id}}]},
    }
    return stripe_sub


def _setup_upgrade_mocks(current_price=UNLIM_MONTHLY, target_interval="month"):
    _users_mod.get_user_subscription.return_value = _make_subscription(price_id=current_price)
    _users_mod.update_user_subscription = MagicMock()
    payment_router.set_credits_invalidation_signal = MagicMock()
    payment_router.clear_trial_paywall_cache = MagicMock()
    payment_router.clear_fair_use_on_upgrade = MagicMock()
    payment_router.conversations_db.unlock_all_conversations = MagicMock()
    payment_router.memories_db.unlock_all_memories = MagicMock()
    payment_router.action_items_db.unlock_all_action_items = MagicMock()
    stripe.Subscription.retrieve = MagicMock(return_value=_make_stripe_subscription(price_id=current_price))
    stripe.Price.retrieve = MagicMock(return_value=_make_stripe_price("target", 9900, target_interval))


def test_upgrade_subscription_invalid_promotion_code_returns_400():
    _setup_upgrade_mocks()
    stripe.PromotionCode.list = MagicMock(return_value=MagicMock(data=[]))

    response = client.post(
        "/v1/payments/upgrade-subscription",
        json={"price_id": ARCH_MONTHLY, "promotion_code": "NOPE"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid promotion code."


def test_upgrade_subscription_cross_plan_applies_promotion_code_discount():
    _setup_upgrade_mocks()
    promo = {"id": "promo_customer_match", "customer": "cus_test_123"}
    stripe.PromotionCode.list = MagicMock(return_value=MagicMock(data=[promo]))
    updated_sub = _make_stripe_subscription(price_id=ARCH_MONTHLY)
    stripe.Subscription.modify = MagicMock(return_value=updated_sub)

    response = client.post(
        "/v1/payments/upgrade-subscription",
        json={"price_id": ARCH_MONTHLY, "promotion_code": "SAVE20"},
    )

    assert response.status_code == 200
    assert stripe.PromotionCode.list.call_args_list[0].kwargs["customer"] == "cus_test_123"
    modify_kwargs = stripe.Subscription.modify.call_args.kwargs
    assert modify_kwargs["discounts"] == [{"promotion_code": "promo_customer_match"}]


def test_upgrade_subscription_same_plan_applies_promotion_code_to_future_phase():
    _setup_upgrade_mocks(current_price=UNLIM_MONTHLY, target_interval="year")
    stripe.PromotionCode.list = MagicMock(return_value=MagicMock(data=[{"id": "promo_global", "customer": None}]))
    stripe.SubscriptionSchedule.create = MagicMock(return_value=MagicMock(id="sub_sched_test_123"))
    stripe.SubscriptionSchedule.modify = MagicMock(return_value=MagicMock())

    response = client.post(
        "/v1/payments/upgrade-subscription",
        json={"price_id": UNLIM_ANNUAL, "promotion_code": "SAVE20"},
    )

    assert response.status_code == 200
    phases = stripe.SubscriptionSchedule.modify.call_args.kwargs["phases"]
    assert "discounts" not in phases[0]
    assert phases[1]["discounts"] == [{"promotion_code": "promo_global"}]


def test_upgrade_subscription_blank_promotion_code_omits_discounts():
    _setup_upgrade_mocks()
    updated_sub = _make_stripe_subscription(price_id=ARCH_MONTHLY)
    stripe.Subscription.modify = MagicMock(return_value=updated_sub)
    stripe.PromotionCode.list = MagicMock()

    response = client.post(
        "/v1/payments/upgrade-subscription",
        json={"price_id": ARCH_MONTHLY, "promotion_code": "   "},
    )

    assert response.status_code == 200
    assert "discounts" not in stripe.Subscription.modify.call_args.kwargs
    stripe.PromotionCode.list.assert_not_called()


def test_upgrade_subscription_stripe_invalid_request_returns_message():
    _setup_upgrade_mocks()
    stripe.PromotionCode.list = MagicMock(return_value=MagicMock(data=[{"id": "promo_bad", "customer": None}]))
    stripe.Subscription.modify = MagicMock(
        side_effect=stripe.error.InvalidRequestError("Promotion code is not applicable", "discounts")
    )

    response = client.post(
        "/v1/payments/upgrade-subscription",
        json={"price_id": ARCH_MONTHLY, "promotion_code": "SAVE20"},
    )

    assert response.status_code == 400
    assert "Promotion code is not applicable" in response.json()["detail"]

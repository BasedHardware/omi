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
os.environ["STRIPE_UNLIMITED_MONTHLY_PRICE_ID"] = "price_unlim_m"
os.environ["STRIPE_UNLIMITED_ANNUAL_PRICE_ID"] = "price_unlim_a"
os.environ["STRIPE_PRO_MONTHLY_PRICE_ID"] = "price_pro_m"
os.environ["STRIPE_PRO_ANNUAL_PRICE_ID"] = "price_pro_a"

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
]:
    _m = types.ModuleType(_name)
    sys.modules[_name] = _m
    # Set as attribute on database package so `from database import X` works
    setattr(_db_mod, _name.split(".")[-1], _m)

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


def test_invalid_pro_price_skips_pro_but_unlimited_remains():
    """When stripe.Price.retrieve fails for Pro prices, only Unlimited plans are returned."""
    _users_mod.get_user_subscription.return_value = None

    def _mock_retrieve(price_id):
        if price_id in ("price_pro_m", "price_pro_a"):
            raise Exception(f"No such price: {price_id}")
        if price_id == "price_unlim_m":
            return _make_stripe_price(price_id, 1900, "month")
        if price_id == "price_unlim_a":
            return _make_stripe_price(price_id, 18000, "year")
        raise Exception(f"Unexpected price_id: {price_id}")

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 200
    data = response.json()
    plans = data["plans"]

    # Unlimited monthly + annual should be present
    plan_ids = {p["id"] for p in plans}
    assert "price_unlim_m" in plan_ids
    assert "price_unlim_a" in plan_ids

    # Pro prices should be absent (their retrieval failed)
    assert "price_pro_m" not in plan_ids
    assert "price_pro_a" not in plan_ids

    assert len(plans) == 2


def test_all_valid_prices_returns_all_plans():
    """When all Stripe prices are valid, all four pricing options are returned."""
    _users_mod.get_user_subscription.return_value = None

    def _mock_retrieve(price_id):
        intervals = {"price_unlim_m": "month", "price_unlim_a": "year", "price_pro_m": "month", "price_pro_a": "year"}
        amounts = {"price_unlim_m": 1900, "price_unlim_a": 18000, "price_pro_m": 990, "price_pro_a": 9900}
        if price_id not in intervals:
            raise Exception(f"Unexpected price_id: {price_id}")
        return _make_stripe_price(price_id, amounts[price_id], intervals[price_id])

    stripe.Price.retrieve = MagicMock(side_effect=_mock_retrieve)

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 200
    plans = response.json()["plans"]
    plan_ids = {p["id"] for p in plans}
    assert plan_ids == {"price_unlim_m", "price_unlim_a", "price_pro_m", "price_pro_a"}
    assert len(plans) == 4


def test_all_prices_fail_returns_500():
    """When every stripe.Price.retrieve call fails, endpoint returns HTTP 500."""
    _users_mod.get_user_subscription.return_value = None
    stripe.Price.retrieve = MagicMock(side_effect=Exception("Stripe is down"))

    response = client.get("/v1/payments/available-plans")

    assert response.status_code == 500

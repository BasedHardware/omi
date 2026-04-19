"""Regression tests for Stripe Connect account-link refresh authorization.

These tests keep the fix narrow: an authenticated user may only refresh the
account link for the Stripe Connect account stored on their own user record.
"""

import asyncio
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# --- Stub heavy infrastructure before importing project modules ---
_mock_client = types.ModuleType("database._client")
_mock_client.db = MagicMock()
sys.modules["database._client"] = _mock_client

_fb_admin = types.ModuleType("firebase_admin")
_fb_admin.auth = MagicMock()
sys.modules["firebase_admin"] = _fb_admin
sys.modules["firebase_admin.auth"] = _fb_admin.auth

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
    setattr(_db_mod, _name.split(".")[-1], _m)

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

_redis_mod = sys.modules["database.redis_db"]
_redis_mod.set_credits_invalidation_signal = MagicMock()
_redis_mod.mark_event_processed_once = MagicMock(return_value=True)
_redis_mod.r = MagicMock()

for _name in [
    "utils.fair_use",
    "utils.notifications",
    "utils.apps",
    "utils.stripe",
    "utils.other",
    "utils.other.endpoints",
    "utils.other.storage",
    "utils.subscription",
    "utils.log_sanitizer",
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
sys.modules["utils.other"].endpoints = _endpoints_mod

_subscription_mod = sys.modules["utils.subscription"]
for _attr in [
    "get_basic_plan_limits",
    "get_paid_plan_definitions",
    "get_plan_type_from_price_id",
    "get_plan_limits",
    "is_paid_plan",
]:
    setattr(_subscription_mod, _attr, MagicMock())

sys.modules["utils.log_sanitizer"].sanitize = lambda x: x

import stripe
from fastapi import HTTPException
from routers import payment as payment_router


class DummyRequest:
    pass


def test_refresh_account_link_rejects_other_users_account_id():
    """Authenticated callers must not refresh a Stripe link for another account id."""
    payment_router.get_stripe_connect_account_id = MagicMock(return_value="acct_attacker")
    payment_router.refresh_connect_account_link = MagicMock()

    with pytest_raises_http_exception(403) as exc:
        asyncio.run(
            payment_router.refresh_account_link_endpoint(
                DummyRequest(), account_id="acct_victim", uid="attacker_uid"
            )
        )

    assert "not authorized" in exc.detail.lower()
    payment_router.get_stripe_connect_account_id.assert_called_once_with("attacker_uid")
    payment_router.refresh_connect_account_link.assert_not_called()


def test_refresh_account_link_allows_own_account_id():
    """Authenticated callers may refresh the Stripe link for their own account id."""
    payment_router.get_stripe_connect_account_id = MagicMock(return_value="acct_attacker")
    payment_router.refresh_connect_account_link = MagicMock(
        return_value={"account_id": "acct_attacker", "url": "https://example.test/onboard"}
    )

    result = asyncio.run(
        payment_router.refresh_account_link_endpoint(
            DummyRequest(), account_id="acct_attacker", uid="attacker_uid"
        )
    )

    assert result["account_id"] == "acct_attacker"
    payment_router.get_stripe_connect_account_id.assert_called_once_with("attacker_uid")
    payment_router.refresh_connect_account_link.assert_called_once_with("acct_attacker")


def test_refresh_account_link_requires_existing_connected_account():
    """Users without a stored Stripe Connect account should get a not-found error."""
    payment_router.get_stripe_connect_account_id = MagicMock(return_value=None)
    payment_router.refresh_connect_account_link = MagicMock()

    with pytest_raises_http_exception(404) as exc:
        asyncio.run(
            payment_router.refresh_account_link_endpoint(
                DummyRequest(), account_id="acct_missing", uid="attacker_uid"
            )
        )

    assert "connect account not found" in exc.detail.lower()
    payment_router.get_stripe_connect_account_id.assert_called_once_with("attacker_uid")
    payment_router.refresh_connect_account_link.assert_not_called()


class pytest_raises_http_exception:
    """Tiny context manager so this test stays runnable without importing pytest helpers here."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        self.detail = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            raise AssertionError(f"Expected HTTPException({self.status_code})")
        if not isinstance(exc, HTTPException):
            raise AssertionError(f"Expected HTTPException, got {type(exc)!r}")
        if exc.status_code != self.status_code:
            raise AssertionError(f"Expected status {self.status_code}, got {exc.status_code}")
        self.detail = exc.detail
        return True

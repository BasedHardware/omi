"""Unit tests for payment router Stripe Connect & checkout exception sanitization.

Verifies that Stripe errors in Connect onboarding, account link refresh,
app subscription cancellation, and checkout creation do not leak internal details.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import routers.payment as payment_routes


class _FakeStripeError(Exception):
    """Minimal stand-in for stripe.error.StripeError."""

    def __init__(self, message, user_message=None):
        super().__init__(message)
        self.user_message = user_message


class _FakeInvalidRequestError(_FakeStripeError):
    """Minimal stand-in for stripe.error.InvalidRequestError."""

    pass


def test_create_connect_account_masks_stripe_error(monkeypatch):
    """Stripe Connect account creation errors must not leak raw exception detail."""
    monkeypatch.setattr(payment_routes, "get_stripe_connect_account_id", lambda uid: None)
    monkeypatch.setattr(payment_routes, "get_user_profile", lambda uid: {"id": uid})
    monkeypatch.setattr(payment_routes.stripe.error, "StripeError", _FakeStripeError)

    leak_msg = "Stripe Connect API rate limit reached at account_create_endpoint: key=sk_live_secret"

    def _raise(*args, **kwargs):
        raise _FakeStripeError(leak_msg)

    monkeypatch.setattr(payment_routes, "create_connect_account", _raise)

    with pytest.raises(HTTPException) as exc_info:
        payment_routes.create_connect_account_endpoint(country="US", uid="user_123")

    assert exc_info.value.status_code == 400
    assert "sk_live_secret" not in exc_info.value.detail
    assert "rate limit" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to create Stripe Connect account. Please try again."


def test_check_onboarding_status_masks_stripe_error(monkeypatch):
    """Stripe onboarding check errors must not leak raw exception detail."""
    monkeypatch.setattr(payment_routes, "get_stripe_connect_account_id", lambda uid: "acct_test123")
    monkeypatch.setattr(payment_routes.stripe.error, "StripeError", _FakeStripeError)

    leak_msg = "Account acct_test123 does not have access to capabilities: [card_payments]"

    def _raise(*args, **kwargs):
        raise _FakeStripeError(leak_msg)

    monkeypatch.setattr(payment_routes, "is_onboarding_complete", _raise)

    with pytest.raises(HTTPException) as exc_info:
        payment_routes.check_onboarding_status(uid="user_123")

    assert exc_info.value.status_code == 400
    assert "acct_test123" not in exc_info.value.detail
    assert "card_payments" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to check Stripe Connect onboarding status."


def test_refresh_account_link_masks_stripe_error(monkeypatch):
    """Stripe Connect account link refresh errors must not leak raw exception detail."""
    monkeypatch.setattr(payment_routes.stripe.error, "StripeError", _FakeStripeError)

    leak_msg = "Link refresh failed for account acct_live_999: URL generation expired"

    def _raise(*args, **kwargs):
        raise _FakeStripeError(leak_msg)

    monkeypatch.setattr(payment_routes, "refresh_connect_account_link", _raise)

    fake_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        payment_routes.refresh_account_link_endpoint(request=fake_request, account_id="acct_live_999", uid="user_123")

    assert exc_info.value.status_code == 400
    assert "acct_live_999" not in exc_info.value.detail
    assert "expired" not in exc_info.value.detail
    assert exc_info.value.detail == "Failed to refresh Stripe Connect account link."


def test_cancel_app_subscription_masks_stripe_error(monkeypatch):
    """App subscription cancellation errors must not leak raw exception detail."""
    monkeypatch.setattr(payment_routes.stripe.error, "StripeError", _FakeStripeError)
    monkeypatch.setattr(
        payment_routes.apps,
        "find_app_subscription",
        lambda uid, app_id: {"subscription_id": "sub_app_777", "customer_id": "cus_123"},
    )

    leak_msg = "No such subscription: 'sub_app_777'; live mode key used in test environment"

    with patch.object(payment_routes.stripe.Subscription, "modify", side_effect=_FakeStripeError(leak_msg)):
        with pytest.raises(HTTPException) as exc_info:
            payment_routes.cancel_app_subscription_endpoint(app_id="app_123", uid="user_123")

    assert exc_info.value.status_code == 400
    assert "sub_app_777" not in exc_info.value.detail
    assert "live mode" not in exc_info.value.detail
    assert exc_info.value.detail == "Could not cancel app subscription. Please try again."


def test_checkout_session_fallback_masks_invalid_request_error(monkeypatch):
    """Checkout session InvalidRequestError without user_message must return sanitized detail."""
    monkeypatch.setattr(payment_routes.users_db, "get_stripe_customer_id", lambda uid: "cus_123")
    monkeypatch.setattr(payment_routes.stripe.error, "InvalidRequestError", _FakeInvalidRequestError)

    leak_msg = "Invalid API key provided: sk_test_51...xyz"

    def _raise(*args, **kwargs):
        raise _FakeInvalidRequestError(leak_msg, user_message=None)

    monkeypatch.setattr(payment_routes.stripe_utils, "create_subscription_checkout_session", _raise)

    fake_req = MagicMock()
    fake_req.price_id = "price_premium_monthly"
    fake_req.promotion_code_id = None

    with pytest.raises(HTTPException) as exc_info:
        payment_routes.create_checkout_session(request=fake_req, uid="user_123")

    assert exc_info.value.status_code == 400
    assert "sk_test_51" not in exc_info.value.detail
    assert "Invalid API key" not in exc_info.value.detail
    assert exc_info.value.detail == "Invalid payment request. Please check your payment details."

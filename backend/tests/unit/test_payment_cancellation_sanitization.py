"""Unit tests for payment router cancel_subscription_endpoint exception sanitization.

Verifies that Stripe StripeError detail is masked and does not leak
internal Stripe error messages in HTTP 500 responses.
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


def test_cancel_subscription_masks_stripe_error_detail(monkeypatch):
    """Stripe errors must not expose raw str(e) in HTTP detail."""
    fake_sub = MagicMock()
    fake_sub.stripe_subscription_id = "sub_test123"
    monkeypatch.setattr(payment_routes.users_db, "get_user_subscription", lambda uid: fake_sub)
    monkeypatch.setattr(payment_routes.users_db, "set_user_cancellation_feedback", MagicMock())

    stripe_err = _FakeStripeError(
        "No such subscription: 'sub_test123'; a similar object exists in test mode",
        user_message="No such subscription: 'sub_test123'; a similar object exists in test mode",
    )

    with patch.object(payment_routes.stripe.Subscription, "retrieve", side_effect=stripe_err):
        monkeypatch.setattr(payment_routes.stripe.error, "StripeError", _FakeStripeError)

        req = payment_routes.CancelSubscriptionRequest()
        with pytest.raises(HTTPException) as exc_info:
            payment_routes.cancel_subscription_endpoint(req, uid="uid-test-001")

    assert exc_info.value.status_code == 500
    assert "sub_test123" not in exc_info.value.detail
    assert "test mode" not in exc_info.value.detail
    assert "similar object" not in exc_info.value.detail
    assert exc_info.value.detail == "Could not cancel subscription. Please contact support."


def test_cancel_subscription_masks_generic_exception(monkeypatch):
    """Generic exceptions must not expose str(e) in HTTP 500 detail."""
    fake_sub = MagicMock()
    fake_sub.stripe_subscription_id = "sub_xyz"
    monkeypatch.setattr(payment_routes.users_db, "get_user_subscription", lambda uid: fake_sub)

    with patch.object(
        payment_routes.stripe.Subscription,
        "retrieve",
        side_effect=RuntimeError("internal redis timeout: host=cache-prod-01"),
    ):
        req = payment_routes.CancelSubscriptionRequest()
        with pytest.raises(HTTPException) as exc_info:
            payment_routes.cancel_subscription_endpoint(req, uid="uid-test-002")

    assert exc_info.value.status_code == 500
    assert "redis" not in exc_info.value.detail.lower()
    assert "cache-prod-01" not in exc_info.value.detail
    assert exc_info.value.detail == "Could not cancel subscription. Please try again."

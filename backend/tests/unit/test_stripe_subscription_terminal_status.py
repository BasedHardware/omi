"""Regression tests for issue #11289 — reading a subscription's terminal status from Stripe.

Account-deletion wipes stalled forever because `cancel_subscription` cannot cancel an
already-canceled subscription: Stripe answers 400 "A canceled subscription can only update its
cancellation_details and metadata". `is_subscription_terminal` is the seam that tells that case
apart from a real failure, so it is asserted against real `stripe` SDK objects and errors — a
subscription payload whose accessor changed shape, or an error path that returned True, would
put the destructive wipe on the wrong side of the branch.
"""

from unittest.mock import MagicMock

import stripe

from utils import stripe as stripe_utils


def _subscription(status: str) -> stripe.Subscription:
    return stripe.Subscription.construct_from(
        {'id': 'sub_123', 'object': 'subscription', 'status': status},
        'sk_test_not_real',
    )


def test_canceled_subscription_is_terminal(monkeypatch):
    monkeypatch.setattr(stripe_utils.stripe.Subscription, 'retrieve', MagicMock(return_value=_subscription('canceled')))

    assert stripe_utils.is_subscription_terminal('sub_123') is True


def test_incomplete_expired_subscription_is_terminal(monkeypatch):
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription, 'retrieve', MagicMock(return_value=_subscription('incomplete_expired'))
    )

    assert stripe_utils.is_subscription_terminal('sub_123') is True


def test_billing_subscription_is_not_terminal(monkeypatch):
    for status in ('active', 'trialing', 'past_due', 'unpaid', 'paused'):
        monkeypatch.setattr(stripe_utils.stripe.Subscription, 'retrieve', MagicMock(return_value=_subscription(status)))

        assert stripe_utils.is_subscription_terminal('sub_123') is False, status


def test_unreadable_subscription_is_not_terminal(monkeypatch):
    """Fail closed: a Stripe outage must not read as 'already canceled'."""
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription,
        'retrieve',
        MagicMock(side_effect=stripe.APIConnectionError('stripe unreachable')),
    )

    assert stripe_utils.is_subscription_terminal('sub_123') is False

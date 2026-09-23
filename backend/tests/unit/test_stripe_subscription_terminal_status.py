"""Regression tests for issue #11289 — reading a subscription's terminal status from Stripe.

Account-deletion wipes stalled forever because `cancel_subscription` cannot cancel an
already-canceled subscription: Stripe answers 400 "A canceled subscription can only update its
cancellation_details and metadata". `is_subscription_terminal` is the seam that tells that case
apart from a real failure, so it is asserted against real `stripe` SDK objects and errors — a
subscription payload whose accessor changed shape, or an error path that returned True, would
put the destructive wipe on the wrong side of the branch.
"""

from unittest.mock import MagicMock

import pytest
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


def _uid_subscriptions(*subscriptions: tuple[str, str, dict[str, str]]) -> stripe.SearchResultObject:
    return stripe.SearchResultObject.construct_from(
        {
            'object': 'search_result',
            'url': '/v1/subscriptions/search',
            'has_more': False,
            'data': [
                {'id': sub_id, 'object': 'subscription', 'status': status, 'metadata': {'uid': 'uid1', **metadata}}
                for sub_id, status, metadata in subscriptions
            ],
        },
        'sk_test_not_real',
    )


def test_billable_app_subscriptions_are_found_by_their_uid_stamp(monkeypatch):
    monkeypatch.setattr(stripe_utils.stripe, 'api_key', 'sk_test_not_real')
    search = MagicMock(
        return_value=_uid_subscriptions(
            ('sub_plan', 'active', {'sub_type': 'unlimited'}),
            ('sub_app_active', 'active', {'app_id': 'app-1'}),
            ('sub_app_past_due', 'past_due', {'app_id': 'app-2'}),
            ('sub_app_canceled', 'canceled', {'app_id': 'app-3'}),
            ('sub_app_expired', 'incomplete_expired', {'app_id': 'app-4'}),
        )
    )
    monkeypatch.setattr(stripe_utils.stripe.Subscription, 'search', search)

    assert stripe_utils.find_billable_app_subscription_ids('uid1') == ['sub_app_active', 'sub_app_past_due']
    search.assert_called_once_with(query="metadata['uid']:'uid1'")


def test_app_subscription_search_failure_is_raised(monkeypatch):
    monkeypatch.setattr(stripe_utils.stripe, 'api_key', 'sk_test_not_real')
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription,
        'search',
        MagicMock(side_effect=stripe.APIConnectionError('stripe unreachable')),
    )

    with pytest.raises(stripe.APIConnectionError):
        stripe_utils.find_billable_app_subscription_ids('uid1')


def test_a_deployment_without_stripe_has_no_app_subscriptions_to_find(monkeypatch):
    search = MagicMock()
    monkeypatch.setattr(stripe_utils.stripe, 'api_key', None)
    monkeypatch.setattr(stripe_utils.stripe.Subscription, 'search', search)

    assert stripe_utils.find_billable_app_subscription_ids('uid1') == []
    search.assert_not_called()

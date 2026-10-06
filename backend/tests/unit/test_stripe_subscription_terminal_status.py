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


def test_missing_subscription_is_terminal(monkeypatch):
    """A stored subscription id that Stripe does not know cannot bill: the goal state holds.

    Regression for the account-deletion deadlock of 2026-10-06: a user doc pointed at a
    synthetic ``sub_agent_test_model_attr`` id, cancel returned None, this returned False, and
    the wipe failed 15 times while the auth fence kept the user out of the app.
    """
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription,
        'retrieve',
        MagicMock(
            side_effect=stripe.InvalidRequestError(
                "No such subscription: 'sub_agent_test_model_attr'",
                'id',
                code='resource_missing',
                http_status=404,
            )
        ),
    )

    assert stripe_utils.is_subscription_terminal('sub_agent_test_model_attr') is True


def test_other_invalid_requests_are_not_terminal(monkeypatch):
    """Only a missing resource is terminal; a malformed request still fails closed."""
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription,
        'retrieve',
        MagicMock(
            side_effect=stripe.InvalidRequestError('bad id', 'id', code='parameter_invalid_empty', http_status=400)
        ),
    )

    assert stripe_utils.is_subscription_terminal('') is False


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


@pytest.mark.parametrize('status', ['canceled', 'incomplete_expired'])
def test_erasure_skips_cancel_for_terminal_subscription(monkeypatch, status):
    monkeypatch.setattr(stripe.Subscription, 'retrieve', MagicMock(return_value=_subscription(status)))
    delete = MagicMock()
    monkeypatch.setattr(stripe.Subscription, 'delete', delete)
    stripe_utils.cancel_subscription_for_account_deletion('sub_123')
    delete.assert_not_called()


@pytest.mark.parametrize('at_delete', [False, True])
def test_erasure_accepts_missing_subscription_even_during_cancel_race(monkeypatch, at_delete):
    missing = stripe.InvalidRequestError('No such subscription', 'id', code='resource_missing')
    monkeypatch.setattr(
        stripe.Subscription,
        'retrieve',
        MagicMock(return_value=_subscription('active')) if at_delete else MagicMock(side_effect=missing),
    )
    monkeypatch.setattr(stripe.Subscription, 'delete', MagicMock(side_effect=missing))
    stripe_utils.cancel_subscription_for_account_deletion('sub_123')


def test_erasure_accepts_concurrent_terminal_transition(monkeypatch):
    monkeypatch.setattr(
        stripe.Subscription, 'retrieve', MagicMock(side_effect=[_subscription('active'), _subscription('canceled')])
    )
    monkeypatch.setattr(
        stripe.Subscription,
        'delete',
        MagicMock(
            side_effect=stripe.InvalidRequestError(
                'A canceled subscription can only update its cancellation_details and metadata.', 'id'
            )
        ),
    )
    stripe_utils.cancel_subscription_for_account_deletion('sub_123')


@pytest.mark.parametrize(
    'error',
    [
        stripe.APIConnectionError('Stripe timeout'),
        stripe.RateLimitError('Too many requests', http_status=429),
        stripe.APIError('Stripe server unavailable', http_status=503),
    ],
)
@pytest.mark.parametrize('at_delete', [False, True])
def test_erasure_propagates_transient_errors(monkeypatch, error, at_delete):
    monkeypatch.setattr(
        stripe.Subscription,
        'retrieve',
        MagicMock(return_value=_subscription('active')) if at_delete else MagicMock(side_effect=error),
    )
    monkeypatch.setattr(stripe.Subscription, 'delete', MagicMock(side_effect=error))
    with pytest.raises(type(error)):
        stripe_utils.cancel_subscription_for_account_deletion('sub_123')


def test_erasure_does_not_accept_arbitrary_invalid_request(monkeypatch):
    monkeypatch.setattr(stripe.Subscription, 'retrieve', MagicMock(return_value=_subscription('active')))
    monkeypatch.setattr(
        stripe.Subscription, 'delete', MagicMock(side_effect=stripe.InvalidRequestError('invalid credentials', 'id'))
    )
    with pytest.raises(stripe.InvalidRequestError):
        stripe_utils.cancel_subscription_for_account_deletion('sub_123')

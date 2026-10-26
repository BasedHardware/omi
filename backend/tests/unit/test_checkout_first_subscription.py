"""Checkout must prove a stored Stripe subscription ended before creating another.

Refs #21869. These tests execute the real HTTP checkout, eligibility, reactivation
and Checkout-session builder with fake persistence and real Stripe SDK objects.
Stripe status contract: https://docs.stripe.com/api/subscriptions/object#subscription_object-status
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import stripe

from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment

UID = 'checkout-owner'
# The default checkout target is the new-buyer single plan (Omi Pro /
# unlimited_v2): a buyer with no current paid subscription and no platform
# header may only start on it (2026-10-24 ruling), so the eligibility flows
# below are exercised through the plan a header-less first-time buyer can
# actually buy. OTHER_PRICE (Plus) remains a legal plan-change target.
PRICE = 'price_checkout_current'
OTHER_PRICE = 'price_checkout_other'


@pytest.fixture
def checkout(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    state = SimpleNamespace(
        stored=Subscription(
            plan=PlanType.unlimited,
            status=SubscriptionStatus.active,
            current_period_end=now - 86400,
            stripe_subscription_id='sub_existing',
            current_price_id=PRICE,
        ),
        payload={
            'id': 'sub_existing',
            'object': 'subscription',
            'status': 'active',
            'current_period_end': now + 86400,
            'cancel_at_period_end': False,
            'customer': 'cus_existing',
            'metadata': {'uid': UID},
            'items': {'data': [{'price': {'id': PRICE, 'recurring': {'interval': 'month'}}}]},
        },
    )
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', PRICE)
    monkeypatch.setenv('STRIPE_PLUS_MONTHLY_PRICE_ID', OTHER_PRICE)
    monkeypatch.setattr(payment, 'is_purchasable_price_id', lambda price: price in (PRICE, OTHER_PRICE))
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid, **kwargs: state.stored)
    monkeypatch.setattr(payment.users_db, 'get_stripe_customer_id', lambda uid: None)
    state.writes = MagicMock()
    state.customer_writes = MagicMock()
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', state.writes)
    monkeypatch.setattr(payment.users_db, 'set_stripe_customer_id', state.customer_writes)
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', MagicMock())
    monkeypatch.setattr(payment, 'clear_trial_paywall_cache', MagicMock())
    state.retrieve = MagicMock(
        side_effect=lambda subscription_id: stripe.Subscription.construct_from(state.payload, 'sk_test_not_real')
    )
    state.modify = MagicMock()
    state.list_subscriptions = MagicMock(return_value=SimpleNamespace(data=[]))
    state.create = MagicMock(return_value=SimpleNamespace(id='cs_test', url='https://checkout.stripe.test/session'))
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', state.retrieve)
    monkeypatch.setattr(payment.stripe.Subscription, 'modify', state.modify)
    monkeypatch.setattr(payment.stripe.Subscription, 'list', state.list_subscriptions)
    monkeypatch.setattr(payment.stripe.checkout.Session, 'create', state.create)
    monkeypatch.setattr(payment.stripe_utils, 'base_url', 'https://omi.test/')
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        state.client = client
        yield state


def request_checkout(checkout, price=PRICE):
    return checkout.client.post('/v1/payments/checkout-session', json={'price_id': price})


def assert_no_new_billing(checkout):
    checkout.create.assert_not_called()
    checkout.customer_writes.assert_not_called()


@pytest.mark.parametrize('status', ['active', 'trialing', 'past_due', 'unpaid', 'paused', 'incomplete', 'unknown'])
@pytest.mark.parametrize('stored_plan', [PlanType.unlimited, PlanType.basic])
def test_checkout_first_never_creates_a_second_nonterminal_subscription(checkout, status, stored_plan):
    checkout.stored.plan = stored_plan
    checkout.payload['status'] = status
    # No subscription-read heal has run: the real validity projection still says Free.
    assert payment.users_db.get_user_valid_subscription(UID).plan == PlanType.basic
    response = request_checkout(checkout)
    assert response.status_code == 409
    assert_no_new_billing(checkout)
    checkout.modify.assert_not_called()
    checkout.writes.assert_not_called()
    checkout.list_subscriptions.assert_not_called()


@pytest.mark.parametrize('field', ['current_period_end', 'items', 'customer'])
def test_active_subscription_does_not_need_entitlement_fields_to_block_duplicate_checkout(checkout, field):
    checkout.payload.pop(field)
    assert request_checkout(checkout).status_code == 409
    assert_no_new_billing(checkout)


@pytest.mark.parametrize('status', ['canceled', 'incomplete_expired'])
def test_terminal_subscription_permits_a_new_checkout(checkout, status):
    checkout.payload['status'] = status
    response = request_checkout(checkout)
    assert response.status_code == 200
    assert response.json()['session_id'] == 'cs_test'
    checkout.create.assert_called_once()
    checkout.modify.assert_not_called()
    checkout.writes.assert_not_called()


def test_new_buyer_without_a_stored_subscription_id_keeps_checkout(checkout):
    checkout.stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    assert request_checkout(checkout).status_code == 200
    checkout.create.assert_called_once()
    checkout.retrieve.assert_not_called()


def test_new_buyer_legacy_price_platform_matrix_at_http_layer(checkout, monkeypatch):
    """2026-10-24 ruling at the HTTP layer: a buyer with no current paid
    subscription posting a legacy (Plus) price gets 400 on the explicit
    non-desktop platforms (mobile/web). A missing platform header keeps the
    pre-ruling acceptance — every desktop build ever shipped sends the header,
    but desktop compatibility outranks closing the header-less direct-API gap."""
    checkout.stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)

    for platform in ('ios', 'android', 'web'):
        response = checkout.client.post(
            '/v1/payments/checkout-session',
            json={'price_id': OTHER_PRICE},
            headers={'X-App-Platform': platform},
        )
        assert response.status_code == 400, platform
        assert 'Omi Pro' in response.json()['detail'], platform
    assert_no_new_billing(checkout)

    # Missing header: pre-ruling behaviour — the legacy price is accepted.
    assert request_checkout(checkout, OTHER_PRICE).status_code == 200
    checkout.create.assert_called_once()

    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    assert (
        checkout.client.post(
            '/v1/payments/checkout-session',
            json={'price_id': OTHER_PRICE},
            headers={'X-App-Platform': 'ios'},
        ).status_code
        == 200
    )


def test_new_buyer_desktop_platform_keeps_legacy_checkout(checkout):
    checkout.stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    response = checkout.client.post(
        '/v1/payments/checkout-session', json={'price_id': OTHER_PRICE}, headers={'X-App-Platform': 'macos'}
    )
    assert response.status_code == 200
    checkout.create.assert_called_once()


def test_referral_without_stripe_subscription_keeps_checkout(checkout):
    checkout.stored.stripe_subscription_id = None
    checkout.stored.current_period_end = checkout.payload['current_period_end']
    assert request_checkout(checkout, OTHER_PRICE).status_code == 200
    checkout.create.assert_called_once()
    checkout.retrieve.assert_not_called()


def test_missing_local_id_still_recovers_cancel_scheduled_subscription(checkout, monkeypatch):
    checkout.stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    checkout.payload['cancel_at_period_end'] = True
    monkeypatch.setattr(payment.users_db, 'get_stripe_customer_id', lambda uid: 'cus_existing')
    checkout.list_subscriptions.return_value.data = [
        stripe.Subscription.construct_from(checkout.payload, 'sk_test_not_real')
    ]
    response = request_checkout(checkout)
    assert response.status_code == 200
    assert response.json()['status'] == 'reactivated'
    checkout.modify.assert_called_once_with('sub_existing', cancel_at_period_end=False)
    assert_no_new_billing(checkout)


def test_one_time_payment_intent_grant_is_not_treated_as_a_stripe_subscription(checkout):
    checkout.stored.stripe_subscription_id = 'pi_one_time_grant'
    assert request_checkout(checkout).status_code == 200
    checkout.create.assert_called_once()
    checkout.retrieve.assert_not_called()


def test_definitively_missing_subscription_permits_checkout(checkout):
    checkout.retrieve.side_effect = stripe.InvalidRequestError(
        'No such subscription', 'id', code='resource_missing', http_status=404
    )
    assert request_checkout(checkout).status_code == 200
    checkout.create.assert_called_once()


@pytest.mark.parametrize(
    'error',
    [
        stripe.APIConnectionError('secret-provider-response'),
        stripe.AuthenticationError('secret-provider-response'),
        stripe.InvalidRequestError('secret-provider-response', 'id', code='parameter_invalid', http_status=400),
        stripe.InvalidRequestError('secret-provider-response', 'id', code='different_error', http_status=404),
    ],
)
def test_stripe_uncertainty_is_retryable_and_never_falls_through_to_checkout(checkout, error, caplog):
    checkout.retrieve.side_effect = error
    response = request_checkout(checkout)
    assert response.status_code == 503
    assert 'try again' in response.json()['detail'].lower()
    assert 'secret-provider-response' not in response.text + caplog.text
    assert_no_new_billing(checkout)


def test_missing_status_is_unavailable_not_proof_the_subscription_ended(checkout):
    checkout.payload.pop('status')
    assert request_checkout(checkout).status_code == 503
    assert_no_new_billing(checkout)


def test_cancel_scheduled_same_price_reactivates_without_a_second_subscription(checkout):
    checkout.payload['cancel_at_period_end'] = True
    response = request_checkout(checkout)
    assert response.status_code == 200
    assert response.json()['status'] == 'reactivated'
    checkout.modify.assert_called_once_with('sub_existing', cancel_at_period_end=False)
    assert_no_new_billing(checkout)


def test_cancel_scheduled_different_price_cannot_fall_through_to_checkout(checkout):
    checkout.payload['cancel_at_period_end'] = True
    assert request_checkout(checkout, OTHER_PRICE).status_code == 409
    assert_no_new_billing(checkout)
    checkout.modify.assert_not_called()


def test_cancel_scheduled_legacy_price_reactivation_is_not_blocked_by_single_plan_rule(checkout):
    """2026-10-24 ruling preserves existing subscribers: a cancel-scheduled
    subscriber reactivating their own legacy (Plus) price succeeds even from a
    client with no platform header — the single-plan guard runs after this
    subscriber escape."""
    checkout.payload['cancel_at_period_end'] = True
    checkout.payload['items'] = {'data': [{'price': {'id': OTHER_PRICE, 'recurring': {'interval': 'month'}}}]}
    response = request_checkout(checkout, OTHER_PRICE)
    assert response.status_code == 200
    assert response.json()['status'] == 'reactivated'
    checkout.modify.assert_called_once_with('sub_existing', cancel_at_period_end=False)
    assert_no_new_billing(checkout)


@pytest.mark.parametrize('failure', ['modify', 'persist', 'modify_missing'])
def test_failed_reactivation_never_starts_fresh_checkout(checkout, failure):
    checkout.payload['cancel_at_period_end'] = True
    if failure == 'modify_missing':
        checkout.modify.side_effect = stripe.InvalidRequestError(
            'Missing during modification', 'id', code='resource_missing', http_status=404
        )
    elif failure == 'modify':
        checkout.modify.side_effect = stripe.APIConnectionError('Unavailable')
    else:
        checkout.writes.side_effect = RuntimeError('Persistence unavailable')
    assert request_checkout(checkout).status_code == 503
    assert_no_new_billing(checkout)


def test_active_plan_change_must_use_upgrade_not_a_second_subscription(checkout):
    checkout.stored.current_period_end = checkout.payload['current_period_end']
    assert request_checkout(checkout, OTHER_PRICE).status_code == 409
    assert_no_new_billing(checkout)

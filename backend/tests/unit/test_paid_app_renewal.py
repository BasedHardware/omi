"""A paid app's entitlement must follow the Stripe subscription, not a 30-day timer.

`paid_app` writes `users:{uid}:paid_apps:{app_id}` with a fixed 30-day TTL, and the only
writer was the `checkout.session.completed` branch, which fires once at purchase. Apps can
be sold as monthly recurring subscriptions, so on day 31 the key expired while Stripe kept
charging: the user lost access to the app, and `cancel_app_subscription` returned 404
because it gated on that same key before asking Stripe, so they could not stop the billing
either. The same happens to every buyer at once on a Redis eviction or failover.

These tests drive the real webhook handler and the real subscription routes with Stripe
faked at the boundary.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import asyncio
import time

import pytest

import routers.payment as payment
from utils import apps as apps_utils

_DAY = 60 * 60 * 24


class _Request:
    @staticmethod
    async def body():
        return b'{}'


def _invoice_event(event_type, subscription_id):
    return {'type': event_type, 'data': {'object': {'subscription': subscription_id}}}


@pytest.fixture
def webhook(monkeypatch):
    """Drive stripe_webhook with a chosen event; record paid_app re-arms."""
    rearmed = []

    def _install(event, subscription_metadata):
        monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda payload, sig: event)
        monkeypatch.setattr(
            payment.stripe.Subscription,
            'retrieve',
            staticmethod(lambda sub_id: {'id': sub_id, 'metadata': subscription_metadata}),
        )
        monkeypatch.setattr(
            payment, 'paid_app', lambda app_id, uid, current_period_end=None: rearmed.append((app_id, uid))
        )
        return rearmed

    return _install


def _run_webhook():
    return asyncio.run(payment.stripe_webhook(_Request(), 'sig'))


def test_a_renewal_invoice_re_arms_the_paid_app_entitlement(webhook):
    rearmed = webhook(_invoice_event('invoice.paid', 'sub_1'), {'uid': 'user-1', 'app_id': 'app-1'})

    assert _run_webhook() == {"status": "success"}
    assert rearmed == [('app-1', 'user-1')]


def test_the_payment_succeeded_alias_re_arms_it_too(webhook):
    rearmed = webhook(_invoice_event('invoice.payment_succeeded', 'sub_1'), {'uid': 'user-1', 'app_id': 'app-1'})

    assert _run_webhook() == {"status": "success"}
    assert rearmed == [('app-1', 'user-1')]


def test_an_invoice_for_a_plan_subscription_is_left_alone(webhook):
    rearmed = webhook(_invoice_event('invoice.paid', 'sub_1'), {'uid': 'user-1'})

    assert _run_webhook() == {"status": "success"}
    assert rearmed == []


def test_an_invoice_with_no_subscription_is_left_alone(webhook):
    rearmed = webhook(_invoice_event('invoice.paid', None), {'uid': 'user-1', 'app_id': 'app-1'})

    assert _run_webhook() == {"status": "success"}
    assert rearmed == []


def test_an_unreadable_subscription_does_not_fail_the_webhook(webhook, monkeypatch):
    rearmed = webhook(_invoice_event('invoice.paid', 'sub_1'), {'uid': 'user-1', 'app_id': 'app-1'})

    def _boom(sub_id):
        raise RuntimeError('stripe unavailable')

    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', staticmethod(_boom))

    assert _run_webhook() == {"status": "success"}
    assert rearmed == []


def _record_entitlement_ttls(monkeypatch):
    ttls = []
    monkeypatch.setattr(apps_utils, 'set_user_paid_app', lambda app_id, uid, ttl: ttls.append((app_id, uid, ttl)))
    return ttls


def test_a_renewal_keeps_the_entitlement_through_a_31_day_period(monkeypatch):
    period_end = int(time.time()) + 31 * _DAY
    monkeypatch.setattr(
        payment.stripe_utils, 'parse_event', lambda payload, sig: _invoice_event('invoice.paid', 'sub_1')
    )
    monkeypatch.setattr(
        payment.stripe.Subscription,
        'retrieve',
        staticmethod(
            lambda sub_id: {
                'id': sub_id,
                'metadata': {'uid': 'user-1', 'app_id': 'app-1'},
                'current_period_end': period_end,
            }
        ),
    )
    ttls = _record_entitlement_ttls(monkeypatch)

    assert _run_webhook() == {"status": "success"}
    [(app_id, uid, ttl)] = ttls
    assert (app_id, uid) == ('app-1', 'user-1')
    assert 31 * _DAY < ttl <= 32 * _DAY


def test_a_purchase_keeps_the_entitlement_through_a_31_day_first_period(monkeypatch):
    period_end = int(time.time()) + 31 * _DAY
    session = {
        'id': 'cs_1',
        'client_reference_id': 'uid_user-1',
        'metadata': {'app_id': 'app-1'},
        'subscription': 'sub_1',
        'customer': 'cus_1',
    }
    monkeypatch.setattr(
        payment.stripe_utils,
        'parse_event',
        lambda payload, sig: {'type': 'checkout.session.completed', 'data': {'object': session}},
    )
    monkeypatch.setattr(
        payment.stripe_utils,
        'modify_subscription',
        lambda sub_id, **kwargs: {'id': sub_id, 'metadata': kwargs['metadata'], 'current_period_end': period_end},
    )
    monkeypatch.setattr(payment, 'set_user_app_sub_customer_id', lambda app_id, uid, customer_id: None)
    ttls = _record_entitlement_ttls(monkeypatch)

    assert _run_webhook() == {"status": "success"}
    [(app_id, uid, ttl)] = ttls
    assert (app_id, uid) == ('app-1', 'user-1')
    assert 31 * _DAY < ttl <= 32 * _DAY


def test_an_elapsed_period_still_gets_the_renewal_grace(monkeypatch):
    ttls = _record_entitlement_ttls(monkeypatch)

    apps_utils.paid_app('app-1', 'user-1', int(time.time()) - 2 * _DAY)

    assert ttls == [('app-1', 'user-1', apps_utils._PAID_APP_RENEWAL_GRACE_SECONDS)]


def test_a_live_subscription_can_be_cancelled_when_the_entitlement_cache_is_cold(monkeypatch):
    cancelled = []

    class _Updated:
        @staticmethod
        def to_dict():
            return {'cancel_at_period_end': True, 'current_period_end': 1800000000}

    def _modify(sub_id, **kwargs):
        cancelled.append((sub_id, kwargs))
        return _Updated()

    monkeypatch.setattr(
        payment,
        'find_app_subscription',
        lambda app_id, uid, status_filter='all': {'id': 'sub_1', 'status': 'active'},
    )
    monkeypatch.setattr(payment.stripe_utils, 'modify_subscription', _modify)

    result = payment.cancel_app_subscription('app-1', uid='user-1')

    assert cancelled == [('sub_1', {'cancel_at_period_end': True})]
    assert result['status'] == 'success'
    assert result['cancel_at_period_end'] is True


def test_a_live_subscription_is_reported_when_the_entitlement_cache_is_cold(monkeypatch):
    monkeypatch.setattr(
        payment,
        'find_app_subscription',
        lambda app_id, uid, status_filter='all': {
            'id': 'sub_1',
            'status': 'active',
            'current_period_end': 1800000000,
            'cancel_at_period_end': False,
            'items': {'data': [{'price': {'id': 'price_1'}}]},
        },
    )

    result = payment.get_app_subscription('app-1', uid='user-1')

    assert result['subscription'] is not None
    assert result['subscription']['id'] == 'sub_1'
    assert result['subscription']['status'] == 'active'

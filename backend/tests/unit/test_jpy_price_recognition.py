"""JPY storefront prices resolve and unlock exactly like their USD counterparts."""

import asyncio
import time

import pytest
import stripe

from config.plan_catalog import (
    MANAGEMENT_CURRENCY_PRICES,
    RECOGNIZED_STRIPE_PRICE_INTERVALS,
    resolve_stripe_price_plan,
)
from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment
from utils import product_telemetry
from utils.observability import subscription_events
from utils.subscription import price_ids_match_plan_and_interval

JPY_PRICES = [
    ('price_1ULq501F8wnoWYvwwN56CHzO', PlanType.unlimited_v2, 'month'),
    ('price_1ULq5e1F8wnoWYvwQT8XQ4Uw', PlanType.unlimited_v2, 'year'),
    ('price_1ULq6b1F8wnoWYvwtchjjNqq', PlanType.plus, 'month'),
    ('price_1ULq7H1F8wnoWYvwC1poOtd5', PlanType.plus, 'year'),
]


@pytest.mark.parametrize('price_id,plan,interval', JPY_PRICES)
def test_jpy_price_resolves_to_plan_and_interval(price_id, plan, interval):
    assert resolve_stripe_price_plan(price_id) == plan
    assert RECOGNIZED_STRIPE_PRICE_INTERVALS[price_id] == interval
    assert price_ids_match_plan_and_interval(price_id, price_id)


def _stripe_sub(price_id):
    # JPY is zero-decimal: unit_amount is whole yen. The unlock path must not read it.
    # A resolved checkout writes this open period; the unlock gate re-reads it
    # through get_user_valid_subscription.
    now = int(time.time())
    return {
        'id': 'sub-jpy',
        'customer': 'cus-jpy',
        'status': 'active',
        'currency': 'jpy',
        'metadata': {'uid': 'user-jp'},
        'items': {'data': [{'id': 'si-jpy', 'price': {'id': price_id, 'currency': 'jpy', 'unit_amount': 4800}}]},
        'current_period_start': now - 86_400,
        'current_period_end': now + 30 * 86_400,
        'cancel_at_period_end': False,
    }


class _Request:
    async def body(self):
        return b'{}'


class _StripeSubscription:
    def __init__(self, obj):
        self._obj = obj

    def to_dict(self):
        return self._obj


@pytest.fixture
def webhook(monkeypatch):
    state = {'event': None, 'stored': None, 'unlocked': [], 'sub_obj': None}

    async def run_blocking(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    def write(uid, data):
        state['stored'] = Subscription.model_validate(data)

    def unlock(kind):
        return lambda uid: state['unlocked'].append((kind, uid))

    async def notify(uid):
        return None

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda payload, signature: state['event'])
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kwargs: None)
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    # Production re-reads the row _update_subscription_from_session just wrote.
    # A missing row is a new checkout; an open paid period unlocks.
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: state['stored'])
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state['stored'])
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: state['stored'])
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(payment.users_db, 'set_stripe_customer_id', lambda uid, customer_id: None)
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', lambda sid: _StripeSubscription(state['sub_obj']))
    monkeypatch.setattr(payment.stripe.Subscription, 'modify', lambda sid, **kwargs: None)
    monkeypatch.setattr(payment, 'send_subscription_paid_personalized_notification', notify)
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', lambda uid: None)
    monkeypatch.setattr(payment, 'clear_trial_paywall_cache', lambda uid: None)
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', lambda uid: None)
    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', unlock('conversations'))
    monkeypatch.setattr(payment.memories_db, 'unlock_all_memories', unlock('memories'))
    monkeypatch.setattr(payment.action_items_db, 'unlock_all_action_items', unlock('action_items'))
    monkeypatch.setattr('utils.observability.subscription_events.emit_billing_product_event', lambda **kwargs: None)
    return state


def _run():
    return asyncio.run(payment.stripe_webhook(_Request(), 'verified-fixture-signature'))


def _assert_unlocked(state, plan):
    assert state['stored'] is not None
    assert state['stored'].plan == plan
    assert state['stored'].stripe_subscription_id == 'sub-jpy'
    assert {kind for kind, uid in state['unlocked'] if uid == 'user-jp'} == {
        'conversations',
        'memories',
        'action_items',
    }


@pytest.mark.parametrize('price_id,plan,interval', JPY_PRICES)
def test_checkout_session_completed_unlocks_jpy_subscriber(webhook, price_id, plan, interval):
    webhook['sub_obj'] = _stripe_sub(price_id)
    webhook['event'] = {
        'id': 'evt-checkout-jpy',
        'type': 'checkout.session.completed',
        'data': {
            'object': stripe.StripeObject.construct_from(
                {
                    'id': 'cs-jpy',
                    'client_reference_id': 'user-jp',
                    'customer': 'cus-jpy',
                    'subscription': 'sub-jpy',
                    'currency': 'jpy',
                    'amount_total': 4800,
                    'metadata': {},
                },
                'sk_test_fixture',
            )
        },
    }

    _run()

    _assert_unlocked(webhook, plan)


@pytest.mark.parametrize('price_id,plan,interval', JPY_PRICES)
def test_customer_subscription_created_unlocks_jpy_subscriber(webhook, price_id, plan, interval):
    webhook['event'] = {
        'id': 'evt-created-jpy',
        'created': 1_790_000_000,
        'type': 'customer.subscription.created',
        'data': {'object': _stripe_sub(price_id)},
    }

    assert _run() == {'status': 'success'}

    _assert_unlocked(webhook, plan)


def test_jpy_fixture_omits_mrr_cents(monkeypatch):
    """unit_amount 4800 on the JPY storefront is yen, not USD cents."""

    emitted = []
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))
    price_id = JPY_PRICES[0][0]
    subscription = _stripe_sub(price_id)
    subscription['items']['data'][0]['price']['recurring'] = {'interval': 'month'}

    subscription_events.emit_billing_product_event(
        uid='user-jp',
        stripe_event_id='evt-jpy-mrr',
        stripe_event_created=1_790_000_000,
        stripe_event_type='customer.subscription.created',
        subscription_obj=subscription,
        previous_paid_subscription_id=None,
        resulting_paid_subscription_id='sub-jpy',
    )

    properties = emitted[0]['properties']
    assert properties['currency'] == 'jpy'
    assert properties['price_id'] == price_id
    assert 'mrr_cents' not in properties


class _MockPrice:
    def __init__(self, price_id: str, currency: str, unit_amount: int, interval: str, active: bool = True):
        self.id = price_id
        self.currency = currency
        self.unit_amount = unit_amount
        self.active = active
        self.livemode = True
        self.recurring = type('Recurring', (), {'interval': interval, 'interval_count': 1})()


def test_canonical_jpy_catalog_helpers():
    from utils.subscription import is_purchasable_price_id

    canonical_jpy_ids = frozenset(
        pid for pid, binding in MANAGEMENT_CURRENCY_PRICES.items() if binding.get('currency') == 'jpy'
    )
    assert 'price_1ULq6b1F8wnoWYvwtchjjNqq' in canonical_jpy_ids
    assert 'price_1ULq501F8wnoWYvwwN56CHzO' in canonical_jpy_ids
    assert 'price_1ULq5e1F8wnoWYvwQT8XQ4Uw' in canonical_jpy_ids
    assert MANAGEMENT_CURRENCY_PRICES['price_1ULq6b1F8wnoWYvwtchjjNqq']['plan_id'] == PlanType.plus.value
    assert MANAGEMENT_CURRENCY_PRICES['price_1ULq6b1F8wnoWYvwtchjjNqq']['interval'] == 'month'
    assert MANAGEMENT_CURRENCY_PRICES['price_1ULq5e1F8wnoWYvwQT8XQ4Uw']['plan_id'] == PlanType.unlimited_v2.value
    assert MANAGEMENT_CURRENCY_PRICES['price_1ULq5e1F8wnoWYvwQT8XQ4Uw']['interval'] == 'year'
    # Legacy recognition-ledger unlimited (v1) prices remain excluded from upgrade admission and fresh checkout
    assert 'price_1RtJPm1F8wnoWYvwhVJ38kLb' not in canonical_jpy_ids
    assert 'price_1RtJQ71F8wnoWYvwKMPaGlGY' not in canonical_jpy_ids
    assert is_purchasable_price_id('price_1RtJPm1F8wnoWYvwhVJ38kLb') is False
    assert is_purchasable_price_id('price_1ULq501F8wnoWYvwwN56CHzO') is False


def test_upgrade_subscription_allows_jpy_to_jpy_and_rejects_currency_mismatch(webhook, monkeypatch):
    from fastapi import HTTPException

    plus_monthly_jpy = 'price_1ULq6b1F8wnoWYvwtchjjNqq'
    unlim_monthly_jpy = 'price_1ULq501F8wnoWYvwwN56CHzO'
    usd_unlim_monthly = 'price_usd_unlim_monthly'
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', usd_unlim_monthly)

    sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_end=2_000_000_000,
        stripe_subscription_id='sub-jpy',
        current_price_id=plus_monthly_jpy,
    )
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: sub)
    stripe_sub_dict = _stripe_sub(plus_monthly_jpy)
    stripe_sub_dict['currency'] = 'jpy'
    stripe_sub_dict['status'] = 'active'
    monkeypatch.setattr(
        payment.stripe.Subscription,
        'retrieve',
        lambda sid: _StripeSubscription(stripe_sub_dict),
    )

    released = []
    monkeypatch.setattr(payment, '_release_attached_schedules', lambda s: released.append(s['id']))
    monkeypatch.setattr(
        payment.stripe.Price,
        'retrieve',
        lambda pid: _MockPrice(pid, 'jpy' if pid == unlim_monthly_jpy else 'usd', 4800, 'month'),
    )
    monkeypatch.setattr(
        payment,
        'price_for_currency',
        lambda base_price, curr: _MockPrice(unlim_monthly_jpy, 'jpy', 4800, 'month'),
    )
    monkeypatch.setattr(payment, 'funded_processing_enabled', lambda uid: False)

    # Mismatched USD price on JPY subscription is rejected before schedule release or Stripe modify
    with pytest.raises(HTTPException) as exc_info:
        payment.upgrade_subscription_endpoint(
            payment.UpgradeSubscriptionRequest(price_id=usd_unlim_monthly),
            uid='user-jp',
        )
    assert exc_info.value.status_code in (400, 409)
    assert released == []

    # Same-currency JPY target succeeds, releases schedules, and modifies the subscription item
    modified_calls = []
    monkeypatch.setattr(
        payment.stripe.Subscription,
        'modify',
        lambda sid, **kwargs: modified_calls.append((sid, kwargs))
        or _StripeSubscription(_stripe_sub(unlim_monthly_jpy)),
    )
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', lambda uid, data: None)

    result = payment.upgrade_subscription_endpoint(
        payment.UpgradeSubscriptionRequest(price_id=unlim_monthly_jpy),
        uid='user-jp',
    )
    assert released == ['sub-jpy']
    assert len(modified_calls) == 1
    assert modified_calls[0][0] == 'sub-jpy'
    assert result['status'] == 'success'

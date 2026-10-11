"""JPY storefront prices resolve and unlock exactly like their USD counterparts."""

import asyncio

import pytest
import stripe

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_INTERVALS, resolve_stripe_price_plan
from models.users import PlanType, Subscription
from routers import payment
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
    return {
        'id': 'sub-jpy',
        'customer': 'cus-jpy',
        'status': 'active',
        'currency': 'jpy',
        'metadata': {'uid': 'user-jp'},
        'items': {'data': [{'id': 'si-jpy', 'price': {'id': price_id, 'currency': 'jpy', 'unit_amount': 4800}}]},
        'current_period_start': 1_790_000_000,
        'current_period_end': 1_792_592_000,
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
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: None)
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

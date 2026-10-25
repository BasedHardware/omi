"""JPY storefront prices resolve and unlock exactly like their USD counterparts."""

import asyncio
import time

import pytest
import stripe

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_INTERVALS, resolve_stripe_price_plan
from models.users import PlanType, Subscription
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


def test_jpy_available_plans_endpoint_returns_jpy_catalog(monkeypatch):
    """JPY subscribers must receive JPY price IDs and yen pricing strings."""
    from fastapi import HTTPException
    from models.users import PlanType, Subscription, SubscriptionStatus

    uid = "test-jpy-user"
    jpy_sub_id = "sub_jpy_123"
    current_jpy_price = "price_1ULq6b1F8wnoWYvwtchjjNqq"

    user_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        stripe_subscription_id=jpy_sub_id,
        cancel_at_period_end=False,
    )

    stripe_sub_obj = {
        "id": jpy_sub_id,
        "currency": "jpy",
        "items": {
            "data": [
                {
                    "id": "si_123",
                    "price": {"id": current_jpy_price, "currency": "jpy", "unit_amount": 1500},
                }
            ]
        },
    }

    mock_prices = {
        "price_1ULq6b1F8wnoWYvwtchjjNqq": type("Price", (), {"id": "price_1ULq6b1F8wnoWYvwtchjjNqq", "unit_amount": 1500, "currency": "jpy", "recurring": type("R", (), {"interval": "month"})()})(),
        "price_1ULq7H1F8wnoWYvwC1poOtd5": type("Price", (), {"id": "price_1ULq7H1F8wnoWYvwC1poOtd5", "unit_amount": 15000, "currency": "jpy", "recurring": type("R", (), {"interval": "year"})()})(),
        "price_1ULq501F8wnoWYvwwN56CHzO": type("Price", (), {"id": "price_1ULq501F8wnoWYvwwN56CHzO", "unit_amount": 4800, "currency": "jpy", "recurring": type("R", (), {"interval": "month"})()})(),
        "price_1ULq5e1F8wnoWYvwQT8XQ4Uw": type("Price", (), {"id": "price_1ULq5e1F8wnoWYvwQT8XQ4Uw", "unit_amount": 48000, "currency": "jpy", "recurring": type("R", (), {"interval": "year"})()})(),
    }

    monkeypatch.setattr(payment.users_db, "get_user_subscription", lambda u: user_sub)
    monkeypatch.setattr(payment.users_db, "get_user_valid_subscription", lambda u: user_sub)
    monkeypatch.setattr(payment.stripe.Subscription, "retrieve", lambda sid: _StripeSubscription(stripe_sub_obj))
    monkeypatch.setattr(payment.stripe.SubscriptionSchedule, "list", lambda **kwargs: type("Schedules", (), {"data": []})())
    monkeypatch.setattr(payment.stripe.Price, "retrieve", lambda pid: mock_prices[pid])

    resp = payment.get_available_plans_endpoint(
        uid=uid,
        x_app_platform="ios",
        x_app_version="1.0.0",
    )

    plan_ids = [p.id for p in resp.plans]
    assert "price_1ULq6b1F8wnoWYvwtchjjNqq" in plan_ids
    assert "price_1ULq501F8wnoWYvwwN56CHzO" in plan_ids

    for p in resp.plans:
        assert p.price_string.startswith("¥"), f"Expected ¥ in price_string, got {p.price_string}"
        if p.id == current_jpy_price:
            assert p.is_active is True


def test_upgrade_subscription_rejects_currency_mismatch(monkeypatch):
    """Attempting to upgrade/change between USD and JPY prices must raise HTTP 400."""
    from fastapi import HTTPException
    from models.users import PlanType, Subscription, SubscriptionStatus

    uid = "test-jpy-user"
    user_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_jpy_123",
        cancel_at_period_end=False,
    )

    stripe_sub_obj = {
        "id": "sub_jpy_123",
        "currency": "jpy",
        "items": [
            {
                "id": "si_123",
                "price": {"id": "price_1ULq6b1F8wnoWYvwtchjjNqq", "currency": "jpy", "unit_amount": 1500},
            }
        ],
    }
    # Wrap in items.data structure
    stripe_sub_obj = {
        "id": "sub_jpy_123",
        "currency": "jpy",
        "items": {
            "data": [
                {
                    "id": "si_123",
                    "price": {"id": "price_1ULq6b1F8wnoWYvwtchjjNqq", "currency": "jpy", "unit_amount": 1500},
                }
            ]
        },
    }

    usd_target_price = type("Price", (), {
        "id": "price_usd_unlimited",
        "currency": "usd",
        "recurring": type("R", (), {"interval": "month"})(),
    })()

    monkeypatch.setattr(payment, "_validate_price_id", lambda pid: None)
    monkeypatch.setattr(payment.users_db, "get_user_subscription", lambda u: user_sub)
    monkeypatch.setattr(payment.stripe.Subscription, "retrieve", lambda sid: _StripeSubscription(stripe_sub_obj))
    monkeypatch.setattr(payment, "get_plan_type_from_price_id", lambda pid: PlanType.unlimited_v2 if "unlimited" in pid else PlanType.plus)
    monkeypatch.setattr(payment.stripe.Price, "retrieve", lambda pid: usd_target_price)

    req = payment.UpgradeSubscriptionRequest(price_id="price_usd_unlimited")

    with pytest.raises(HTTPException) as exc_info:
        payment.upgrade_subscription_endpoint(req, uid=uid)

    assert exc_info.value.status_code == 400
    assert "currency USD, which does not match your current subscription currency (JPY)" in exc_info.value.detail

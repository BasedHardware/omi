"""Exercise billing projection at the real webhook's reconciliation boundary."""

import asyncio

import pytest

from models.users import PlanType, Subscription
from routers import payment
from utils import product_telemetry


class _Request:
    async def body(self):
        return b'{}'


@pytest.fixture
def webhook(monkeypatch):
    state = {
        'stored': Subscription(plan=PlanType.unlimited, stripe_subscription_id='sub-old'),
        'replacement': None,
        'write_error': None,
        'writes': [],
        'events': [],
    }
    event = {
        'id': 'evt-paid-loss',
        'created': 1_758_700_800,
        'type': 'customer.subscription.deleted',
        'data': {'object': {'id': 'sub-old', 'status': 'canceled', 'metadata': {'uid': 'user-1'}}},
    }

    async def run_blocking(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    def write(uid, data):
        if state['write_error']:
            raise state['write_error']
        state['writes'].append((uid, data))
        state['stored'] = Subscription.model_validate(data)

    def capture(**kwargs):
        # A product event can only follow a confirmed durable write.
        assert state['writes']
        state['events'].append(kwargs)

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda payload, signature: event)
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kwargs: None)
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state['stored'])
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(payment, 'find_active_paid_subscription_for_user', lambda uid: state['replacement'])
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', lambda uid: None)
    monkeypatch.setattr(payment, 'clear_trial_paywall_cache', lambda uid: None)
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', lambda uid: None)
    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', lambda uid: None)
    monkeypatch.setattr(payment.memories_db, 'unlock_all_memories', lambda uid: None)
    monkeypatch.setattr(payment.action_items_db, 'unlock_all_action_items', lambda uid: None)
    monkeypatch.setattr(product_telemetry, 'emit_product_event', capture)
    return state


def _run():
    return asyncio.run(payment.stripe_webhook(_Request(), 'verified-fixture-signature'))


def test_replacement_paid_subscription_is_adopted_without_false_churn(webhook):
    webhook['replacement'] = Subscription(plan=PlanType.unlimited, stripe_subscription_id='sub-replacement')

    assert _run() == {'status': 'success'}
    assert webhook['stored'].stripe_subscription_id == 'sub-replacement'
    assert webhook['stored'].plan == PlanType.unlimited
    assert len(webhook['writes']) == 1
    assert webhook['events'] == []


@pytest.mark.parametrize(
    'error', [RuntimeError('durable write unavailable'), payment.FirestoreNotFound('owner removed')]
)
def test_failed_durable_entitlement_write_never_emits_churn(webhook, error):
    webhook['write_error'] = error

    if isinstance(error, payment.FirestoreNotFound):
        assert _run() == {'status': 'success'}
    else:
        with pytest.raises(RuntimeError, match='durable write unavailable'):
            _run()
    assert webhook['writes'] == []
    assert webhook['events'] == []
    assert webhook['stored'].plan == PlanType.unlimited


def test_confirmed_paid_loss_emits_once_and_webhook_replay_does_not_duplicate(webhook):
    assert _run() == {'status': 'success'}
    assert webhook['stored'].plan == PlanType.basic
    assert len(webhook['events']) == 1
    emitted = webhook['events'][0]
    assert emitted['event'] == 'Billing Subscription Churned'
    assert emitted['uid'] == 'user-1'
    assert emitted['properties']['billing_event_id'] == 'evt-paid-loss'

    assert _run() == {'status': 'success'}
    assert len(webhook['events']) == 1


def test_cache_failure_after_durable_write_does_not_erase_confirmed_transition(webhook, monkeypatch):
    def fail_cache(uid):
        raise RuntimeError('cache unavailable')

    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', fail_cache)
    with pytest.raises(RuntimeError, match='cache unavailable'):
        _run()
    assert webhook['stored'].plan == PlanType.basic
    assert [event['event'] for event in webhook['events']] == ['Billing Subscription Churned']

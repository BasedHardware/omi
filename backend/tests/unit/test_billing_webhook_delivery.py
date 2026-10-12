import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import BackgroundTasks

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from models.users import PlanType, Subscription
from routers import payment
from utils import product_telemetry
from utils.observability import billing_webhook, subscription_events


def _obj(price_id=None, amount=1799, interval='month', status='active', cancel=False):
    price_id = price_id or next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.plus)
    return {
        'id': 'sub-fixture',
        'created': 1758700700,
        'status': status,
        'cancel_at_period_end': cancel,
        'metadata': {'uid': 'user-fixture'},
        'items': {'data': [{'price': {'id': price_id, 'unit_amount': amount, 'recurring': {'interval': interval}}}]},
    }


def _args(**changes):
    args = dict(
        uid='user-fixture',
        stripe_event_id='evt-fixture',
        stripe_event_created=1758700800,
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_obj(),
        previous_paid_subscription_id='sub-fixture',
        resulting_paid_subscription_id='sub-fixture',
    )
    return args | changes


@pytest.fixture
def captures(monkeypatch):
    events = []
    monkeypatch.setattr(product_telemetry, 'emit_product_event', lambda **kw: events.append(kw))
    return events


@pytest.mark.parametrize('prior', [None, 'sub-fixture'])
def test_checkout_before_or_after_activation_has_one_subscription_identity(captures, prior):
    subscription_events.emit_billing_product_event(
        **_args(previous_paid_subscription_id=prior, previous_attributes={'status': 'incomplete'})
    )
    subscription_events.emit_billing_product_event(
        **_args(
            stripe_event_type='customer.subscription.created',
            stripe_event_id='evt-other',
            stripe_event_created=1758700700,
        )
    )
    assert [e['event'] for e in captures] == ['Billing Subscription Started'] * 2
    ids = {e['properties']['$insert_id'] for e in captures}
    assert len({e['properties']['occurred_at'] for e in captures}) == 1
    assert len(ids) == 1
    assert UUID(ids.pop())
    assert all('sub-fixture' not in str(e['properties']) for e in captures)


@pytest.mark.parametrize(
    'previous,status,cancel,expected',
    [
        ({'cancel_at_period_end': False}, 'active', True, 1),
        ({'cancel_at_period_end': False}, 'trialing', True, 1),
        ({'cancel_at_period_end': True}, 'active', True, 0),
        ({'status': 'trialing'}, 'active', True, 0),
        ({'cancel_at_period_end': True}, 'active', False, 0),
    ],
)
def test_scheduled_cancellation_is_a_transition_not_churn(captures, previous, status, cancel, expected):
    billing_webhook.emit_billing_webhook_events(
        **_args(subscription_obj=_obj(status=status, cancel=cancel), previous_attributes=previous)
    )
    assert len(captures) == expected
    if expected:
        assert captures[0]['event'] == 'Billing Subscription Cancellation Scheduled'
        assert captures[0]['properties']['mrr_cents'] == 1799
        assert captures[0]['properties']['reason'] == 'none'


@pytest.mark.parametrize('reverse', [False, True])
def test_paid_price_change_emits_both_tiers_and_monthly_amounts(captures, reverse):
    plus = _obj()
    operator_id = next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.operator)
    operator = _obj(operator_id, amount=58800, interval='year')
    before, after = (operator, plus) if reverse else (plus, operator)
    billing_webhook.emit_billing_webhook_events(**_args(subscription_obj=after, previous_attributes=before))
    assert len(captures) == 1
    e = captures[0]
    assert e['event'] == 'Billing Subscription Plan Changed'
    assert e['properties']['previous_plan'] == ('operator' if reverse else 'plus')
    assert e['properties']['new_plan'] == ('plus' if reverse else 'operator')
    assert e['properties']['mrr_before_cents'] == (4900 if reverse else 1799)
    assert e['properties']['mrr_after_cents'] == (1799 if reverse else 4900)


@pytest.mark.parametrize('prior', [None, {}, {'items': {'data': []}}])
def test_missing_prior_price_does_not_invent_a_plan_change(captures, prior):
    billing_webhook.emit_billing_webhook_events(**_args(previous_attributes=prior))
    assert captures == []


def test_simultaneous_price_and_cancel_transition_emits_both(captures):
    before = _obj()
    after = _obj(next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.operator), cancel=True)
    billing_webhook.emit_billing_webhook_events(**_args(subscription_obj=after, previous_attributes=before))
    assert {e['event'] for e in captures} == {
        'Billing Subscription Plan Changed',
        'Billing Subscription Cancellation Scheduled',
    }


def test_trial_to_active_is_not_another_start(captures):
    billing_webhook.emit_billing_webhook_events(**_args(previous_attributes={'status': 'trialing'}))
    assert captures == []


@pytest.fixture
def isolated_clients(monkeypatch):
    for name in ('POSTHOG_PROJECT_API_KEY', 'POSTHOG_API_KEY', 'POSTHOG_BILLING_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(product_telemetry, '_posthog_client', None)
    monkeypatch.setattr(product_telemetry, '_posthog_disabled', False)
    monkeypatch.setattr(product_telemetry, '_billing_client', None)


def test_no_key_never_constructs_sdk(isolated_clients, monkeypatch):
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', lambda _: pytest.fail('must not construct SDK'))
    product_telemetry.emit_product_event(uid='user', event='Billing Subscription Started', properties={})


def test_alias_only_constructs_billing_sync_client(isolated_clients, monkeypatch):
    created = []

    class Client:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def capture(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', 'fake-offline-key')
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=Client))
    product_telemetry.emit_product_event(uid='user', event='Task Extracted', properties={})
    assert created == []
    product_telemetry.emit_product_event(
        uid='user', event='Billing Subscription Started', properties={'$insert_id': 'uuid-fixture'}
    )
    assert created[0]['sync_mode'] is True
    assert created[0]['timeout'] == 2
    assert created[0]['max_retries'] == 0
    assert created[1]['uuid'] == 'uuid-fixture'


def test_capture_failure_after_response_preserves_entitlement(monkeypatch):
    event = {
        'id': 'evt-new',
        'type': 'customer.subscription.updated',
        'created': 1758700800,
        'data': {'object': _obj(), 'previous_attributes': {'status': 'incomplete'}},
    }
    state = {'writes': [], 'captures': 0}

    class Request:
        async def body(self):
            return b'{}'

    class Client:
        def capture(self, **kwargs):
            state['captures'] += 1
            assert state['writes']
            raise RuntimeError('offline SDK failure')

    async def blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(payment, 'run_blocking', blocking)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    monkeypatch.setattr(
        payment.users_db,
        'get_existing_user_subscription',
        lambda uid: Subscription(plan=PlanType.plus, stripe_subscription_id='sub-fixture'),
    )
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', lambda *args: state['writes'].append(args))
    monkeypatch.setattr(payment.users_db, 'set_stripe_customer_id', lambda *args: None)
    for module, name in [
        (payment, 'set_credits_invalidation_signal'),
        (payment, 'clear_trial_paywall_cache'),
        (payment, 'clear_fair_use_on_upgrade'),
        (payment.conversations_db, 'unlock_all_conversations'),
        (payment.memories_db, 'unlock_all_memories'),
        (payment.action_items_db, 'unlock_all_action_items'),
    ]:
        monkeypatch.setattr(module, name, lambda *args: None)
    monkeypatch.setattr(product_telemetry, '_billing_client', Client())

    async def run():
        tasks = BackgroundTasks()
        response = await payment.stripe_webhook(Request(), 'fixture-signature', tasks)
        assert response == {'status': 'success'}
        assert state['writes'][0][1]['plan'] == PlanType.plus.value
        assert state['captures'] == 0
        await tasks()
        assert state['captures'] == 1

    asyncio.run(run())

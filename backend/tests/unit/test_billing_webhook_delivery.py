import asyncio
from threading import Lock
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from database import redis_db, stripe_event_ledger
from models.users import PlanType, Subscription
from routers import payment
from utils import product_telemetry, stripe_webhook_ledger
from utils.observability import billing_webhook, subscription_events


def _obj(price_id=None, amount=1799, interval='month', status='active', cancel=False, currency='usd'):
    price_id = price_id or next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.plus)
    return {
        'id': 'sub-fixture',
        'created': 1758700700,
        'status': status,
        'cancel_at_period_end': cancel,
        'metadata': {'uid': 'user-fixture'},
        'items': {
            'data': [
                {
                    'price': {
                        'id': price_id,
                        'currency': currency,
                        'unit_amount': amount,
                        'recurring': {'interval': interval},
                    }
                }
            ]
        },
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
        if status == 'trialing':
            assert 'mrr_cents' not in captures[0]['properties']
        else:
            assert captures[0]['properties']['mrr_cents'] == 1799
        assert captures[0]['properties']['is_trial'] is (status == 'trialing')
        assert captures[0]['properties']['reason'] == 'none'


@pytest.mark.parametrize('reverse', [False, True])
def test_paid_price_change_emits_both_tiers_and_monthly_amounts(captures, reverse):
    plus = _obj()
    operator_id = next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.operator)
    operator = _obj(operator_id, amount=58800, interval='year')
    before, after = (operator, plus) if reverse else (plus, operator)
    billing_webhook.emit_billing_webhook_events(
        **_args(subscription_obj=after, previous_attributes={'items': before['items']})
    )
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
    previous = {'items': before['items'], 'cancel_at_period_end': False}
    after = _obj(next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.operator), cancel=True)
    billing_webhook.emit_billing_webhook_events(**_args(subscription_obj=after, previous_attributes=previous))
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
    monkeypatch.setattr(product_telemetry, '_posthog_clients', {})
    monkeypatch.setattr(product_telemetry, '_invalid_key_logged', False)


def test_no_key_never_constructs_sdk(isolated_clients, monkeypatch):
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', lambda _: pytest.fail('must not construct SDK'))
    product_telemetry.emit_product_event(uid='user', event='Billing Subscription Started', properties={})


def test_billing_uses_shared_client_and_preserves_delivery_metadata(isolated_clients, monkeypatch):
    client = SimpleNamespace(capture=Mock())
    monkeypatch.setattr(product_telemetry, '_injected_client', client)
    product_telemetry.emit_product_event(
        uid='user',
        event='Billing Subscription Started',
        properties={
            '$insert_id': 'uuid-fixture',
            'occurred_at': '2026-10-15T12:00:00Z',
        },
    )
    assert client.capture.call_args.kwargs['uuid'] == 'uuid-fixture'
    assert client.capture.call_args.kwargs['timestamp'].isoformat() == '2026-10-15T12:00:00+00:00'
    assert client.capture.call_args.kwargs['properties']['emitter'] == 'server'


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
        (payment, 'clear_fair_use_on_upgrade'),
        (payment.conversations_db, 'unlock_all_conversations'),
        (payment.memories_db, 'unlock_all_memories'),
        (payment.action_items_db, 'unlock_all_action_items'),
    ]:
        monkeypatch.setattr(module, name, lambda *args: None)
    monkeypatch.setattr(product_telemetry, '_injected_client', Client())

    async def run():
        tasks = BackgroundTasks()
        response = await payment.stripe_webhook(Request(), 'fixture-signature', tasks)
        assert response == {'status': 'success'}
        assert state['writes'][0][1]['plan'] == PlanType.plus.value
        assert state['captures'] == 0
        await tasks()
        assert state['captures'] == 1

    asyncio.run(run())


@pytest.mark.parametrize('failed_status', ['past_due', 'unpaid'])
def test_payment_recovery_is_a_later_distinct_started_event(captures, failed_status):
    initial = _args(
        stripe_event_type='customer.subscription.created',
        stripe_event_id='evt-initial',
        previous_paid_subscription_id=None,
    )
    loss = _args(
        stripe_event_id='evt-loss',
        stripe_event_created=1758700900,
        subscription_obj=_obj(status=failed_status),
        resulting_paid_subscription_id=None,
        previous_attributes={'status': 'active'},
    )
    recovery = _args(
        stripe_event_id='evt-recovery',
        stripe_event_created=1758701000,
        previous_paid_subscription_id=None,
        previous_attributes={'status': failed_status},
    )
    for delivery in (initial, loss, recovery, recovery):
        billing_webhook.emit_billing_webhook_events(**delivery)
    assert [event['event'] for event in captures] == [
        'Billing Subscription Started',
        'Billing Subscription Churned',
        'Billing Subscription Started',
        'Billing Subscription Started',
    ]
    first, churn, recovered, replay = [event['properties'] for event in captures]
    assert recovered['$insert_id'] != first['$insert_id']
    assert first['occurred_at'] < churn['occurred_at'] < recovered['occurred_at']
    assert recovered['$insert_id'] == replay['$insert_id']
    assert recovered['occurred_at'] == replay['occurred_at']


@pytest.mark.parametrize(
    'status,currency',
    [('active', 'usd'), ('active', ' USD '), ('trialing', 'usd'), ('active', 'eur'), ('active', None)],
)
def test_lifecycle_currency_and_trial_gate_catalog_mrr(captures, status, currency):
    billing_webhook.emit_billing_webhook_events(
        **_args(
            stripe_event_type='customer.subscription.created',
            previous_paid_subscription_id=None,
            subscription_obj=_obj(status=status, currency=currency),
        )
    )
    properties = captures[0]['properties']
    assert properties['currency'] == (currency.strip().lower() if currency else 'unknown')
    assert properties['is_trial'] is (status == 'trialing')
    assert properties['billing_measurement'] == (
        'trial_plan_entitlement' if status == 'trialing' else 'paid_plan_entitlement'
    )
    if status != 'trialing' and currency and currency.strip().lower() == 'usd':
        assert properties['mrr_cents'] == 1799
    else:
        assert 'mrr_cents' not in properties


@pytest.mark.parametrize('status,currency', [('trialing', 'usd'), ('active', 'eur'), ('active', None)])
def test_plan_movement_keeps_tiers_but_omits_ineligible_mrr(captures, status, currency):
    before = _obj(status=status, currency=currency)
    operator_id = next(k for k, v in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if v == PlanType.operator)
    after = _obj(operator_id, amount=4900, status=status, currency=currency)
    billing_webhook.emit_billing_webhook_events(
        **_args(
            subscription_obj=after,
            previous_attributes={'items': before['items']},
        )
    )
    properties = captures[0]['properties']
    assert properties['previous_plan'] == 'plus'
    assert properties['new_plan'] == 'operator'
    assert properties['currency'] == (currency.strip().lower() if currency else 'unknown')
    assert properties['is_trial'] is (status == 'trialing')
    assert not {'mrr_cents', 'mrr_before_cents', 'mrr_after_cents'} & properties.keys()


def test_annual_catalog_mrr_matches_w2_round_half_up(captures):
    billing_webhook.emit_billing_webhook_events(
        **_args(
            stripe_event_type='customer.subscription.created',
            previous_paid_subscription_id=None,
            subscription_obj=_obj(amount=19990, interval='year'),
        )
    )
    assert captures[0]['properties']['mrr_cents'] == 1666


def _recovery_event(status='past_due', previous_status='active', previous_invoice=None):
    subscription = _obj(status=status)
    subscription.update(
        {
            'collection_method': 'charge_automatically',
            'latest_invoice': 'in-recovery',
            'current_period_start': 1758600000,
        }
    )
    previous = {'status': previous_status}
    if previous_invoice is not None:
        previous['latest_invoice'] = previous_invoice
    return {
        'id': 'evt-recovery-push',
        'type': 'customer.subscription.updated',
        'created': 1758700800,
        'data': {'object': subscription, 'previous_attributes': previous},
    }


@pytest.fixture
def recovery_lane(monkeypatch):
    monkeypatch.delenv('PAYMENT_RECOVERY_NOTIFICATION_ENABLED', raising=False)
    state = SimpleNamespace(
        calls=[],
        notifications=[],
        current=Subscription(plan=PlanType.plus, stripe_subscription_id='sub-fixture'),
        persist_error=None,
        invoice_error=None,
        claim_error=None,
        claims=set(),
        claim_lock=Lock(),
        invoice={
            'status': 'open',
            'attempted': True,
            'amount_remaining': 1799,
            'billing_reason': 'subscription_cycle',
        },
    )

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def write(uid, payload):
        if state.persist_error:
            raise state.persist_error
        state.calls.append(('write', uid))
        state.current = Subscription.model_validate(payload)

    def retrieve_invoice(invoice_id):
        state.calls.append(('invoice', invoice_id))
        if state.invoice_error:
            raise state.invoice_error
        return SimpleNamespace(to_dict=lambda: dict(state.invoice))

    def claim(uid, invoice_id):
        state.calls.append(('claim', uid, invoice_id))
        if state.claim_error:
            raise state.claim_error
        marker = (uid, invoice_id)
        with state.claim_lock:
            if marker in state.claims:
                return False
            state.claims.add(marker)
            return True

    def notify(intent):
        state.notifications.append(
            {'uid': intent.user_id, 'title': intent.title, 'body': intent.body, 'data': intent.data}
        )

    async def no_telemetry(*args, **kwargs):
        return None

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kwargs: None)
    monkeypatch.setattr(payment, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(payment, 'find_active_paid_subscription_for_user', lambda uid: None)
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', lambda uid: None)
    monkeypatch.setattr(payment, 'funded_processing_enabled', lambda uid: False)
    monkeypatch.setattr(payment.stripe.Invoice, 'retrieve', retrieve_invoice)
    monkeypatch.setattr(payment, 'claim_payment_recovery_notification', claim)
    monkeypatch.setattr(payment, 'dispatch_notification', notify)
    monkeypatch.setattr(billing_webhook, 'schedule_billing_webhook_events', no_telemetry)
    return state


def test_payment_recovery_push_defaults_on_and_is_scheduled_after_persistence(recovery_lane):
    async def run():
        tasks = BackgroundTasks()
        await payment._handle_stripe_event(_recovery_event(), tasks)
        assert recovery_lane.calls == [
            ('write', 'user-fixture'),
            ('invoice', 'in-recovery'),
            ('claim', 'user-fixture', 'in-recovery'),
        ]
        assert recovery_lane.notifications == []

        await tasks()
        assert recovery_lane.notifications == [
            {
                'uid': 'user-fixture',
                'title': 'Payment declined',
                'body': 'Update your payment method to restore your subscription benefits.',
                'data': {'type': 'payment_issue', 'navigate_to': '/conversations'},
            }
        ]

    asyncio.run(run())


def test_payment_recovery_push_off_preserves_persistence_without_invoice_retrieval(recovery_lane, monkeypatch):
    monkeypatch.setenv('PAYMENT_RECOVERY_NOTIFICATION_ENABLED', 'off')

    async def run():
        tasks = BackgroundTasks()
        result = await payment._handle_stripe_event(_recovery_event(), tasks)

        assert result == {'status': 'success'}
        assert recovery_lane.current.plan == PlanType.basic
        assert recovery_lane.current.stripe_subscription_id == 'sub-fixture'
        assert recovery_lane.calls == [('write', 'user-fixture')]
        await tasks()
        assert recovery_lane.notifications == []

    asyncio.run(run())


def test_previous_paid_invoice_cannot_replace_current_failed_invoice(recovery_lane):
    async def run():
        tasks = BackgroundTasks()
        previous_invoice = {
            'status': 'paid',
            'attempted': True,
            'amount_remaining': 0,
            'billing_reason': 'subscription_cycle',
        }
        event = _recovery_event(previous_invoice=previous_invoice)
        await payment._handle_stripe_event(event, tasks)
        assert recovery_lane.calls == [
            ('write', 'user-fixture'),
            ('invoice', 'in-recovery'),
            ('claim', 'user-fixture', 'in-recovery'),
        ]
        await tasks()
        assert len(recovery_lane.notifications) == 1

    asyncio.run(run())


def test_recovery_state_update_does_not_retrieve_or_notify(recovery_lane):
    async def run():
        tasks = BackgroundTasks()
        await payment._handle_stripe_event(_recovery_event(status='unpaid', previous_status='past_due'), tasks)
        assert recovery_lane.calls == [('write', 'user-fixture')]
        await tasks()
        assert recovery_lane.notifications == []

    asyncio.run(run())


def test_failed_persistence_schedules_no_recovery_push(recovery_lane):
    recovery_lane.persist_error = RuntimeError('fixture persistence failure')

    async def run():
        tasks = BackgroundTasks()
        with pytest.raises(RuntimeError, match='fixture persistence failure'):
            await payment._handle_stripe_event(_recovery_event(), tasks)
        assert recovery_lane.calls == []
        await tasks()
        assert recovery_lane.notifications == []

    asyncio.run(run())


def test_invoice_failure_after_persistence_remains_retryable(recovery_lane):
    recovery_lane.invoice_error = RuntimeError('fixture invoice failure')

    async def run():
        tasks = BackgroundTasks()
        with pytest.raises(RuntimeError, match='fixture invoice failure'):
            await payment._handle_stripe_event(_recovery_event(), tasks)
        assert recovery_lane.calls == [('write', 'user-fixture'), ('invoice', 'in-recovery')]
        await tasks()
        assert recovery_lane.notifications == []

    asyncio.run(run())


def test_payment_recovery_claim_uses_atomic_bounded_redis_marker(monkeypatch):
    client = Mock()
    client.set.side_effect = [True, None]
    monkeypatch.setattr(redis_db, 'r', client)

    assert payment.claim_payment_recovery_notification('user-fixture', 'in-recovery') is True
    assert payment.claim_payment_recovery_notification('user-fixture', 'in-recovery') is False
    assert len(client.set.call_args_list) == 2
    for invocation in client.set.call_args_list:
        assert invocation.args == ('users:user-fixture:payment_recovery_notification:in-recovery', '1')
        assert invocation.kwargs == {
            'nx': True,
            'ex': redis_db.PAYMENT_RECOVERY_NOTIFICATION_TTL_SECONDS,
        }
    assert redis_db.PAYMENT_RECOVERY_NOTIFICATION_TTL_SECONDS == 90 * 24 * 60 * 60


def test_duplicate_current_invoice_is_suppressed_with_webhook_ledger_off(recovery_lane, monkeypatch):
    event = _recovery_event()

    class Request:
        async def body(self):
            return b'{}'

    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'false')
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)

    async def run():
        for _ in range(2):
            tasks = BackgroundTasks()
            assert await payment.stripe_webhook(Request(), 'fixture-signature', tasks) == {'status': 'success'}
            await tasks()

        assert len(recovery_lane.notifications) == 1
        assert recovery_lane.claims == {('user-fixture', 'in-recovery')}
        assert recovery_lane.calls.count(('write', 'user-fixture')) == 2
        assert recovery_lane.calls.count(('invoice', 'in-recovery')) == 2
        assert recovery_lane.calls.count(('claim', 'user-fixture', 'in-recovery')) == 2

    asyncio.run(run())


def test_concurrent_duplicate_invoice_claims_schedule_once(recovery_lane, monkeypatch):
    event = _recovery_event()
    subscription_obj = event['data']['object']
    previous_attributes = event['data']['previous_attributes']

    async def run_blocking(executor, fn, *args, **kwargs):
        await asyncio.sleep(0)
        return fn(*args, **kwargs)

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)

    async def schedule():
        tasks = BackgroundTasks()
        await payment._schedule_payment_recovery_notification(
            tasks,
            'user-fixture',
            subscription_obj,
            previous_attributes,
            recovery_lane.current,
            True,
        )
        return tasks

    async def run():
        scheduled = await asyncio.gather(schedule(), schedule())
        for tasks in scheduled:
            await tasks()
        assert len(recovery_lane.notifications) == 1
        assert recovery_lane.claims == {('user-fixture', 'in-recovery')}
        assert recovery_lane.calls.count(('invoice', 'in-recovery')) == 2
        assert recovery_lane.calls.count(('claim', 'user-fixture', 'in-recovery')) == 2

    asyncio.run(run())


def test_different_current_invoice_can_notify(recovery_lane):
    first = _recovery_event()
    second = _recovery_event()
    second['id'] = 'evt-recovery-push-next'
    second['data']['object']['latest_invoice'] = 'in-recovery-next'

    async def run():
        for event in (first, second):
            tasks = BackgroundTasks()
            await payment._handle_stripe_event(event, tasks)
            await tasks()

        assert len(recovery_lane.notifications) == 2
        assert recovery_lane.claims == {
            ('user-fixture', 'in-recovery'),
            ('user-fixture', 'in-recovery-next'),
        }

    asyncio.run(run())


def test_missing_current_invoice_id_notifies_zero_and_remains_retryable(recovery_lane):
    event = _recovery_event()
    event['data']['object']['latest_invoice'] = dict(recovery_lane.invoice)

    async def run():
        first_tasks = BackgroundTasks()
        with pytest.raises(ValueError, match='requires a current invoice id'):
            await payment._handle_stripe_event(event, first_tasks)
        await first_tasks()
        assert recovery_lane.calls == [('write', 'user-fixture')]
        assert recovery_lane.notifications == []
        assert recovery_lane.claims == set()

        event['data']['object']['latest_invoice']['id'] = 'in-recovery'
        retry_tasks = BackgroundTasks()
        await payment._handle_stripe_event(event, retry_tasks)
        await retry_tasks()
        assert len(recovery_lane.notifications) == 1
        assert recovery_lane.claims == {('user-fixture', 'in-recovery')}

    asyncio.run(run())


def test_claim_failure_notifies_zero_and_remains_retryable(recovery_lane):
    recovery_lane.claim_error = RuntimeError('fixture claim failure')

    async def run():
        first_tasks = BackgroundTasks()
        with pytest.raises(RuntimeError, match='fixture claim failure'):
            await payment._handle_stripe_event(_recovery_event(), first_tasks)
        await first_tasks()
        assert recovery_lane.notifications == []
        assert recovery_lane.claims == set()

        recovery_lane.claim_error = None
        retry_tasks = BackgroundTasks()
        await payment._handle_stripe_event(_recovery_event(), retry_tasks)
        await retry_tasks()
        assert len(recovery_lane.notifications) == 1
        assert recovery_lane.claims == {('user-fixture', 'in-recovery')}

    asyncio.run(run())


def test_duplicate_transition_delivery_is_suppressed_by_existing_ledger(recovery_lane, monkeypatch):
    event = _recovery_event()
    acknowledged = set()

    def claim(delivery, token):
        if delivery['id'] in acknowledged:
            return stripe_event_ledger.Claim('duplicate')
        return stripe_event_ledger.Claim('claimed', token)

    def finish(delivery, token, *, succeeded):
        if succeeded:
            acknowledged.add(delivery['id'])
        return False

    class Request:
        async def body(self):
            return b'{}'

    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(stripe_webhook_ledger, 'webhook_ledger_enabled', lambda: True)
    monkeypatch.setattr(stripe_event_ledger, 'claim_event', claim)
    monkeypatch.setattr(stripe_event_ledger, 'finish_event', finish)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)

    async def run():
        first_tasks = BackgroundTasks()
        assert await payment.stripe_webhook(Request(), 'fixture-signature', first_tasks) == {'status': 'success'}
        await first_tasks()
        second_tasks = BackgroundTasks()
        assert await payment.stripe_webhook(Request(), 'fixture-signature', second_tasks) == {'status': 'success'}
        await second_tasks()
        assert len(recovery_lane.notifications) == 1
        assert recovery_lane.claims == {('user-fixture', 'in-recovery')}
        assert recovery_lane.calls.count(('claim', 'user-fixture', 'in-recovery')) == 1
        assert recovery_lane.calls.count(('write', 'user-fixture')) == 1

    asyncio.run(run())

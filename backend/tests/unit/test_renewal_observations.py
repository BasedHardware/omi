"""Renewal observations stay off entitlement paths and retain provider facts."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import AlreadyExists
from routers import payment

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from utils.observability import renewal_observations as observations

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def invoice(kind='invoice.payment_failed', attempt=1, event_id='evt_fixture'):
    price = next(iter(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES))
    return {
        'id': event_id,
        'livemode': True,
        'created': 1794358800,
        'type': kind,
        'data': {
            'object': {
                'id': 'in_fixture',
                'subscription': 'sub_fixture',
                'billing_reason': 'subscription_cycle',
                'status': 'paid' if kind in {'invoice.paid', 'invoice.payment_succeeded'} else 'open',
                'attempt_count': attempt,
                'attempted': True,
                'amount_due': 3000,
                'customer': 'cus_private',
                'customer_email': 'fixture@example.invalid',
                'lines': {'data': [{'price': {'id': price, 'recurring': {'interval': 'year'}}}]},
            }
        },
    }


class Store:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        assert name == observations.COLLECTION
        return self

    def document(self, key):
        def create(fields, *, retry, timeout):
            assert retry is None and timeout == 1.0
            if key in self.rows:
                raise AlreadyExists('fixture duplicate')
            self.rows[key] = deepcopy(fields)

        return SimpleNamespace(create=create)


@pytest.mark.parametrize('kind,outcome', observations.INVOICE_OUTCOMES.items())
def test_observes_actual_provider_outcome_without_private_payload(kind, outcome):
    key, fields = observations.project_event(invoice(kind), now=NOW)
    assert len(key) == 64
    assert fields['outcome'] == outcome
    assert fields['interval'] == 'year'
    assert fields['attempt_count'] == 1
    assert fields['expires_at'] == NOW + timedelta(days=90)
    assert fields['renewal_ordinal'] == 'unknown'
    assert not any(value in str(fields) for value in ['cus_private', 'sub_fixture', 'in_fixture', 'fixture@example'])
    assert not {'uid', 'customer', 'email', 'payload', 'line_items', 'event_id'}.intersection(fields)


def test_duplicate_webhooks_and_paid_alias_are_one_semantic_fact_and_retries_are_distinct():
    store = Store()
    for kind in ['invoice.payment_succeeded', 'invoice.paid', 'invoice.paid']:
        observations.persist_observation(observations.project_event(invoice(kind), now=NOW), client=store)
    assert len(store.rows) == 1
    observations.persist_observation(observations.project_event(invoice(attempt=2), now=NOW), client=store)
    observations.persist_observation(observations.project_event(invoice(attempt=1), now=NOW), client=store)
    assert len(store.rows) == 3
    assert sorted(x['attempt_count'] for x in store.rows.values()) == [1, 1, 2]
    assert {x['outcome'] for x in store.rows.values()} == {'paid', 'failed'}


@pytest.mark.parametrize(
    'patch',
    [
        {'billing_reason': 'subscription_create'},
        {'subscription': None},
        {'attempt_count': True},
        {'attempt_count': -1},
        {'attempt_count': '1'},
        {'metadata': {'app_id': 'fixture_app'}},
    ],
)
def test_nonrenewals_creator_apps_and_unknown_attempts_are_not_claimed(patch):
    event = invoice()
    event['data']['object'].update(patch)
    assert observations.project_event(event, now=NOW) is None


def test_unknown_and_truncated_line_coverage_remains_unknown_and_no_attempt_is_inferred():
    event = invoice('invoice.finalized', attempt=0)
    event['data']['object'].update(attempted=False, paid_out_of_band=True)
    event['data']['object']['lines']['has_more'] = True
    _, fields = observations.project_event(event, now=NOW)
    assert fields['attempted'] is False
    assert fields['outcome'] == 'finalized'
    assert fields['scope'] == fields['interval'] == fields['plan'] == 'unknown'


def test_mixed_unknown_price_is_not_mistaken_for_full_consumer_coverage():
    event = invoice()
    event['data']['object']['lines']['data'].append({'price': {'id': 'price_unrecognized'}})
    _, fields = observations.project_event(event, now=NOW)
    assert fields['scope'] == fields['plan'] == fields['interval'] == 'unknown'


def test_subscription_snapshot_links_provider_cancellation_not_effective_payer_churn():
    event = {
        'id': 'evt_subscription',
        'created': 1794358801,
        'type': 'customer.subscription.updated',
        'data': {
            'previous_attributes': {'cancel_at_period_end': False},
            'object': {
                'id': 'sub_fixture',
                'latest_invoice': 'in_fixture',
                'status': 'active',
                'cancel_at_period_end': True,
                'items': {'data': []},
            },
        },
    }
    _, fields = observations.project_event(event, now=NOW)
    _, attempt = observations.project_event(invoice(), now=NOW)
    assert fields['subscription_key'] == attempt['subscription_key']
    assert fields['invoice_key'] == attempt['invoice_key']
    assert fields['cancel_at_period_end'] is True
    assert fields['observation_kind'] == 'subscription_snapshot'
    assert 'attempt_count' not in fields
    event['data']['previous_attributes'] = {'description': 'private content'}
    assert observations.project_event(event, now=NOW) is None


def test_disabled_observer_performs_no_projection_or_io(monkeypatch):
    monkeypatch.setenv('BILLING_RENEWAL_OBSERVATIONS_ENABLED', 'off')
    monkeypatch.setattr(observations, 'project_event', lambda _: pytest.fail('gate must precede projection'))
    asyncio.run(observations.observe_verified_event(invoice()))


@pytest.mark.parametrize('mode', ['success', 'error', 'timeout'])
def test_real_observer_executor_boundary_is_bounded_and_fail_open(monkeypatch, mode):
    monkeypatch.delenv('BILLING_RENEWAL_OBSERVATIONS_ENABLED', raising=False)
    calls = []
    fallback = []
    outcomes = []
    monkeypatch.setattr(observations, '_record_outcome', outcomes.append)
    monkeypatch.setattr(observations, 'record_fallback', lambda **kw: fallback.append(kw))

    async def run(executor, fn, payload):
        calls.append((fn, payload))
        if mode == 'error':
            raise RuntimeError('private exception must not be logged')
        if mode == 'timeout':
            raise asyncio.TimeoutError()
        return 'created'

    monkeypatch.setattr(observations, 'run_blocking', run)
    assert asyncio.run(observations.observe_verified_event(invoice())) is None
    assert len(calls) == 1
    assert len(fallback) == (mode != 'success')
    assert outcomes == ['eligible', {'success': 'created', 'error': 'write_error', 'timeout': 'timeout'}[mode]]


def test_verified_webhook_seam_preserves_response_and_does_not_observe_invalid_signature(monkeypatch):

    event = invoice()
    observed = AsyncMock()
    monkeypatch.setattr(payment, 'observe_verified_event', observed)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)
    dispatch = AsyncMock(return_value={'status': 'success', 'fixture': 'unchanged'})
    monkeypatch.setattr(payment, 'dispatch_with_ledger', dispatch)

    class Request:
        async def body(self):
            return b'fixture'

    assert asyncio.run(payment.stripe_webhook(Request(), 'signature')) == {'status': 'success', 'fixture': 'unchanged'}
    observed.assert_awaited_once_with(event)

    def invalid(*args):
        raise ValueError('invalid fixture signature')

    monkeypatch.setattr(payment.stripe_utils, 'parse_event', invalid)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        asyncio.run(payment.stripe_webhook(Request(), 'signature'))
    assert error.value.status_code == 400
    assert observed.await_count == 1


@pytest.mark.parametrize('kind', ['invoice', 'subscription'])
def test_all_truncated_and_unexpanded_price_shapes_abstain(kind):
    event = invoice()
    if kind == 'subscription':
        event['type'] = 'customer.subscription.updated'
        event['data']['previous_attributes'] = {'status': 'active'}
        event['data']['object']['id'] = 'sub_fixture'
        event['data']['object']['items'] = event['data']['object'].pop('lines')
    key = 'items' if kind == 'subscription' else 'lines'
    event['data']['object'][key]['has_more'] = True
    _, fields = observations.project_event(event, now=NOW)
    assert fields['plan'] == fields['interval'] == fields['scope'] == 'unknown'
    event['data']['object'][key]['has_more'] = False
    event['data']['object'][key]['data'].append({'price': 'price_unexpanded'})
    _, fields = observations.project_event(event, now=NOW)
    assert fields['plan'] == fields['interval'] == fields['scope'] == 'unknown'


def test_mixed_intervals_and_unconfigured_prices_abstain(monkeypatch):
    event = invoice()
    line = deepcopy(event['data']['object']['lines']['data'][0])
    line['price']['recurring']['interval'] = 'month'
    event['data']['object']['lines']['data'].append(line)
    _, fields = observations.project_event(event, now=NOW)
    assert fields['plan'] == fields['interval'] == fields['scope'] == 'unknown'
    from config import plan_catalog

    def unavailable(_):
        raise ValueError('fixture unmapped configuration')

    monkeypatch.setattr(plan_catalog, 'resolve_stripe_price_plan', unavailable)
    _, fields = observations.project_event(invoice(), now=NOW)
    assert fields['scope'] == 'unknown'


def test_creator_markers_are_checked_in_both_metadata_locations():
    event = invoice()
    event['data']['object'].update(
        subscription_details={'metadata': {'uid': 'private_fixture'}}, metadata={'app_id': 'creator_fixture'}
    )
    assert observations.project_event(event, now=NOW) is None
    event['data']['object'].update(
        subscription_details={'metadata': {'app_id': 'creator_fixture'}}, metadata={'uid': 'private_fixture'}
    )
    assert observations.project_event(event, now=NOW) is None


@pytest.mark.parametrize('livemode', [True, False, None])
def test_provider_test_mode_is_not_confused_with_production(livemode):
    event = invoice()
    event['livemode'] = livemode
    _, fields = observations.project_event(event, now=NOW)
    assert fields['provider_livemode'] is livemode


def test_production_response_container_defers_observation_until_after_response(monkeypatch):
    from fastapi import BackgroundTasks

    event = invoice()
    observed = AsyncMock()
    monkeypatch.setattr(payment, 'observe_verified_event', observed)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)
    monkeypatch.setattr(payment, 'dispatch_with_ledger', AsyncMock(return_value={'status': 'success'}))

    class Request:
        async def body(self):
            return b'fixture'

    tasks = BackgroundTasks()
    assert asyncio.run(payment.stripe_webhook(Request(), 'signature', tasks)) == {'status': 'success'}
    observed.assert_not_awaited()
    assert len(tasks.tasks) == 1
    asyncio.run(tasks())
    observed.assert_awaited_once_with(event)


def test_coverage_counter_accepts_only_closed_delivery_outcomes(monkeypatch):
    from utils import metrics

    counter = SimpleNamespace(labels=lambda **kw: seen.append(kw) or SimpleNamespace(inc=lambda: None))
    seen = []
    monkeypatch.setattr(metrics, 'OMI_BILLING_RENEWAL_OBSERVATIONS', counter)
    for outcome in ['eligible', 'created', 'duplicate', 'projection_error', 'write_error', 'timeout', 'private_other']:
        observations._record_outcome(outcome)
    assert [x['outcome'] for x in seen] == [
        'eligible',
        'created',
        'duplicate',
        'projection_error',
        'write_error',
        'timeout',
    ]


def test_observation_survives_failure_in_owning_handlers_background_work(monkeypatch):
    from fastapi import BackgroundTasks

    event = invoice()
    observed = AsyncMock()
    monkeypatch.setattr(payment, 'observe_verified_event', observed)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: event)
    tasks = BackgroundTasks()

    async def failing_policy():
        raise RuntimeError('fixture policy failure')

    async def dispatch(*args):
        tasks.add_task(failing_policy)
        return {'status': 'success'}

    monkeypatch.setattr(payment, 'dispatch_with_ledger', dispatch)

    class Request:
        async def body(self):
            return b'fixture'

    assert asyncio.run(payment.stripe_webhook(Request(), 'signature', tasks)) == {'status': 'success'}
    with pytest.raises(RuntimeError, match='fixture policy failure'):
        asyncio.run(tasks())
    observed.assert_awaited_once_with(event)


def test_creation_snapshot_preserves_provider_creation_without_inventing_renewal_ordinal():
    event = {
        'id': 'evt_created',
        'created': 1794358801,
        'livemode': True,
        'type': 'customer.subscription.created',
        'data': {
            'object': {
                'id': 'sub_fixture',
                'created': 1794350000,
                'latest_invoice': 'in_fixture',
                'status': 'active',
                'items': {'data': []},
            }
        },
    }
    _, fields = observations.project_event(event, now=NOW)
    assert fields['subscription_created'] == 1794350000
    assert fields['renewal_ordinal'] == 'unknown'
    assert fields['observation_kind'] == 'subscription_snapshot'

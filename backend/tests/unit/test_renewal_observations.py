"""Renewal observations stay off entitlement paths and retain provider facts."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import AlreadyExists

from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from utils.observability import renewal_observations as observations

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def invoice(kind='invoice.payment_failed', attempt=1, event_id='evt_fixture'):
    price = next(iter(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES))
    return {
        'id': event_id,
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


def test_subscription_created_snapshot_carries_the_joinable_creation_time():
    event = {
        'id': 'evt_subscription_created',
        'created': 1794358802,
        'type': 'customer.subscription.created',
        'data': {
            'object': {
                'id': 'sub_fixture',
                'created': 1794000000,
                'latest_invoice': 'in_fixture',
                'status': 'active',
                'cancel_at_period_end': False,
                'items': {'data': []},
            },
        },
    }
    _, fields = observations.project_event(event, now=NOW)
    assert fields['observation_kind'] == 'subscription_snapshot'
    assert fields['subscription_created'] == 1794000000
    assert fields['renewal_ordinal'] == 'unknown'
    assert fields['subscription_key'] == observations.project_event(invoice(), now=NOW)[1]['subscription_key']


def test_price_resolver_failure_keeps_coverage_unknown_instead_of_dropping_the_fact(monkeypatch):
    from config import plan_catalog

    def _boom(_price_id):
        raise RuntimeError('catalog fixture failure')

    monkeypatch.setattr(plan_catalog, 'resolve_stripe_price_plan', _boom)
    _, fields = observations.project_event(invoice(), now=NOW)
    assert fields['plan'] == 'unknown'
    assert fields['scope'] == 'unknown'
    assert fields['interval'] == 'year'


def test_disabled_observer_performs_no_projection_or_io(monkeypatch):
    monkeypatch.setenv('BILLING_RENEWAL_OBSERVATIONS_ENABLED', 'off')
    monkeypatch.setattr(observations, 'project_event', lambda _: pytest.fail('gate must precede projection'))
    asyncio.run(observations.observe_verified_event(invoice()))


@pytest.mark.parametrize('mode', ['success', 'error', 'timeout'])
def test_real_observer_executor_boundary_is_bounded_and_fail_open(monkeypatch, mode):
    monkeypatch.delenv('BILLING_RENEWAL_OBSERVATIONS_ENABLED', raising=False)
    calls = []
    fallback = []
    monkeypatch.setattr(observations, 'record_fallback', lambda **kw: fallback.append(kw))

    async def run(executor, fn, payload):
        calls.append((fn, payload))
        if mode == 'error':
            raise RuntimeError('private exception must not be logged')
        if mode == 'timeout':
            raise asyncio.TimeoutError()

    monkeypatch.setattr(observations, 'run_blocking', run)
    assert asyncio.run(observations.observe_verified_event(invoice())) is None
    assert len(calls) == 1
    assert len(fallback) == (mode != 'success')


def test_verified_webhook_seam_preserves_response_and_does_not_observe_invalid_signature(monkeypatch):
    from routers import payment

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

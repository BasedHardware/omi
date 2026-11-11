"""EXP-005 paid-start clocks, assignment, privacy and transactional suppression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config.plan_catalog import PlanType
from database import first_value_recovery as recovery
from services import first_value_recovery as dispatcher
from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
START_AT = NOW - timedelta(days=4)
START_ID = 'a' * 32


def _start(**changes):
    return {
        'experiment_id': recovery.EXPERIMENT_ID,
        'uid': 'fixture-user',
        'variant': 'treatment',
        'source': recovery.SOURCE,
        'paid_start_at': START_AT,
        'assigned_at': START_AT,
        'expires_at': START_AT + recovery.DEDUPE_WINDOW,
        'subscription_id': 'fixture-subscription',
        'price_id': 'fixture-monthly-price',
        'signal_coverage': 'complete',
        **changes,
    }


def _user(**changes):
    return {
        'time_zone': 'UTC',
        'notifications_enabled': True,
        'subscription': {
            'stripe_subscription_id': 'fixture-subscription',
            'current_price_id': 'fixture-monthly-price',
            'current_period_end': int((NOW + timedelta(days=20)).timestamp()),
            'cancel_at_period_end': False,
        },
        **changes,
    }


def _projection(**changes):
    created = int(START_AT.timestamp())
    subscription = {
        'id': 'fixture-subscription',
        'created': created,
        'status': 'active',
        'current_period_end': int((NOW + timedelta(days=20)).timestamp()),
        'items': {
            'data': [
                {'price': {'id': 'fixture-monthly-price', 'recurring': {'interval': 'month'}}},
            ]
        },
    }
    return {
        'uid': 'fixture-user',
        'stripe_event_id': 'fixture-event',
        'stripe_event_type': 'customer.subscription.created',
        'subscription_obj': subscription,
        'previous_paid_subscription_id': None,
        'resulting_paid_subscription_id': 'fixture-subscription',
        'previous_attributes': {},
        **changes,
    }


def test_off_enrollment_never_resolves_client_or_writes(monkeypatch):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: False)
    monkeypatch.setattr(recovery, '_client', Mock(side_effect=AssertionError('user I/O is forbidden while off')))
    emitted = []
    monkeypatch.setattr(recovery, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    assert recovery.enroll_verified_paid_start(**_projection()) is False
    assert recovery._client.call_count == 0
    assert emitted == []


@pytest.mark.parametrize('status', ['trialing', 'active'])
def test_enrollment_verifies_non_trial_and_stores_paid_start_assignment(monkeypatch, status):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    monkeypatch.setattr(recovery, 'intake_admitted', lambda *_args: True)
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    emitted = []
    monkeypatch.setattr(recovery, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))
    client = FakeFirestore()
    projection = _projection()
    projection['subscription_obj']['status'] = status

    enrolled = recovery.enroll_verified_paid_start(firestore_client=client, **projection)

    assert enrolled is (status == 'active')
    assert len(client.docs) == (1 if status == 'active' else 0)
    if status == 'active':
        start_id = recovery.paid_start_id('fixture-user', 'fixture-subscription', int(START_AT.timestamp()))
        row = client.docs[f'users/fixture-user/first_value_starts/{start_id}']
        assert row['assigned_at'] == START_AT
        assert row['next_push_probe_at'] == START_AT + recovery.RESULT_DELAY
        assert row['variant'] in {'control', 'treatment'}
        assert len(emitted) == 1
        assert emitted[0]['properties']['experiment_id'] == recovery.EXPERIMENT_ID
        assert 'fixture-user' not in str(emitted[0]['properties'])
        assert 'fixture-subscription' not in str(emitted[0]['properties'])


def test_duplicate_webhook_adopts_committed_assignment_and_recovers_enrollment_event(monkeypatch):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    monkeypatch.setattr(recovery, 'intake_admitted', lambda *_args: True)
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    emitted = []
    monkeypatch.setattr(recovery, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))
    client = FakeFirestore()

    assert recovery.enroll_verified_paid_start(firestore_client=client, **_projection()) is True
    assert recovery.enroll_verified_paid_start(firestore_client=client, **_projection()) is True

    assert len(client.docs) == 1
    assert len(emitted) == 2
    assert emitted[0]['properties']['$insert_id'] == emitted[1]['properties']['$insert_id']
    assert emitted[0]['properties']['variant'] == emitted[1]['properties']['variant']


def test_assignment_is_stable_and_split_before_eligibility(monkeypatch):
    # The stored record is created before any product query; no conversation or
    # eligibility model is needed by this entrypoint.
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    monkeypatch.setattr(recovery, 'intake_admitted', lambda *_args: True)
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    variants = []
    for index in range(30):
        projection = _projection(uid=f'aggregate-fixture-{index}', previous_paid_subscription_id=None)
        projection['subscription_obj'] = {
            **projection['subscription_obj'],
            'created': int(START_AT.timestamp()) + index,
        }
        client = FakeFirestore()
        monkeypatch.setattr(recovery, 'emit_product_event', lambda **_kwargs: None)
        recovery.enroll_verified_paid_start(firestore_client=client, **projection)
        variants.append(next(iter(client.docs.values()))['variant'])
    assert set(variants) == {'control', 'treatment'}


def test_capture_and_result_use_distinct_clocks():
    capture_start = _start()
    before_capture = START_AT + recovery.CAPTURE_DELAY - timedelta(microseconds=1)
    assert recovery.prompt_kind(capture_start, recovery.CAPTURE, now=before_capture) is False
    assert recovery.prompt_kind(capture_start, recovery.CAPTURE, now=START_AT + recovery.CAPTURE_DELAY) is True

    ready_at = START_AT + timedelta(hours=10)
    ready = _start(capture_saved_at=START_AT, ready_result_at=ready_at, ready_result_conversation_id='result-1')
    assert (
        recovery.prompt_kind(ready, recovery.RESULT, now=ready_at + recovery.RESULT_DELAY - timedelta(microseconds=1))
        is False
    )
    assert recovery.prompt_kind(ready, recovery.RESULT, now=ready_at + recovery.RESULT_DELAY) is True
    assert (
        recovery.prompt_kind(ready, recovery.RESULT, now=ready_at + recovery.RESULT_DELAY + timedelta(days=30)) is False
    )
    assert recovery.prompt_kind(_start(variant='control'), recovery.CAPTURE, now=NOW) is False
    assert recovery.prompt_kind(_start(signal_coverage='truncated'), recovery.CAPTURE, now=NOW) is False


def _strict(rows=None):
    seeded = {
        ('users', 'fixture-user'): _user(),
        ('users', 'fixture-user', 'first_value_starts', START_ID): _start(),
    }
    seeded.update(rows or {})
    return StrictFirestore(seeded)


def test_claim_is_durable_per_start_and_daily_cap_is_transactional():
    client = _strict()
    first = recovery.claim_prompt(
        'fixture-user', START_ID, _start(), recovery.CAPTURE, 'in_app', now=NOW, firestore_client=client
    )
    second = recovery.claim_prompt(
        'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=client
    )
    other = 'b' * 32
    client.rows[('users', 'fixture-user', 'first_value_starts', other)] = _start()
    third = recovery.claim_prompt(
        'fixture-user', other, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=client
    )

    assert first == {
        'kind': recovery.CAPTURE,
        'channel': 'in_app',
        'route': '/settings/device',
        'claimed_at': NOW,
    }
    assert second is None
    assert third is None  # one first-value prompt per local day across paid starts
    day = client.rows[('users', 'fixture-user', 'first_value_delivery_days', '2026-11-11')]
    assert day['prompt_count'] == 1


@pytest.mark.parametrize(
    'user_change,expected_reason',
    [
        ({'notifications_enabled': False}, 'opt_out'),
        ({'time_zone': 'not/a-zone'}, 'timezone'),
        ({'time_zone': 'UTC'}, None),
    ],
)
def test_missing_consent_timezone_and_quiet_hours_suppress(user_change, expected_reason):
    client = _strict({('users', 'fixture-user'): _user(**user_change)})
    claim = recovery.claim_prompt(
        'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=client
    )
    if expected_reason is None:
        assert claim is not None
    else:
        assert claim is None
    if expected_reason is not None:
        assert not any(path[-2:] == ('first_value_prompts', 'capture') for path in client.rows)


def test_quiet_hours_and_paid_end_cancellation_and_value_suppress():
    quiet = _strict()
    assert (
        recovery.claim_prompt(
            'fixture-user',
            START_ID,
            _start(),
            recovery.CAPTURE,
            'push',
            now=NOW.replace(hour=23),
            firestore_client=quiet,
        )
        is None
    )

    cancelled = _strict()
    cancelled.rows[('users', 'fixture-user')]['subscription']['cancel_at_period_end'] = True
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=cancelled
        )
        is None
    )

    ended = _strict()
    ended.rows[('users', 'fixture-user')]['subscription']['current_period_end'] = int(
        (NOW - timedelta(seconds=1)).timestamp()
    )
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=ended
        )
        is None
    )

    valued = _strict({f'users/fixture-user/first_value_starts/{START_ID}': _start(capture_saved_at=START_AT)})
    assert (
        recovery.claim_prompt(
            'fixture-user',
            START_ID,
            _start(capture_saved_at=START_AT),
            recovery.CAPTURE,
            'in_app',
            now=NOW,
            firestore_client=valued,
        )
        is None
    )


def test_result_claim_rechecks_result_availability_and_inactive_paid_state():
    ready_at = NOW - timedelta(days=2)
    ready_start = _start(ready_result_at=ready_at, ready_result_conversation_id='result-1')
    row = {'status': 'completed', 'summary_completed_at': ready_at, 'discarded': False, 'deleted': False}
    client = _strict(
        {
            ('users', 'fixture-user', 'conversations', 'result-1'): row,
        }
    )
    client.rows[('users', 'fixture-user', 'first_value_starts', START_ID)] = ready_start
    claim = recovery.claim_prompt(
        'fixture-user', START_ID, ready_start, recovery.RESULT, 'push', now=NOW, firestore_client=client
    )
    assert claim is not None and claim['route'] == '/conversation/result-1'

    inactive = _strict(
        {
            ('users', 'fixture-user', 'first_value_starts', START_ID): _start(),
            ('users', 'fixture-user', 'conversations', 'result-1'): row,
        }
    )
    inactive.rows[('users', 'fixture-user')]['subscription']['status'] = 'inactive'
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=inactive
        )
        is None
    )


def test_deleted_ready_result_cannot_be_claimed_or_navigated():
    ready_at = NOW - timedelta(days=2)
    ready_start = _start(ready_result_at=ready_at, ready_result_conversation_id='result-1')
    client = _strict({('users', 'fixture-user', 'first_value_starts', START_ID): ready_start})
    client.rows[('users', 'fixture-user', 'first_value_starts', START_ID, 'first_value_prompts', 'result')] = {
        'kind': 'result',
        'channel': 'push',
        'claimed_at': NOW - timedelta(hours=1),
    }
    client.rows[('users', 'fixture-user', 'conversations', 'result-1')] = {
        'status': 'completed',
        'summary_completed_at': ready_at,
        'deleted': True,
    }
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, ready_start, recovery.RESULT, 'push', now=NOW, firestore_client=client
        )
        is None
    )
    assert (
        recovery.resolve_push_navigation(
            'fixture-user', START_ID, ready_start, recovery.RESULT, now=NOW, firestore_client=client
        )
        is None
    )


def test_product_probe_requires_actual_ready_result_and_never_emits_identifiers(monkeypatch):
    client = FakeFirestore(
        {
            f'users/fixture-user/conversations/capture-only': {
                'created_at': START_AT + timedelta(hours=1),
                'status': 'processing',
                'discarded': False,
            }
        }
    )
    values = []
    monkeypatch.setattr(recovery, '_emit_value', lambda *args: values.append(args))
    result = recovery.probe_start(
        'fixture-user',
        START_ID,
        _start(signal_coverage='pending', capture_saved_at=None),
        now=NOW,
        firestore_client=client,
    )
    assert result['capture_saved_at'] == START_AT + timedelta(hours=1)
    assert recovery.prompt_kind(result, recovery.RESULT, now=NOW) is False


def test_result_open_records_value_and_stops_worker(monkeypatch):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    ready_at = START_AT + timedelta(hours=2)
    client = FakeFirestore(
        {
            'users/fixture-user/conversations/result-1': {'status': 'completed', 'summary_completed_at': ready_at},
            f'users/fixture-user/first_value_starts/{START_ID}': _start(variant='control'),
            'users/fixture-user/conversations/result-2': {'status': 'processing'},
        }
    )
    assert recovery.record_result_open('fixture-user', 'result-1', now=NOW, firestore_client=client) == 1
    updated = client.docs[f'users/fixture-user/first_value_starts/{START_ID}']
    assert updated['result_opened_at'] == NOW
    assert updated['next_push_probe_at'] is None


def test_dispatch_off_never_selects_or_dispatches(monkeypatch):
    monkeypatch.setattr(dispatcher, 'recovery_enabled', lambda: False)
    monkeypatch.setattr(dispatcher.recovery, 'due_push_starts', Mock(side_effect=AssertionError('query forbidden')))
    monkeypatch.setattr(dispatcher, 'dispatch_notification', Mock(side_effect=AssertionError('dispatch forbidden')))
    summary = dispatcher.run_first_value_recovery_dispatch(now=NOW)
    assert summary.considered == summary.claimed == summary.delivered == 0


def test_ready_push_contains_no_object_identifier(monkeypatch):
    monkeypatch.setattr(dispatcher, 'recovery_enabled', lambda: False)
    intent = dispatcher._intent('not-observed', recovery.RESULT)
    assert intent.data['navigate_to'] == '/conversations'
    assert 'conversation_id' not in intent.data
    assert 'target_id' not in intent.data
    assert 'user_id' not in intent.data
    assert dispatcher.RESULT_BODY == 'Open Omi to read your result.'

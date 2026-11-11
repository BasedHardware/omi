"""EXP-005 paid-start clocks, assignment, privacy and transactional suppression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config import first_value_recovery as recovery_config
from config.plan_catalog import PlanType
from database import first_value_recovery as recovery
from services import first_value_recovery as dispatcher
from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils.observability import billing_webhook
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
        'client_protocol': 1,
        'client_time_zone': 'UTC',
        'client_capability_at': NOW,
        'push_permission_granted_at': NOW,
        **changes,
    }


def _user(**changes):
    return {
        'time_zone': 'UTC',
        'notifications_enabled': True,
        'fcm_token': 'fixture-token',
        'subscription': {
            'stripe_subscription_id': 'fixture-subscription',
            'current_price_id': 'fixture-monthly-price',
            'current_period_end': int((NOW + timedelta(days=20)).timestamp()),
            'cancel_at_period_end': False,
            'plan': 'unlimited',
            'status': 'active',
        },
        **changes,
    }


def _projection(**changes):
    paid_at = int(START_AT.timestamp())
    subscription = {
        'id': 'fixture-subscription',
        'customer': 'fixture-customer',
        'created': paid_at - 300,
        'status': 'active',
        'current_period_end': int((NOW + timedelta(days=20)).timestamp()),
        'latest_invoice': 'fixture-invoice',
        'metadata': {'uid': 'fixture-user'},
        'items': {
            'has_more': False,
            'data': [
                {
                    'id': 'fixture-subscription-item',
                    'price': {
                        'id': 'fixture-monthly-price',
                        'recurring': {'interval': 'month', 'interval_count': 1},
                    },
                },
            ],
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
        'paid_invoice': {
            'id': 'fixture-invoice',
            'subscription': 'fixture-subscription',
            'customer': 'fixture-customer',
            'billing_reason': 'subscription_create',
            'status': 'paid',
            'amount_paid': 3000,
            'total': 3000,
            'paid_out_of_band': False,
            'lines': {
                'has_more': False,
                'data': [
                    {
                        'type': 'subscription',
                        'subscription': 'fixture-subscription',
                        'subscription_item': 'fixture-subscription-item',
                        'price': {'id': 'fixture-monthly-price'},
                        'amount': 3000,
                    }
                ],
            },
            'status_transitions': {'paid_at': paid_at},
        },
        **changes,
    }


def test_flag_and_intake_both_default_closed(monkeypatch):
    monkeypatch.delenv(recovery_config.ENABLED_ENV, raising=False)
    monkeypatch.delenv(recovery_config.COHORT_PERCENT_ENV, raising=False)
    assert recovery_config.cohort_percent() == 0
    assert recovery_config.recovery_enabled() is False
    monkeypatch.setenv(recovery_config.ENABLED_ENV, 'true')
    assert recovery_config.recovery_enabled() is False
    monkeypatch.setenv(recovery_config.COHORT_PERCENT_ENV, '100')
    assert recovery_config.recovery_enabled() is True
    monkeypatch.setenv(recovery_config.ENABLED_ENV, 'false')
    assert recovery_config.recovery_enabled() is False
    monkeypatch.setenv(recovery_config.ENABLED_ENV, 'true')
    monkeypatch.setenv(recovery_config.COHORT_PERCENT_ENV, 'invalid')
    assert recovery_config.recovery_enabled() is False


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
        assert row['assigned_at'].timestamp() == projection['paid_invoice']['status_transitions']['paid_at']
        assert row['assigned_at'].timestamp() != projection['subscription_obj']['created']
        assert row['next_push_probe_at'] == START_AT + recovery.RESULT_DELAY
        assert row['variant'] in {'control', 'treatment'}
        assert len(emitted) == 1
        assert emitted[0]['properties']['experiment_id'] == recovery.EXPERIMENT_ID
        assert 'fixture-user' not in str(emitted[0]['properties'])
        assert 'fixture-subscription' not in str(emitted[0]['properties'])


@pytest.mark.parametrize(
    'invoice_change',
    [
        {'amount_paid': 0},
        {'status': 'open'},
        {'billing_reason': 'subscription_cycle'},
        {'subscription': 'other-subscription'},
        {'customer': 'other-customer'},
        {'status_transitions': {'paid_at': None}},
    ],
)
def test_zero_unpaid_renewal_or_mismatched_invoice_never_admits(monkeypatch, invoice_change):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    projection = _projection()
    projection['paid_invoice'].update(invoice_change)
    assert recovery.verified_direct_monthly_start(projection) is None


@pytest.mark.parametrize(
    'line_change',
    [
        {'amount': 0},
        {'price': {'id': 'other-monthly-price'}},
        {'subscription': 'other-subscription'},
        {'subscription_item': 'other-subscription-item'},
        {'type': 'invoiceitem'},
    ],
)
def test_invoice_must_pay_for_the_same_single_monthly_subscription_item(monkeypatch, line_change):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    projection = _projection()
    projection['paid_invoice']['lines']['data'][0].update(line_change)
    assert recovery.verified_direct_monthly_start(projection) is None


def test_another_invoice_or_subscription_item_cannot_fund_a_free_recurring_line(monkeypatch):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    projection = _projection()
    projection['paid_invoice']['lines']['data'][0]['amount'] = 0
    projection['paid_invoice']['lines']['data'].append(
        {'type': 'invoiceitem', 'price': {'id': 'other-price'}, 'amount': 3000}
    )
    assert recovery.verified_direct_monthly_start(projection) is None

    projection = _projection()
    items = projection['subscription_obj']['items']['data']
    items.append({'id': 'other-item', 'price': {'id': 'other-price'}})
    assert recovery.verified_direct_monthly_start(projection) is None


def test_trial_conversion_reactivation_replacement_and_creator_app_never_admit(monkeypatch):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    excluded = [
        _projection(subscription_obj={**_projection()['subscription_obj'], 'trial_start': 1, 'trial_end': 2}),
        _projection(previous_paid_subscription_id='previous-paid-subscription'),
        _projection(stripe_event_type='customer.subscription.updated', previous_attributes={'status': 'canceled'}),
        _projection(
            subscription_obj={
                **_projection()['subscription_obj'],
                'metadata': {'uid': 'fixture-user', 'app_id': 'creator-app'},
            }
        ),
        _projection(),
    ]
    excluded[-1]['subscription_obj']['latest_invoice'] = None
    assert all(recovery.verified_direct_monthly_start(projection) is None for projection in excluded)


@pytest.mark.asyncio
async def test_off_billing_projection_has_zero_stripe_or_background_first_value_io(monkeypatch):
    monkeypatch.setattr(billing_webhook, 'recovery_enabled', lambda: False)
    retrieve = Mock(side_effect=AssertionError('Stripe is forbidden while off'))
    http = Mock()
    factory = Mock(return_value=Mock(invoices=Mock(retrieve=retrieve)))
    monkeypatch.setattr(billing_webhook.stripe, 'api_key', 'synthetic-key')
    monkeypatch.setattr(billing_webhook.stripe, 'RequestsClient', Mock(return_value=http))
    monkeypatch.setattr(billing_webhook.stripe, 'StripeClient', factory)
    background = Mock()
    projection = _projection()
    projection.pop('paid_invoice')

    await billing_webhook.schedule_billing_webhook_events(background, **projection)

    retrieve.assert_not_called()
    assert 'paid_invoice' not in background.add_task.call_args.kwargs


@pytest.mark.asyncio
async def test_candidate_ack_schedules_before_bounded_post_response_invoice_retrieval(monkeypatch):
    monkeypatch.setattr(billing_webhook, 'recovery_enabled', lambda: True)
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _price: PlanType.unlimited)
    retrieved = Mock()
    retrieved.to_dict.return_value = _projection()['paid_invoice']
    retrieve = Mock(return_value=retrieved)
    http = Mock()
    factory = Mock(return_value=Mock(invoices=Mock(retrieve=retrieve)))
    monkeypatch.setattr(billing_webhook.stripe, 'api_key', 'synthetic-key')
    monkeypatch.setattr(billing_webhook.stripe, 'RequestsClient', Mock(return_value=http))
    monkeypatch.setattr(billing_webhook.stripe, 'StripeClient', factory)
    monkeypatch.setattr(billing_webhook.lifecycle, 'emit_billing_product_event', Mock())
    monkeypatch.setattr(billing_webhook.lifecycle, 'emit_billing_plan_changed', Mock())
    enrolled = Mock()
    monkeypatch.setattr(billing_webhook, 'enroll_verified_paid_start', enrolled)
    background = Mock()
    projection = _projection()
    projection.pop('paid_invoice')

    await billing_webhook.schedule_billing_webhook_events(background, **projection)

    # No provider await/call delays acknowledgement; the exact projection is
    # handed to FastAPI first and only its post-response callback retrieves.
    retrieve.assert_not_called()
    task = background.add_task.call_args.args[0]
    assert task is billing_webhook.emit_billing_webhook_events
    task(*background.add_task.call_args.args[1:], **background.add_task.call_args.kwargs)
    retrieve.assert_called_once_with('fixture-invoice')
    billing_webhook.stripe.RequestsClient.assert_called_once_with(timeout=5)
    assert factory.call_args.kwargs['http_client'] is http
    assert factory.call_args.kwargs['max_network_retries'] == 0
    assert enrolled.call_args.kwargs['paid_invoice']['amount_paid'] == 3000


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
            'metadata': {'uid': f'aggregate-fixture-{index}'},
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


@pytest.fixture(autouse=True)
def strict_product_probe(monkeypatch):
    # The product query is OUTSIDE the claim transaction. Evaluate its real
    # filters on a snapshot fake; keep strict document transaction ordering.
    # This does not model retries, phantom locks or Firestore contention.
    original = recovery._probe_conversations

    def probe(uid, paid_start_at, client):
        if isinstance(client, StrictFirestore):
            client = FakeFirestore({'/'.join(path): row for path, row in client.rows.items()})
        return original(uid, paid_start_at, client)

    monkeypatch.setattr(recovery, '_probe_conversations', probe)
    monkeypatch.setattr(recovery, '_emit_value', Mock())


@pytest.mark.parametrize('channel', ['in_app', 'push'])
def test_capture_saved_after_initial_probe_is_rechecked_and_durably_suppresses(channel):
    stale = _start()  # Earlier product probe observed absence.
    client = _strict(
        {
            ('users', 'fixture-user', 'conversations', 'new-capture'): {
                'created_at': NOW - timedelta(minutes=1),
                'status': 'processing',
            }
        }
    )
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, stale, recovery.CAPTURE, channel, now=NOW, firestore_client=client
        )
        is None
    )
    start_path = ('users', 'fixture-user', 'first_value_starts', START_ID)
    assert client.rows[start_path]['capture_saved_at'] == NOW - timedelta(minutes=1)
    assert not any('first_value_prompts' in path or 'first_value_delivery_days' in path for path in client.rows)
    recovery._emit_value.assert_called_once()

    # Even if the product row disappears and a stale caller tries again, the
    # observed positive fact survives on the transaction's start document.
    del client.rows[('users', 'fixture-user', 'conversations', 'new-capture')]
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, stale, recovery.CAPTURE, channel, now=NOW, firestore_client=client
        )
        is None
    )
    recovery._emit_value.assert_called_once()


def test_truncated_claim_recheck_cannot_use_earlier_complete_absence():
    rows = {
        ('users', 'fixture-user', 'conversations', f'hidden-{index}'): {
            'created_at': START_AT,
            'status': 'hidden',
        }
        for index in range(recovery.MAX_PRODUCT_ROWS)
    }
    client = _strict(rows)
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'in_app', now=NOW, firestore_client=client
        )
        is None
    )
    assert not any('first_value_prompts' in path for path in client.rows)


def test_claim_recheck_failure_never_creates_claim_or_daily_charge(monkeypatch):
    client = _strict()
    monkeypatch.setattr(recovery, '_probe_conversations', Mock(side_effect=RuntimeError('synthetic probe failure')))
    with pytest.raises(RuntimeError, match='synthetic probe failure'):
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'in_app', now=NOW, firestore_client=client
        )
    assert client.transactions == []
    assert not any('first_value_prompts' in path for path in client.rows)


def test_observed_capture_between_recheck_and_transaction_fences_stale_absence(monkeypatch):
    client = _strict()

    def recheck_then_record(*_args):
        client.rows[('users', 'fixture-user', 'first_value_starts', START_ID)]['capture_saved_at'] = NOW
        return [], False

    monkeypatch.setattr(recovery, '_probe_conversations', recheck_then_record)
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, 'push', now=NOW, firestore_client=client
        )
        is None
    )
    assert not any('first_value_prompts' in path for path in client.rows)


@pytest.mark.parametrize('channel', ['in_app', 'push'])
def test_unobserved_save_after_recheck_can_still_race_claim(monkeypatch, channel):
    # Honest boundary test: a conversation insertion does not modify the start
    # read set. The residual interval is NOT an atomic absence guarantee.
    client = _strict()
    start_path = ('users', 'fixture-user', 'first_value_starts', START_ID)
    earlier_start = dict(client.rows[start_path])

    def recheck_then_save(*_args):
        client.rows[('users', 'fixture-user', 'conversations', 'racing-capture')] = {
            'created_at': NOW,
            'status': 'processing',
        }
        return [], False  # The recheck's snapshot preceded the save.

    monkeypatch.setattr(recovery, '_probe_conversations', recheck_then_save)
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, _start(), recovery.CAPTURE, channel, now=NOW, firestore_client=client
        )
        is not None
    )
    assert client.rows[start_path] == earlier_start


def test_stale_empty_probe_cannot_erase_new_durable_capture(monkeypatch):
    path = f'users/fixture-user/first_value_starts/{START_ID}'
    client = FakeFirestore({path: _start()})

    def stale_snapshot_after_positive_write(*_args):
        client.docs[path]['capture_saved_at'] = NOW
        return [], False

    monkeypatch.setattr(recovery, '_probe_conversations', stale_snapshot_after_positive_write)
    recovery.probe_start('fixture-user', START_ID, _start(capture_saved_at=None), now=NOW, firestore_client=client)
    assert client.docs[path]['capture_saved_at'] == NOW


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
    start = _start(client_time_zone=None) if expected_reason == 'timezone' else _start()
    client.rows[('users', 'fixture-user', 'first_value_starts', START_ID)] = start
    claim = recovery.claim_prompt(
        'fixture-user', START_ID, start, recovery.CAPTURE, 'push', now=NOW, firestore_client=client
    )
    if expected_reason is None:
        assert claim is not None
    else:
        assert claim is None
    if expected_reason is not None:
        assert not any(path[-2:] == ('first_value_prompts', 'capture') for path in client.rows)


def test_old_denied_or_stale_client_cannot_claim_despite_legacy_token():
    for start in (
        _start(client_protocol=None),
        _start(push_permission_granted_at=None),
        _start(client_capability_at=NOW - recovery.CLIENT_CAPABILITY_MAX_AGE - timedelta(seconds=1)),
        _start(client_time_zone=None),
    ):
        client = _strict({('users', 'fixture-user', 'first_value_starts', START_ID): start})
        claim = recovery.claim_prompt(
            'fixture-user', START_ID, start, recovery.CAPTURE, 'push', now=NOW, firestore_client=client
        )
        assert claim is None


def test_client_capability_requires_real_permission_and_valid_iana_zone():
    client = FakeFirestore()
    denied = recovery.record_client_capability(
        'fixture-user',
        START_ID,
        _start(),
        notifications_authorized=False,
        time_zone='America/Los_Angeles',
        now=NOW,
        firestore_client=client,
    )
    assert denied['push_permission_granted_at'] is None
    assert denied['client_time_zone'] == 'America/Los_Angeles'
    unknown = recovery.record_client_capability(
        'fixture-user',
        START_ID,
        _start(),
        notifications_authorized=True,
        time_zone='not/a-zone',
        now=NOW,
        firestore_client=client,
    )
    assert unknown['client_time_zone'] is None
    assert unknown['push_permission_granted_at'] is None
    assert recovery._client_capability_current(unknown, NOW) is False
    stale_client = _strict({('users', 'fixture-user', 'first_value_starts', START_ID): unknown})
    assert (
        recovery.claim_prompt(
            'fixture-user', START_ID, unknown, recovery.CAPTURE, 'in_app', now=NOW, firestore_client=stale_client
        )
        is None
    )


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


@pytest.mark.parametrize(
    'row_change',
    [{'status': 'failed'}, {'visibility': 'hidden'}, {'discarded': True}, {'is_locked': True}],
)
def test_failed_hidden_or_locked_conversation_is_never_saved_value(monkeypatch, row_change):
    created_at = START_AT + timedelta(hours=1)
    row = {'created_at': created_at, 'status': 'processing', **row_change}
    client = FakeFirestore(
        {
            'users/fixture-user/conversations/result-1': row,
            f'users/fixture-user/first_value_starts/{START_ID}': _start(),
        }
    )
    emitted = []
    monkeypatch.setattr(recovery, '_emit_value', lambda *args: emitted.append(args))

    result = recovery.probe_start(
        'fixture-user', START_ID, _start(signal_coverage='pending'), now=NOW, firestore_client=client
    )

    assert 'capture_saved_at' not in result
    assert emitted == []
    ready_row = {
        **row,
        'status': 'failed' if row_change.get('status') == 'failed' else 'completed',
        'summary_completed_at': created_at,
    }
    client.docs['users/fixture-user/conversations/result-1'] = ready_row
    assert recovery.record_result_open('fixture-user', 'result-1', now=NOW, firestore_client=client) == 0


@pytest.mark.parametrize('ready_offset', [timedelta(hours=2), -timedelta(days=1)])
def test_control_result_open_records_any_owned_ready_result(monkeypatch, ready_offset):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: True)
    ready_at = START_AT + ready_offset
    client = FakeFirestore(
        {
            'users/fixture-user/conversations/result-1': {'status': 'completed', 'summary_completed_at': ready_at},
            f'users/fixture-user/first_value_starts/{START_ID}': _start(
                variant='control', ready_result_conversation_id='result-2'
            ),
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


@pytest.mark.parametrize(
    'change',
    [
        {'paid_out_of_band': True},
        {'paid_out_of_band': None},
        {'total': 0},
        {'lines': {'has_more': True, 'data': []}},
    ],
)
def test_ambiguous_invoice_funding_or_pagination_never_admits(monkeypatch, change):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _: PlanType.unlimited)
    projection = _projection()
    projection['paid_invoice'].update(change)
    assert recovery.verified_direct_monthly_start(projection) is None


@pytest.mark.parametrize('credit_field', ['discount_amounts', 'pretax_credit_amounts'])
def test_fully_credited_monthly_line_cannot_be_funded_by_fees(monkeypatch, credit_field):
    monkeypatch.setattr(recovery, 'resolve_stripe_price_plan', lambda _: PlanType.unlimited)
    projection = _projection()
    projection['paid_invoice']['lines']['data'][0][credit_field] = [{'amount': 3000}]
    assert recovery.verified_direct_monthly_start(projection) is None


def test_kill_stops_result_outcome_io(monkeypatch):
    monkeypatch.setattr(recovery, 'recovery_enabled', lambda: False)
    monkeypatch.setattr(recovery, '_client', Mock(side_effect=AssertionError('off outcome IO')))
    assert recovery.record_result_open('fixture-user', 'result-1', now=NOW) == 0


@pytest.mark.parametrize(
    'status,plan', [('canceled', 'unlimited'), ('past_due', 'unlimited'), ('active', 'basic'), ('active', None)]
)
def test_current_access_uncertainty_or_cancellation_suppresses(status, plan):
    user = _user()
    user['subscription'].update(status=status, plan=plan)
    assert recovery._current_suppression(user, _start(), now=NOW) is not None


@pytest.mark.parametrize(
    'row',
    [
        {'dream_duplicate_of': 'synthetic-parent'},
        {'sync_bridge_pending': {'expires_at': 9999999999}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}},
    ],
)
def test_canonical_hidden_metadata_is_not_saved(row):
    assert not recovery._visible_saved_conversation({'status': 'completed', **row})


def test_invalid_current_capability_revokes_previous_permission():
    client = FakeFirestore()
    updated = recovery.record_client_capability(
        'fixture-user',
        START_ID,
        _start(),
        notifications_authorized=False,
        time_zone='not/a/zone',
        now=NOW,
        firestore_client=client,
    )
    assert not recovery._client_capability_current(updated, NOW)

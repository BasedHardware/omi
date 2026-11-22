"""Watch rollout cannot change admission; strict reads never synthesize zero."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.stt import allowance_watch as watch


@pytest.fixture
def policy(monkeypatch):
    users = SimpleNamespace(get_user_valid_subscription=Mock(return_value=SimpleNamespace(plan='basic')))
    policy = SimpleNamespace(
        is_marketplace_reviewer=lambda uid: False,
        RELEASE_PROBE_UID='probe',
        is_paid_plan=lambda plan: plan in {'plus', 'unlimited_v2', 'operator', 'architect'},
        transcription_allowance_seconds=lambda plan: 18000,
    )
    monkeypatch.setattr(watch, '_policy', lambda: (users, policy))
    monkeypatch.setattr(watch, '_monthly_seconds', Mock(return_value=17999))
    return users, policy


@pytest.mark.parametrize('plan', ['plus', 'unlimited_v2', 'operator', 'architect'])
def test_paying_and_trial_plans_never_refused(policy, plan):
    users, _ = policy
    users.get_user_valid_subscription.return_value.plan = plan
    assert watch.snapshot('u') == watch.Snapshot('paid_or_trial')
    watch._monthly_seconds.assert_not_called()
    users.get_user_valid_subscription.assert_called_once_with('u', provision=False)


def test_provider_funding_is_authoritative_even_during_usage_failure(policy):
    users, _ = policy
    assert watch.snapshot('u', customer_funded=True) == watch.Snapshot('customer_funded')
    users.get_user_valid_subscription.assert_not_called()
    assert watch.snapshot('u') == watch.Snapshot('free', 1)


@pytest.mark.parametrize('used,remaining', [(0, 18000), (17999, 1), (18000, 0), (20000, 0)])
def test_free_reads_billing_seconds_without_launch_configuration(policy, monkeypatch, used, remaining):
    monkeypatch.delenv('SUBSCRIPTION_LAUNCH_DATE', raising=False)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', '')
    monkeypatch.setattr(watch, '_monthly_seconds', lambda uid, now: used)
    assert watch.snapshot('u') == watch.Snapshot('free', remaining)


def test_unreadable_usage_is_not_an_allow(policy):
    watch._monthly_seconds.side_effect = TimeoutError
    assert watch.snapshot('u') == watch.Snapshot('usage_unavailable')


def test_missing_identity_or_subscription_is_explicit(policy):
    users, _ = policy
    assert watch.snapshot(None).decision == 'identity_unavailable'
    users.get_user_valid_subscription.return_value = None
    assert watch.snapshot('u').decision == 'subscription_unavailable'


def test_unknown_plan_does_not_get_paid_exemption(policy):
    users, _ = policy
    users.get_user_valid_subscription.return_value.plan = 'surprise'
    assert watch.snapshot('u').decision == 'subscription_unavailable'
    watch._monthly_seconds.assert_not_called()


def test_no_flag_or_cohort_on_snapshot(policy, monkeypatch):
    monkeypatch.setenv('STT_FREE_ALLOWANCE_WATCH_ENABLED', 'false')
    assert watch.snapshot('u') == watch.Snapshot('free', 1)


@pytest.mark.parametrize('seconds,decision', [(0, 'would_allow'), (1, 'would_allow'), (2, 'would_refuse')])
def test_watch_uses_full_requested_duration_and_never_returns_permission(policy, monkeypatch, seconds, decision):
    decisions, measured = Mock(), Mock()
    monkeypatch.setattr(watch, 'DECISIONS', decisions)
    monkeypatch.setattr(watch, 'SECONDS', measured)
    assert watch.observe('u', 'batch_gpu', 'parakeet', seconds) is None
    decisions.labels.assert_called_once_with('batch_gpu', 'parakeet', decision)
    measured.labels.return_value.inc.assert_called_once_with(seconds)


def test_untrusted_metric_input_cannot_create_labels_or_fail_serving(policy, monkeypatch):
    decisions = Mock()
    monkeypatch.setattr(watch, 'DECISIONS', decisions)
    assert watch.observe('u', 'untrusted/account-id', 'provider') is None
    assert watch.observe('u', 'live_open', 'provider', float('nan')) is None
    decisions.labels.assert_not_called()


def test_observer_failure_never_refuses_audio(policy, monkeypatch):
    monkeypatch.setattr(watch, 'snapshot', Mock(side_effect=RuntimeError('synthetic')))
    assert watch.observe('u', 'live_open', 'soniox') is None


def test_observation_kill_switch_avoids_io(policy, monkeypatch):
    users, _ = policy
    monkeypatch.setenv('STT_FREE_ALLOWANCE_WATCH_ENABLED', 'false')
    assert watch.observe('u', 'live_open', 'soniox') is None
    users.get_user_valid_subscription.assert_not_called()


@pytest.fixture
def monthly_store():
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    return StrictFirestore(
        {
            ('users', 'u'): {},
            ('users', 'u', 'monthly_usage_totals', '2026-11'): {
                'schema_version': 1,
                'epoch': 'v1',
                'ready': True,
                'totals': {'transcription_seconds': 18001},
                'days': {'12': {'transcription_seconds': 18001}},
            },
        }
    )


def test_direct_reader_uses_verified_current_utc_billing_month(monthly_store):
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert watch._monthly_seconds('u', now, firestore_client=monthly_store) == 18001
    with pytest.raises(ValueError, match='unverified'):
        watch._monthly_seconds('u', now.replace(month=12), firestore_client=monthly_store)


@pytest.mark.parametrize(
    'mutation',
    [
        {'ready': False},
        {'epoch': 'old'},
        {'schema_version': 0},
        {'totals': {}},
        {'totals': {'transcription_seconds': True}},
        {'totals': {'transcription_seconds': float('nan')}},
        {'totals': {'transcription_seconds': float('inf')}},
        {'totals': {'transcription_seconds': -1}},
        {'totals': {'transcription_seconds': '18000'}},
        {'days': {'31': {}}},
    ],
)
def test_direct_reader_rejects_incomplete_and_malformed_ledgers(monthly_store, mutation):
    monthly_store.rows['users', 'u', 'monthly_usage_totals', '2026-11'].update(mutation)
    with pytest.raises((ValueError, KeyError)):
        watch._monthly_seconds('u', datetime(2026, 11, 12, tzinfo=timezone.utc), firestore_client=monthly_store)


def test_direct_reader_does_not_rebuild_or_synthesize_zero(monthly_store, monkeypatch):
    monkeypatch.setenv('FSR_USAGE_MONTH_TOTAL_EPOCH', '')
    before = monthly_store.rows.copy()
    with pytest.raises(ValueError, match='unverified'):
        watch._monthly_seconds('u', datetime(2026, 11, 12, tzinfo=timezone.utc), firestore_client=monthly_store)
    assert monthly_store.rows == before
    assert all(not tx.has_written for tx in monthly_store.transactions)


@pytest.mark.asyncio
async def test_async_observer_has_a_bounded_wait_without_reclassifying_timeout(monkeypatch):
    import asyncio
    from utils import executors

    cancelled = []
    budgets = []

    async def unavailable(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    decisions = Mock()

    async def expire(awaitable, *, timeout):
        budgets.append(timeout)
        task = asyncio.create_task(awaitable)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        raise asyncio.TimeoutError

    monkeypatch.setattr(executors, 'run_blocking', unavailable)
    monkeypatch.setattr(asyncio, 'wait_for', expire)
    monkeypatch.setattr(watch, 'DECISIONS', decisions)
    assert await watch.observe_async('u', 'batch_gpu', 'parakeet', 60) is None
    assert budgets == [2.5]
    assert cancelled == [True]
    decisions.labels.assert_not_called()


@pytest.mark.asyncio
async def test_request_cancellation_is_not_swallowed_by_observer(monkeypatch):
    import asyncio
    from utils import executors

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(executors, 'run_blocking', cancelled)
    with pytest.raises(asyncio.CancelledError):
        await watch.observe_async('u', 'live_open', 'parakeet')


@pytest.mark.asyncio
async def test_live_watch_covers_fallback_with_legacy_dispatch_disabled(policy, monkeypatch):
    from unittest.mock import AsyncMock
    from utils import executors, stt_cap_dispatch as dispatch
    from utils import byok

    async def inline(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(executors, 'run_blocking', inline)
    monkeypatch.setattr(byok, 'get_byok_uid', lambda: 'u')
    monkeypatch.setattr(dispatch, 'get_byok_key', lambda provider: 'customer-key')
    monkeypatch.delenv('DEEPGRAM_SELF_HOSTED_ENABLED', raising=False)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    decisions = Mock()
    monkeypatch.setattr(watch, 'DECISIONS', decisions)
    monkeypatch.setattr(watch, '_monthly_seconds', lambda uid, now: 18000)
    first, fallback = AsyncMock(return_value=object()), AsyncMock(return_value=object())
    await dispatch.live_provider('deepgram', 0)(first)(16000)
    await dispatch.live_provider('parakeet', 0)(fallback)(16000)
    assert decisions.labels.call_args_list == [
        (('live_open', 'deepgram', 'customer_funded'),),
        (('live_open', 'parakeet', 'would_refuse'),),
    ]
    first.assert_awaited_once()
    fallback.assert_awaited_once()


@pytest.fixture
def batch_admission_case(monkeypatch):
    from tests.unit.test_batch_pipeline_admission import setup, tokens
    from utils.batch_pipeline import admission

    return setup(monkeypatch), tokens, admission


@pytest.mark.asyncio
async def test_gpu_observations_cannot_starve_another_authorization(monkeypatch, batch_admission_case):
    from copy import deepcopy

    (store, _, lease, _), tokens, admission = batch_admission_case
    store.rows['jobs', 'second'] = deepcopy(store.rows['jobs', 'segment'])
    requests = tokens(lease) + [{'segment_id': 'second', 'token': lease.token}]
    monkeypatch.setattr(admission, 'cap_dispatch_enabled', lambda *args: False)
    clock = [0.0]
    monkeypatch.setattr(admission, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1.0))
    observations = []

    async def observe(self, *args, **kwargs):
        assert all(
            store.rows['jobs', name].get('compute_admission_token') == lease.token for name in ('segment', 'second')
        )
        observations.append((args, kwargs))
        clock[0] += 5  # Even spending the entire remaining budget cannot undo either decision.

    from utils.stt.allowance_session import Operation

    monkeypatch.setattr(Operation, 'reserve_async', observe)
    receipt = await admission.authorize(store, requests, now=1)
    assert receipt == {'allowed': ['segment', 'second'], 'retry_after': {}, 'held_reason': {}}
    assert len(observations) == 1
    assert observations[0][1]['timeout'] == 0.1


def test_missing_free_balance_is_unavailable_instead_of_an_allow(monkeypatch):
    decisions = Mock()
    monkeypatch.setattr(watch, 'snapshot', lambda *args, **kwargs: watch.Snapshot('free'))
    monkeypatch.setattr(watch, 'DECISIONS', decisions)
    assert watch.observe('u', 'live_open', 'parakeet') is None
    decisions.labels.assert_called_once_with('live_open', 'parakeet', 'usage_unavailable')

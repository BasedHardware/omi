"""Operation ownership, actual billing units, and watch-only failure isolation."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import free_allowance_leases as ledger
from database.legal_holds import DestructiveOperationInProgress
from utils import analytics
from utils.stt import allowance_watch as watch
from utils.stt.allowance_session import Operation, current, operation


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setattr(watch, 'entitlement', Mock(return_value=('free', 100)))
    monkeypatch.setattr(watch, 'emit', Mock())
    monkeypatch.setattr(
        ledger,
        'reserve',
        Mock(return_value=ledger.Decision('reserved', 94, ledger.Lease('u', '2026-11', 'k' * 64, 6, 0))),
    )
    monkeypatch.setattr(ledger, 'settle_billed', Mock(return_value=True))


def test_retry_and_fallback_reuse_the_same_server_operation(policy):
    scope = Operation('u', 'one_shot', operation='one', seconds=6)
    scope.reserve('modulate')
    scope.reserve('soniox')
    assert ledger.reserve.call_count == 2
    assert {call.args[1] for call in ledger.reserve.call_args_list} == {'one'}
    assert scope.reference is not None


def test_customer_key_exempts_only_that_provider_not_managed_fallback(policy):
    scope = Operation('u', 'ptt', operation='one', live=True)
    watch.entitlement.side_effect = [('customer_funded', None), ('free', 100)]
    scope.reserve('deepgram', customer_funded=True)
    ledger.reserve.assert_not_called()
    scope.reserve('parakeet')
    ledger.reserve.assert_called_once()
    assert not scope.customer_funded


def test_paying_or_trial_plan_never_reads_or_writes_ledger(policy):
    watch.entitlement.return_value = ('paid_or_trial', None)
    scope = Operation('u', 'one_shot', seconds=6)
    scope.reserve('modulate')
    scope.billed(6)
    ledger.reserve.assert_not_called()
    ledger.settle_billed.assert_not_called()


def test_unknown_duration_is_evidence_of_missing_coverage_not_zero_cost(policy):
    scope = Operation('u', 'prerecorded')
    scope.reserve('modulate')
    ledger.reserve.assert_not_called()
    watch.emit.assert_called_with('prerecorded', 'modulate', 'duration_unavailable', 0)


def test_ledger_failure_never_becomes_serving_permission_or_raises(policy):
    ledger.reserve.side_effect = TimeoutError
    scope = Operation('u', 'one_shot', seconds=6)
    assert scope.reserve('modulate') is None
    watch.emit.assert_called_with('one_shot', 'modulate', 'usage_unavailable', 0)


def test_confirmed_billing_settles_actual_units_and_finishes_offline_operation(policy):
    scope = Operation('u', 'one_shot', seconds=6)
    scope.reserve('modulate')
    reference = scope.reference
    scope.billed(3)
    ledger.settle_billed.assert_called_once_with(
        [reference], 3, daily_ptt=False, source='one_shot', decision='would_allow'
    )
    assert scope.reference is None
    ledger.reserve.assert_called_once()


@pytest.mark.parametrize('reason', ['already_settled', 'lease_expired', 'operation_too_old', 'ledger_full'])
def test_administrative_outcomes_are_not_allowance_refusals(policy, reason):
    ledger.reserve.return_value = ledger.Decision(reason, 4)
    scope = Operation('u', 'sync', operation='sync:retry', seconds=6)
    scope.reserve('modulate')
    watch.emit.assert_called_once_with('sync', 'modulate', reason, 0 if reason == 'already_settled' else 6)
    assert not scope.refused
    scope.billed(6)
    assert ledger.settle_billed.call_args.kwargs['decision'] == 'unobserved'


def test_only_exhaustion_marks_an_operation_refused_and_survives_later_diagnostics(policy):
    ledger.reserve.side_effect = [ledger.Decision('allowance_exhausted', 0), ledger.Decision('lease_expired', 0)]
    scope = Operation('u', 'sync', seconds=6)
    scope.reserve('modulate')
    scope.reserve('modulate')
    assert scope.refused
    scope.billed(6)
    assert ledger.settle_billed.call_args.kwargs['decision'] == 'would_refuse'
    assert not scope.refused and not scope.observed


def test_unavailable_usage_is_not_stamped_as_a_measured_overage(policy):
    ledger.reserve.side_effect = TimeoutError
    scope = Operation('u', 'one_shot', seconds=6)
    scope.reserve('modulate')
    scope.billed(6)
    assert ledger.settle_billed.call_args.kwargs['decision'] == 'unobserved'


def test_final_live_flush_cannot_reserve_an_unused_window(policy):
    scope = Operation('u', 'live_open', live=True)
    scope.reserve('soniox')
    scope.closed = True
    scope.billed(3)
    ledger.reserve.assert_called_once()
    assert scope.reference is None


def test_billing_clock_caller_owns_the_next_window_after_advancing_its_boundary(policy):
    scope = Operation('u', 'live_open', live=True)
    scope.reserve('soniox')
    previous = scope.operation
    scope.billed(3)
    ledger.reserve.assert_called_once()
    scope.reserve('soniox')
    assert ledger.reserve.call_count == 2
    assert scope.operation != previous
    assert scope.reference is not None


def test_failed_billing_is_not_settled_or_retried(policy, monkeypatch):
    writer = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(analytics.user_usage_db, 'update_hourly_usage', writer)
    scope = SimpleNamespace(uid='u', billed=Mock())
    with pytest.raises(TimeoutError):
        analytics.record_usage('u', transcription_seconds=3, allowance_operation=scope)
    scope.billed.assert_not_called()
    writer.assert_called_once()


def test_erasure_refusal_never_releases_a_hold(policy, monkeypatch):
    monkeypatch.setattr(
        analytics.user_usage_db, 'update_hourly_usage', Mock(side_effect=DestructiveOperationInProgress('synthetic'))
    )
    scope = SimpleNamespace(uid='u', billed=Mock())
    analytics.record_usage('u', transcription_seconds=3, allowance_operation=scope)
    scope.billed.assert_not_called()


def test_telemetry_failure_after_billing_cannot_retry_or_undo_billing(policy, monkeypatch):
    writer = Mock()
    monkeypatch.setattr(analytics.user_usage_db, 'update_hourly_usage', writer)
    scope = SimpleNamespace(uid='u', billed=Mock(side_effect=RuntimeError))
    analytics.record_usage('u', transcription_seconds=3, allowance_operation=scope)
    writer.assert_called_once()
    scope.billed.assert_called_once_with(3)


def test_another_accounts_billing_cannot_release_a_hold(policy, monkeypatch):
    monkeypatch.setattr(analytics.user_usage_db, 'update_hourly_usage', Mock())
    scope = SimpleNamespace(uid='other', billed=Mock())
    analytics.record_usage('u', transcription_seconds=3, allowance_operation=scope)
    scope.billed.assert_not_called()


@pytest.mark.asyncio
async def test_context_and_renewal_are_owned_until_exit(policy):
    seen = []
    before = asyncio.all_tasks()

    @operation('one_shot')
    async def handler(uid):
        scope = current.get()
        assert scope.uid == uid
        seen.append(scope)
        await scope.reserve_async('modulate')
        await asyncio.sleep(0)
        return 'served'

    assert await handler('u') == 'served'
    assert current.get() is None
    assert seen[0].closed
    assert asyncio.all_tasks() == before


def test_processing_reads_the_same_billed_plus_reservations_ledger(policy, monkeypatch):
    monkeypatch.setattr(ledger, 'chargeable_seconds', Mock(return_value=99))
    assert watch.snapshot('u', now=datetime(2026, 11, 12, tzinfo=timezone.utc)) == watch.Snapshot('free', 1)
    ledger.chargeable_seconds.assert_called_once()


@pytest.mark.asyncio
async def test_sync_provider_async_loop_cannot_steal_the_operation_owner_loop(policy):
    from utils.executors import run_blocking, sync_executor

    @operation('one_shot')
    async def handler(uid):
        scope = current.get()
        owner = asyncio.get_running_loop()

        def sync_provider():
            asyncio.run(scope.reserve_async('modulate'))

        await run_blocking(sync_executor, sync_provider)
        assert scope.loop is owner

    await handler('u')


def test_only_a_missing_baseline_can_trigger_source_proof(policy, monkeypatch):
    from database import monthly_usage_totals

    proof = Mock()
    monkeypatch.setattr(monthly_usage_totals, 'establish_verified_month', proof)
    result = ledger.reserve.return_value
    ledger.reserve.side_effect = [monthly_usage_totals.UsageBaselineNotReady('not ready'), result]
    Operation('u', 'one_shot', seconds=6).reserve('modulate')
    proof.assert_called_once()
    assert ledger.reserve.call_count == 2
    proof.reset_mock()
    ledger.reserve.side_effect = TimeoutError
    Operation('u', 'one_shot', seconds=6).reserve('modulate')
    proof.assert_not_called()


def test_live_reservation_uses_billing_exposure_instead_of_socket_age(policy):
    scope = Operation('u', 'live_open', live=True)
    scope.clock = lambda: 2.75
    scope.reserve('soniox')
    assert ledger.reserve.call_args.args[2] == 32.75
    assert ledger.reserve.call_args.kwargs['elapsed_seconds'] == 2.75


def test_unbound_free_provider_cannot_treat_a_snapshot_as_reservation_permission(policy):
    decisions = Mock()
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(watch, 'LEASE_DECISIONS', decisions)
        watch.observe_unbound('u', 'live_open', 'soniox', 30)
        decisions.labels.assert_called_once_with('live_open', 'billing_scope_unavailable')
        watch.emit.assert_called_once_with('live_open', 'soniox', 'would_refuse', 30)
        ledger.reserve.assert_not_called()
    finally:
        monkey.undo()

"""Retry caps preserve legacy shadow behavior and the existing terminal fences."""

from datetime import timedelta
import logging
from unittest.mock import Mock
from uuid import uuid4

import pytest

from config.refactor_modes import uid_digest
from database import sync_backfill_sequencer as registry, sync_jobs
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from tests.unit.test_batch_pipeline_quarantine_recovery import setup  # noqa: F401
from tests.unit.test_sync_backfill_uid_sequencer import db, NOW, _register  # noqa: F401
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.sync import uid_sequencer, retry_hygiene


@pytest.fixture(autouse=True)
def isolate_modes(monkeypatch):
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S', raising=False)


@pytest.mark.parametrize(
    'mode,cohort,serving',
    [
        ('off', False, False),
        ('shadow', False, False),
        ('typo', False, False),
        ('serve', False, True),
        ('shadow', True, True),
    ],
)
def test_lease_expiry_cap_preserves_fences_and_shadow(mode, cohort, serving, monkeypatch, caplog):
    account = uuid4().hex
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    if cohort:
        monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S', uid_digest(account))
    store = MemoryStore()
    metrics = Mock()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('poison', owner=account), 0)
    with caplog.at_level(logging.INFO):
        for attempt in (1, 2):
            now = attempt * 1000
            queue.recover(now)
            lease = queue.pull(now)[0]
            assert lease.attempt == attempt
            assert queue.recover(now + 121) == 1
    job = store.rows['jobs', 'poison']
    if serving:
        assert job['state'] == 'quarantined' and not job['merge_pending']
        # RecoveryStore.prepare requires this exact reason, not a new category.
        assert job['quarantine_reason'] == 'worker_failed' and job['recovery_state'] == 'held'
        assert job['token'] == '' and job['lease_until'] == 0
        assert 'retry_started_at' not in job and 'result' not in job
        assert queue.recover(99999) == 0 and queue.pull(99999) == []
        assert not queue.complete(WorkResult('poison', 'gs://synthetic/stale'), lease.token, 99999)
        assert ('results', 'poison') not in store.rows
        assert store.rows['owners', owner_key(account)]['revision'] >= 1
        metrics.record.assert_any_call('quarantined')
        metrics.record.assert_any_call('recovery_held')
    else:
        assert job['state'] == 'retry' and job['merge_pending']
        if mode != 'off':
            assert 'check=scheduler_lease_expiry outcome=disagree would_quarantine=True' in caplog.text
    assert account not in caplog.text


def test_lease_expiry_uses_pinned_maximum(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('poison', owner=uuid4().hex), 0)
    lease = queue.pull(0)[0]
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    queue.recover(121)
    assert store.rows['jobs', 'poison']['state'] == 'retry'
    queue.recover(126)
    lease = queue.pull(126)[0]
    queue.recover(247)
    assert store.rows['jobs', 'poison']['state'] == 'quarantined'


def setup_dispatch(db, monkeypatch, mode='serve'):
    account = uuid4().hex
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '2')
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _: {'status': 'queued'})
    _register(account, 'poison', 0, db=db)
    claim = registry.claim_next(account, now=NOW)
    current = NOW + timedelta(minutes=6)
    replacement = registry.redrive_job(account, 'poison', claim['epoch'], now=current)
    assert replacement['dispatch_attempt'] == 1
    return account, claim, current + timedelta(minutes=6)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'typo'])
def test_dispatch_shadow_keeps_redriving(db, monkeypatch, caplog, mode):
    account, claim, current = setup_dispatch(db, monkeypatch, mode)
    dispatch = Mock()
    finalizer = Mock(side_effect=AssertionError('shadow terminalization'))
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    monkeypatch.setattr(uid_sequencer, '_finalize_abandoned_budget_chain_job', finalizer)
    with caplog.at_level(logging.INFO):
        assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=current) == 'lease_expired'
    assert registry.get_owner(account)['dispatch_attempt'] == 2
    assert dispatch.call_args.args[0]['epoch'] == claim['epoch']
    finalizer.assert_not_called()
    if mode != 'off':
        assert 'check=sequencer_dispatch outcome=disagree would_quarantine=True' in caplog.text
    assert account not in caplog.text


@pytest.mark.parametrize('blocked', ['lock', 'write', 'cleanup', 'none'])
def test_dispatch_cap_terminalizes_before_release(db, monkeypatch, blocked):
    account, claim, current = setup_dispatch(db, monkeypatch)
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    # Registry calls are independently capped even without the reconciler.
    assert registry.redrive_job(account, 'poison', claim['epoch'], now=current) is None
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _: None if blocked == 'lock' else 'lock')
    release = Mock()
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', release)
    failure = Mock(
        return_value=sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED,
            job={'status': 'failed'},
        )
    )
    if blocked == 'write':
        failure.side_effect = RuntimeError('offline write')
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', failure)
    cleanup = Mock(return_value=blocked != 'cleanup')
    monkeypatch.setattr(uid_sequencer, '_cleanup_capped_chain_job_side_effects', cleanup)
    kick = Mock()
    monkeypatch.setattr(uid_sequencer, 'kick', kick)
    outcome = uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=current)
    if blocked != 'none':
        assert outcome == 'finalize_deferred'
        assert registry.get_owner(account)['active_job_id'] == 'poison'
        kick.assert_not_called()
    else:
        assert outcome == 'dispatch_retry_cap_reached'
        assert not registry.get_owner(account).get('active_job_id')
        assert failure.call_args.kwargs['reason_code'] == 'sync_dispatch_exhausted'
        cleanup.assert_called_once_with({'status': 'queued'}, release_claim=True)
        kick.assert_called_once()
    dispatch.assert_not_called()
    if blocked != 'lock':
        release.assert_called_once()


def test_dispatch_cap_refuses_renewed_owner(db, monkeypatch):
    account, claim, current = setup_dispatch(db, monkeypatch)
    old = registry.get_owner(account)
    # A queued task begins after the sweep snapshot: the finalizer must recheck.
    assert registry.begin_job(account, 'poison', claim['epoch'], now=current)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', Mock())
    failure = Mock()
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', failure)
    assert uid_sequencer.reconcile_uid(account, old, now=current) == 'finalize_deferred'
    failure.assert_not_called()
    assert registry.get_owner(account)['active_state'] == 'running'


def test_retry_cap_metrics_are_bounded(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    metric = retry_hygiene.DECISIONS.labels('sequencer_dispatch', 'would_quarantine')._value
    before = metric.get()
    retry_hygiene.observe('sequencer_dispatch', retry_hygiene.retry_cap(uuid4().hex, 2, 2))
    assert metric.get() == before + 1


def test_legacy_lease_shadow_does_not_pin_a_new_policy(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('legacy', owner=uuid4().hex), 0)
    queue.pull(0)
    job = store.rows['jobs', 'legacy']
    job.pop('policy_parts', None)
    job.pop('policy_part_sources', None)
    queue.recover(121)
    assert 'policy_parts' not in store.rows['jobs', 'legacy']
    assert 'policy_part_sources' not in store.rows['jobs', 'legacy']


def test_dispatch_cap_converges_completed_content(db, monkeypatch):
    account, claim, current = setup_dispatch(db, monkeypatch)
    job = {'status': 'queued', 'ledger_fence_mode': 'active'}
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _: job)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_sync_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', Mock())
    converge = Mock(return_value={'status': 'completed'})
    monkeypatch.setattr(uid_sequencer, '_converge_capped_ledger_completion', converge)
    failure = Mock(side_effect=AssertionError('durably completed work must not fail'))
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', failure)
    cleanup = Mock(return_value=True)
    monkeypatch.setattr(uid_sequencer, '_cleanup_capped_chain_job_side_effects', cleanup)
    monkeypatch.setattr(uid_sequencer, 'kick', Mock())
    assert (
        uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=current) == 'dispatch_retry_cap_reached'
    )
    converge.assert_called_once()
    cleanup.assert_called_once_with(job, release_claim=False)
    failure.assert_not_called()
    assert not registry.get_owner(account).get('active_job_id')


def test_expired_quarantine_reaches_existing_recovery(setup, monkeypatch):
    from config.policy import resolve_stage_policy
    from tests.unit.test_batch_pipeline_quarantine_recovery import row

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    client, store, binding, _, _, recovery = setup
    row(client).update(
        state='leased',
        attempt=2,
        lease_until=1,
        token='expired',
        merge_pending=True,
        policy_parts={
            'scheduler': resolve_stage_policy(
                binding.owner_id, 'scheduler', flags={'BATCH_PIPELINE_MAX_ATTEMPTS': '2'}
            ).to_dict()
        },
    )
    # Query enumeration is outside this transaction test's strict fake scope.
    monkeypatch.setattr(store, 'due', lambda state, now, limit: ['bad'] if state == 'leased' else [])
    assert Scheduler(store).recover(2) == 1
    prepared = recovery.protocol.prepare('bad', binding.owner_id, 3)
    assert prepared['recovery_state'] == 'prepared'
    assert prepared['recovery']['epoch'] == 1

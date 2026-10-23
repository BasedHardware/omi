"""Shared batch retry caps preserve shadow behavior and terminal fences."""

import logging
from unittest.mock import Mock
from uuid import uuid4

import pytest

from config.refactor_modes import uid_digest
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from tests.unit.test_batch_pipeline_quarantine_recovery import setup  # noqa: F401
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.capture import retry_cap as retry_hygiene


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


def test_retry_cap_metrics_are_bounded(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    metric = retry_hygiene.DECISIONS.labels('scheduler_lease_expiry', 'would_quarantine')._value
    before = metric.get()
    retry_hygiene.observe('scheduler_lease_expiry', retry_hygiene.retry_cap(uuid4().hex, 2, 2))
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

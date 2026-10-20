"""Bounded failure, ordered skip and retained ownership; no cloud/model access."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging
import time
from types import SimpleNamespace
from unittest.mock import Mock

from prometheus_client import CollectorRegistry
import pytest

from config.batch_pipeline import max_worker_attempts
from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from database.sync_ledger import _bind_run_token_transaction, SyncContentRunBindingOutcome
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_intake import proposal, submit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import PoolCapacity, ProjectionBinding, WorkResult
from utils.batch_pipeline.intake import durable_status
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owner_key


@pytest.mark.parametrize('value,expected', [('1', 1), ('8', 8), ('20', 20), ('0', 5), ('21', 5), ('bad', 5)])
def test_ceiling_is_configurable_and_invalid_values_remain_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', value)
    assert max_worker_attempts() == expected


def test_ordered_skip_preserves_predecessors_and_fences_late_success(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    store = MemoryStore()
    queue, merge = Scheduler(store), OrderedMerge(store)
    for name, stamp in [('before', 1), ('poison', 2), ('after', 3)]:
        queue.enqueue(item(name, capture=stamp), 0)
    leases = {v.item.segment_id: v for v in queue.pull(0, 3)}
    queue.complete(WorkResult('after', 'gs://synthetic/after'), leases['after'].token, 1)
    assert queue.fail('poison', leases['poison'].token, 1)
    # Quarantine cannot bypass a genuinely unfinished earlier successful span.
    assert merge.commit_next('heavy', 2) is None
    queue.complete(WorkResult('before', 'gs://synthetic/before'), leases['before'].token, 2)
    assert merge.commit_next('heavy', 3)['segment_id'] == 'before'
    later = merge.commit_next('heavy', 3)
    assert later['segment_id'] == 'after' and later['previous_segment_id'] == 'before'
    assert later['log_sequence'] == 2
    assert not queue.complete(WorkResult('poison', 'gs://synthetic/stale'), leases['poison'].token, 4)
    assert not queue.heartbeat('poison', leases['poison'].token, 4)
    assert merge.commit_next('heavy', 4) is None
    assert ('results', 'poison') not in store.rows


@pytest.mark.asyncio
async def test_pump_drains_already_ready_sibling_when_last_lease_quarantines(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('poison', capture=1), 0)
    queue.enqueue(item('later', capture=2), 0)
    leases = {v.item.segment_id: v for v in queue.pull(0, 2)}
    queue.complete(WorkResult('later', 'gs://synthetic/later'), leases['later'].token, 1)
    queue.defer('poison', leases['poison'].token, 1, 1)
    worker = Mock()
    worker.process_batch.return_value = []
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), 8))
    assert await pump.run_once() == 1
    assert store.rows['jobs', 'poison']['state'] == 'quarantined'
    assert store.rows['jobs', 'later']['state'] == 'committed'
    assert store.rows['results', 'later']['previous_segment_id'] is None


def test_recoverable_quarantine_holds_batch_claim_and_keeps_polling(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    store = MemoryStore()
    submit(store, *proposal())
    queue = Scheduler(store)
    lease = queue.pull(100)[0]
    assert queue.fail(lease.item.segment_id, lease.token, 101)
    original = deepcopy(store.rows['content', 'synthetic-owner/content'])
    for _ in range(2):
        status = durable_status(store, 'synthetic-owner', 'bp_first')
        assert status['status'] == 'processing' and status['failed_segments'] == 0
        assert status['result'] is None and status['poll_after_ms'] == 3000
        assert status['errors'] == []
        assert submit(store, *proposal('another', 'another')) == {'outcome': 'batch', 'job_id': 'bp_first'}
    assert store.rows['content', 'synthetic-owner/content'] == original
    # The existing legacy entry point cannot bind this retained whole-upload claim.
    client = StrictFirestore({('ledger', 'content'): original})
    ref = client.collection('ledger').document('content')
    for _ in range(2):
        binding = _bind_run_token_transaction(
            client.transaction(), ref, 'bp_first', 'legacy', 1, datetime.now(timezone.utc)
        )
        assert binding.outcome == SyncContentRunBindingOutcome.LOST
    assert client.rows[('ledger', 'content')] == original


def projection_fixture():
    binding = ProjectionBinding('synthetic-owner', 'bp_upload', 'content', ('bad', 'good'))
    work = replace(item('good', owner=binding.owner_id), privacy_generation=0)
    result = asdict(WorkResult('good', 'gs://synthetic/good'))
    rows = {
        ('users', binding.owner_id): {'data_protection_level': 'standard'},
        ('batch_pipeline_dev_jobs', 'good'): {**asdict(work), 'projection_binding': asdict(binding), 'result': result},
        ('batch_pipeline_dev_jobs', 'bad'): {
            'state': 'quarantined',
            'projection_binding': asdict(binding),
            'merge_pending': False,
        },
        ('batch_pipeline_dev_results', 'good'): {
            'protocol_version': 1,
            'segment_id': 'good',
            'owner_key': owner_key(binding.owner_id),
            'capture_at': work.capture_at,
            'previous_segment_id': None,
            'result': result,
            'projection_state': 'ready',
            'projection': {'state': 'ready', 'speech_seconds': 3},
        },
        ('users', binding.owner_id, 'sync_content_ledger', binding.content_id): {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {
                'protocol_version': 1,
                'namespace': 'batch_pipeline_dev',
                'segment_ids': list(binding.segment_ids),
            },
        },
    }
    for (collection, *_), value in rows.items():
        if collection == 'batch_pipeline_dev_jobs':
            value['policy_parts'] = {'projection': ProjectionPolicy().to_dict()}
    client = StrictFirestore(rows)
    store = ProjectionStore(SimpleNamespace(client=client, namespace='batch_pipeline_dev'))
    store.policy = lambda sid: ProjectionPolicy.from_dict(
        client.rows[('batch_pipeline_dev_jobs', sid)]['policy_parts']['projection']
    )
    return client, store, binding


def test_persisted_sibling_leaves_sweep_without_success_or_claim_release(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')  # Uses the unprefixed production ledger name, entirely in memory.
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    client, store, binding = projection_fixture()
    before = deepcopy(client.rows)
    assert store.hold_for_quarantine('good', binding, 100)
    assert store.hold_for_quarantine('good', binding, 101)
    entry = client.rows[('batch_pipeline_dev_results', 'good')]
    assert entry['projection_state'] == 'quarantine_held'
    assert entry['projection'] == before[('batch_pipeline_dev_results', 'good')]['projection']
    assert client.rows[('users', binding.owner_id, 'sync_content_ledger', 'content')]['status'] == 'processing'
    assert store.prepare_accounting(binding, 102) is None
    assert ('batch_pipeline_dev_results', 'bad') not in client.rows
    assert all(not t.creates and not t.sets for t in client.transactions)


@pytest.mark.parametrize('change', ['binding', 'privacy', 'not_ready', 'pending', 'ledger'])
def test_hold_fails_closed_against_revoked_or_invalid_sibling(monkeypatch, change):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client, store, binding = projection_fixture()
    if change == 'binding':
        client.rows[('batch_pipeline_dev_jobs', 'bad')]['projection_binding']['content_id'] = 'foreign'
    elif change == 'privacy':
        client.rows[('users', binding.owner_id)]['data_protection_level'] = 'e2ee'
    elif change == 'not_ready':
        client.rows[('batch_pipeline_dev_results', 'good')]['projection']['state'] = 'persisted'
    elif change == 'pending':
        client.rows[('batch_pipeline_dev_jobs', 'bad')]['merge_pending'] = True
    else:
        client.rows[('users', binding.owner_id, 'sync_content_ledger', 'content')]['job_id'] = 'replacement'
    before = deepcopy(client.rows)
    if change == 'not_ready':
        assert not store.hold_for_quarantine('good', binding, 100)
    else:
        with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
            store.hold_for_quarantine('good', binding, 100)
    assert client.rows == before


def test_quarantine_counter_and_recovery_hold_emit_once(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    registry = CollectorRegistry()
    store = MemoryStore()
    queue = Scheduler(store, metrics=QueueMetrics(registry))
    queue.enqueue(item('bad'), 0)
    lease = queue.pull(0)[0]
    with caplog.at_level(logging.WARNING):
        assert queue.fail('bad', lease.token, 1)
        assert not queue.fail('bad', lease.token, 2)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'quarantined'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'recovery_held'}) == 1
    assert sum('event=batch_quarantined ' in r.message for r in caplog.records) == 1
    assert sum('event=batch_recovery ' in r.message for r in caplog.records) == 1


def test_quarantine_transaction_reads_before_writes_and_telemetry_cannot_escape(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    memory = MemoryStore()
    queue = Scheduler(memory)
    queue.enqueue(replace(item('bad', owner='synthetic-owner'), privacy_generation=0), 0)
    lease = queue.pull(0)[0]
    rows = {(f'batch_pipeline_dev_{table}', key): value for (table, key), value in memory.rows.items()}
    rows[('users', 'synthetic-owner')] = {'data_protection_level': 'standard'}
    client = StrictFirestore(rows)
    queue = Scheduler(FirestoreStore('batch_pipeline_dev', firestore_client=client), metrics=Mock())
    queue.metrics.record.side_effect = RuntimeError('synthetic metrics failure')
    monkeypatch.setattr(
        'utils.batch_pipeline.scheduler.logger.error', Mock(side_effect=RuntimeError('synthetic logger failure'))
    )
    assert queue.fail('bad', lease.token, 1)
    assert client.rows[('batch_pipeline_dev_jobs', 'bad')]['state'] == 'quarantined'
    assert not queue.fail('bad', lease.token, 2)


def test_later_projection_accepts_persisted_predecessor_after_quarantine_hold(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client, store, binding = projection_fixture()
    assert store.hold_for_quarantine('good', binding, 100)
    next_binding = replace(binding, job_id='bp_next', content_id='next', segment_ids=('next',))
    job = deepcopy(client.rows[('batch_pipeline_dev_jobs', 'good')])
    job.update(segment_id='next', capture_at=2, projection_binding=asdict(next_binding))
    job['result'] = asdict(WorkResult('next', 'gs://synthetic/next'))
    client.rows[('batch_pipeline_dev_jobs', 'next')] = job
    client.rows[('batch_pipeline_dev_owners', owner_key(binding.owner_id))] = {'projection_watermark': 'good'}
    client.rows[('batch_pipeline_dev_results', 'next')] = {
        'protocol_version': 1,
        'segment_id': 'next',
        'owner_key': owner_key(binding.owner_id),
        'capture_at': 2,
        'previous_segment_id': 'good',
        'result': job['result'],
        'projection_state': 'pending',
    }
    ledger = deepcopy(client.rows[('users', binding.owner_id, 'sync_content_ledger', 'content')])
    ledger.update(
        job_id='bp_next',
        batch_pipeline={'protocol_version': 1, 'namespace': 'batch_pipeline_dev', 'segment_ids': ['next']},
    )
    client.rows[('users', binding.owner_id, 'sync_content_ledger', 'next')] = ledger
    # Runs the real privacy, immutable binding, ledger ownership and predecessor checks.
    store.check(store.session('next', next_binding, 101))
    # Moving the cursor back proves we did not loosen the preceding-success fence.
    client.rows[('batch_pipeline_dev_owners', owner_key(binding.owner_id))]['projection_watermark'] = None
    with pytest.raises(ProjectionBlocked, match='earlier committed projection'):
        store.check(store.session('next', next_binding, 102))


def test_policy_deferrals_do_not_spend_ceiling_and_stale_fail_is_inert(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('wait'), 0)
    for stamp in (1, 100, 200):
        queue.recover(stamp)
        lease = queue.pull(stamp)[0]
        assert lease.attempt == 1
        assert not queue.fail('wait', 'foreign-token', stamp)
        assert queue.defer('wait', lease.token, stamp, 1)
        assert store.rows['jobs', 'wait']['attempt'] == 0
        assert store.rows['jobs', 'wait']['state'] == 'retry'

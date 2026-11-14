"""Sealed records retain fresh delivery without changing backlog or custody."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from config import record_latency
from config.policy import ProjectionPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_projection import ProjectionStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import live
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler
from utils.sync import reprocess

NOW = 100_000.0


@pytest.mark.parametrize(
    'reader,name',
    [
        (record_latency.record_fresh_merge_enabled, 'RECORD_FRESH_MERGE_ENABLED'),
        (record_latency.record_notes_eager_enabled, 'RECORD_NOTES_EAGER_ENABLED'),
        (record_latency.record_followup_wake_enabled, 'RECORD_FOLLOWUP_WAKE_ENABLED'),
        (record_latency.record_seal_wake_preserved_enabled, 'RECORD_SEAL_WAKE_PRESERVED_ENABLED'),
    ],
)
def test_latency_controls_default_on_with_explicit_kill_words(monkeypatch, reader, name):
    monkeypatch.delenv(name, raising=False)
    assert reader()
    for value in ('false', 'off', '0', 'no'):
        monkeypatch.setenv(name, value)
        assert not reader()


@pytest.mark.parametrize(
    'end,expected',
    [
        (NOW, True),
        (NOW - 1800, True),
        (NOW - 1801, False),
        (NOW + 1, False),
        (None, False),
        (True, False),
        (float('nan'), False),
        (float('inf'), False),
        ('yesterday', False),
    ],
)
def test_recent_record_end_has_a_bounded_trusted_clock(end, expected):
    assert record_latency.recent_record_end(end, NOW) is expected
    assert record_latency.recent_record_end(datetime.fromtimestamp(NOW - 1800, timezone.utc), NOW)


@pytest.mark.parametrize(
    'end_lag,enabled,expected', [(700, True, True), (1800, True, True), (1801, True, False), (700, False, False)]
)
def test_native_record_freshness_uses_record_end_for_every_sibling(monkeypatch, end_lag, enabled, expected):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', str(enabled).lower())
    store = MemoryStore()
    queue = Scheduler(store)
    # Old unresolved work must keep its own result and append later; it may
    # not block this recording simply because sealing took over ten minutes.
    queue.enqueue(item('older', owner='synthetic-owner', capture=1, duration=10), NOW)
    store.rows['jobs', 'older']['state'] = 'retry'
    works = [
        replace(item(sid, owner='synthetic-owner', capture=NOW - 5000 + i * 1000, duration=60), privacy_generation=0)
        for i, sid in enumerate(('first', 'last'))
    ]
    binding = ProjectionBinding(
        'synthetic-owner',
        'record-job',
        'record-content',
        ('first', 'last'),
        record_origin=True,
        native_record=True,
        target_conversation_id='capture',
    )
    store.rows['conversations', 'synthetic-owner/capture'] = {
        'status': 'completed',
        'record_audio_closed': True,
        'record_lane_owner': 'batch_sync_v1',
        'finished_at': datetime.fromtimestamp(NOW - end_lag, timezone.utc),
    }
    admit(store, works, binding, NOW, namespace='test')
    for work in works:
        job = store.rows['jobs', work.segment_id]
        assert job['fresh_capture'] is expected
        job.update(
            state='result_ready', result=WorkResult(work.segment_id, 'gs://synthetic/result').to_dict(), ready_at=NOW
        )
    if expected:
        merge = OrderedMerge(store)
        assert merge.commit_next('synthetic-owner', NOW)['segment_id'] == 'first'
        assert merge.commit_next('synthetic-owner', NOW)['segment_id'] == 'last'
        assert store.rows['jobs', 'older']['state'] == 'retry'
        assert merge.commit_next('synthetic-owner', NOW) is None


@pytest.mark.parametrize('summary_seen', [False, True])
@pytest.mark.parametrize('case', ['recent', 'old', 'partial', 'upload', 'unstamped', 'off'])
def test_only_recent_sealed_native_records_enqueue_notes_without_settle(monkeypatch, case, summary_seen):
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '600')
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false' if case == 'off' else 'true')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', '')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', '')
    client = StrictFirestore()
    store = ProjectionStore(Mock(client=client))
    receipt_ref = client.collection('receipts').document('segment')
    receipt_ref.create({'state': 'persisted'})
    binding = ProjectionBinding(
        'synthetic-owner',
        'job',
        'content',
        ('segment',),
        record_origin=case != 'upload',
        native_record=case != 'upload',
        partial_record=case == 'partial',
    )
    session = Mock()
    session.job = {
        'priority': 0,
        'fresh_capture': True,
        'record_finished_at': NOW - (1801 if case == 'old' else 700),
        'projection_binding': {'native_record': binding.native_record, 'partial_record': binding.partial_record},
    }
    if case == 'unstamped':
        session.job.pop('record_finished_at')
    session.prepare.side_effect = lambda tx, **_: receipt_ref.get(transaction=tx)
    session.guard.side_effect = lambda tx, _: receipt_ref.get(transaction=tx)
    session.receipt.return_value = {'state': 'persisted'}
    session.write_receipt.side_effect = lambda tx, receipt: tx.set(receipt_ref, receipt)
    monkeypatch.setattr(store, 'session', lambda *a, **k: session)
    monkeypatch.setattr(store, 'run', lambda operation, **_: operation(client.transaction()))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    if summary_seen:
        client.collection(reprocess.COLLECTION).document(reprocess.key(binding.owner_id, 'capture')).create(
            {
                'summary_seen': True,
                'first_pending_at': NOW,
                'version': 1,
                'due_at': NOW + 300,
                'task_due_at': NOW + 300,
                'task_token': 'a' * 32,
            }
        )
    store.mark_enrichment('segment', binding, NOW, 'capture', 'en', policy=ProjectionPolicy())
    row = client.collection(reprocess.COLLECTION).document(reprocess.key(binding.owner_id, 'capture')).get().to_dict()
    # First-summary debt already clips the legacy 600s settle to 120s.
    # Refreshes keep the full settle. The sealed-record wake removes both.
    delay = 600 if summary_seen else 120
    assert row['due_at'] == (NOW if case == 'recent' else NOW + delay)
    assert receipt_ref.get().to_dict()['state'] == 'ready'
    session.guard.assert_called_once_with(client.transactions[0], ['capture'])


@pytest.mark.asyncio
@pytest.mark.parametrize('wake', [0, NOW])
@pytest.mark.parametrize('enabled', [False, True])
async def test_seal_wake_wins_over_inflight_barrier_refusal(monkeypatch, wake, enabled):
    monkeypatch.setenv('RECORD_SEAL_WAKE_PRESERVED_ENABLED', str(enabled).lower())
    monkeypatch.setattr(live.time, 'time', lambda: NOW)
    store = MemoryStore()
    store.rows['jobs', 'record'] = {
        'owner_id': 'synthetic-owner',
        'segment_id': 'record',
        'state': 'record_pending',
        'available_at': 0,
        'enqueued_at': NOW - 700,
    }

    async def seal_after_read(store, pending):
        # The barrier read happened before the sealer's transaction; its wake
        # then commits before this attempt persists the stale retry delay.
        store.rows['jobs', 'record']['available_at'] = wake
        raise ValueError(live.BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', seal_after_read)
    await live.drain_recordings(store)
    assert store.rows['jobs', 'record']['available_at'] == (wake if enabled else NOW + 900)
    assert store.rows['jobs', 'record']['state'] == 'record_pending'

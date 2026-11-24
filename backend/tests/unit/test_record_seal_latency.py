"""Sealed records retain fresh delivery without changing backlog or custody."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from config import record_latency
from config.policy import ProjectionPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_projection import ProjectionStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import live, merge as merge_module
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.sync import reprocess

NOW = 100_000.0


@pytest.mark.parametrize(
    'reader,name,default',
    [
        (record_latency.record_fresh_merge_enabled, 'RECORD_FRESH_MERGE_ENABLED', False),
        (record_latency.record_notes_eager_enabled, 'RECORD_NOTES_EAGER_ENABLED', False),
        (record_latency.record_followup_wake_enabled, 'RECORD_FOLLOWUP_WAKE_ENABLED', True),
        (record_latency.record_seal_wake_preserved_enabled, 'RECORD_SEAL_WAKE_PRESERVED_ENABLED', True),
    ],
)
def test_latency_controls_have_safe_unset_defaults(monkeypatch, reader, name, default):
    monkeypatch.delenv(name, raising=False)
    assert reader() is default
    for value in ('false', 'off', '0', 'no'):
        monkeypatch.setenv(name, value)
        assert not reader()
    for value in ('true', 'on', '1', 'yes'):
        monkeypatch.setenv(name, value)
        assert reader()


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
    'end_lag,enabled,expected',
    [(700, True, True), (1800, True, True), (1801, True, False), (700, False, False), (900, None, False)],
)
def test_native_record_freshness_uses_record_end_for_every_sibling(monkeypatch, end_lag, enabled, expected):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    if enabled is None:
        monkeypatch.delenv('RECORD_FRESH_MERGE_ENABLED', raising=False)
    else:
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
        # That blocked drain requeued the due retry head; it still appends later with its own result.
        assert store.rows['jobs', 'older']['state'] == 'ready'
        assert store.rows['jobs', 'older']['merge_pending'] is True


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
        'record_notes_after_complete': case == 'recent',
        'fresh_capture': True,
        'record_finished_at': NOW - (1801 if case == 'old' else 700),
        'projection_binding': {'native_record': binding.native_record, 'partial_record': binding.partial_record},
    }
    if case == 'unstamped':
        session.job.pop('record_finished_at')
    session.ledger = {}
    session.ledger_ref = client.collection('ledgers').document('content')
    session.ledger_ref.create({})
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
    if case == 'recent':
        # A delayed fallback survives a missing sibling; only completion
        # may advance this obligation to now.
        assert row['version'] == 1 + int(summary_seen)
        assert row['due_at'] == NOW + (300 if summary_seen else delay)
        assert receipt_ref.get().to_dict()['record_notes_deferred'] is True
    else:
        assert row['due_at'] == NOW + delay
    assert receipt_ref.get().to_dict()['state'] == 'ready'
    session.guard.assert_called_once_with(client.transactions[0], ['capture'])


@pytest.mark.parametrize('transactional', [False, True])
@pytest.mark.parametrize('older_stock', [False, True])
def test_expired_head_wait_never_bypasses_an_unready_record_sibling(monkeypatch, transactional, older_stock):
    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', 'true')
    from dataclasses import asdict

    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', str(transactional).lower())
    store = MemoryStore()
    queue = Scheduler(store)
    if older_stock:
        queue.enqueue(item('stock', owner='owner', capture=1), NOW)
        store.rows['jobs', 'stock'].update(state='retry', fresh_capture=False)
    binding = ProjectionBinding('owner', 'record-job', 'record-content', ('first', 'last'), native_record=True)
    for i, sid in enumerate(binding.segment_ids):
        queue.enqueue(item(sid, owner='owner', capture=NOW - 100 + i), NOW)
        store.rows['jobs', sid].update(projection_binding=asdict(binding), fresh_capture=True)
    store.rows['jobs', 'last'].update(
        state='result_ready', result=WorkResult('last', 'gs://synthetic/result').to_dict(), ready_at=NOW - 600
    )
    merge = OrderedMerge(store)
    assert merge.commit_next('owner', NOW) is None
    assert merge.commit_next('owner', NOW + 600) is None
    assert store.rows['jobs', 'last']['state'] == 'result_ready'
    store.rows['jobs', 'first'].update(
        state='result_ready', result=WorkResult('first', 'gs://synthetic/result').to_dict(), ready_at=NOW
    )
    assert merge.commit_next('owner', NOW + 600)['segment_id'] == 'first'
    assert merge.commit_next('owner', NOW + 600)['segment_id'] == 'last'


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


@pytest.mark.asyncio
@pytest.mark.parametrize('fresh_repair,dead_letter', [(False, False), (False, True), (True, False), (True, True)])
async def test_merge_preserves_claim_clock_and_retry_marker_contract(monkeypatch, fresh_repair, dead_letter):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_FRESH_ENABLED', str(fresh_repair).lower())
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', str(dead_letter).lower())
    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'off')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)
    store = MemoryStore()
    store.rows['jobs', 'record'] = {
        'owner_id': 'synthetic-owner',
        'segment_id': 'record',
        'state': 'record_pending',
        'available_at': 0,
        'record_intake_retry_at': 0,
        'enqueued_at': NOW - 700,
    }

    async def barrier_refusal(store, pending):
        claimed = store.rows['jobs', 'record']
        assert claimed['record_intake_claimed_at'] == NOW
        assert 'record_intake_retry_at' not in claimed
        raise ValueError(live.BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', barrier_refusal)
    await live.drain_recordings(store)
    row = store.rows['jobs', 'record']
    assert row['available_at'] == NOW + 60
    assert ('record_intake_retry_at' in row) is (fresh_repair and dead_letter)
    if fresh_repair and dead_letter:
        assert row['record_intake_retry_at'] == row['available_at']


@pytest.mark.parametrize(
    'process',
    ['backend', 'backend-integration', 'backend-sync', 'backend-sync-backfill', 'backend-listen', 'batch-worker'],
)
def test_image_only_process_without_fresh_merge_env_is_inert(monkeypatch, process):
    # All process entrypoints use this shared intake reader; no overlay is required.
    monkeypatch.setenv('K_SERVICE', process)
    monkeypatch.delenv('RECORD_FRESH_MERGE_ENABLED', raising=False)
    assert record_latency.record_fresh_merge_enabled() is False


@pytest.mark.parametrize('fresh_merge', [True])
@pytest.mark.parametrize('fresh_class', [False, True])
def test_recovering_record_sibling_does_not_block_an_independent_record(monkeypatch, fresh_merge, fresh_class):
    from dataclasses import asdict

    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', str(fresh_merge).lower())
    store = MemoryStore()
    queue = Scheduler(store)
    binding = ProjectionBinding('owner', 'x', 'x-content', ('x1', 'x2'), native_record=True)
    for i, sid in enumerate(('x1', 'x2', 'y')):
        queue.enqueue(item(sid, owner='owner', capture=NOW - 100 + i), NOW)
        store.rows['jobs', sid].update(fresh_capture=fresh_class)
    for sid in ('x1', 'x2'):
        store.rows['jobs', sid]['projection_binding'] = asdict(binding)
    store.rows['jobs', 'x1'].update(
        state='quarantined',
        merge_pending=False,
        recovery_state='running',
    )
    for sid in ('x2', 'y'):
        store.rows['jobs', sid].update(
            state='result_ready',
            ready_at=NOW - 600,
            result=WorkResult(sid, 'gs://synthetic/result').to_dict(),
        )
    merged = OrderedMerge(store).commit_next('owner', NOW)
    assert merged and merged['segment_id'] == 'y'
    assert store.rows['jobs', 'x2']['state'] == 'result_ready'


@pytest.mark.parametrize('over_depth', [False, True])
def test_sibling_probe_advances_full_held_pages_across_merge_instances(monkeypatch, over_depth):
    page_size = 8
    monkeypatch.setattr(merge_module, 'RECORD_SIBLING_PROBE_ROWS', page_size)
    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    binding = ProjectionBinding('owner', 'x', 'x-content', ('x1', 'x2'), native_record=True)
    for i, sid in enumerate(('x1', 'x2', *(f'old-{j:03d}' for j in range(page_size)), 'y')):
        queue.enqueue(item(sid, owner='owner', capture=NOW - 500 + i), NOW)
        job = store.rows['jobs', sid]
        job.update(
            fresh_capture=sid == 'y',
            state='result_ready',
            ready_at=NOW - 600,
            result=WorkResult(sid, 'gs://synthetic/result').to_dict(),
        )
        if sid.startswith('old-'):
            job['stt_route'] = {'stt_route': 'provider'}
    for sid in ('x1', 'x2'):
        store.rows['jobs', sid]['projection_binding'] = asdict(binding)
    store.rows['jobs', 'x1'].update(state='quarantined', merge_pending=False, recovery_state='running')
    if over_depth:
        store.rows['owners', owner_key('owner')]['log_sequence'] = 16
    probe = Mock(wraps=store.ready_pending)
    store.ready_pending = probe
    merge = OrderedMerge(store, catch_up_depth=16)
    assert merge.commit_next('owner', NOW) is None
    cursor = store.rows['owners', owner_key('owner')]['record_sibling_cursor']
    assert cursor['segment_id'] == f'old-{page_size - 2:03d}'
    assert probe.call_args.kwargs['after'] is None
    assert probe.call_args.args[1] == page_size
    merged = OrderedMerge(store, catch_up_depth=16).commit_next('owner', NOW)
    assert merged and merged['segment_id'] == 'y'
    assert probe.call_args.kwargs['after'] == (cursor['capture_at'], cursor['segment_id'])
    assert probe.call_count == 2
    assert 'record_sibling_cursor' not in store.rows['owners', owner_key('owner')]
    assert store.rows['jobs', 'x2']['state'] == 'result_ready'


@pytest.mark.parametrize('switch', [None, 'false'])
@pytest.mark.parametrize('recovery', ['running', 'failed_held', 'normal'])
def test_fresh_merge_off_preserves_main_selection_without_sibling_reads(monkeypatch, switch, recovery):
    from dataclasses import asdict

    if switch is None:
        monkeypatch.delenv('RECORD_FRESH_MERGE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', switch)
    store = MemoryStore()
    queue = Scheduler(store)
    binding = ProjectionBinding('owner', 'x', 'x-content', ('x1', 'x2'), native_record=True)
    for i, sid in enumerate(('x1', 'x2', 'y')):
        queue.enqueue(item(sid, owner='owner', capture=NOW - 100 + i), NOW)
    for sid in ('x1', 'x2'):
        store.rows['jobs', sid]['projection_binding'] = asdict(binding)
    store.rows['jobs', 'x1'].update(state='quarantined', merge_pending=False, recovery_state=recovery)
    if recovery == 'normal':
        store.rows['jobs', 'x1'].update(
            state='result_ready',
            merge_pending=True,
            ready_at=NOW,
            result=WorkResult('x1', 'gs://synthetic/result').to_dict(),
        )
    for sid in ('x2', 'y'):
        store.rows['jobs', sid].update(
            state='result_ready', ready_at=NOW, result=WorkResult(sid, 'gs://synthetic/result').to_dict()
        )
    store.ready_pending = Mock(side_effect=AssertionError('cut 4 off must not query sibling bypass'))
    first = OrderedMerge(store).commit_next('owner', NOW)
    assert first and first['segment_id'] == ('x1' if recovery == 'normal' else 'x2')
    if recovery == 'normal':
        assert OrderedMerge(store).commit_next('owner', NOW)['segment_id'] == 'x2'
    assert OrderedMerge(store).commit_next('owner', NOW)['segment_id'] == 'y'
    store.ready_pending.assert_not_called()

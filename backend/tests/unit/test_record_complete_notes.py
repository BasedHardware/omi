"""Record completion advances one bounded, coalesced notes obligation."""

from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from database.outbox_firestore import FirestoreEnrichmentOutbox
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority
from utils.batch_pipeline.scheduler import owner_key
from utils.sync import capture_end, reprocess

NOW = 100_000.0
POLICY = ProjectionPolicy()


@pytest.fixture
def recording(monkeypatch, request):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'true')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', '')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', '')
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='record_notes'))
    for method in ('_mirror', '_settle_allowance', '_observe_transcription'):
        monkeypatch.setattr(store, method, Mock())
    count = getattr(request, 'param', 2)
    segments = ('first',) if count == 1 else ('first', *(f'middle-{i}' for i in range(count - 2)), 'last')
    binding = ProjectionBinding(
        'synthetic-owner',
        'record-job',
        'record-content',
        segments,
        record_origin=True,
        native_record=True,
        target_conversation_id='capture',
    )
    user = client.collection('users').document(binding.owner_id)
    user.create({'data_protection_level': 'standard'})
    conversation = user.collection('conversations').document('capture')
    conversation.create(
        {
            'status': 'completed',
            'record_audio_closed': True,
            'record_lane_owner': 'batch_sync_v1',
            'record_upload_revision': 1,
            'finished_at': datetime.fromtimestamp(NOW - 700, timezone.utc),
        }
    )
    ledger = sync_content_ledger_ref(client, binding.owner_id, binding.content_id)
    ledger.create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {
                'protocol_version': 1,
                'namespace': store.store.namespace,
                'segment_ids': list(binding.segment_ids),
            },
        }
    )
    store.ref('owners', owner_key(binding.owner_id)).create({})
    for i, sid in enumerate(binding.segment_ids):
        work = WorkItem(
            sid, binding.owner_id, NOW - 2000 + i, 'gs://synthetic/audio', 4, Priority.FRESH, privacy_generation=0
        )
        result = {'outcome': 'success', 'result_uri': 'gs://synthetic/result'}
        store.ref('jobs', sid).create(
            {
                **asdict(work),
                'projection_binding': asdict(binding),
                'result': result,
                'fresh_capture': True,
                'record_notes_after_complete': True,
                'record_input_upload_revision': 1,
                'record_finished_at': NOW - 700,
            }
        )
        store.ref('results', sid).create(
            {
                'protocol_version': 1,
                'segment_id': sid,
                'owner_key': owner_key(binding.owner_id),
                'capture_at': work.capture_at,
                'committed_at': NOW - 10,
                'previous_segment_id': None,
                'result': result,
                'projection_state': 'persisted',
                'projection': {
                    'state': 'persisted',
                    'conversation_id': 'capture',
                    'created': False,
                    'speech_seconds': 0,
                },
            }
        )
    wake = Mock()
    monkeypatch.setattr(FirestoreEnrichmentOutbox, 'wake', wake)
    accounting = {'seconds': 0, 'updates': {}}
    return SimpleNamespace(**locals())


@pytest.mark.parametrize('recording', [1, 2, 128], indirect=True)
def test_complete_binding_has_one_fallback_and_completion_update_independent_of_sibling_count(recording):
    f = recording
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    # Siblings share one delayed fallback and cannot create immediate notes. Probe completion
    # with first/middle/last missing receipts, then the full 128-sibling set;
    # replaying the same incomplete scan after every unit adds no coverage.
    count = len(f.binding.segment_ids)
    probes = {0, count // 2, max(0, count - 2), count - 1}
    for index, sid in enumerate(f.binding.segment_ids):
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
        assert row.get().to_dict()['version'] == 1
        assert row.get().to_dict()['due_at'] > NOW
        if index in probes:
            result = f.store.complete(sid, f.binding, NOW, f.accounting, policy=POLICY)
            if index + 1 < count:
                assert result is None
    assert result and row.get().to_dict()['version'] == 2
    f.store.complete(sid, f.binding, NOW + 1, f.accounting, policy=POLICY)
    assert row.get().to_dict()['version'] == 2


def test_switch_off_uses_normal_settle_despite_admitted_completion_owner(recording, monkeypatch):
    f = recording
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    later = NOW + 1801
    f.store.mark_enrichment('last', f.binding, later, 'capture', 'en', policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert row.get().to_dict()['version'] == 2
    assert f.store.complete('last', f.binding, later, f.accounting, policy=POLICY)
    assert row.get().to_dict()['version'] == 2


def test_size_rollover_keeps_one_obligation_per_distinct_output_without_read_after_write(recording):
    f = recording
    split = f.user.collection('conversations').document('split')
    split.create({'status': 'completed'})
    entry = f.client.rows[f.store.ref('results', 'last').path]
    entry['projection']['size_rollover_outputs'] = [
        {'conversation_id': 'capture', 'created': False},
        {'conversation_id': 'split', 'created': True},
    ]
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    for canonical in ('capture', 'split'):
        ref = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, canonical))
        assert ref.get().to_dict()['version'] == 2
    assert f.store.complete('first', f.binding, NOW + 1, f.accounting, policy=POLICY)
    assert all(data.get('version') == 2 for path, data in f.client.rows.items() if path[0] == reprocess.COLLECTION)


@pytest.mark.parametrize('recording', [1], indirect=True)
def test_large_output_set_checkpoints_without_repeating_notes_after_restart(recording):
    f = recording
    outputs = ['capture', *(f'split-{i}' for i in range(128))]
    for cid in outputs[1:]:
        f.user.collection('conversations').document(cid).create({'status': 'completed'})
    entry = f.client.rows[f.store.ref('results', 'first').path]
    entry['projection']['size_rollover_outputs'] = [{'conversation_id': cid, 'created': False} for cid in outputs]
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('first', f.binding, NOW, f.accounting, policy=POLICY) is None
    assert len(f.ledger.get().to_dict()['record_notes_prepared_outputs']) == 128
    assert len([path for path in f.client.rows if path[0] == reprocess.COLLECTION]) == 129
    assert f.store.ref('results', 'first').get().to_dict()['projection_state'] == 'ready'
    assert f.store.complete('first', f.binding, NOW + 1, f.accounting, policy=POLICY)
    rows = [data for path, data in f.client.rows.items() if path[0] == reprocess.COLLECTION]
    assert len(rows) == 129 and all(row['version'] == 2 for row in rows)


def test_eager_completion_reuses_visible_rows_with_a_decision_only_privacy_guard(recording, monkeypatch):
    from database.batch_pipeline_privacy import assert_batch_write_allowed
    from database.batch_pipeline_projection_session import ProjectionSession

    def decision_only(session, transaction, conversation_ids=()):
        return assert_batch_write_allowed(
            session.client,
            transaction,
            session.binding.owner_id,
            conversation_ids=conversation_ids,
            expected_generation=session.binding.privacy_generation,
        )

    monkeypatch.setattr(ProjectionSession, 'guard', decision_only)
    f = recording
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    row = (
        f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture')).get().to_dict()
    )
    assert row['version'] == 2 and row['due_at'] == NOW


def test_two_siblings_no_immediate_notes_until_both_ready_then_one_completion_refresh(recording, monkeypatch):
    f = recording
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'synthetic-notes')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://synthetic.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    key = reprocess.key(f.binding.owner_id, 'capture')
    row = f.client.collection(reprocess.COLLECTION).document(key)
    # A later ready receipt cannot enqueue notes while the earlier one is unready.
    f.store.mark_enrichment('last', f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY) is None
    fallback = row.get().to_dict()
    assert fallback['version'] == 1 and fallback['due_at'] > NOW
    assert f.wake.call_count == 1  # Delayed fallback, never an immediate wake.
    f.store.mark_enrichment('first', f.binding, NOW + 1, 'capture', 'en', policy=POLICY)
    assert row.get().to_dict() == fallback
    assert f.store.complete('first', f.binding, NOW + 1, f.accounting, policy=POLICY)
    saved = row.get().to_dict()
    assert saved['version'] == 2 and saved['due_at'] == NOW + 1
    # The sibling's followup and a retry both replay the completed ledger.
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW + 2, 'capture', 'en', policy=POLICY)
        assert f.store.complete(sid, f.binding, NOW + 2, f.accounting, policy=POLICY)
    assert row.get().to_dict() == saved
    assert f.wake.call_count == 2


@pytest.mark.parametrize(
    'hold', ['producer', 'partial', 'failed', 'revision', 'processing', 'sync', 'merge', 'off', 'aged']
)
def test_complete_record_respects_holds_and_toggle_or_age_change(recording, monkeypatch, hold):
    f = recording
    key = reprocess.key(f.binding.owner_id, 'capture')
    row = f.client.collection(reprocess.COLLECTION).document(key)
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    patch = {
        'producer': {'record_upload_sessions': {'producer': True}},
        'partial': {'record_audio_partial': True},
        'failed': {'record_upload_failed': True},
        'revision': {'record_upload_revision': 2},
        'processing': {'sync_processing_hold': {'held': True}},
    }.get(hold, {})
    f.client.rows[f.conversation.path].update(patch)
    if hold in {'sync', 'merge'}:
        f.client.rows[row.path] = {
            'uid': f.binding.owner_id,
            'conversation_id': 'capture',
            'version': 1,
            'summary_seen': True,
            'first_pending_at': NOW,
            'due_at': NOW + 900,
            f'{hold}_hold': True,
        }
    if hold == 'off':
        monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    now = NOW + (1801 if hold == 'aged' else 1)
    assert f.store.complete('last', f.binding, now, f.accounting, policy=POLICY)
    if hold == 'aged':
        assert row.get().to_dict()['due_at'] == NOW + 120
    else:
        assert row.get().to_dict()['due_at'] > now


@pytest.mark.parametrize('end_lag,immediate', [(900, True), (3 * 86400, False)])
def test_notes_urgency_uses_recording_end_with_fresh_merge_off(recording, monkeypatch, end_lag, immediate):
    f = recording
    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', 'false')
    for sid in f.binding.segment_ids:
        f.client.rows[f.store.ref('jobs', sid).path].update(fresh_capture=False, record_finished_at=NOW - end_lag)
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert (row.get().to_dict()['due_at'] == NOW) is immediate


@pytest.mark.parametrize('sibling_state', ['held', 'dead', 'missing'])
@pytest.mark.parametrize('summary_seen', [False, True])
def test_completion_marker_has_one_durable_deadline_when_sibling_cannot_arrive(
    recording, monkeypatch, sibling_state, summary_seen
):
    f = recording
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '600')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'synthetic-notes')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://synthetic.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    if summary_seen:
        row.create(
            {
                'uid': f.binding.owner_id,
                'conversation_id': 'capture',
                'summary_seen': True,
                'first_pending_at': NOW,
                'version': 0,
                'due_at': NOW + 600,
                'task_due_at': NOW + 600,
                'task_token': 'a' * 32,
                'dispatch': reprocess.dispatch_binding(),
            }
        )
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    fallback = row.get().to_dict()
    deadline = NOW + (600 if summary_seen else 120)
    assert fallback['version'] == 1 and fallback['due_at'] == deadline
    assert fallback['task_due_at'] == deadline
    assert f.wake.call_count == (0 if summary_seen else 1)
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    if sibling_state == 'missing':
        del f.client.rows[f.store.ref('results', 'last').path]
    else:
        f.client.rows[f.store.ref('jobs', 'last').path].update(
            state='quarantined' if sibling_state == 'held' else 'dead',
            recovery_state='held',
            dead_letter_reason='held_expired',
            merge_pending=False,
        )
    assert f.store.complete('first', f.binding, deadline, f.accounting, policy=POLICY) is None
    f.store.mark_enrichment('first', f.binding, deadline + 1, 'capture', 'en', policy=POLICY)
    assert row.get().to_dict() == fallback
    assert f.ledger.get().to_dict()['record_notes_fallback_outputs'] == ['capture']


def test_flag_off_before_first_projection_uses_main_settle_without_fallback_marker(recording, monkeypatch):
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    f = recording
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert row.get().to_dict()['due_at'] == NOW + 120
    assert 'record_notes_fallback_outputs' not in f.ledger.get().to_dict()


@pytest.mark.parametrize('quiet,remaining', [(120, 0), (300, 50), (600, 350)])
def test_complete_record_uses_processing_hold_deadline_without_another_settle(recording, monkeypatch, quiet, remaining):
    f = recording
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', str(quiet))
    f.client.rows[f.conversation.path]['sync_processing_hold'] = {
        'held': True,
        'pending_since': NOW - 300,
        'last_content_at': NOW - 250,
    }
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    # First-summary policy may deliver earlier, but its consumer still checks
    # this same absolute hold deadline before making a paid call.
    assert row.get().to_dict()['due_at'] == min(NOW + remaining, NOW + 120)
    from utils.sync import processing_hold

    if remaining > 120:
        outcome, due = processing_hold.admission(f.conversation.get().to_dict(), row.get().to_dict(), now=NOW + 120)
        assert outcome == 'quiet_wait' and due == NOW + remaining
    outcome, due = processing_hold.admission(
        f.conversation.get().to_dict(),
        row.get().to_dict(),
        now=NOW + remaining,
    )
    assert due is None and outcome in {'ready', 'max_hold'}
    assert row.get().to_dict()['version'] == 2
    f.store.complete('first', f.binding, NOW + remaining + 1, f.accounting, policy=POLICY)
    assert row.get().to_dict()['version'] == 2


@pytest.mark.parametrize('notes_written', [False, True])
def test_sealed_live_record_completion_is_due_now_until_its_first_notes(recording, monkeypatch, notes_written):
    f = recording
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '600')
    f.client.rows[f.conversation.path].update(
        record_lane_owner='batch_live_v1',
        private_cloud_sync_enabled=True,
        record_projection_revision=1,
        sync_processing_hold={'held': True, 'pending_since': NOW - 30, 'last_content_at': NOW - 20},
        **({'summary_completed_at': NOW - 60} if notes_written else {}),
    )
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    # Unit 1 projected, its sibling still pending: completion cannot run, nothing is due now.
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('first', f.binding, NOW, f.accounting, policy=POLICY) is None
    assert row.get().to_dict()['due_at'] == NOW + 120
    f.store.mark_enrichment('last', f.binding, NOW, 'capture', 'en', policy=POLICY)
    counted = Mock()
    monkeypatch.setattr(capture_end, 'record_proof', counted)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    # Every unit landed: no quiet wait. After notes, a phone copy keeps it.
    assert row.get().to_dict()['due_at'] == (NOW + 120 if notes_written else NOW)
    assert counted.call_args_list == ([] if notes_written else [(('sealed',),)])


@pytest.mark.parametrize('hold', ['sync_hold', 'merge_hold'])
def test_complete_record_preserves_existing_outbox_hold_without_renewing_quiet(recording, monkeypatch, hold):
    f = recording
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '300')
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    f.client.rows[row.path].update(
        {hold: True, 'due_at': NOW + 40, 'first_pending_at': NOW - 260, 'summary_seen': True}
    )
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    saved = row.get().to_dict()
    assert saved['due_at'] == NOW + 40
    assert saved[hold] is True and saved['version'] == 2


def test_hold_scheduling_does_not_inspect_encrypted_projection_content(recording, monkeypatch):
    f = recording
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '120')
    f.client.rows[f.conversation.path].update(
        transcript_segments='encrypted-envelope',
        sync_processing_hold={
            'held': True,
            'pending_since': NOW - 300,
            'last_content_at': NOW - 250,
            'full_snapshot': {'digest': 'prior-content'},
        },
    )
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert row.get().to_dict()['due_at'] == NOW


@pytest.mark.parametrize('hold', ['sync_hold', 'merge_hold'])
def test_dormant_summary_receipt_does_not_preserve_retired_hold_deadline(recording, hold):
    f = recording
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    row.create(
        {
            'dormant': True,
            'summary_seen': True,
            'due_at': None,
            'version': 1,
            'first_pending_at': NOW - 1000,
            hold: True,
        }
    )
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    saved = row.get().to_dict()
    assert not saved.get('dormant') and saved['due_at'] == NOW + 600
    assert saved['record_notes_producers'] == {'capture': 1}


def test_held_refresh_completion_moves_an_earlier_fallback_to_canonical_deadline(recording, monkeypatch):
    f = recording
    monkeypatch.setenv('SYNC_PROCESSING_QUIET_SECONDS', '600')
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    f.client.rows[row.path].update(summary_seen=True, due_at=NOW + 600, sync_hold=False)
    f.client.rows[f.conversation.path]['sync_processing_hold'] = {
        'held': True,
        'pending_since': NOW,
        'last_content_at': NOW + 50,
    }
    f.store.mark_enrichment('last', f.binding, NOW + 50, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW + 50, f.accounting, policy=POLICY)
    assert row.get().to_dict()['due_at'] == NOW + 650
    assert row.get().to_dict()['sync_hold'] is True


@pytest.mark.parametrize('recording', [3], indirect=True)
@pytest.mark.parametrize('recovery', ['failed_held', 'disabled'])
def test_terminal_record_unit_allows_suffix_to_merge_and_complete_partial(recording, recovery, monkeypatch):
    monkeypatch.setenv('RECORD_FRESH_MERGE_ENABLED', 'true')
    from database.batch_pipeline_projection import held_without_recovery
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.contracts import WorkResult

    f = recording
    memory = MemoryStore()
    queue = Scheduler(memory)
    for i, sid in enumerate(f.binding.segment_ids):
        work = WorkItem(sid, f.binding.owner_id, NOW - 100 + i, 'gs://synthetic/audio', 4, Priority.FRESH)
        queue.enqueue(work, NOW)
        memory.rows['jobs', sid].update(
            projection_binding=asdict(f.binding),
            fresh_capture=True,
            state='result_ready',
            result=WorkResult(sid, 'gs://synthetic/result').to_dict(),
            ready_at=NOW,
        )
    terminal = {
        'state': 'quarantined',
        'merge_pending': False,
        'result': None,
        'recovery_state': 'failed_held' if recovery == 'failed_held' else 'held',
        'policy_parts': {'recovery': {'recovery_enabled': False}},
    }
    assert held_without_recovery(terminal)
    memory.rows['jobs', 'first'].update(terminal)
    f.client.rows[f.store.ref('jobs', 'first').path].update(terminal)
    del f.client.rows[f.store.ref('results', 'first').path]
    merge = OrderedMerge(memory)
    for sid in f.binding.segment_ids[1:]:
        assert merge.commit_next(f.binding.owner_id, NOW)['segment_id'] == sid
        f.client.rows[f.store.ref('jobs', sid).path]['state'] = 'committed'
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
    result, _ = f.store.complete_partial(f.binding, NOW, f.accounting)
    assert result['outcome'] == 'partial' and result['held_segments'] == 1
    assert result['total_segments'] == 3

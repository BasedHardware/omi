"""A sealed recording produces one notes obligation after all sibling receipts."""

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
from utils.sync import reprocess

NOW = 100_000.0
POLICY = ProjectionPolicy()


@pytest.fixture
def recording(monkeypatch, request):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
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
def test_complete_binding_has_one_outbox_revision_independent_of_sibling_count(recording):
    f = recording
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    # Each newly projected unit tries content completion. None may dispatch
    # notes for the partial transcript, including the maximum-size binding.
    for index, sid in enumerate(f.binding.segment_ids):
        f.store.mark_enrichment(sid, f.binding, NOW, 'capture', 'en', policy=POLICY)
        result = f.store.complete(sid, f.binding, NOW, f.accounting, policy=POLICY)
        if index + 1 < len(f.binding.segment_ids):
            assert result is None and not row.get().exists
    assert result and row.get().to_dict()['version'] == 1
    f.store.complete(sid, f.binding, NOW + 1, f.accounting, policy=POLICY)
    assert row.get().to_dict()['version'] == 1


def test_siblings_keep_completion_owner_across_age_and_switch_changes(recording, monkeypatch):
    f = recording
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY)
    monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    later = NOW + 1801
    f.store.mark_enrichment('last', f.binding, later, 'capture', 'en', policy=POLICY)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert not row.get().exists
    assert f.store.complete('last', f.binding, later, f.accounting, policy=POLICY)
    assert row.get().to_dict()['version'] == 1 and row.get().to_dict()['due_at'] > later


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
        assert ref.get().to_dict()['version'] == 1
    assert f.store.complete('first', f.binding, NOW + 1, f.accounting, policy=POLICY)
    assert all(data.get('version') == 1 for path, data in f.client.rows.items() if path[0] == reprocess.COLLECTION)


def test_two_siblings_no_notes_until_both_ready_then_one_durable_refresh(recording, monkeypatch):
    f = recording
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'synthetic-notes')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://synthetic.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    key = reprocess.key(f.binding.owner_id, 'capture')
    row = f.client.collection(reprocess.COLLECTION).document(key)
    # A later ready receipt cannot enqueue notes while the earlier one is unready.
    f.store.mark_enrichment('last', f.binding, NOW, 'capture', 'en', policy=POLICY)
    assert f.store.complete('last', f.binding, NOW, f.accounting, policy=POLICY) is None
    assert not row.get().exists
    f.wake.assert_not_called()
    f.store.mark_enrichment('first', f.binding, NOW + 1, 'capture', 'en', policy=POLICY)
    assert not row.get().exists
    assert f.store.complete('first', f.binding, NOW + 1, f.accounting, policy=POLICY)
    saved = row.get().to_dict()
    assert saved['version'] == 1 and saved['due_at'] == NOW + 1
    # The sibling's followup and a retry both replay the completed ledger.
    for sid in f.binding.segment_ids:
        f.store.mark_enrichment(sid, f.binding, NOW + 2, 'capture', 'en', policy=POLICY)
        assert f.store.complete(sid, f.binding, NOW + 2, f.accounting, policy=POLICY)
    assert row.get().to_dict() == saved
    assert f.wake.call_count == 1


@pytest.mark.parametrize('hold', ['producer', 'partial', 'failed', 'processing', 'sync', 'merge', 'off', 'aged'])
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
        'processing': {'sync_processing_hold': {'held': True}},
    }.get(hold, {})
    f.client.rows[f.conversation.path].update(patch)
    if hold in {'sync', 'merge'}:
        row.create(
            {
                'uid': f.binding.owner_id,
                'conversation_id': 'capture',
                'version': 1,
                'summary_seen': True,
                'first_pending_at': NOW,
                'due_at': NOW + 900,
                f'{hold}_hold': True,
            }
        )
    if hold == 'off':
        monkeypatch.setenv('RECORD_NOTES_EAGER_ENABLED', 'false')
    now = NOW + (1801 if hold == 'aged' else 1)
    assert f.store.complete('last', f.binding, now, f.accounting, policy=POLICY)
    assert row.get().to_dict()['due_at'] > now

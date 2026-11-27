"""Run the Finish read and race proofs with the loopback Firestore emulator."""

import os
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config.policy import ProjectionPolicy
from config.record_audio import record_identity
from database import batch_pipeline_projection as completion
from database import conversations_v3_live as store
from database.batch_pipeline_store import FirestoreStore
from database.sync_ledger import sync_content_ledger_ref
from tests.integration.test_server_batch_completion_emulator import assert_deltas
from tests.integration.test_server_batch_completion_emulator import seeded as server_batch_completion
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.v3 import live
from utils.conversations.v3.policy import NATIVE_MANUAL_STOP


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    endpoint = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{endpoint}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires the loopback Firestore emulator')
    client = firestore.Client(project=os.getenv('GCLOUD_PROJECT', 'demo-listen'), credentials=AnonymousCredentials())
    uid = uuid4().hex
    try:
        yield client, uid, client.collection('users').document(uid).collection('conversations')
    finally:
        client.close()


def test_native_finish_keeps_stop_intent_and_settles_capture_status(server_batch_completion):
    _, row, job, projection, baseline, _, complete = server_batch_completion
    finished_at = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    row.update({'recording': True, 'finished_at': finished_at, 'finalization_status': 'queued'})
    job.update({'processing_trigger': ProcessingTrigger.CLIENT_FINALIZE.value})

    assert complete() == complete() == 'completed'
    result = row.get().to_dict()
    assert result['finalization_status'] == 'completed'
    assert result[NATIVE_MANUAL_STOP] == {'job_id': job.id, 'revision': 1, 'finished_at': finished_at}
    assert result['home_transcription_pending_at'] is not None
    assert_deltas(projection, baseline, leased=-1, completed=1, success=1)


def test_recent_source_query_ranges_orders_projects_and_limits(owner):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    for index in reversed(range(store.RECENT_FINISH_LIMIT + 2)):
        recordings.document(f'source-{index}').set(
            {
                'finished_at': now - timedelta(seconds=index),
                'external_data': {'recording_session_id': f'listen-{index}', 'not_projected': True},
                'transcript_segments': [{'text': 'synthetic'}],
            }
        )
    recordings.document('old').set({'finished_at': now - store.RECENT_FINISH_AGE - timedelta(seconds=1)})
    recordings.document('missing_clock').set({'recording': True})
    client.collection('users').document(uid + '-other').collection('conversations').document('foreign').set(
        {'finished_at': now}
    )

    @firestore.transactional
    def scan(tx):
        return store._recent_finish_sources(recordings, tx, now)

    snapshots = scan(client.transaction())
    assert [row.id for row in snapshots] == [f'source-{index}' for index in range(store.RECENT_FINISH_LIMIT)]
    assert snapshots[0].to_dict() == {'finished_at': now, 'external_data': {'recording_session_id': 'listen-0'}}

    # A later logical clock places source-0 exactly on the inclusive cutoff.
    now += store.RECENT_FINISH_AGE
    assert [row.id for row in scan(client.transaction())] == ['source-0']


def _recording(now):
    return {
        'created_at': now - timedelta(seconds=30),
        'started_at': now - timedelta(seconds=30),
        'finished_at': now,
        'recording': True,
        'status': 'completed',
        'source': 'omi',
        'external_data': {'recording_session_id': 'test-listen'},
        'has_content': True,
        'v3_pending': True,
        'v3_speech_landed_at': now,
    }


def _window(end, *, is_live):
    return {
        'started_at': end - timedelta(minutes=1),
        'finished_at': end,
        'v3_derived': True,
        'status': 'in_progress' if is_live else 'completed',
        'tile_state': 'live' if is_live else 'done',
    }


@pytest.mark.parametrize('window_age', [timedelta(minutes=30), live.MAX_IDLE + timedelta(minutes=1)])
def test_finish_rechecks_window_inserted_after_initial_lookup(owner, window_age):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    recording = recordings.document('recent-source')
    recording.set(_recording(now))
    assert store.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active, firestore_client=client) is None

    producer = firestore.Client(project=client.project, credentials=AnonymousCredentials())
    try:
        window = producer.collection('users').document(uid).collection('conversations').document('projected-window')
        window.set(_window(now - window_age, is_live=True))
    finally:
        producer.close()

    outcome, _ = store.request_recording_finish(uid, now=now, firestore_client=client)
    current = recording.get().to_dict()
    if window_age < live.MAX_IDLE:
        assert outcome == 'no_live_window'
        assert live.FINISH_RECORDING_FIELD not in current
        assert 'v3_manual_end_requested' not in current and 'v3_manual_end' not in current
    else:
        assert outcome == 'recording_cut'
        assert current[live.FINISH_RECORDING_FIELD] and current['v3_manual_end']


def test_finish_declines_when_transactional_window_lookup_reaches_its_bound(owner, monkeypatch):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(store, 'READ_CAP', 2)
    source = recordings.document('recent-source')
    source.set(_recording(now))
    for minutes in (30, 31):
        recordings.document(f'finished-window-{minutes}').set(_window(now - timedelta(minutes=minutes), is_live=False))

    outcome, recording = store.request_recording_finish(uid, now=now, firestore_client=client)
    assert (outcome, recording) == ('window_lookup_capped', None)
    assert live.FINISH_RECORDING_FIELD not in source.get().to_dict()


def _pending_native_finish(owner, monkeypatch, unit_count, *, receipt_id, outcome='success'):
    client, uid, recordings = owner
    client.collection('users').document(uid).set({'data_protection_level': 'standard'})
    monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'on')
    monkeypatch.setattr(completion, 'writing', lambda *_: nullcontext())
    monkeypatch.setattr(completion, 'record_notes_eager_enabled', lambda: False)
    monkeypatch.setattr(completion.capture_end, 'enabled', lambda: False)
    counter, enqueue = Mock(), Mock()
    monkeypatch.setattr(completion.v3_metrics, 'FINISH_NO_POINTER', counter)
    monkeypatch.setattr(completion.v3_triggers, 'enqueue_pending', enqueue)

    now = datetime.now(timezone.utc)
    source = recordings.document('capture')
    source.set(
        {
            **_recording(now),
            'id': source.id,
            'record_lane_owner': 'batch_live_v1',
            'server_batch_only': True,
            'private_cloud_sync_enabled': True,
            'structured': {},
            'discarded': False,
            'data_protection_level': 'standard',
            'server_batch_audio_start': now.timestamp() - 30,
            'server_batch_audio_end': now.timestamp(),
        }
    )
    assert store.request_recording_finish(uid, now=now, firestore_client=client)[0] == 'recording_requested'

    namespace = f'batch_pipeline_test_{uuid4().hex}'
    projector = completion.ProjectionStore(FirestoreStore(namespace, firestore_client=client))
    monkeypatch.setattr(projector, '_observe_transcription', Mock())
    monkeypatch.setattr(projector, '_settle_allowance', Mock())
    content, first = record_identity(uid, source.id)
    ids = (first, *(f'{first}-{unit}' for unit in range(1, unit_count)))
    binding = ProjectionBinding(
        uid, 'bp_' + content, content, ids, target_conversation_id=source.id, record_origin=True, native_record=True
    )
    ledger = sync_content_ledger_ref(client, uid, content)
    ledger.set(
        {
            'status': 'processing',
            'dispatch_protocol': 'batch_v1',
            'job_id': binding.job_id,
            'batch_pipeline': {'protocol_version': 1, 'namespace': namespace, 'segment_ids': list(ids)},
        }
    )
    result = {'outcome': outcome}
    for sid in ids:
        projector.ref('jobs', sid).set(
            {
                'projection_binding': asdict(binding),
                'owner_id': uid,
                'privacy_generation': binding.privacy_generation,
                'capture_at': now.timestamp(),
                'duration_seconds': 30,
                'result': result,
            }
        )
        projector.ref('results', sid).set(
            {
                'protocol_version': 1,
                'segment_id': sid,
                'owner_key': owner_key(uid),
                'capture_at': now.timestamp(),
                'previous_segment_id': None,
                'result': result,
                'projection': {
                    'state': 'ready',
                    'conversation_id': receipt_id,
                    'created': False,
                    'speech_seconds': float(outcome == 'success'),
                },
            }
        )

    def complete():
        seconds = float(unit_count) if outcome == 'success' else 0.0
        return projector.complete(
            first, binding, now.timestamp(), {'seconds': seconds, 'updates': {}}, policy=ProjectionPolicy()
        )

    return complete, source, ledger, counter, enqueue


@pytest.mark.parametrize('unit_count', [1, 2])
@pytest.mark.parametrize('receipt_already_canonical', [False, True])
def test_whole_native_completion_resolves_finish_on_redirect_donor(
    owner, monkeypatch, unit_count, receipt_already_canonical
):
    _, _, recordings = owner
    complete, source, ledger, counter, enqueue = _pending_native_finish(
        owner, monkeypatch, unit_count, receipt_id='survivor' if receipt_already_canonical else 'capture'
    )
    source.update({'deleted': True, 'discarded': True, 'sync_merged_into': 'survivor'})
    survivor = recordings.document('survivor')
    survivor.set(_recording(datetime.now(timezone.utc) + timedelta(minutes=1)))
    survivor_row = survivor.get().to_dict()

    for _ in range(2):
        assert complete()['updated_memories'] == [survivor.id]
    assert ledger.get().to_dict()['status'] == 'completed'
    donor = source.get().to_dict()
    assert donor['v3_manual_end_requested'] is False and 'v3_manual_end' not in donor
    assert survivor.get().to_dict() == survivor_row
    counter.labels.assert_called_once_with('whole_record_redirected')
    counter.labels.return_value.inc.assert_called_once_with()
    enqueue.assert_not_called()


@pytest.mark.parametrize('outcome', ['silence', 'no_recoverable_speech'])
def test_whole_native_completion_counts_async_empty_finish_once(owner, monkeypatch, outcome):
    complete, source, ledger, counter, enqueue = _pending_native_finish(
        owner, monkeypatch, 2, receipt_id=None, outcome=outcome
    )
    source.update({'has_content': False, 'record_projection_revision': 2})
    for _ in range(2):
        assert complete() is not None

    assert ledger.get().to_dict()['status'] == 'completed'
    stored = source.get().to_dict()
    assert stored['v3_manual_end_requested'] is False
    assert stored['recording'] and not stored['discarded'] and 'v3_manual_end' not in stored
    counter.labels.assert_called_once_with('whole_record_resolved_empty')
    counter.labels.return_value.inc.assert_called_once_with()
    enqueue.assert_not_called()


def _claimed(window_id, end, **fields):
    row = _recording(end)
    row.update(claims=[{'conversation_id': window_id, 'start': end - timedelta(seconds=30), 'end': end}], **fields)
    return row


def test_named_finish_cuts_the_capture_that_sealed_after_the_named_window(owner):
    """A seals and its window ends; B seals 2 min later into a window hidden under the word floor."""
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    end_a, end_b = now - timedelta(minutes=2), now - timedelta(seconds=5)
    recordings.document('capture-a').set(_claimed('window-a', end_a))
    recordings.document('capture-b').set(_claimed('window-b', end_b))
    recordings.document('window-a').set(
        {
            **_window(end_a, is_live=False),
            'status': 'processing',
            'tile_state': 'writing',
            'v3_recording_ids': ['capture-a'],
        }
    )
    recordings.document('window-b').set(
        {**_window(end_b, is_live=True), 'home_hidden': True, 'v3_recording_ids': ['capture-b']}
    )
    assert store.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active, firestore_client=client) is None

    outcome, response, recording_id = store.request_named_finish(uid, 'window-a', now=now, firestore_client=client)

    assert (outcome, response['id'], recording_id) == ('named_recording_cut', 'window-b', 'capture-b')
    b = recordings.document('capture-b').get().to_dict()
    assert b['v3_manual_end'] and b['v3_pending'] and b[live.FINISH_WINDOW_FIELD] == 'window-b'
    a = recordings.document('capture-a').get().to_dict()
    assert 'v3_manual_end' not in a and live.FINISH_WINDOW_FIELD not in a


def test_named_finish_leaves_completed_visible_window_unwritten(owner):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    recordings.document('capture-a').set(_claimed('window-a', now))
    card = {'title': 'Morning standup', 'overview': 'Planned the release train.', 'emoji': '🗓️'}
    recordings.document('window-a').set(
        {**_window(now, is_live=False), 'v3_recording_ids': ['capture-a'], 'structured': card, 'starred': True}
    )

    outcome, response, _ = store.request_named_finish(uid, 'window-a', now=now, firestore_client=client)

    assert (outcome, response['id']) == ('already_visible', 'window-a')
    assert {key: response['structured'][key] for key in card} == card and response['starred'] is True
    assert 'v3_manual_end' not in recordings.document('capture-a').get().to_dict()


def _named_window_with_sealed_tail(recordings, end):
    recordings.document('capture-a').set(_claimed('window-a', end))
    recordings.document('window-a').set(
        {
            **_window(end, is_live=False),
            'status': 'processing',
            'tile_state': 'writing',
            'v3_recording_ids': ['capture-a'],
        }
    )


@pytest.mark.parametrize('speech', [False, True])
def test_named_finish_ignores_in_progress_successor(owner, speech):
    """A speech-pause rotation writes the next capture in progress, with a later clock, before A seals."""
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    end_a = now - timedelta(seconds=10)
    _named_window_with_sealed_tail(recordings, end_a)
    successor = {
        'created_at': end_a + timedelta(seconds=2),
        'started_at': end_a + timedelta(seconds=2),
        'finished_at': end_a + timedelta(seconds=2),
        'status': 'in_progress',
        'source': 'omi',
        'external_data': {'recording_session_id': 'next-listen'},
    }
    if speech:
        successor.update(recording=True, has_content=True, v3_pending=True, v3_speech_landed_at=end_a)
    recordings.document('capture-next').set(successor)

    outcome, response, recording_id = store.request_named_finish(uid, 'window-a', now=now, firestore_client=client)

    assert (outcome, response['id'], recording_id) == ('named_recording_cut', 'window-a', 'capture-a')
    assert recordings.document('capture-a').get().to_dict()['v3_manual_end']
    assert 'v3_manual_end' not in recordings.document('capture-next').get().to_dict()


def test_named_finish_declines_two_sealed_captures_tied_after_the_named_one(owner):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    end_a, end_b = now - timedelta(minutes=2), now - timedelta(seconds=5)
    _named_window_with_sealed_tail(recordings, end_a)
    for name in ('capture-b', 'capture-c'):
        recordings.document(name).set(
            {**_recording(end_b), 'external_data': {'recording_session_id': f'{name}-listen'}}
        )

    assert store.request_named_finish(uid, 'window-a', now=now, firestore_client=client) == (
        'recording_ambiguous',
        None,
        '',
    )
    for name in ('capture-a', 'capture-b', 'capture-c'):
        assert 'v3_manual_end' not in recordings.document(name).get().to_dict()

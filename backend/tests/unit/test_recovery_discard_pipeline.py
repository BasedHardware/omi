"""Encoded recovery reads through worker termination and next-tick verification."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversations as conversations_db, conversation_finalization_jobs as jobs_db
from database import redis_db
from models.structured import Structured
from routers import conversation_finalization as worker
from services import conversation_selfheal as selfheal
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreTransaction,
)
from utils import encryption
from utils.conversations import finalizer, lifecycle
from utils.conversations.recovery import raw_transcript_bytes

pc = importlib.import_module('utils.conversations.process_conversation')
UID, CID, JOB = 'recovery-user', 'recovery-conversation', 'recovery-job'
CONVERSATION_PATH = ('users', UID, 'conversations', CID)
JOB_PATH = (jobs_db.FINALIZATION_JOBS_COLLECTION, JOB)
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


async def _inline(_executor, function, *args, **kwargs):
    return function(*args, **kwargs)


@pytest.fixture
def pipeline(monkeypatch):
    store = StrictFirestore()
    # Keep the fixture's reference ownership and read-before-write enforcement.
    # This boundary also needs Firestore's merge=True document-set semantics.
    original_set = StrictFirestoreTransaction.set
    writes = []

    def merge_set(transaction, ref, data, *, merge=False):
        writes.append((ref.path, deepcopy(data)))
        payload = {**store.rows.get(ref.path, {}), **data} if merge else data
        original_set(transaction, ref, payload)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', merge_set)
    monkeypatch.setattr(StrictFirestoreDocument, 'id', property(lambda ref: ref.path[-1]), raising=False)
    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(jobs_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(jobs_db, '_now', lambda: NOW)
    monkeypatch.setattr(jobs_db, '_record_projection_delta', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(redis_db, 'get_user_data_protection_level', lambda uid: 'enhanced')
    monkeypatch.setattr(lifecycle, 'observe_completed_conversation_shape', lambda *args: None)
    monkeypatch.setenv('LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED', 'true')
    monkeypatch.setattr(worker, 'run_blocking', _inline)
    monkeypatch.setattr(finalizer, 'run_blocking', _inline)
    monkeypatch.setattr(worker, 'try_acquire_job_run_lock', lambda key: 'lock')
    monkeypatch.setattr(worker, 'release_job_run_lock', lambda *args: None)
    monkeypatch.setattr(worker, 'should_skip_background_account_mutation', lambda *args, **kwargs: False)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *args: None)
    monkeypatch.setattr(pc, 'is_release_probe_uid', lambda uid: False)
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda uid: False)
    monkeypatch.setattr(pc, '_enrich_meeting_context', lambda *args: None)
    monkeypatch.setattr(pc, 'resolve_speakers_for_processing', lambda *args: False)
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(pc, 'has_structural_wake_word_marker', lambda text: False)
    monkeypatch.setattr(pc, '_calendar_overlap_retains_conversation', lambda *args: False)
    monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: False)
    monkeypatch.setattr(pc, 'conversation_transcripts_for_llm', lambda *args: ('', '', {}))
    # Restored rows may attempt structuring; a minimum must still terminalize
    # visibly, rather than persisting an incoherent discard/keep combination.
    paid_notes = MagicMock(return_value=Structured())
    monkeypatch.setattr(pc, 'get_reprocess_transcript_structure', paid_notes)
    monkeypatch.setattr(pc, 'get_conversation_notes', paid_notes)
    monkeypatch.setattr(pc, 'extract_action_items', lambda *args, **kwargs: [])
    monkeypatch.setattr(pc, '_fetch_dedup_candidates', lambda *args: [])
    monkeypatch.setattr(pc, '_primary_user_name', lambda uid: None)
    decisions = []
    decide = pc.decide_relevance

    def observe_decision(**kwargs):
        result = decide(**kwargs)
        decisions.append(result)
        return result

    monkeypatch.setattr(pc, 'decide_relevance', observe_decision)
    # Any escaped derived effect is a regression, including on a raced edit.
    for name in ('extract_memories', 'trigger_external_integrations', 'smart_merge_step'):
        monkeypatch.setattr(finalizer, name, MagicMock(side_effect=AssertionError('derived effect escaped')))

    return SimpleNamespace(store=store, writes=writes, paid_notes=paid_notes, decisions=decisions)


def _seed(pipeline, *, level='enhanced', transcript=None, **overrides):
    row = {
        'id': CID,
        'status': 'processing',
        'source': 'omi',
        'created_at': NOW - timedelta(days=30),
        'started_at': NOW - timedelta(days=30),
        'finished_at': NOW - timedelta(days=30),
        'structured': {'title': '', 'overview': ''},
        'transcript_segments': transcript or [],
        'has_photos': False,
        'audio_files': [{'id': 'audio-1', 'uid': UID, 'conversation_id': CID, 'chunk_timestamps': [], 'duration': 1}],
        'discarded': False,
        'finalization_job_id': JOB,
        'finalization_revision': 1,
        **overrides,
    }
    encoded = conversations_db.encode_conversation_for_write(UID, row, level=level)
    encoded['data_protection_level'] = level
    pipeline.store.rows[CONVERSATION_PATH] = encoded
    pipeline.store.rows[JOB_PATH] = {
        'uid': UID,
        'conversation_id': CID,
        'status': 'queued',
        'dispatch_generation': 1,
        'finalization_revision': 1,
        'processing_trigger': 'server_recovery',
        'created_at': NOW,
        'selfheal_transcript_bytes': raw_transcript_bytes(encoded),
        'selfheal_audio_file_ids': ['audio-1'],
    }
    return encoded['transcript_segments']


async def _run_and_verify(pipeline):
    async def payload():
        return {'job_id': JOB, 'dispatch_generation': 1}

    response = await worker.run_listen_finalization_job(SimpleNamespace(json=payload), task_retry_count=0)
    assert response.status_code == 200
    counters = {'verified': 0, 'refused': 0, 'errors': 0, 'skipped': 0}
    remaining = selfheal._verify_pending_attempts(
        [{'uid': UID, 'conversation_id': CID, 'job_id': JOB}],
        firestore_client=pipeline.store,
        conversation_reader=conversations_db.get_conversation_raw_snapshot,
        counters=counters,
    )
    assert remaining == []
    return json.loads(response.body), counters


@pytest.mark.asyncio
@pytest.mark.parametrize('level', ['enhanced', 'standard'])
@pytest.mark.parametrize('text', ['', 'hmm'])
async def test_decoded_rule_discard_completes_and_verifies_without_rewriting_blob(pipeline, level, text):
    transcript = [{'text': text, 'start': 0, 'end': 1, 'speaker': 'SPEAKER_00', 'is_user': False}] if text else []
    blob = _seed(pipeline, level=level, transcript=transcript)
    response, counters = await _run_and_verify(pipeline)
    row, job = pipeline.store.rows[CONVERSATION_PATH], pipeline.store.rows[JOB_PATH]
    assert response == {'status': 'done'}
    assert row['status'] == job['status'] == 'completed'
    assert row['discarded'] is True
    assert row['relevance_decision']['trigger'] == 'server_recovery'
    assert row['relevance_decision']['verdict'] == 'discard'
    assert row['transcript_segments'] == blob
    assert row['transcript_segments_compressed'] is True
    assert row['data_protection_level'] == level
    assert counters == {'verified': 1, 'refused': 0, 'errors': 0, 'skipped': 0}
    pipeline.paid_notes.assert_not_called()
    for path, data in pipeline.writes:
        if path == CONVERSATION_PATH:
            assert 'transcript_segments' not in data
            assert 'transcript_segments_compressed' not in data
            assert 'data_protection_level' not in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'corruption', ['encrypted_garbage', 'non_list_json', 'invalid_utf8', 'standard_garbage', 'plaintext_payload']
)
async def test_decode_failure_preserves_blob_and_uses_existing_terminal_path(pipeline, corruption, capsys):
    import zlib

    _seed(pipeline, level='standard' if corruption == 'standard_garbage' else 'enhanced')
    if corruption == 'non_list_json':
        blob = encryption.encrypt(zlib.compress(b'{"not": "segments"}').hex(), UID)
    elif corruption == 'invalid_utf8':
        blob = encryption.encrypt(zlib.compress(b'\xff').hex(), UID)
    elif corruption == 'standard_garbage':
        blob = b'invalid compressed transcript' * 10
    elif corruption == 'plaintext_payload':
        blob = zlib.compress(b'[]').hex()  # parseable decrypt fallback still failed authentication
    else:
        blob = 'unreadable encrypted transcript' * 10
    row = pipeline.store.rows[CONVERSATION_PATH]
    row['transcript_segments'] = blob
    pipeline.store.rows[JOB_PATH]['selfheal_transcript_bytes'] = raw_transcript_bytes(row)
    response, counters = await _run_and_verify(pipeline)
    assert response == {'status': 'dead_letter'}
    assert row['transcript_segments'] == blob
    assert row['status'] == 'completed' and row['discarded'] is False
    assert 'relevance_decision' not in row
    assert pipeline.store.rows[JOB_PATH]['last_failure_code'] == 'recovery_structure_unavailable'
    assert counters['verified'] == 0 and counters['refused'] == 1
    assert 'verify_not_rich' not in capsys.readouterr().out
    pipeline.paid_notes.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'protection',
    [
        {'user_title': 'My recording'},
        {'structured': {'title': 'Existing generated title'}},
        {'structured': {'overview': 'Saved notes'}},
        {'structured': {'sections': [{'title': 'Saved section'}]}},
        {'structured': {'action_items': [{'description': 'Saved task'}]}},
        {'structured': {'events': [{'title': 'Saved event'}]}},
        {'sync_relevance_user_kept': True},
    ],
)
async def test_post_read_protection_refuses_discard_transactionally(pipeline, monkeypatch, protection, capsys):
    blob = _seed(pipeline)
    persist = lifecycle.persist_processed_conversation

    def raced_persist(uid, data, **kwargs):
        pipeline.store.rows[CONVERSATION_PATH].update(deepcopy(protection))
        return persist(uid, data, **kwargs)

    monkeypatch.setattr(lifecycle, 'persist_processed_conversation', raced_persist)
    response, counters = await _run_and_verify(pipeline)
    row = pipeline.store.rows[CONVERSATION_PATH]
    assert response == {'status': 'dead_letter'}
    assert row['status'] == 'completed' and row['discarded'] is False
    assert row['transcript_segments'] == blob
    assert 'relevance_decision' not in row
    assert all(row[key] == value for key, value in protection.items())
    assert counters['verified'] == 0 and counters['refused'] == 1
    events = capsys.readouterr().out
    assert '"reason": "dead_letter"' in events and 'verify_not_rich' not in events
    assert not any(path == CONVERSATION_PATH for path, _ in pipeline.writes)


@pytest.mark.asyncio
async def test_restore_before_finalizer_read_never_decides_discard(pipeline, capsys):
    blob = _seed(pipeline, sync_relevance_user_kept=True)
    response, counters = await _run_and_verify(pipeline)
    row = pipeline.store.rows[CONVERSATION_PATH]
    assert response == {'status': 'dead_letter'}  # kept minimum, existing terminal policy
    assert row['discarded'] is False and row['sync_relevance_user_kept'] is True
    assert row['transcript_segments'] == blob and 'relevance_decision' not in row
    assert pipeline.decisions and all(not decision.discard for decision in pipeline.decisions)
    assert counters['refused'] == 1 and 'verify_not_rich' not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_title_added_while_job_is_queued_remains_visible(pipeline, capsys):
    blob = _seed(pipeline, user_title='Title added after admission')
    response, counters = await _run_and_verify(pipeline)
    row = pipeline.store.rows[CONVERSATION_PATH]
    assert response == {'status': 'dead_letter'}
    assert row['status'] == 'completed' and row['discarded'] is False
    assert row['user_title'] == 'Title added after admission'
    assert row['transcript_segments'] == blob and 'relevance_decision' not in row
    assert counters['refused'] == 1 and 'verify_not_rich' not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_blob_corrupted_after_read_cannot_commit_discard(pipeline, monkeypatch, capsys):
    _seed(pipeline)
    persist = lifecycle.persist_processed_conversation
    corrupted = 'corrupt after processing read' * 10

    def raced_persist(uid, data, **kwargs):
        pipeline.store.rows[CONVERSATION_PATH]['transcript_segments'] = corrupted
        return persist(uid, data, **kwargs)

    monkeypatch.setattr(lifecycle, 'persist_processed_conversation', raced_persist)
    response, counters = await _run_and_verify(pipeline)
    row = pipeline.store.rows[CONVERSATION_PATH]
    assert response == {'status': 'dead_letter'}
    assert row['status'] == 'completed' and row['discarded'] is False
    assert row['transcript_segments'] == corrupted and 'relevance_decision' not in row
    assert counters['refused'] == 1 and 'verify_not_rich' not in capsys.readouterr().out


def test_decode_status_is_opt_in_and_not_written(pipeline):
    _seed(pipeline)
    assert '_recovery_transcript_decoded' not in conversations_db.get_conversation(UID, CID)
    checked = conversations_db.get_conversation(UID, CID, include_transcript_decode_status=True)
    assert checked['_recovery_transcript_decoded'] is True
    assert checked['transcript_segments'] == []
    assert '_recovery_transcript_decoded' not in pipeline.store.rows[CONVERSATION_PATH]


@pytest.mark.asyncio
async def test_rule_discard_keeps_stored_speaker_metadata_with_its_transcript(pipeline, monkeypatch):
    """Resolution runs before relevance; a discard that keeps the stored
    transcript must also keep the speaker metadata describing it."""
    from models.conversation import ConversationSpeakers

    stored = {'status': 'capture', 'version': 1, 'participant_speaker_ids': [7]}
    transcript = [{'text': 'hmm', 'start': 0, 'end': 1, 'speaker': 'SPEAKER_07', 'speaker_id': 7, 'is_user': False}]

    def resolve(uid, conversation):
        conversation.speaker_resolution = ConversationSpeakers(
            status='resolved', participant_speaker_ids=[7, 100, 101, 102]
        )
        return False

    monkeypatch.setattr(pc, 'resolve_speakers_for_processing', resolve)
    _seed(pipeline, transcript=transcript, speaker_resolution=stored)
    response, counters = await _run_and_verify(pipeline)
    row = pipeline.store.rows[CONVERSATION_PATH]
    assert response == {'status': 'done'}
    assert row['discarded'] is True
    assert row['speaker_resolution'] == stored
    assert counters['verified'] == 1
    for path, data in pipeline.writes:
        if path == CONVERSATION_PATH:
            assert 'speaker_resolution' not in data

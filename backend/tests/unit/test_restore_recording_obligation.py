"""Explicit restore repairs sealed recording debt through canonical registration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from config.policy import BatchUnitPolicy
from config.record_audio import record_identity
from database import batch_pipeline_privacy, batch_pipeline_store
from database import conversations as conversations_db
from database import processing_attention as attention_db
from database.batch_pipeline_store import FirestoreStore
from routers import conversations as conversations_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import live
from utils.conversations import lifecycle

UID, CID = 'synthetic', 'capture'
ROW_PATH = ('users', UID, 'conversations', CID)
_, SEGMENT = record_identity(UID, CID)
JOB_PATH = ('batch_pipeline_dev_jobs', SEGMENT)


@pytest.fixture
def restore_store(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(batch_pipeline_privacy, 'lever_enabled', lambda *_: False)
    monkeypatch.setattr(batch_pipeline_store, 'contention_retry_enabled', lambda: False)
    monkeypatch.setattr(live, 'resolve_batch_policy', lambda *_: BatchUnitPolicy())
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    monkeypatch.setattr(lifecycle, 'FirestoreStore', lambda namespace: store)
    client.rows[('users', UID)] = {'data_protection_level': 'enhanced'}
    client.rows[ROW_PATH] = {
        'id': CID,
        'status': 'completed',
        'discarded': True,
        'record_lane_owner': 'batch_live_v1',
        'private_cloud_sync_enabled': True,
        'record_audio_closed': True,
        'server_batch_only': True,
        'server_batch_audio_closed': True,
        'server_batch_audio_start': 0,
        'server_batch_audio_end': 10,
        'has_content': True,
        'finalization_job_id': 'terminal',
        'finalization_revision': 1,
    }
    client.rows[('conversation_finalization_jobs_dev', 'terminal')] = {'status': 'completed', 'fanout_status': 'fenced'}
    return client


def test_restored_sealed_capture_registers_exactly_once_even_after_terminal_fence(restore_store):
    client = restore_store
    assert JOB_PATH not in client.rows
    assert lifecycle.restore_discarded(UID, CID) is True
    obligation = dict(client.rows[JOB_PATH])
    assert obligation['state'] == 'record_pending'
    assert obligation['conversation_id'] == CID
    assert client.rows[ROW_PATH]['discarded'] is False
    assert lifecycle.restore_discarded(UID, CID) is True
    assert client.rows[JOB_PATH] == obligation
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in client.rows) == 1
    assert client.rows[('conversation_finalization_jobs_dev', 'terminal')] == {
        'status': 'completed',
        'fanout_status': 'fenced',
    }


@pytest.mark.parametrize('change', [{'discarded': True}, {'deleted': True}, {'record_lane_owner': 'legacy'}])
def test_second_discard_deletion_or_owner_change_before_registration_creates_no_job(restore_store, monkeypatch, change):
    original = conversations_db.restore_conversation_from_discarded

    def restore_then_change(*args, **kwargs):
        result = original(*args, **kwargs)
        assert restore_store.rows[ROW_PATH]['discarded'] is False
        ref = restore_store.collection('users').document(UID).collection('conversations').document(CID)
        restore_store.transaction().update(ref, change)
        return result

    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', restore_then_change)
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore'):
        lifecycle.restore_discarded(UID, CID)
    assert JOB_PATH not in restore_store.rows


@pytest.mark.parametrize('privacy_scope', ['user', 'row'])
def test_privacy_refusal_surfaces_retry_and_can_be_retried_after_metadata_commits(restore_store, privacy_scope):
    row = restore_store.rows[('users', UID) if privacy_scope == 'user' else ROW_PATH]
    row['private_cloud_sync_enabled'] = False
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore') as blocked:
        lifecycle.restore_discarded(UID, CID)
    if privacy_scope == 'user':
        assert isinstance(blocked.value.__cause__, batch_pipeline_privacy.BatchPrivacyBlocked)
    assert restore_store.rows[ROW_PATH]['discarded'] is False
    assert restore_store.rows[ROW_PATH]['sync_relevance_user_kept'] is True
    assert JOB_PATH not in restore_store.rows
    row['private_cloud_sync_enabled'] = True
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[JOB_PATH]['state'] == 'record_pending'


def test_reprocess_retry_of_user_kept_row_runs_restore_registration_again(restore_store, monkeypatch):
    # Metadata may already have committed on an earlier refused registration.
    assert conversations_db.restore_conversation_from_discarded(UID, CID) is True
    conversation = SimpleNamespace(discarded=False, sync_relevance='keep')
    monkeypatch.setattr(conversations_router, 'process_conversation', lambda *args, **kwargs: conversation)
    monkeypatch.setattr(conversations_router, 'schedule_reprocessed_learning', lambda *args, **kwargs: conversation)
    assert (
        conversations_router.execute_reprocess(
            UID, CID, conversation, 'en', None, None, False, None, None, user_kept=True
        )
        is conversation
    )
    assert restore_store.rows[JOB_PATH]['state'] == 'record_pending'


def test_reprocess_surfaces_registration_refusal_as_retryable_http(monkeypatch):
    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', lambda *_: {'discarded': True})
    monkeypatch.setattr(conversations_router, 'deserialize_conversation', lambda _: SimpleNamespace(language='en'))
    monkeypatch.setattr(attention_db, 'generation', lambda _: 'generation')
    monkeypatch.setattr(attention_db, 'claim', lambda *args, **kwargs: ('operation', True))
    monkeypatch.setattr(attention_db, 'owns_live_claim', lambda *_: True)
    finish = Mock()
    monkeypatch.setattr(attention_db, 'finish', finish)
    monkeypatch.setattr(
        conversations_router,
        'execute_reprocess',
        Mock(side_effect=lifecycle.RestoredRecordingRegistrationUnavailable('retry restore')),
    )
    with pytest.raises(HTTPException) as refused:
        conversations_router.reprocess_conversation(CID, uid=UID)
    assert refused.value.status_code == 503
    assert refused.value.detail['code'] == 'recording_restore_retry_required'
    assert refused.value.headers == {'Retry-After': '1'}
    finish.assert_called_once_with(UID, 'operation', 'failed')

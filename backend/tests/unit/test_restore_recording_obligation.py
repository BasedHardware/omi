"""Explicit restore registers recording debt before committing visibility metadata."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from config.policy import BatchUnitPolicy
from config.record_audio import BARRIER_NOT_CLOSED, record_identity, require_record_audio_barrier
from database import batch_pipeline_privacy, batch_pipeline_store
from database import conversation_finalization_jobs as jobs
from database import conversations as conversations_db
from database import processing_attention as attention_db
from database.batch_pipeline_store import FirestoreStore
from routers import conversations as conversations_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import live
from utils.batch_pipeline.record_seal_repair import seal_refusal
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
        'has_photos': False,
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


@pytest.mark.parametrize('privacy_scope', ['user', 'row'])
def test_privacy_refusal_leaves_metadata_unchanged_and_retry_registers_once(restore_store, privacy_scope):
    row = restore_store.rows[('users', UID) if privacy_scope == 'user' else ROW_PATH]
    row['private_cloud_sync_enabled'] = False
    before = deepcopy(restore_store.rows[ROW_PATH])
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore') as blocked:
        lifecycle.restore_discarded(UID, CID)
    if privacy_scope == 'user':
        assert isinstance(blocked.value.__cause__, batch_pipeline_privacy.BatchPrivacyBlocked)
    assert restore_store.rows[ROW_PATH] == before
    assert JOB_PATH not in restore_store.rows
    row['private_cloud_sync_enabled'] = True
    assert lifecycle.restore_discarded(UID, CID) is True
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[JOB_PATH] == obligation
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in restore_store.rows) == 1


def test_metadata_failure_leaves_one_parked_obligation_and_retry_reuses_it(restore_store, monkeypatch):
    before = deepcopy(restore_store.rows[ROW_PATH])
    original = conversations_db.restore_conversation_from_discarded
    metadata_write = Mock(side_effect=RuntimeError('synthetic metadata failure'))
    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', metadata_write)
    for _ in range(2):
        with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore'):
            lifecycle.restore_discarded(UID, CID)
        assert restore_store.rows[ROW_PATH] == before
        assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in restore_store.rows) == 1
        assert seal_refusal(restore_store.rows[JOB_PATH], before, repair_closed=True) == 'privacy_refused'
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', original)
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[JOB_PATH] == obligation
    assert restore_store.rows[ROW_PATH]['discarded'] is False


def test_registration_receives_current_discarded_row_with_explicit_restore(restore_store, monkeypatch):
    original = live.register_recording
    seen = []

    def register(uid, snapshot, **kwargs):
        assert restore_store.rows[ROW_PATH]['discarded'] is True
        assert snapshot == restore_store.rows[ROW_PATH]
        assert snapshot['discarded'] is True
        assert kwargs['restoring'] is True
        seen.append(snapshot)
        return original(uid, snapshot, **kwargs)

    monkeypatch.setattr(live, 'register_recording', register)
    assert lifecycle.restore_discarded(UID, CID) is True
    assert len(seen) == 1
    assert restore_store.rows[ROW_PATH]['discarded'] is False


def test_explicit_restore_registration_creates_exactly_one_obligation(restore_store):
    store = FirestoreStore('batch_pipeline_dev', firestore_client=restore_store)
    before = deepcopy(restore_store.rows[ROW_PATH])
    assert live.register_recording(UID, before, store=store, restoring=True) is True
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    assert live.register_recording(UID, before, store=store, restoring=True) is True
    assert restore_store.rows[JOB_PATH] == obligation
    assert obligation['state'] == 'record_pending'
    assert obligation['conversation_id'] == CID
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in restore_store.rows) == 1
    assert restore_store.rows[ROW_PATH] == before


@pytest.mark.parametrize(
    'unrestorable',
    [
        pytest.param({'deleted': True}, id='deleted'),
        pytest.param({'deleted': True, 'status': 'deleted'}, id='tombstoned'),
        pytest.param({'deleted': True, 'sync_merged_into': 'survivor'}, id='redirect-tombstoned'),
        pytest.param({'sync_merged_into': 'survivor'}, id='merged-away'),
    ],
)
def test_explicit_restore_registration_refuses_unrestorable_rows(restore_store, unrestorable):
    restore_store.rows[ROW_PATH].update(unrestorable)
    before = deepcopy(restore_store.rows)
    store = FirestoreStore('batch_pipeline_dev', firestore_client=restore_store)
    assert live.register_recording(UID, restore_store.rows[ROW_PATH], store=store, restoring=True) is False
    assert restore_store.rows == before
    assert JOB_PATH not in restore_store.rows


def test_default_registration_still_refuses_discarded_row(restore_store):
    before = deepcopy(restore_store.rows)
    store = FirestoreStore('batch_pipeline_dev', firestore_client=restore_store)
    assert live.register_recording(UID, restore_store.rows[ROW_PATH], store=store) is False
    assert restore_store.rows == before
    assert JOB_PATH not in restore_store.rows


def test_legacy_restore_has_no_recording_obligation(restore_store):
    restore_store.rows[ROW_PATH]['record_lane_owner'] = 'legacy'
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[ROW_PATH]['discarded'] is False
    assert JOB_PATH not in restore_store.rows


def test_open_audio_restore_registers_exactly_once(restore_store):
    restore_store.rows[ROW_PATH]['record_audio_closed'] = False
    assert lifecycle.restore_discarded(UID, CID) is True
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    assert obligation['state'] == 'record_pending'
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[JOB_PATH] == obligation
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in restore_store.rows) == 1


def test_proven_empty_photo_only_restore_has_no_obligation(restore_store):
    restore_store.rows[ROW_PATH].update(
        server_batch_audio_received=False, has_content=False, has_photos=True, photos=[{'id': 'photo'}]
    )
    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[ROW_PATH]['discarded'] is False
    assert JOB_PATH not in restore_store.rows


@pytest.mark.parametrize(
    'unproven',
    [
        {'record_audio_closed': False},
        {'server_batch_audio_received': True},
        {'server_batch_audio_received': None},
        {'record_upload_failed': True},
        {'record_upload_sessions': {'producer': 'active'}},
    ],
)
def test_unproven_empty_restore_is_refused_before_metadata(restore_store, unproven):
    restore_store.rows[ROW_PATH].update({'server_batch_audio_received': False, 'has_content': False, **unproven})
    before = deepcopy(restore_store.rows[ROW_PATH])
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable):
        lifecycle.restore_discarded(UID, CID)
    assert restore_store.rows[ROW_PATH] == before
    assert JOB_PATH not in restore_store.rows


@pytest.mark.parametrize('missing', [False, True])
def test_tombstone_or_missing_restore_stays_refused(restore_store, missing):
    if missing:
        del restore_store.rows[ROW_PATH]
    else:
        restore_store.rows[ROW_PATH]['deleted'] = True
    before = deepcopy(restore_store.rows)
    assert lifecycle.restore_discarded(UID, CID) is False
    assert restore_store.rows == before


def test_restore_then_discard_refuses_further_registration(restore_store):
    assert lifecycle.restore_discarded(UID, CID) is True
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    restore_store.rows[ROW_PATH]['discarded'] = True
    assert live.register_recording(UID, restore_store.rows[ROW_PATH]) is False
    assert restore_store.rows[JOB_PATH] == obligation
    assert seal_refusal(obligation, restore_store.rows[ROW_PATH], repair_closed=True) == 'privacy_refused'


def test_registration_refusal_does_not_attempt_restore_metadata(restore_store, monkeypatch):
    metadata = Mock()
    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', metadata)
    monkeypatch.setattr(live, 'register_recording', lambda *args, **kwargs: False)
    before = deepcopy(restore_store.rows[ROW_PATH])
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable):
        lifecycle.restore_discarded(UID, CID)
    metadata.assert_not_called()
    assert restore_store.rows[ROW_PATH] == before
    assert JOB_PATH not in restore_store.rows


def test_reprocess_retry_of_user_kept_row_runs_restore_registration_again(restore_store, monkeypatch):
    # Register-first refusal cannot commit visibility or the user's keep marker.
    restore_store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    before = deepcopy(restore_store.rows[ROW_PATH])
    conversation = SimpleNamespace(discarded=False, sync_relevance='keep')
    monkeypatch.setattr(conversations_router, 'process_conversation', lambda *args, **kwargs: conversation)
    learning = Mock(return_value=conversation)
    monkeypatch.setattr(conversations_router, 'schedule_reprocessed_learning', learning)

    def reprocess():
        return conversations_router.execute_reprocess(
            UID, CID, conversation, 'en', None, None, False, None, None, user_kept=True
        )

    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore'):
        reprocess()
    assert restore_store.rows[ROW_PATH] == before
    assert restore_store.rows[ROW_PATH]['discarded'] is True
    assert restore_store.rows[ROW_PATH].get('sync_relevance_user_kept') == before.get('sync_relevance_user_kept')
    assert JOB_PATH not in restore_store.rows
    learning.assert_not_called()
    restore_store.rows[('users', UID)]['private_cloud_sync_enabled'] = True
    assert reprocess() is conversation
    assert restore_store.rows[ROW_PATH]['discarded'] is False
    assert restore_store.rows[ROW_PATH]['sync_relevance_user_kept'] is True
    obligation = deepcopy(restore_store.rows[JOB_PATH])
    assert obligation['state'] == 'record_pending'
    assert reprocess() is conversation
    assert restore_store.rows[JOB_PATH] == obligation
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in restore_store.rows) == 1


def test_reprocess_surfaces_registration_refusal_as_retryable_http(restore_store, monkeypatch):
    restore_store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    before = deepcopy(restore_store.rows[ROW_PATH])
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
        lambda *args, **kwargs: lifecycle.restore_discarded(UID, CID),
    )
    with pytest.raises(HTTPException) as refused:
        conversations_router.reprocess_conversation(CID, uid=UID)
    assert refused.value.status_code == 503
    assert refused.value.detail['code'] == 'recording_restore_retry_required'
    assert refused.value.headers == {'Retry-After': '1'}
    finish.assert_called_once_with(UID, 'operation', 'failed')
    assert restore_store.rows[ROW_PATH] == before
    assert JOB_PATH not in restore_store.rows


def test_local_non_batch_restore_never_constructs_batch_store(restore_store, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    restore_store.rows[ROW_PATH]['record_lane_owner'] = 'legacy'

    def forbidden(*args, **kwargs):
        raise AssertionError('non-batch restore must not resolve a batch stage or store')

    monkeypatch.setattr(lifecycle, 'FirestoreStore', forbidden)
    monkeypatch.setattr(lifecycle, 'current_stage', forbidden)
    assert lifecycle.restore_discarded(UID, CID) is True
    restored = restore_store.rows[ROW_PATH]
    assert restored['discarded'] is False
    assert restored['sync_relevance_user_kept'] is True
    assert restored['relevance_decision']['reason'] == 'restored'
    assert JOB_PATH not in restore_store.rows


def test_discarded_zero_preview_parent_passes_restore_barrier_after_fanout_close(restore_store, monkeypatch):
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: restore_store)
    job_path = (jobs.FINALIZATION_JOBS_COLLECTION, 'fjob')
    row = restore_store.rows[ROW_PATH]
    row.update(status='processing', finalization_job_id='fjob', finalization_revision=1)
    restore_store.rows[job_path] = {
        'uid': UID,
        'conversation_id': CID,
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 7,
        'finalization_revision': 1,
        'fanout_status': 'pending',
    }
    with pytest.raises(ValueError) as parked:
        require_record_audio_barrier(row)
    assert str(parked.value) == BARRIER_NOT_CLOSED

    assert jobs.mark_discarded_server_batch_fanout_completed(UID, CID, 'fjob', 1, 7) is True
    assert jobs.mark_finalization_completed('fjob', 1, 7) is True
    assert restore_store.rows[ROW_PATH]['status'] == 'completed'

    assert lifecycle.restore_discarded(UID, CID) is True
    restored = restore_store.rows[ROW_PATH]
    assert restored['discarded'] is False
    require_record_audio_barrier(restored)


def test_restore_after_receipt_expiry_on_projected_row_creates_no_obligation(restore_store):
    # The 45-day receipt has expired, so no job remains for register_recording to dedupe against.
    restore_store.rows[ROW_PATH]['record_projection_revision'] = 3
    assert JOB_PATH not in restore_store.rows

    assert lifecycle.restore_discarded(UID, CID) is True
    assert JOB_PATH not in restore_store.rows
    assert restore_store.rows[ROW_PATH]['discarded'] is False


def test_restore_with_open_server_archive_registers_once_despite_closed_generic_flag(restore_store):
    # record_audio_closed is true on the row, but the server archive is still open.
    row = restore_store.rows[ROW_PATH]
    row.update(server_batch_audio_closed=False, server_batch_audio_received=False)

    assert lifecycle.restore_discarded(UID, CID) is True
    assert restore_store.rows[JOB_PATH]['state'] == 'record_pending'
    assert restore_store.rows[ROW_PATH]['discarded'] is False


def test_restore_with_closed_empty_server_archive_creates_no_obligation(restore_store):
    row = restore_store.rows[ROW_PATH]
    row.update(has_content=False, server_batch_audio_received=False)

    assert lifecycle.restore_discarded(UID, CID) is True
    assert JOB_PATH not in restore_store.rows
    assert restore_store.rows[ROW_PATH]['discarded'] is False

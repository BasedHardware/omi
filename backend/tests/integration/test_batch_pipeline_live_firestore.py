"""Record projection/finalize/WAL ownership with real Firestore contention."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace, asdict
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import fakeredis

from database import batch_pipeline_projection_claim as projection_claims
from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows, frozen_manifest
from utils.batch_pipeline.live import register_recording, record_identity
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.projection import build_incoming
from utils.sync.assignment_errors import SyncAssignmentConflict
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_intake import admit
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority, WorkResult

pytestmark = pytest.mark.integration


def native(lane, *, status='completed', private=True, custom=False):
    lane.payload['speech_spans'] = [{'start': 0.0, 'end': 4.0}]
    content, segment = record_identity(lane.uid, 'live-record')
    item = WorkItem(
        segment,
        lane.uid,
        1750000100,
        'gs://synthetic/audio#1',
        30,
        Priority.FRESH,
        conversation_id='live-record',
        privacy_generation=0,
    )
    binding = ProjectionBinding(
        lane.uid,
        'bp_' + content,
        content,
        (segment,),
        target_conversation_id='live-record',
        private_cloud_sync_enabled=private,
        data_protection_level='standard',
        record_origin=True,
        native_record=True,
    )
    live = build_incoming(item, binding, lane.payload)
    live.update(
        id='live-record',
        record_lane_owner='batch_live_v1',
        private_cloud_sync_enabled=private,
        uses_custom_stt=custom,
        status=status,
        record_audio_closed=True,
    )
    lane.user.update({'private_cloud_sync_enabled': private})
    lane.user.collection('conversations').document('live-record').set(
        lane.conversations.encode_conversation_for_write(lane.uid, live, 'standard')
    )
    return item, binding, live


def complete(lane, item, binding):
    admit(lane.store, [item], binding, 0, namespace=lane.store.namespace)
    lease = lane.queue.pull(0)[0]
    assert lane.queue.complete(WorkResult(item.segment_id, 'gs://synthetic/result#1'), lease.token, 1)
    lane.merge.commit_next(lane.uid, 2)


def test_finalize_racing_projection_and_replay_preserve_one_visible_record(lane):
    item, binding, live = native(lane, status='processing')
    register_recording(lane.uid, live, store=lane.store, now=0)
    complete(lane, item, binding)
    with pytest.raises(SyncAssignmentConflict, match='finalize'):
        lane.projector.project(item.segment_id)
    reference = lane.user.collection('conversations').document('live-record')
    reference.update({'status': 'completed'})
    result = lane.projector.project(item.segment_id)
    row = active_rows(lane)[0]
    assert row['id'] == 'live-record' and row['record_projection_revision'] == 1
    assert len(row['transcript_segments']) == 1
    assert row['transcript_segments'][0]['speaker_id_scope'].startswith('final:batch:')
    assert lane.projector.project(item.segment_id) == result
    assert len(active_rows(lane)) == 1 and active_rows(lane)[0]['record_projection_revision'] == 1
    accounting = lane.projector.store.prepare_accounting(binding, 3)
    assert accounting['seconds'] == 4 and accounting['completed'] and not accounting['updates']


def test_concurrent_wal_and_record_admission_share_one_obligation(lane):
    item, binding, live = native(lane)
    register_recording(lane.uid, live, store=lane.store, now=0)
    # The upload fence resolves to the native immutable record identity; two
    # independent reconcilers/requests can lose replies without enqueueing twins.
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(lambda _: admit(lane.store, [item], binding, 1, namespace=lane.store.namespace), range(2))
        )
    assert outcomes == [{'outcome': 'batch', 'job_id': binding.job_id}] * 2
    jobs = list(lane.client.collection(lane.store.namespace + '_jobs').stream())
    assert len(jobs) == 1 and jobs[0].to_dict()['state'] == 'ready'


@pytest.mark.parametrize('change', ['custom', 'consent', 'e2ee', 'deleted'])
def test_current_privacy_fences_record_before_enqueue(lane, change):
    item, binding, live = native(lane)
    if change == 'custom':
        lane.user.collection('conversations').document('live-record').update({'uses_custom_stt': True})
    elif change == 'consent':
        lane.user.collection('conversations').document('live-record').update({'private_cloud_sync_enabled': False})
    elif change == 'e2ee':
        lane.user.update({'data_protection_level': 'e2ee'})
    else:
        lane.user.collection('deleted_conversations').document('live-record').set({'deleted': True})
    with pytest.raises(BatchPrivacyBlocked):
        register_recording(lane.uid, live, store=lane.store, now=0)
    assert not list(lane.client.collection(lane.store.namespace + '_jobs').stream())


async def test_real_wal_upload_race_and_rollback_replay_use_record_receipt(lane, monkeypatch, tmp_path):
    import asyncio
    import json
    import struct
    from utils.batch_pipeline import live_upload
    from utils.batch_pipeline.audio import audio_unit

    item, binding, live = native(lane)
    register_recording(lane.uid, live, store=lane.store, now=0)
    admit(
        lane.store,
        [item],
        binding,
        0,
        namespace=lane.store.namespace,
        intake={
            'owner_id': lane.uid,
            'owner_key': owner_key(lane.uid),
            'content_id': binding.content_id,
            'conversation_id': 'live-record',
            'segment_ids': [item.segment_id],
            'total_files': 1,
            'lane': 'fresh',
        },
    )
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: lane.store)
    monkeypatch.setattr(live_upload, 'current_stage', lambda: 'local')
    pcm = b'\x01\x00' * 16000
    wav = audio_unit(1750000100, pcm * 30).wav
    calls = []
    artifacts = SimpleNamespace(fetch_audio=lambda _: calls.append('fetch') or wav)
    monkeypatch.setattr(live_upload, 'artifacts_for', lambda _: artifacts)
    paths = []
    for index in range(2):
        directory = tmp_path / str(index)
        directory.mkdir()
        path = directory / 'audio_omi_pcm16_16000_1_fs160_1750000100.bin'
        path.write_bytes((len(pcm).to_bytes(4, 'little') + pcm) * 30)
        paths.append(str(path))
    kwargs = dict(
        uid=lane.uid,
        conversation_id='live-record',
        content_id='wal-content',
        source='omi',
        client_device_id=None,
        loaded_conversation=live,
    )
    responses = await asyncio.gather(
        *(live_upload.registered_record_response(paths=[path], **kwargs) for path in paths)
    )
    assert all(response.status_code == 202 for response in responses)
    assert {json.loads(response.body)['job_id'] for response in responses} == {binding.job_id}
    assert len(list(lane.client.collection(lane.store.namespace + '_jobs').stream())) == 1
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setattr(artifacts, 'fetch_audio', lambda _: pytest.fail('replay read expired audio'))
    replay = await live_upload.registered_record_response(paths=[paths[0]], **kwargs)
    assert replay.status_code == 202 and json.loads(replay.body)['job_id'] == binding.job_id


async def test_pre_enable_capture_holds_wal_until_finalizer_reserves_owner(lane, monkeypatch):
    from utils.batch_pipeline import live_upload
    from database.conversations import claim_record_lane_owner

    item, binding, live = native(lane, status='processing')
    reference = lane.user.collection('conversations').document('live-record')
    reference.update({'record_lane_owner': None, 'language': 'en'})
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: lane.store)
    response = await live_upload.registered_record_response(
        uid=lane.uid,
        conversation_id='live-record',
        content_id='early-wal',
        paths=[],
        source='omi',
        client_device_id=None,
    )
    assert response.status_code == 503
    assert not list(lane.client.collection(lane.store.namespace + '_jobs').stream())
    snapshot = reference.get()
    assert (
        claim_record_lane_owner(
            lane.uid, 'live-record', 'batch_live_v1', snapshot.update_time, firestore_client=lane.client
        )
        is not None
    )
    register_recording(lane.uid, live, store=lane.store, now=0)
    admit(lane.store, [item], binding, 0, namespace=lane.store.namespace)
    jobs = list(lane.client.collection(lane.store.namespace + '_jobs').stream())
    assert len(jobs) == 1 and jobs[0].to_dict()['state'] == 'ready'


@pytest.mark.parametrize('batch_enabled,owner', [(False, 'legacy_final_pass_v1'), (True, 'batch_sync_v1')])
async def test_enabled_wal_routing_fences_existing_dispatcher_against_native_twin(
    lane, monkeypatch, batch_enabled, owner
):
    from utils.batch_pipeline import live_upload, live as admission

    # Enabled in-progress captures deliberately hold WALs for native reservation.
    # A finalized unowned row can instead freeze its existing upload dispatcher.
    native(lane)
    reference = lane.user.collection('conversations').document('live-record')
    reference.update({'record_lane_owner': None, 'language': 'en'})
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', str(batch_enabled).lower())
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: lane.store)
    response = await live_upload.registered_record_response(
        uid=lane.uid,
        conversation_id='live-record',
        content_id='pre-enable-wal',
        paths=[],
        source='omi',
        client_device_id=None,
    )
    expected = live_upload.RecordUploadRoute.BATCH if batch_enabled else live_upload.RecordUploadRoute.LEGACY
    assert response is expected  # Existing dispatcher keeps its route through cohort changes.
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    row = reference.get().to_dict()
    assert row['record_lane_owner'] == owner
    assert admission.reserve_recording(lane.uid, row) == owner
    assert not admission.register_recording(lane.uid, row, store=lane.store, now=0)
    assert not list(lane.client.collection(lane.store.namespace + '_jobs').stream())
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', str(not batch_enabled).lower())
    replay = await live_upload.registered_record_response(
        uid=lane.uid,
        conversation_id='live-record',
        content_id='pre-enable-wal',
        paths=[],
        source='omi',
        client_device_id=None,
    )
    assert replay is expected


def test_desktop_upload_projects_into_existing_from_segments_record(lane):
    item, binding, live = native(lane)
    target = lane.user.collection('conversations').document('live-record')
    target.update({'record_lane_owner': None, 'source': 'desktop'})
    binding = replace(binding, native_record=False, source='desktop')
    playback = []
    lane.projector.playback = lambda item, canonical: playback.append(canonical)
    complete(lane, item, binding)
    result = lane.projector.project(item.segment_id)
    assert result['updated_memories'] == ['live-record']
    assert playback == ['live-record']
    row = active_rows(lane)[0]
    assert row['record_lane_owner'] == 'batch_sync_v1'
    assert row['record_projection_revision'] == 1
    assert len(row['transcript_segments']) == 1


def test_stale_finalizer_and_late_socket_cannot_overwrite_record(lane):
    from models.conversation import Conversation

    item, binding, live = native(lane)
    # Internal markers do not round-trip through the public model dump. The
    # canonical finalizer must retain both the route and pusher's close receipt.
    processed = Conversation(**live).model_dump()
    assert 'record_lane_owner' not in processed
    assert lane.conversations.persist_processing_result_with_lifecycle(lane.uid, processed)
    current = lane.user.collection('conversations').document('live-record').get().to_dict()
    assert current['record_lane_owner'] == 'batch_live_v1' and current['record_audio_closed']
    register_recording(lane.uid, live, store=lane.store, now=0)
    complete(lane, item, binding)
    lane.projector.project(item.segment_id)
    assert not lane.conversations.persist_processing_result_with_lifecycle(lane.uid, dict(live))
    assert not lane.conversations.update_conversation_segments(
        lane.uid,
        'live-record',
        live['transcript_segments'],
        live_segments=live['transcript_segments'],
        firestore_client=lane.client,
        return_segments=True,
    )
    assert active_rows(lane)[0]['record_projection_revision'] == 1


@pytest.mark.parametrize('contended', [False, True])
def test_true_vad_silence_replaces_unprotected_provisional_speech(lane, monkeypatch, contended):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', str(contended).lower())
    if contended:
        redis = fakeredis.FakeRedis()
        monkeypatch.setattr(projection_claims, '_redis_client', lambda: redis)
        assign = lane.projector.assign_record_silence

        def lost_reply(item, binding, session):
            assign(item, binding, session)
            # The receipt committed; surface a competing projector's replay
            # before completion and verify the remaining obligations resume.
            lane.projector.store.check(session)

        monkeypatch.setattr(lane.projector, 'assign_record_silence', lost_reply)
    item, binding, live = native(lane)
    register_recording(lane.uid, live, store=lane.store, now=0)
    admit(lane.store, [item], binding, 0, namespace=lane.store.namespace)
    lease = lane.queue.pull(0)[0]
    assert lane.queue.complete(WorkResult(item.segment_id, 'gs://synthetic/silence#1', 'silence'), lease.token, 1)
    lane.merge.commit_next(lane.uid, 2)
    result = lane.projector.project(item.segment_id)
    row = active_rows(lane)[0]
    assert result['updated_memories'] == ['live-record']
    assert row['record_projection_revision'] == 1 and not row['transcript_segments']


def test_native_record_preserves_real_correction_translation_and_manual_receipt(lane):
    from database import review_store
    from utils.agent_capabilities import transcripts

    item, binding, live = native(lane)
    original = live['transcript_segments'][0]
    original.update(
        person_id='synthetic-person',
        speaker_label_source='manual',
        speaker_id_scope='live:synthetic',
        translations=[{'lang': 'fr', 'text': 'Synthetic translation.'}],
    )
    live.update(
        has_transcript_corrections=True,
        manual_speaker_assignments={'segments': {original['id']: {'person_id': 'synthetic-person', 'is_user': False}}},
    )
    target = lane.user.collection('conversations').document('live-record')
    target.set(lane.conversations.encode_conversation_for_write(lane.uid, live, 'standard'))
    correction = {
        'segment_id': original['id'],
        'segment_index': 0,
        'start': original['start'],
        'before': 'project',
        'after': 'plan',
        'kind': 'word',
        'source': 'human',
        'change_id': 'synthetic-edit',
        'undone': False,
    }
    overlay = review_store.encode_doc(lane.uid, {'source': [correction]})
    correction_ref = lane.user.collection('transcript_corrections').document('live-record')
    correction_ref.set(overlay)
    register_recording(lane.uid, live, store=lane.store, now=0)
    complete(lane, item, binding)
    lane.projector.project(item.segment_id)
    row = active_rows(lane)[0]
    stored = row['transcript_segments'][0]
    assert row['id'] == 'live-record' and len(row['transcript_segments']) == 1
    for field in ('id', 'text', 'translations', 'person_id', 'speaker_label_source'):
        assert stored[field] == original[field]
    assert stored['speaker_id_scope'].startswith('final:batch:')
    projected = transcripts.project(lane.uid, row, firestore_client=lane.client)
    assert projected['transcript_segments'][0]['text'] == 'We discussed the plan.'
    assert correction_ref.get().to_dict() == overlay


def test_inflight_recording_and_legacy_final_pass_cas_choose_exactly_one_owner(lane):
    item, binding, live = native(lane, status='processing')
    ref = lane.user.collection('conversations').document('live-record')
    ref.update({'record_lane_owner': None})
    revision = ref.get().update_time
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda owner: lane.conversations.claim_record_lane_owner(lane.uid, 'live-record', owner, revision),
                ['batch_live_v1', 'legacy_final_pass_v1'],
            )
        )
    assert sum(result is not None for result in outcomes) == 1
    assert ref.get().to_dict()['record_lane_owner'] in {'batch_live_v1', 'legacy_final_pass_v1'}


def test_enablement_reserves_already_inflight_capture_from_loaded_revision(lane, monkeypatch):
    from utils.batch_pipeline.live import reserve_recording

    item, binding, live = native(lane, status='processing')
    ref = lane.user.collection('conversations').document('live-record')
    ref.update({'record_lane_owner': None})
    snapshot = ref.get()
    loaded = dict(live, record_lane_owner=None, language='en', updated_at=snapshot.update_time)
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    assert reserve_recording(lane.uid, loaded) == 'batch_live_v1'
    assert ref.get().to_dict()['record_lane_owner'] == 'batch_live_v1'


def test_native_reference_proof_outlives_gpu_result_for_first_late_wal(lane):
    from datetime import timedelta

    item, binding, live = native(lane)
    register_recording(lane.uid, live, store=lane.store, now=0)
    complete(lane, item, binding)
    refs = lane.client.collection(lane.store.namespace + '_artifacts')
    for kind in ('audio', 'results'):
        refs.document(kind).set(
            {
                'segment_id': item.segment_id,
                'owner_id': lane.uid,
                'owner_key': owner_key(lane.uid),
                'kind': kind,
                'uri': 'gs://synthetic/proof#1',
            }
        )
    lane.projector.project(item.segment_id)
    audio = refs.document('audio').get().to_dict()['cleanup_after']
    result = refs.document('results').get().to_dict()['cleanup_after']
    assert audio - result == timedelta(days=44)

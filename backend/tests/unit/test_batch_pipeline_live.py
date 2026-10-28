"""Synthetic record ownership, raw-reference and annotation contracts."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
import wave

import pytest

from config.batch_pipeline import live_record_enabled_for
from database.batch_pipeline_intake import AdmissionDisabled, admit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.live import record_identity, register_recording
from utils.batch_pipeline.live_projection import replace_record
from utils.batch_pipeline.source_audio import MAGIC, materialize, validate_reference
from utils.sync.assignment_errors import SyncAssignmentConflict


def recording(**changes):
    return {
        'id': 'record',
        'record_lane_owner': 'batch_live_v1',
        'source': 'desktop',
        'language': 'en',
        'private_cloud_sync_enabled': True,
        'status': 'completed',
        'data_protection_level': 'standard',
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'finished_at': datetime.fromtimestamp(102, timezone.utc),
        'transcript_segments': [
            {'id': 'old', 'text': 'Synthetic speech.', 'start': 0, 'end': 2, 'speaker_id': 0, 'is_user': False}
        ],
        **changes,
    }


def incoming():
    return {
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'transcript_segments': [
            {
                'id': 'new',
                'text': 'Synthetic speech.',
                'start': 0,
                'end': 2,
                'speaker_id': 0,
                'speaker': 'SPEAKER_00',
                'speaker_id_scope': 'final:batch:unit',
                'is_user': False,
                'speaker_match_source': 'batch_pyannote',
            }
        ],
    }


def test_cohort_requires_both_flags_and_uses_the_sync_hash(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    assert not live_record_enabled_for('synthetic')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    assert live_record_enabled_for('synthetic')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert not live_record_enabled_for('synthetic')


def test_record_owner_stays_server_internal_without_expanding_the_client_contract():
    from models.conversation import Conversation

    row = recording()
    model = Conversation(**{**row, 'created_at': row['started_at'], 'structured': {}})
    assert model.record_lane_owner == 'batch_live_v1'
    assert 'record_lane_owner' not in model.model_dump()
    assert 'record_lane_owner' not in Conversation.model_json_schema()['properties']


@pytest.mark.parametrize(
    'change',
    [
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'discarded': True},
        {'deleted': True},
        {'record_lane_owner': None},
    ],
)
def test_privacy_refusals_never_create_obligations(change):
    store = MemoryStore()
    assert not register_recording('synthetic', recording(**change), store=store, now=0)
    assert not store.rows


def test_concurrent_finalize_registration_and_replay_create_one_pending_obligation():
    store = MemoryStore()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(lambda _: register_recording('synthetic', recording(), store=store, now=0), range(2)))
    assert len(store.rows) == 1
    assert next(iter(store.rows.values()))['state'] == 'record_pending'


@pytest.mark.parametrize('recorded_enabled', [True, False])
def test_reserved_record_drains_after_rollback_and_cannot_rebind_to_wal(monkeypatch, recorded_enabled):
    store = MemoryStore()
    register_recording('synthetic', recording(), store=store, now=0)
    content, segment = record_identity('synthetic', 'record')
    store.rows['conversations', 'synthetic/record'] = recording()
    item = WorkItem(
        segment,
        'synthetic',
        100,
        'gs://synthetic/audio#1',
        2,
        Priority.FRESH,
        conversation_id='record',
        privacy_generation=0,
    )
    binding = ProjectionBinding(
        'synthetic',
        'bp_' + content,
        content,
        (segment,),
        target_conversation_id='record',
        record_origin=True,
        native_record=True,
    )
    store.rows['jobs', segment]['policy'].update(
        batch_enabled=recorded_enabled, source_role='reserve-role', final_pass_enabled=True
    )
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    if not recorded_enabled:
        with pytest.raises(AdmissionDisabled):
            admit(store, [item], binding, 1, namespace='batch_pipeline_test_live')
        assert store.rows['jobs', segment]['state'] == 'record_pending'
        return
    result = admit(store, [item], binding, 1, namespace='batch_pipeline_test_live')
    assert result == {'outcome': 'batch', 'job_id': binding.job_id}
    assert admit(store, [item], binding, 2, namespace='batch_pipeline_test_live') == result
    assert store.rows['jobs', segment]['state'] == 'ready'
    assert len([v for (t, _), v in store.rows.items() if t == 'jobs']) == 1


def test_projection_replaces_provisional_instead_of_appending_and_keeps_id():
    result, survivors = replace_record(recording(), incoming(), {'start': 100, 'end': 102})
    assert result['id'] == 'record'
    assert len(result['transcript_segments']) == 1
    assert result['transcript_segments'][0]['id'] == 'new'
    assert result['sync_content_revision'] == result['record_projection_revision'] == 1
    assert survivors[0]['speaker_id_scope'] == 'final:batch:unit'


def test_projection_waits_for_finalize_without_mutating_provisional():
    original = recording(status='processing')
    with pytest.raises(SyncAssignmentConflict, match='finalize'):
        replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert original['transcript_segments'][0]['id'] == 'old'


def test_translation_and_manual_edit_anchors_survive_projection():
    old = recording(has_transcript_corrections=True)
    old['transcript_segments'][0]['translations'] = [{'language': 'es', 'text': 'Synthetic translation.'}]
    old['manual_speaker_assignments'] = {'segments': {'old': {'is_user': True, 'person_id': None, 'generation': 1}}}
    result, _ = replace_record(old, incoming(), {'start': 100, 'end': 102})
    segment = result['transcript_segments'][0]
    assert segment['id'] == 'old' and segment['text'] == old['transcript_segments'][0]['text']
    assert segment['translations'] == old['transcript_segments'][0]['translations']
    assert segment['is_user']
    assert segment['speaker_id_scope'] == 'final:batch:unit'


def test_reference_manifest_joins_sample_slices_without_copying_source_audio():
    pcm = b'\x01\x00' * 32000
    item = WorkItem('unit', 'synthetic', 100, 'manifest', 1, Priority.FRESH, conversation_id='record')
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': 'synthetic',
                'conversation_id': 'record',
                'capture_at': 100,
                'context': {'synthetic': True},
                'references': [
                    {
                        'start_frame': 0,
                        'offset_frame': 16000,
                        'frames': 16000,
                        'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
                    }
                ],
            }
        ).encode()
    )
    wav = materialize(body, item, lambda ref: pcm)
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        assert stream.readframes(stream.getnframes()) == pcm[32000:]
    with pytest.raises(ValueError, match='digest changed'):
        materialize(body, item, lambda ref: b'\0' * 64000)


@pytest.mark.parametrize(
    'change',
    [
        {'bucket': 'foreign'},
        {'path': 'chunks/other/record/a'},
        {'generation': 0},
        {'path': 'chunks/synthetic/record/../a'},
    ],
)
def test_reference_scope_and_generation_are_fail_closed(change):
    with pytest.raises(ValueError):
        validate_reference(
            {'bucket': 'retained', 'path': 'chunks/synthetic/record/a', 'generation': 1, **change},
            'synthetic',
            'record',
            {'retained'},
        )


@pytest.mark.parametrize('server_only', [False, True])
async def test_native_admission_stages_references_and_drains_after_rollback(monkeypatch, server_only):
    from types import SimpleNamespace
    from utils.batch_pipeline import live
    from database.batch_pipeline_staging import artifact_id

    store = MemoryStore()
    store.namespace = 'batch_pipeline_test_live'
    current = recording(record_audio_closed=True, finished_at=datetime.fromtimestamp(101, timezone.utc))
    if server_only:
        current['external_data'] = {**(current.get('external_data') or {}), 'server_batch_only': True}
        current.update(
            has_content=True, server_batch_audio_start=100, server_batch_audio_end=101, transcript_segments=[]
        )
    register_recording('synthetic', current, store=store, now=0)
    content, segment = record_identity('synthetic', 'record')
    pending = store.rows['jobs', segment]
    store.rows['conversations', 'synthetic/record'] = current

    class Reference:
        def collection(self, *args):
            return self

        document = collection

        def get(self):
            return SimpleNamespace(to_dict=lambda: current)

    store.client = Reference()

    class Client:
        def bucket(self, name):
            return self

        def blob(self, path, generation=None):
            return SimpleNamespace(reload=lambda **kwargs: None, metadata={})

    monkeypatch.setattr(live, 'create_storage_client', Client)
    listings = []
    monkeypatch.setattr(
        live,
        'list_audio_chunks',
        lambda *args, **kwargs: listings.append(kwargs)
        or [
            {
                'path': 'chunks/synthetic/record/audio.batch.bin',
                'generation': 1,
                'timestamp': 100,
                'span': {'sample_rate': 16000},
            }
        ],
    )
    monkeypatch.setattr(live, 'read_reference', lambda *args: b'\x01\x00' * 16000)
    manifests = []

    def stage(item, body):
        manifests.append(json.loads(body[len(MAGIC) :]))
        assert body.startswith(MAGIC) and len(body) < 2000
        uri = 'gs://synthetic-manifest/audio#1'
        store.rows['artifacts', artifact_id(item.segment_id, uri)] = {
            'owner_id': item.owner_id,
            'privacy_generation': 0,
        }
        return uri

    monkeypatch.setattr(
        live,
        'create_artifact_store',
        lambda *args: SimpleNamespace(
            key_for_owner=lambda uid: b'a' * 32,
            stage_audio=stage,
            authorize=lambda item: SimpleNamespace(level='standard'),
        ),
    )
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    result = await live.admit_recording(store, pending, now=1)
    assert result == {'outcome': 'batch', 'job_id': 'bp_' + content}
    assert store.rows['jobs', segment]['state'] == 'ready'
    assert manifests[0]['references'][0]['generation'] == 1
    assert store.rows['jobs', segment]['projection_binding']['native_record']
    assert (store.rows['intakes', 'bp_' + content].get('server_batch_only') is True) is server_only
    # A slow raw-archive listing must raise and retry, never admit a short capture.
    assert listings == [{'max_count': 4096, 'require_archive': True}]


@pytest.mark.parametrize('language,admitted', [('en', True), ('vi', False), ('multi', False)])
def test_capture_reservation_preserves_supported_language_route(monkeypatch, language, admitted):
    from utils.conversations import lifecycle

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    captured = []
    monkeypatch.setattr(
        lifecycle.conversations_db,
        'create_conversation_if_absent_with_lifecycle',
        lambda uid, row: captured.append(dict(row)) or True,
    )
    row = recording(status='in_progress', language=language, record_lane_owner=None)
    assert lifecycle.create_in_progress_conversation('synthetic', row, idempotent=True)
    assert (captured[0].get('record_lane_owner') == 'batch_live_v1') == admitted


def test_ambiguous_annotated_sentence_preserves_text_and_abstains_instead_of_guessing():
    old = recording()
    old['transcript_segments'][0]['translations'] = [{'language': 'es', 'text': 'Synthetic translation.'}]
    new = incoming()
    new['transcript_segments'][0]['text'] = 'Unrelated synthetic recognition.'
    result, _ = replace_record(old, new, {'start': 100, 'end': 102})
    segment = result['transcript_segments'][0]
    assert segment['id'] == 'old' and segment['text'] == 'Synthetic speech.'
    assert segment['speaker_match_source'] == 'batch_abstention' and not segment['is_user']
    assert segment['translations'] == old['transcript_segments'][0]['translations']

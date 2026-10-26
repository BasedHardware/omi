"""Synthetic PCM only: encrypted sync-off evidence through real resolver inputs."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import partial
import io
import time
from types import SimpleNamespace
from unittest.mock import Mock
import wave
import weakref

from cryptography.exceptions import InvalidTag
import numpy as np
import pytest

from config import batch_conversation_speakers as flags
from database import batch_voice_evidence as db
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from utils.batch_pipeline import voice_centroids as schema, voice_evidence as evidence
from utils.batch_pipeline.artifacts import ArtifactStore
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.batch_pipeline.retention import batch_artifact_authorize, batch_artifact_register
from utils.conversations import speaker_resolution as stage
from utils.conversations import sync_off_speakers
from utils.stt import conversation_speakers as grouping

UID, CID, NS = 'synthetic-owner', 'synthetic-conversation', 'batch_pipeline_test_centroids'
VECTOR = np.eye(1, 256, dtype=np.float32)[0]


def payload(capture, seconds=2):
    return {
        'schema': schema.SCHEMA,
        'space': schema.SPACE,
        'capture_at': capture,
        'expires_at': schema.deadline(capture),
        'labels': [{'label': 'SPEAKER_00', 'vector': VECTOR.tolist(), 'seconds': seconds}],
    }


def state(level='enhanced'):
    capture = float(int(time.time()) - 10)
    client = StrictFirestore(
        {('users', UID): {'data_protection_level': level}, ('users', UID, 'conversations', CID): {'id': CID}}
    )
    store = SimpleNamespace(client=client, namespace=NS)
    objects = ObjectClient()
    artifacts = ArtifactStore(
        objects,
        bucket='synthetic-batch-bucket',
        namespace=NS,
        authorize=partial(batch_artifact_authorize, store),
        key_for_owner=lambda uid: b'v' * 32,
        register_artifact=partial(batch_artifact_register, store),
    )
    return store, artifacts, objects, capture


def persist(store, artifacts, capture, unit='unit0', seconds=2, *, upload=True):
    item = WorkItem(unit, UID, capture, 'gs://synthetic/audio#123', 10, Priority.FRESH, privacy_generation=0)
    store.client.rows[(NS + '_jobs', unit)] = {
        **asdict(item),
        'state': 'projected',
        'projection_binding': {'owner_id': UID, 'private_cloud_sync_enabled': False},
    }
    store.client.rows[(NS + '_results', unit)] = {
        'projection_parts': {'0': {'conversation_id': CID, 'speaker_scope': f'final:batch:{unit}'}},
    }
    if not upload:
        return item, None
    uri = artifacts.persist_voice_evidence(item, payload(capture, seconds))
    db.publish(store, item, uri, CID)
    return item, uri


def test_conversation_deleted_during_upload_discards_exact_generation(monkeypatch):
    store, artifacts, objects, capture = state()
    item, _ = persist(store, artifacts, capture, upload=False)
    projection_store = SimpleNamespace(
        store=store, ref=lambda table, key: store.client.collection(NS + '_' + table).document(key)
    )
    projector = SimpleNamespace(
        store=projection_store,
        load_result=lambda *a: {'diarization': {'turns': [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 8}]}},
        fetch_audio=lambda item: audio_unit(item.capture_at, b'\x01\x00' * (10 * 16000)).wav,
    )
    store.client.rows[(NS + '_results', item.segment_id)]['result'] = {'result_uri': 'synthetic-result'}
    objects.after_upload = lambda: store.client.rows[('users', UID, 'conversations', CID)].update(deleted=True)
    monkeypatch.setattr(evidence, 'artifacts_for', lambda store: artifacts)
    monkeypatch.setattr(evidence, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(evidence, 'extract_embedding_from_bytes', lambda *a, **kw: VECTOR)
    evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
    assert objects.uploads == 1 and not objects.objects
    assert 'voice_evidence' not in store.client.rows[(NS + '_jobs', item.segment_id)]
    assert any(path[0] == NS + '_artifacts' for path in store.client.rows)


def setup_prepare(monkeypatch):
    store, artifacts, objects, capture = state()
    item, _ = persist(store, artifacts, capture, upload=False)
    projection_store = SimpleNamespace(
        store=store, ref=lambda table, key: store.client.collection(NS + '_' + table).document(key)
    )
    projector = SimpleNamespace(
        store=projection_store,
        load_result=Mock(return_value={'diarization': {'turns': [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 8}]}}),
        fetch_audio=Mock(return_value=audio_unit(item.capture_at, b'\x01\x00' * (10 * 16000)).wav),
    )
    store.client.rows[(NS + '_results', item.segment_id)]['result'] = {'result_uri': 'synthetic-result'}
    embedding = Mock(return_value=VECTOR)
    monkeypatch.setattr(evidence, 'artifacts_for', lambda store: artifacts)
    monkeypatch.setattr(evidence, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(evidence, 'extract_embedding_from_bytes', embedding)
    return store, artifacts, objects, item, projector, embedding


def test_bucket_gate_precedes_audio_and_model_calls(monkeypatch):
    store, _, objects, item, projector, embedding = setup_prepare(monkeypatch)
    objects.soft_delete_policy.retention_duration_seconds = 604800
    evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
    projector.load_result.assert_not_called()
    projector.fetch_audio.assert_not_called()
    embedding.assert_not_called()
    assert not objects.objects and not any(path[0] == NS + '_artifacts' for path in store.client.rows)


def test_bucket_gate_rechecks_after_extraction_and_after_registration(monkeypatch):
    for phase in ('extraction', 'registration'):
        store, artifacts, objects, item, projector, _ = setup_prepare(monkeypatch)
        if phase == 'extraction':

            def embed(*args, **kwargs):
                objects.soft_delete_policy.retention_duration_seconds = 604800
                return VECTOR

            monkeypatch.setattr(evidence, 'extract_embedding_from_bytes', embed)
        else:
            register = artifacts.register_artifact

            def register_then_change(*args):
                register(*args)
                objects.soft_delete_policy.retention_duration_seconds = 604800

            monkeypatch.setattr(artifacts, 'register_artifact', register_then_change)
        evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
        assert not objects.objects and objects.uploads == 0
        assert 'voice_evidence' not in store.client.rows[(NS + '_jobs', item.segment_id)]


def test_publication_commit_with_lost_reply_preserves_object_and_replay(monkeypatch):
    store, artifacts, objects, item, projector, _ = setup_prepare(monkeypatch)
    publish = db.publish

    def commit_then_lose_reply(*args):
        publish(*args)
        raise TimeoutError('synthetic publication response loss')

    monkeypatch.setattr(db, 'publish', commit_then_lose_reply)
    evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
    assert objects.uploads == 1 and len(objects.objects) == 1
    reference = db.load_reference(store, UID, item.segment_id, CID)
    assert reference and artifacts.load_voice_evidence(item, reference[1], expires_at=reference[2])['labels']
    projector.fetch_audio = Mock(side_effect=AssertionError('replay cannot refetch audio'))
    evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
    projector.fetch_audio.assert_not_called()
    assert objects.uploads == 1 and len(objects.objects) == 1


def test_extraction_deadline_covers_exclusive_turn_processing():
    wav = audio_unit(1, b'\x01\x00' * 16000).wav
    extractor = Mock(return_value=VECTOR)
    with pytest.raises(TimeoutError):
        schema.extract(
            wav,
            [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 1}],
            1,
            extractor,
            execution_deadline=time.monotonic() - 1,
        )
    extractor.assert_not_called()


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_encryption_aad_and_no_audio_or_identity_payload(level):
    store, artifacts, objects, capture = state(level)
    item, uri = persist(store, artifacts, capture)
    assert artifacts.load_voice_evidence(item, uri, expires_at=schema.deadline(capture)) == payload(capture)
    assert len(objects.objects) == 1
    assert all('/voice_evidence/' in name and b'SPEAKER_00' not in body for name, (_, body) in objects.objects.items())
    for changed in (
        replace(item, audio_uri=item.audio_uri + '0'),
        replace(item, capture_at=capture + 1),
        replace(item, duration_seconds=9),
        replace(item, conversation_id='other'),
    ):
        with pytest.raises(InvalidTag):
            artifacts.load_voice_evidence(changed, uri, expires_at=schema.deadline(changed.capture_at))
    assert not any('audio_files' in row for row in store.client.rows.values())


def test_schema_refuses_names_audio_wrong_space_dimensions_and_budget():
    data = payload(time.time())
    for key in ('audio', 'person_id', 'name', 'transcript'):
        with pytest.raises(ValueError):
            schema.encode({**data, key: 'forbidden'})
    with pytest.raises(ValueError):
        schema.encode({**data, 'space': 'community-1'})
    with pytest.raises(ValueError):
        schema.encode({**data, 'labels': [{**data['labels'][0], 'vector': [1, 0]}]})
    with pytest.raises(ValueError):
        schema.encode({**data, 'labels': data['labels'] * 33})


def test_full_32_label_float32_payload_fits_64k_without_precision_truncation():
    data = payload(time.time())
    generator = np.random.default_rng(42)
    labels = []
    for i in range(32):
        vector = generator.normal(size=256).astype(np.float32)
        vector /= np.linalg.norm(vector)
        labels.append({'label': f'SPEAKER_{i:02}', 'vector': vector.tolist(), 'seconds': 15})
    data['labels'] = labels
    body = schema.encode(data)
    assert len(body) < schema.MAX_BYTES
    assert schema.decode(body) == data


def test_exclusive_union_measures_once_and_never_embeds_overlap():
    wav = audio_unit(1, b'\x01\x00' * (10 * 16000)).wav
    turns = [
        {'speaker': 'SPEAKER_00', 'start': 0, 'end': 8},
        {'speaker': 'SPEAKER_00', 'start': 0, 'end': 8},
        {'speaker': 'SPEAKER_01', 'start': 4, 'end': 10},
    ]
    sizes = []

    def extract(clip):
        with wave.open(io.BytesIO(clip), 'rb') as source:
            sizes.append(source.getnframes() / source.getframerate())
        return VECTOR

    actual = schema.extract(wav, turns, 1, extract)
    assert sizes == [4, 2]
    assert [row['seconds'] for row in actual['labels']] == [4, 2]


@pytest.mark.parametrize('policy', ['soft_delete', 'unknown_soft_delete', 'hold', 'retention', 'unreadable'])
def test_voice_creation_refuses_unverified_permanent_deletion_policy(monkeypatch, policy):
    store, artifacts, objects, capture = state()
    if policy == 'soft_delete':
        objects.soft_delete_policy.retention_duration_seconds = 604800
    elif policy == 'unknown_soft_delete':
        objects.soft_delete_policy.retention_duration_seconds = None
    elif policy == 'hold':
        objects.default_event_based_hold = True
    elif policy == 'retention':
        objects.retention_period = 3600
    else:

        def denied(**kwargs):
            raise PermissionError('synthetic metadata read denied')

        monkeypatch.setattr(objects, 'reload', denied)
    with pytest.raises(PermissionError):
        persist(store, artifacts, capture)
    assert not objects.objects
    assert not any(path[0] == NS + '_artifacts' for path in store.client.rows)


def test_capture_expiry_and_finalization_shortening_refuse_before_download(monkeypatch):
    store, artifacts, objects, capture = state()
    item, uri = persist(store, artifacts, capture)
    ref = db.load_reference(store, UID, item.segment_id, CID)
    assert ref and ref[2] == pytest.approx(schema.deadline(capture), abs=0.000001)
    metadata = store.client.rows[
        (NS + '_artifacts', store.client.rows[(NS + '_jobs', item.segment_id)]['voice_evidence'])
    ]
    shortened = schema.deadline(capture, capture + 20)
    metadata['cleanup_after'] = datetime.fromtimestamp(shortened, timezone.utc)
    monkeypatch.setattr(db.time, 'time', lambda: shortened)
    assert db.load_reference(store, UID, item.segment_id, CID) is None
    with pytest.raises(PermissionError):
        artifacts.load_voice_evidence(item, uri, expires_at=shortened)
    monkeypatch.setattr(db.time, 'time', lambda: schema.deadline(capture))
    with pytest.raises(PermissionError):
        artifacts.load_voice_evidence(item, uri, expires_at=schema.deadline(capture))
    assert objects.downloads == 0


def test_privacy_generation_and_conversation_binding_are_checked_again(monkeypatch):
    store, artifacts, _, capture = state()
    item, _ = persist(store, artifacts, capture)
    assert db.load_reference(store, UID, item.segment_id, 'foreign') is None
    conversation = fixture_conversation([item.segment_id])
    _, _, validate = evidence.load_vectors(UID, conversation, time.monotonic() + 10, store=store, artifacts=artifacts)
    store.client.rows[('batch_pipeline_privacy', privacy_owner_key(UID))] = {'generation': 1}
    with pytest.raises(BatchPrivacyBlocked):
        validate()


def fixture_conversation(units):
    return Conversation(
        id=CID,
        created_at=datetime.now(timezone.utc),
        structured=Structured(),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        private_cloud_sync_enabled=False,
        audio_files=[],
        transcript_segments=[
            TranscriptSegment(
                id=f's{i}',
                text='Synthetic voice.',
                speaker='SPEAKER_00',
                speaker_id=i,
                is_user=False,
                start=i * 2,
                end=i * 2 + 2,
                provider_speaker={'scope': f'final:batch:{unit}', 'id': 0, 'provider': 'pyannote'},
                speaker_id_scope=f'final:batch:{unit}',
            )
            for i, unit in enumerate(units)
        ],
    )


def test_materialized_centroid_copies_are_bounded_by_labels_not_sentence_count(monkeypatch):
    store, artifacts, _, capture = state()
    item, _ = persist(store, artifacts, capture)
    conversation = fixture_conversation([item.segment_id] * 1500)
    vectors, seconds, _ = evidence.load_vectors(
        UID, conversation, time.monotonic() + 10, store=store, artifacts=artifacts
    )
    assert len({id(vector) for vector in vectors.values()}) == 1
    assert sum(seconds.values()) == 2
    source_vector = next(iter(vectors.values()))
    normalize = grouping._unit_vector
    normalized_source = []
    live_weighted, peak_weighted = [], []

    class TrackedVector(np.ndarray):
        def __mul__(self, weight):
            result = np.asarray(super().__mul__(weight))
            live_weighted[:] = [reference for reference in live_weighted if reference() is not None]
            live_weighted.append(weakref.ref(result))
            peak_weighted.append(len(live_weighted))
            return result

    def count_source(value):
        if value is source_vector:
            normalized_source.append(True)
        result = normalize(value)
        return result.view(TrackedVector) if result is not None else None

    monkeypatch.setattr(grouping, '_unit_vector', count_source)
    result = grouping.resolve_conversation_speakers(
        conversation.transcript_segments,
        vectors,
        embedding_seconds=seconds,
        grouping='batch_authoritative',
        provider_keys={s.id: ('unit', 0) for s in conversation.transcript_segments},
    )
    assert result and len(set(result.speaker_ids.values())) == 1
    assert len(normalized_source) == 1
    assert max(peak_weighted) <= 4  # Bound live arrays even for 1,500 sentences.


@pytest.mark.parametrize('evidence_mode', ['off', 'serve'])
@pytest.mark.parametrize('identity', ['user', 'synthetic-person'])
def test_sync_off_four_unit_naming_reuses_policy_without_audio_cache(monkeypatch, evidence_mode, identity):
    store, artifacts, objects, capture = state()
    units = [f'unit{i}' for i in range(4)]
    for i, unit in enumerate(units):
        persist(store, artifacts, capture + i, unit)
    conversation = fixture_conversation(units)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', evidence_mode)
    monkeypatch.setattr(stage.speaker_evidence, '_roster', lambda *a: [])
    monkeypatch.setattr(stage.speaker_evidence.storage, 'store_evidence', lambda *a, **kw: None)
    monkeypatch.setattr(
        sync_off_speakers,
        'load_vectors',
        lambda uid, conv, deadline: evidence.load_vectors(uid, conv, deadline, store=store, artifacts=artifacts),
    )
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(stage, 'resolution_enabled', lambda: True)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda uid, **kw: {identity: VECTOR})
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', lambda *a: pytest.fail('no durable cache'))
    monkeypatch.setattr(stage, 'upload_speaker_embedding_cache', lambda *a: pytest.fail('no durable cache'))
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', lambda *a, **kw: pytest.fail('no audio_files'))
    stage.resolve_speakers_for_processing(UID, conversation)
    assert all(s.is_user if identity == 'user' else s.person_id == identity for s in conversation.transcript_segments)
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 1
    assert not conversation.audio_files and objects.uploads == 4
    assert all('/voice_evidence/' in name for name in objects.objects)


def test_sync_off_subswitch_and_parent_kill_switch(monkeypatch):
    monkeypatch.delenv(flags.SYNC_OFF_CENTROIDS_ENV, raising=False)
    monkeypatch.delenv(flags.BATCH_CONVERSATION_SPEAKERS_ENV, raising=False)
    assert flags.sync_off_enabled()
    monkeypatch.setenv(flags.SYNC_OFF_CENTROIDS_ENV, 'false')
    assert not flags.sync_off_enabled()
    monkeypatch.setenv(flags.SYNC_OFF_CENTROIDS_ENV, 'true')
    monkeypatch.setenv(flags.BATCH_CONVERSATION_SPEAKERS_ENV, 'false')
    assert not flags.sync_off_enabled()

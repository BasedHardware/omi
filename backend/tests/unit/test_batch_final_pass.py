"""Exercise enrichment -> batch artifacts -> store proof -> shared final pass -> labels."""

import io
import wave
from dataclasses import asdict
import hashlib
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import fakeredis
import numpy as np
import pytest

from config import batch_conversation_speakers as flags
from config.policy import ProjectionPolicy
from database import batch_final_pass as references
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from models.audio_file import AudioFile
from models.conversation import Conversation
from models.diarization import OMI_EMBEDDING_SPACE
from models.structured import Structured
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, Priority
from utils.batch_pipeline.projection_segments import projection_segments
from utils.conversations import final_pass_batch as batch, final_pass_pyannote as final, speaker_resolution as stage

UID = 'synthetic-batch-owner'
CAPTURE = 1000.0


def wav(pcm):
    output = io.BytesIO()
    with wave.open(output, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(16000)
        file.writeframes(pcm)
    return output.getvalue()


@pytest.fixture
def lane(monkeypatch):
    monkeypatch.setenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', 'true')
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'true')
    monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', '100')
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_BACKEND', 'legacy_ahc')
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true')
    monkeypatch.setattr(batch, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(stage.speaker_evidence, 'begin', lambda *_: None)
    monkeypatch.setattr(stage.speaker_evidence, 'finish', lambda *_: None)
    binding = ProjectionBinding(
        UID, 'job', 'content', ('unit-a', 'unit-b'), private_cloud_sync_enabled=True, record_origin=True
    )
    payload = {
        'audio_seconds': 8,
        'words_provider': 'parakeet',
        'words': [{'word': 'Hello', 'timestamp': [0.2, 2.8]}, {'word': 'there.', 'timestamp': [3, 5.8]}],
        'diarization': {'turns': [{'start': 0, 'end': 8, 'speaker': 'SPEAKER_00'}]},
    }
    items = {
        unit: WorkItem(unit, UID, CAPTURE + i * 8, f'gs://fake/{unit}#1', 8, Priority.FRESH, privacy_generation=0)
        for i, unit in enumerate(binding.segment_ids)
    }
    audio = {unit: bytes([i + 1, 0]) * (8 * 16000) for i, unit in enumerate(binding.segment_ids)}
    segments = [s for item in items.values() for s in projection_segments(item, binding, payload)]
    for i, segment in enumerate(segments):
        # Stored offsets are deliberately unrelated to any audio clock.
        segment.start, segment.end = 900 + i * 8, 906 + i * 8
    conversation = Conversation(
        id='conversation',
        created_at=datetime.fromtimestamp(CAPTURE, timezone.utc),
        started_at=datetime.fromtimestamp(CAPTURE - 200, timezone.utc),
        finished_at=datetime.fromtimestamp(CAPTURE + 16, timezone.utc),
        structured=Structured(),
        transcript_segments=segments,
        private_cloud_sync_enabled=True,
        audio_files=[
            AudioFile(id='f', uid=UID, conversation_id='conversation', chunk_timestamps=[CAPTURE], duration=16)
        ],
    )
    receipts, fallbacks, gpu, resolutions, reads = {}, [], [], [], []
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *_: receipts)

    def resolver(uid, current, **kwargs):
        resolutions.append(True)
        for s in current.transcript_segments:
            s.assign_resolved_speaker(s.speaker_id, f'final:batch:conversation:{current.id}')
            if s.speaker_label_source != 'manual':
                s.person_id = 'resolver-person'
                s.speaker_label_source = 'auto'

    monkeypatch.setattr(stage, '_resolve', resolver)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': np.array([1.0, 0.0])})
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: object())

    def reference(store, uid, unit, cid):
        reads.append(unit)
        return items[unit], 'gs://fake/result#1', binding, ProjectionPolicy()

    monkeypatch.setattr(batch, 'load_reference', reference)
    monkeypatch.setattr(
        batch,
        'artifacts_for',
        lambda _: SimpleNamespace(load_result=lambda *_: payload, fetch_audio=lambda item: wav(audio[item.segment_id])),
    )
    chunks = [{'path': 'chunk.batch.enc', 'timestamp': CAPTURE, 'generation': 1}]
    chunk_pcm = {'chunk.batch.enc': audio['unit-a'] + audio['unit-b']}

    def session(*_):
        return SimpleNamespace(chunks=chunks, deadline=float('inf'))

    def iterator(uid, cid, wanted, *, session, chunk_filter):
        for chunk in session.chunks:
            if not chunk_filter(chunk):
                continue
            yield chunk['timestamp'], chunk_pcm[chunk['path']]

    monkeypatch.setattr(batch, 'AudioChunkReadSession', session)
    monkeypatch.setattr(batch, 'iter_audio_chunk_pcm', iterator)
    monkeypatch.setattr(batch, '_reserve_budget', lambda _: True)
    monkeypatch.setattr(batch, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    monkeypatch.setattr(final, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    monkeypatch.setattr(final, 'get_diarizer_backend', lambda: object())

    def diarize(pcm, *_args, **_kwargs):
        assert _args[0].backend == 'pyannote'
        gpu.append(pcm)
        return {
            'turns': [{'start': 0, 'end': 16, 'speaker': 'voice'}],
            'overlaps': [],
            'centroids': {'voice': {'embedding': [1.0, 0.0], 'evidence_seconds': 12}},
            'embedding_space': OMI_EMBEDDING_SPACE,
            'version': 'test',
            'provenance': {'backend': 'pyannote'},
        }

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize)
    return SimpleNamespace(
        conversation=conversation,
        items=items,
        audio=audio,
        payload=payload,
        binding=binding,
        receipts=receipts,
        fallbacks=fallbacks,
        gpu=gpu,
        resolutions=resolutions,
        reads=reads,
        chunks=chunks,
        chunk_pcm=chunk_pcm,
    )


def resolve(lane):
    assert stage.resolve_speakers_for_processing(UID, lane.conversation)
    return lane.conversation.transcript_segments


def test_batch_owner_admitted_before_summary_on_unit_word_clock(lane):
    original = [(s.id, s.text, s.start, s.end) for s in lane.conversation.transcript_segments]
    segments = resolve(lane)
    assert len(lane.gpu) == 1 and lane.resolutions
    assert all(s.is_user and s.person_id is None for s in segments)
    assert all(s.speaker_id_scope == 'final:batch:conversation:conversation' for s in segments)
    assert all(s.speaker_label_source == 'auto' for s in segments)
    assert [(s.id, s.text, s.start, s.end) for s in segments] == original
    assert len({s.speaker_id for s in segments}) == 1
    # IDs replay exactly as projection, including the unit partition.
    assert segments[0].id == str(uuid5(NAMESPACE_URL, 'batch:unit-a:0'))


@pytest.mark.parametrize('key', ['BATCH_FINAL_PASS_ENABLED', 'BATCH_CONVERSATION_SPEAKERS_ENABLED'])
def test_flag_off_retains_current_resolver_and_never_calls_diarizer(lane, monkeypatch, key):
    # Establish that this input exercises the feature, then compare the rollback.
    from copy import deepcopy

    admitted = deepcopy(lane.conversation)
    assert all(s.is_user for s in resolve(lane))
    lane.conversation = admitted
    lane.gpu.clear()
    lane.reads.clear()
    monkeypatch.setenv(key, 'false')
    resolve(lane)
    assert not lane.gpu and not lane.reads
    if key == 'BATCH_FINAL_PASS_ENABLED':
        assert all(s.person_id == 'resolver-person' for s in lane.conversation.transcript_segments)


@pytest.mark.parametrize('proven_store', ['live', 'sync'])
def test_per_store_pcm_proof_and_unplaceable_unit_abstention(lane, proven_store):
    # Two independent stores overlap in wall time; only one matches this unit.
    lane.chunks.append({'path': 'chunk.opus.enc', 'timestamp': CAPTURE, 'generation': 2})
    matching = lane.audio['unit-a'] + b'\x04\0' * (8 * 16000)
    other = b'\x03\0' * (16 * 16000)
    lane.chunk_pcm['chunk.opus.enc'] = matching if proven_store == 'sync' else other
    lane.chunk_pcm['chunk.batch.enc'] = matching if proven_store == 'live' else other
    segments = resolve(lane)
    assert segments[0].is_user
    assert segments[1].person_id == 'resolver-person' and not segments[1].is_user
    assert lane.gpu == [matching]
    assert lane.fallbacks


def test_manual_receipt_beats_final_labels_and_reserves_owner(lane):
    sid = lane.conversation.transcript_segments[0].id
    lane.receipts['segments'] = {sid: {'is_user': True, 'person_id': None, 'source': 'manual', 'generation': 1}}
    segments = resolve(lane)
    assert lane.gpu
    assert segments[0].is_user and segments[0].speaker_label_source == 'manual'
    assert not segments[1].is_user  # Joint naming sees the receipt's reserved owner.
    assert segments[1].speaker_identity_status == 'no_match'


def test_too_long_skips_gpu_and_keeps_resolver_labels(lane):
    # The sparse span itself exceeds the limit; no huge test allocation needed.
    lane.chunks.append({'path': 'late.batch.enc', 'timestamp': CAPTURE + 7201, 'generation': 1})
    lane.conversation.audio_files[0].chunk_timestamps.append(CAPTURE + 7201)
    lane.chunk_pcm['late.batch.enc'] = b'\x01\0'
    before = batch.OUTCOMES.labels(lane='batch', outcome='failed:too_long')._value.get()
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert not lane.gpu and lane.fallbacks
    assert batch.OUTCOMES.labels(lane='batch', outcome='failed:too_long')._value.get() == before + 1


def test_diarizer_error_falls_back_to_current_resolver(lane, monkeypatch):
    def failed(*_args, **_kwargs):
        lane.gpu.append('attempt')
        raise RuntimeError('synthetic diarizer failure')

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', failed)
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert lane.gpu == ['attempt']
    assert any(f['from_mode'] == 'whole_conversation_diarizer' for f in lane.fallbacks)


def test_revocation_during_gpu_does_not_publish(lane, monkeypatch):
    original = batch.load_reference
    monkeypatch.setattr(batch, 'load_reference', lambda *args: None if lane.gpu else original(*args))
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert lane.gpu and lane.fallbacks


def test_gap_words_abstain_whole_segment(lane, monkeypatch):
    original = final.diarize_with_speech_compaction

    def gap(*args, **kwargs):
        output = original(*args, **kwargs)
        output['turns'][0]['start'] = 4
        return output

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', gap)
    segments = resolve(lane)
    assert segments[0].person_id == 'resolver-person'
    assert segments[1].is_user


def test_sync_off_remains_on_existing_centroid_resolver(lane):
    lane.conversation.private_cloud_sync_enabled = False
    resolve(lane)
    assert lane.resolutions and not lane.gpu and not lane.reads


def test_cohort_uses_existing_hash_bucket_and_invalid_percent_refuses(monkeypatch, lane):
    bucket = flags.cohort_bucket(UID, '')
    monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', str(bucket))
    assert not flags.final_pass_enabled_for(UID, lane.conversation.transcript_segments)
    monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', str(bucket + 0.01))
    assert flags.final_pass_enabled_for(UID, lane.conversation.transcript_segments)
    for invalid in ('nan', 'inf', 'invalid', '-1', '0'):
        monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', invalid)
        assert not flags.final_pass_enabled_for(UID, lane.conversation.transcript_segments)


def test_budget_is_atomic_and_charges_daily_hourly_and_retries(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    server = fakeredis.FakeServer()
    monkeypatch.setattr(batch, 'create_bounded_redis_client', lambda _: fakeredis.FakeRedis(server=server))
    monkeypatch.setenv('BATCH_FINAL_PASS_DAILY_AUDIO_HOURS', str(3 / 3600))
    monkeypatch.setenv('BATCH_FINAL_PASS_HOURLY_AUDIO_HOURS', '100')
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(batch._reserve_budget, [1] * 16)) == 3
    assert not batch._reserve_budget(0.001)


@pytest.mark.parametrize('key', ['BATCH_FINAL_PASS_DAILY_AUDIO_HOURS', 'BATCH_FINAL_PASS_HOURLY_AUDIO_HOURS'])
def test_invalid_budget_and_redis_error_fail_closed(monkeypatch, key):
    monkeypatch.setenv(key, 'nan')
    assert not batch._reserve_budget(1)
    monkeypatch.setenv(key, '100')
    monkeypatch.setattr(batch, 'create_bounded_redis_client', lambda _: (_ for _ in ()).throw(ConnectionError()))
    assert not batch._reserve_budget(1)


@pytest.fixture
def reference_store(lane, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    unit = 'unit-a'
    item = lane.items[unit]
    ns = 'batch_pipeline_dev'
    client = StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard'},
            ('users', UID, 'conversations', 'conversation'): {'id': 'conversation'},
            (ns + '_jobs', unit): {**asdict(item), 'projection_binding': asdict(lane.binding)},
            (ns + '_results', unit): {
                'projection_parts': {'0': {'conversation_id': 'conversation', 'speaker_scope': 'final:batch:unit-a'}},
                'result': {'result_uri': 'gs://fake/result#1'},
            },
        }
    )
    for kind, uri in (('audio', item.audio_uri), ('results', 'gs://fake/result#1')):
        key = hashlib.sha256(f"{unit}\0{uri.split('#')[0]}".encode()).hexdigest()
        client.rows[(ns + '_artifacts', key)] = {
            'kind': kind,
            'owner_id': UID,
            'segment_id': unit,
            'privacy_generation': 0,
            'uri': uri,
            'cleanup_after': datetime.now(timezone.utc) + timedelta(hours=1),
        }
    return FirestoreStore(ns, firestore_client=client), client


def test_reference_is_read_only_and_requires_bound_owner_and_conversation(reference_store):
    store, client = reference_store
    before = deepcopy(client.rows)
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is not None
    assert references.load_reference(store, 'other-owner', 'unit-a', 'conversation') is None
    assert references.load_reference(store, UID, 'unit-a', 'other-conversation') is None
    assert client.rows == before


@pytest.mark.parametrize('refusal', ['expired', 'erasing', 'generation', 'wrong_kind'])
def test_reference_refuses_expired_erasing_or_changed_artifacts(reference_store, refusal):
    store, client = reference_store
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is not None
    for path, row in client.rows.items():
        if path[0].endswith('_artifacts'):
            row.update(
                {
                    'expired': {'cleanup_after': datetime.now(timezone.utc) - timedelta(seconds=1)},
                    'erasing': {'erasure_requested': True},
                    'generation': {'privacy_generation': 1},
                    'wrong_kind': {'kind': 'voice_evidence'},
                }[refusal]
            )
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is None


def test_reference_privacy_deletion_fence(reference_store):
    store, client = reference_store
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is not None
    client.rows[('users', UID, 'conversations', 'conversation')]['deleted'] = True
    with pytest.raises(BatchPrivacyBlocked):
        references.load_reference(store, UID, 'unit-a', 'conversation')


def test_final_labels_survive_speaker_evidence_projection(lane, monkeypatch):
    def evidence_projection(_token, _uid, conversation, _receipt):
        for segment in conversation.transcript_segments:
            segment.is_user = False
            segment.person_id = 'evidence-person'

    monkeypatch.setattr(stage.speaker_evidence, 'finish', evidence_projection)
    assert all(s.is_user for s in resolve(lane))


def test_budget_refusal_retains_resolver_labels_before_gpu(lane, monkeypatch):
    monkeypatch.setattr(batch, '_reserve_budget', lambda _: False)
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert not lane.gpu and lane.fallbacks


def test_identity_only_retry_keeps_its_budget_without_whole_pass(lane):
    assert stage.resolve_speakers_for_processing(UID, lane.conversation, budget_seconds=5, max_embedding_attempts=24)
    assert lane.resolutions and not lane.gpu and not lane.reads


def test_incompatible_final_embedding_space_keeps_resolver_labels(lane, monkeypatch):
    original = final.diarize_with_speech_compaction

    def incompatible(*args, **kwargs):
        output = original(*args, **kwargs)
        output['embedding_space'] = 'incompatible'
        return output

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', incompatible)
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert lane.gpu and lane.fallbacks


def test_pcm_iterator_filters_store_objects_before_timestamp_selection(monkeypatch):
    from utils.other import audio_chunks

    chunks = [{'path': 'store.batch.enc', 'timestamp': CAPTURE}, {'path': 'store.opus.enc', 'timestamp': CAPTURE}]
    fetched = []

    def fetch(path):
        fetched.append(path)
        return b'\x01\0'

    session = SimpleNamespace(chunks=chunks, cache={}, fetch=fetch)
    monkeypatch.setattr(audio_chunks.storage, 'get_private_cloud_sync_bucket', lambda: object())
    result = list(
        audio_chunks.iter_audio_chunk_pcm(
            UID,
            'conversation',
            lambda *_: True,
            session=session,
            chunk_filter=lambda chunk: chunk['path'].endswith('.opus.enc'),
        )
    )
    assert result == [(CAPTURE, b'\x01\0')]
    assert fetched == ['store.opus.enc']  # Equal timestamps cannot select the other store.

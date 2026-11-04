"""Exercise enrichment -> batch artifacts -> capture clock -> shared final pass -> labels."""

import io
import wave
from dataclasses import asdict, replace
import hashlib
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import httpx
import time
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
from utils.batch_pipeline.projection_parts import split_result
from utils.conversations import final_pass_batch as batch, final_pass_pyannote as final, speaker_resolution as stage

UID = 'synthetic-batch-owner'
CAPTURE = 1000.0
REAL_RESERVE_BUDGET = batch._reserve_budget


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
        'speech_seconds': 8,
        'speech_spans': [{'start': 0, 'end': 8}],
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

    def result(item, uri, *, read_budget):
        read_budget.begin()
        read_budget.reserve(1024)
        return payload

    def fetch(item, *, read_budget):
        read_budget.begin()
        body = wav(audio[item.segment_id])
        read_budget.reserve(len(body))
        return body

    artifacts = SimpleNamespace(load_result=result, fetch_audio=fetch)
    monkeypatch.setattr(batch, 'artifacts_for', lambda _: artifacts)
    monkeypatch.setattr(batch, '_reserve_budget', lambda _: True)
    monkeypatch.setattr(batch, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    monkeypatch.setattr(final, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    monkeypatch.setattr(final, 'get_diarizer_backend', lambda: object())

    def diarize(pcm, *_args, **_kwargs):
        assert _args[0].backend == 'pyannote'
        if _args[0].reserve_attempt is not None and not _args[0].reserve_attempt(len(pcm) / 32000):
            raise RuntimeError('diarizer_attempt_budget')
        gpu.append(pcm)
        return {
            'turns': [{'start': 0, 'end': len(pcm) / 32000, 'speaker': 'voice'}],
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
        artifacts=artifacts,
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


@pytest.mark.parametrize('sync_on', [True, False])
@pytest.mark.parametrize('record_origin', [True, False])
def test_staged_pcm_and_projection_ids_with_speech_spans(lane, sync_on, record_origin):
    lane.conversation.private_cloud_sync_enabled = sync_on
    lane.conversation.audio_files = []  # No retained playback audio is required.
    lane.binding = replace(lane.binding, private_cloud_sync_enabled=sync_on, record_origin=record_origin)
    # The reference loader closes over the original fixture binding, so replace it.
    original_reference = batch.load_reference

    def reference(*args):
        item, uri, _, _ = original_reference(*args)
        return item, uri, lane.binding, ProjectionPolicy(authoritative_labels=True)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(batch, 'load_reference', reference)
        parts = [
            (part, output)
            for item in lane.items.values()
            for part, output in ([(item, lane.payload)] if record_origin else split_result(item, lane.payload))
        ]
        expected = [
            s
            for part, output in parts
            for s in projection_segments(
                part,
                lane.binding,
                output,
                batch_segment_id=('unit-a' if part.capture_at < CAPTURE + 8 else 'unit-b'),
                policy=ProjectionPolicy(authoritative_labels=True),
            )
        ]
        for i, segment in enumerate(expected):
            segment.start, segment.end = 900 + i * 8, 906 + i * 8
        lane.conversation.transcript_segments = expected
        before = [(s.id, s.text, s.start, s.end) for s in expected]
        segments = resolve(lane)
    assert all(s.is_user for s in segments)
    assert lane.gpu == [lane.audio['unit-a'] + lane.audio['unit-b']]
    assert [(s.id, s.text, s.start, s.end) for s in segments] == before
    part_id = 'unit-a' if record_origin else uuid5(NAMESPACE_URL, 'batch-part:unit-a:0').hex
    assert segments[0].id == str(uuid5(NAMESPACE_URL, f'batch:{part_id}:0'))


@pytest.mark.parametrize(
    'refusal', ['missing', 'expired', 'privacy', 'read_bytes', 'read_objects', 'read_time', 'segment']
)
def test_incomplete_coverage_keeps_all_resolver_labels(lane, monkeypatch, refusal):
    original = batch.load_reference

    def reference(*args):
        if args[2] == 'unit-b':
            if refusal in ('missing', 'expired'):
                return None
            if refusal == 'privacy':
                raise BatchPrivacyBlocked('synthetic privacy fence')
        return original(*args)

    monkeypatch.setattr(batch, 'load_reference', reference)
    original_fetch = lane.artifacts.fetch_audio

    def fetch(item, *, read_budget):
        assert read_budget.max_bytes == 320 * 1024 * 1024
        assert read_budget.max_objects == 512
        assert 170 < read_budget.deadline - time.monotonic() <= 180
        if item.segment_id == 'unit-b':
            if refusal == 'read_bytes':
                read_budget.reserve(read_budget.max_bytes)
            elif refusal == 'read_objects':
                read_budget.objects = read_budget.max_objects
            elif refusal == 'read_time':
                read_budget.deadline = time.monotonic() - 1
        return original_fetch(item, read_budget=read_budget)

    monkeypatch.setattr(lane.artifacts, 'fetch_audio', fetch)
    if refusal == 'segment':
        lane.conversation.transcript_segments[-1].id = 'cannot-reconstruct'
    metric = batch.OUTCOMES.labels(
        lane='batch', outcome=('failed_read_budget' if refusal.startswith('read_') else 'failed_incomplete_coverage')
    )
    before = metric._value.get()
    assert all(s.person_id == 'resolver-person' and not s.is_user for s in resolve(lane))
    assert not lane.gpu and lane.fallbacks
    assert metric._value.get() == before + 1
    assert lane.fallbacks[-1]['reason'] == ('recovery_budget' if refusal.startswith('read_') else 'unavailable')


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
    lane.items['unit-b'] = replace(lane.items['unit-b'], capture_at=CAPTURE + 7201)
    before = batch.OUTCOMES.labels(lane='batch', outcome='failed_too_long')._value.get()
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert not lane.gpu and lane.fallbacks
    assert batch.OUTCOMES.labels(lane='batch', outcome='failed_too_long')._value.get() == before + 1


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


def test_sync_off_reference_available_until_24_hours_after_projection(reference_store, monkeypatch):
    store, client = reference_store
    job = client.rows[(store.namespace + '_jobs', 'unit-a')]
    job['projection_binding']['private_cloud_sync_enabled'] = False
    projected = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    due = projected + timedelta(hours=24)
    for path, row in client.rows.items():
        if path[0].endswith('_artifacts'):
            row['cleanup_after'] = due

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.current

    Clock.current = due - timedelta(microseconds=1)
    monkeypatch.setattr(references, 'datetime', Clock)
    before = deepcopy(client.rows)
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is not None
    Clock.current = due
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is None
    assert client.rows == before  # Reading never renews retention.


@pytest.mark.parametrize('limited_by', ['daily', 'hourly', 'requests'])
@pytest.mark.parametrize('allowed_attempts', [1, 2])
def test_each_http_retry_is_charged_before_request(lane, monkeypatch, limited_by, allowed_attempts):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(batch, 'create_bounded_redis_client', lambda _: fakeredis.FakeRedis(server=server))
    # The fixture stubs admission; restore the real Redis reservation function.
    monkeypatch.setattr(batch, '_reserve_budget', REAL_RESERVE_BUDGET)
    for key in ('DAILY_AUDIO_HOURS', 'HOURLY_AUDIO_HOURS'):
        monkeypatch.setenv('BATCH_FINAL_PASS_' + key, '100')
    monkeypatch.setenv('BATCH_FINAL_PASS_HOURLY_REQUESTS', '100')
    if limited_by == 'requests':
        monkeypatch.setenv('BATCH_FINAL_PASS_HOURLY_REQUESTS', str(allowed_attempts))
    else:
        monkeypatch.setenv('BATCH_FINAL_PASS_' + limited_by.upper() + '_AUDIO_HOURS', str(16 * allowed_attempts / 3600))
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'false')
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs['content'])
        response = httpx.Response(
            503 if len(calls) == 1 else 200,
            request=httpx.Request('POST', url),
            json={
                'turns': [{'start': 0, 'end': 16, 'speaker': 'voice'}],
                'overlaps': [],
                'centroids': {'voice': {'embedding': [1.0, 0.0], 'evidence_seconds': 12}},
                'embedding_space': OMI_EMBEDDING_SPACE,
                'version': 'test',
                'provenance': {'backend': 'pyannote'},
            },
        )
        return response

    monkeypatch.setattr(httpx, 'post', post)
    # Exercise the real HTTP adapter rather than the lane's fake diarizer.
    monkeypatch.setattr(
        final, 'diarize_with_speech_compaction', lambda pcm, backend, *a, **kw: backend.diarize(pcm, **kw).model_dump()
    )
    segments = resolve(lane)
    assert len(calls) == allowed_attempts
    assert all(s.is_user for s in segments) == (allowed_attempts == 2)
    client = fakeredis.FakeRedis(server=server)
    hour = next(key for key in client.scan_iter('batch-final-pass:hour:*'))
    day = next(key for key in client.scan_iter('batch-final-pass:day:*'))
    assert int(client.hget(hour, 'calls')) == allowed_attempts
    assert int(client.hget(hour, 'audio_ms')) == 16000 * allowed_attempts
    assert int(client.hget(day, 'audio_ms')) == 16000 * allowed_attempts
    if allowed_attempts == 1:
        assert all(s.person_id == 'resolver-person' for s in segments)
        assert lane.fallbacks


def test_capture_clock_places_staged_pcm_and_words_across_gap(lane, monkeypatch):
    lane.items['unit-b'] = replace(lane.items['unit-b'], capture_at=CAPTURE + 10)
    received = []
    original = batch.run_final_pass

    def run(pcm, words, *args, **kwargs):
        received.extend(words)
        return original(pcm, words, *args, **kwargs)

    monkeypatch.setattr(batch, 'run_final_pass', run)
    assert all(s.is_user for s in resolve(lane))
    assert lane.gpu == [lane.audio['unit-a'] + b'\0' * (2 * 32000) + lane.audio['unit-b']]
    assert [w['timestamp'] for w in received] == [[0.2, 2.8], [3, 5.8], [10.2, 12.8], [13, 15.8]]


def test_overlapping_incompatible_unit_clocks_keep_all_labels(lane):
    lane.items['unit-b'] = replace(lane.items['unit-b'], capture_at=CAPTURE + 4)
    metric = batch.OUTCOMES.labels(lane='batch', outcome='failed_incomplete_coverage')
    before = metric._value.get()
    assert all(s.person_id == 'resolver-person' for s in resolve(lane))
    assert not lane.gpu and lane.fallbacks
    assert metric._value.get() == before + 1


def test_staged_read_budget_can_exceed_playback_64_mib_limit(lane, monkeypatch):
    original = lane.artifacts.fetch_audio

    def fetch(item, *, read_budget):
        # Account for a large object without allocating it in a fast unit test.
        read_budget.reserve(65 * 1024 * 1024)
        return original(item, read_budget=read_budget)

    monkeypatch.setattr(lane.artifacts, 'fetch_audio', fetch)
    assert all(s.is_user for s in resolve(lane))
    assert len(lane.gpu) == 1

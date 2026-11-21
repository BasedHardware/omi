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
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
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
REAL_LOAD_PRINTS = stage.load_voiceprints_for_resolution


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

    def reference(store, uid, unit, cid, **kwargs):
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

    def reference(*args, **kwargs):
        item, uri, _, _ = original_reference(*args, **kwargs)
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


@pytest.mark.parametrize('refusal', ['missing', 'expired', 'privacy', 'read_bytes', 'read_objects'])
def test_incomplete_coverage_keeps_all_resolver_labels(lane, monkeypatch, refusal):
    original = batch.load_reference

    def reference(*args, **kwargs):
        if args[2] == 'unit-b':
            if refusal in ('missing', 'expired'):
                return None
            if refusal == 'privacy':
                raise BatchPrivacyBlocked('synthetic privacy fence')
        return original(*args, **kwargs)

    monkeypatch.setattr(batch, 'load_reference', reference)
    original_fetch = lane.artifacts.fetch_audio

    def fetch(item, *, read_budget):
        assert read_budget.max_bytes == 320 * 1024 * 1024
        assert read_budget.max_objects == 3 * batch.MAX_UNITS
        assert 170 < read_budget.deadline - time.monotonic() <= 180
        if item.segment_id == 'unit-b':
            if refusal == 'read_bytes':
                read_budget.reserve(read_budget.max_bytes)
            elif refusal == 'read_objects':
                read_budget.objects = read_budget.max_objects
        return original_fetch(item, read_budget=read_budget)

    monkeypatch.setattr(lane.artifacts, 'fetch_audio', fetch)
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
    monkeypatch.setattr(
        batch, 'load_reference', lambda *args, **kwargs: None if lane.gpu else original(*args, **kwargs)
    )
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
    store = FirestoreStore(ns, firestore_client=client)
    # StrictFirestore models transaction ordering, not transport lifecycle.
    # Deadline/transport options are exercised with the real SDK below.
    from database import batch_pipeline_reads

    snapshot = batch_pipeline_reads.read_snapshot

    def read_snapshot(selected_store, body, budget):
        if selected_store is store:
            return store.run(body)
        return snapshot(selected_store, body, budget)

    monkeypatch.setattr(batch_pipeline_reads, 'read_snapshot', read_snapshot)
    return store, client


def test_reference_is_read_only_and_requires_bound_owner_and_conversation(reference_store):
    store, client = reference_store
    before = deepcopy(client.rows)
    assert references.load_reference(store, UID, 'unit-a', 'conversation') is not None
    with pytest.raises(references.ReferenceUnavailable, match='job_owner_mismatch'):
        references.load_reference(store, 'other-owner', 'unit-a', 'conversation')
    with pytest.raises(references.ReferenceUnavailable, match='skipped_merged'):
        references.load_reference(store, UID, 'unit-a', 'other-conversation')
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
    if refusal == 'expired':
        with pytest.raises(references.ReferenceUnavailable, match='skipped_expired'):
            references.load_reference(store, UID, 'unit-a', 'conversation')
    else:
        with pytest.raises(
            references.ReferenceUnavailable,
            match={'erasing': 'erasure', 'generation': 'generation_mismatch', 'wrong_kind': 'artifact_kind_mismatch'}[
                refusal
            ],
        ):
            references.load_reference(store, UID, 'unit-a', 'conversation')


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
    with pytest.raises(references.ReferenceUnavailable, match='skipped_expired'):
        references.load_reference(store, UID, 'unit-a', 'conversation')
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


@pytest.mark.parametrize('failure', ['diarizer', 'revoked', 'apply'])
def test_failed_pass_never_publishes_recurring_profile(lane, monkeypatch, failure):
    writes = []
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(batch.recurring_voices, 'learn', lambda *a, **kw: writes.append(kw))
    if failure == 'diarizer':

        def fail(*a, **kw):
            raise RuntimeError('synthetic failure')

        monkeypatch.setattr(final, 'diarize_with_speech_compaction', fail)
    elif failure == 'revoked':
        original = batch.load_reference

        def revoked(*a, **kw):
            return None if lane.gpu else original(*a, **kw)

        monkeypatch.setattr(batch, 'load_reference', revoked)
    else:

        def fail(*a, **kw):
            raise RuntimeError('synthetic apply failure')

        # Call the real adapter with the documented apply seam.
        batch.run_batch_final_pass(
            UID, lane.conversation, {}, load_prints=lambda *a, **kw: {'user': [1.0, 0.0]}, apply=fail, requeue=None
        )
        assert not writes
        return
    resolve(lane)
    assert not writes


def test_successful_pass_projects_recurring_identity_only_after_learning(lane, monkeypatch):
    writes, mix = [], []
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(batch, 'emit_product_event', lambda **kw: mix.append(kw))

    def learn(uid, conversation, centroids, prints, expected, **kwargs):
        writes.append((uid, centroids, expected))
        assert len(lane.gpu) == 1 and len(lane.reads) >= 4
        assert centroids == {'voice': {'embedding': [1.0, 0.0], 'evidence_seconds': 12}}
        return {'voice': {'recurring_voice_id': 'private-recurring'}}

    monkeypatch.setattr(batch.recurring_voices, 'learn', learn)
    segments = resolve(lane)
    assert writes and all(s.recurring_voice_id == 'private-recurring' for s in segments)
    assert all(s.person_id is None and not s.is_user for s in segments)
    assert mix[0]['event'] == 'Batch Speaker Identity Mix'
    assert mix[0]['properties']['recurring'] > 0 and mix[0]['properties']['person'] == 0


@pytest.mark.parametrize('failure', ['owner', 'entitlement', 'people'])
def test_recurring_pass_refuses_an_incomplete_person_roster(lane, monkeypatch, failure):
    writes = []
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(batch.recurring_voices, 'learn', lambda *a, **kw: writes.append(True) or {})
    monkeypatch.setattr(stage, 'load_owner_embedding', lambda *a, **kw: np.array([[1.0, 0.0]]))
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda *_: True)
    monkeypatch.setattr(stage.users_db, 'get_people', lambda *_: [])

    def unavailable(*a, **kw):
        raise RuntimeError('synthetic roster read failure')

    if failure == 'owner':
        monkeypatch.setattr(stage, 'load_owner_embedding', unavailable)
    elif failure == 'entitlement':
        monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', unavailable)
    else:
        monkeypatch.setattr(stage.users_db, 'get_people', unavailable)
    with pytest.raises(RuntimeError, match='synthetic roster read failure'):
        REAL_LOAD_PRINTS(UID, allow_audio_repair=False, require_complete=True)
    legacy = REAL_LOAD_PRINTS(UID, allow_audio_repair=False)
    assert ('user' in legacy) == (failure != 'owner')
    before = lane.conversation.model_dump()
    batch.run_batch_final_pass(
        UID, lane.conversation, {}, load_prints=REAL_LOAD_PRINTS, apply=lambda *a, **kw: None, requeue=None
    )
    assert not writes and not lane.gpu
    assert lane.conversation.model_dump() == before


@pytest.fixture
def prod_shaped(monkeypatch):
    """Literal persisted projection, independently specified (never projected here)."""
    from models.transcript_segment import TranscriptSegment

    monkeypatch.setenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', 'true')
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'true')
    monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', '100')
    monkeypatch.setattr(batch, 'current_stage', lambda: 'dev')
    binding = ProjectionBinding(UID, 'job', 'content', ('unit-a',), private_cloud_sync_enabled=True, record_origin=True)
    payload = {
        'audio_seconds': 8,
        'speech_seconds': 8,
        'speech_spans': [{'start': 0, 'end': 8}],
        'words_provider': 'parakeet',
        'words': [{'word': 'Hello', 'timestamp': [0.2, 2.8]}, {'word': 'there.', 'timestamp': [3, 5.8]}],
        'diarization': {'turns': [{'start': 0, 'end': 8, 'speaker': 'SPEAKER_00'}]},
    }
    items = {'unit-a': WorkItem('unit-a', UID, CAPTURE, 'gs://fake/unit-a#1', 8, Priority.FRESH, privacy_generation=0)}
    audio = {'unit-a': b'\x01\0' * (8 * 16000)}
    segments = [
        TranscriptSegment(
            is_user=False,
            id='932fc062-cfd5-5cc1-b6b4-3ce28580abff',
            text='Hello there.',
            start=900.2,
            end=905.8,
            speaker='SPEAKER_00',
            speaker_id=0,
            speaker_id_scope='final:batch:unit-a',
            person_id='resolver-person',
            stt_provider='parakeet',
        )
    ]
    conversation = Conversation(
        id='conversation',
        created_at=datetime.fromtimestamp(CAPTURE, timezone.utc),
        started_at=datetime.fromtimestamp(CAPTURE, timezone.utc),
        finished_at=datetime.fromtimestamp(CAPTURE + 8, timezone.utc),
        structured=Structured(),
        transcript_segments=segments,
    )
    reads, gpu, fallbacks = [], [], []
    lane = SimpleNamespace(
        conversation=conversation,
        binding=binding,
        payload=payload,
        items=items,
        audio=audio,
        reads=reads,
        gpu=gpu,
        fallbacks=fallbacks,
    )

    def reference(store, uid, unit, cid, **kwargs):
        reads.append(unit)
        return items[unit], 'gs://fake/result#1', lane.binding, ProjectionPolicy(authoritative_labels=True)

    def fetch(item, *, read_budget):
        read_budget.begin()
        body = wav(audio[item.segment_id])
        read_budget.reserve(len(body))
        return body

    def diarize(pcm, backend, *args, **kwargs):
        if backend.reserve_attempt is not None and not backend.reserve_attempt(len(pcm) / 32000):
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

    lane.artifacts = SimpleNamespace(load_result=lambda *a, **kw: payload, fetch_audio=fetch)
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: object())
    monkeypatch.setattr(batch, 'load_reference', reference)
    monkeypatch.setattr(batch, 'artifacts_for', lambda _: lane.artifacts)
    monkeypatch.setattr(batch, '_reserve_budget', lambda _: True)
    monkeypatch.setattr(batch, 'record_fallback', lambda **kw: fallbacks.append(kw))
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: None)
    monkeypatch.setattr(final, 'record_fallback', lambda **kw: fallbacks.append(kw))
    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize)
    monkeypatch.setattr(batch, 'emit_product_event', lambda **kw: None)
    return lane


def run_prod(lane):
    from utils.conversations import final_pass_retry as retry

    return batch.run_batch_final_pass(
        UID,
        lane.conversation,
        {},
        load_prints=lambda *a, **kw: {'user': [1.0, 0.0]},
        apply=stage.apply_speaker_resolution,
        requeue=lambda *args: retry.enqueue(UID, lane.conversation),
    )


@pytest.mark.parametrize('scope', ['final:batch:sync:opaque', 'sync:opaque', 'live:opaque'])
@pytest.mark.parametrize('resolved', [False, True])
def test_prod_mixed_scope_only_changes_batch_evidenced_part(prod_shaped, scope, resolved):
    lane = prod_shaped
    other = lane.conversation.transcript_segments[0].model_copy(deep=True)
    other.id, other.speaker_id_scope = 'synthetic-other-segment', scope
    if resolved:
        other.provider_speaker = {'id': 0, 'scope': scope, 'provider': 'parakeet'}
        other.speaker_id_scope = 'final:batch:conversation:conversation'
    lane.conversation.transcript_segments.append(other)
    before = other.model_dump()
    result = run_prod(lane)
    assert set(lane.reads) == {'unit-a'}
    assert lane.gpu
    assert result['outcome'] == 'success'
    assert lane.conversation.transcript_segments[0].is_user
    assert lane.conversation.transcript_segments[1].model_dump() == before
    assert result['changed_segments'] == 1


def test_sync_only_is_ineligible_without_unit_reads(prod_shaped):
    lane = prod_shaped
    lane.conversation.transcript_segments[0].speaker_id_scope = 'final:batch:sync:opaque'
    result = run_prod(lane)
    assert not lane.reads and not lane.gpu
    assert result['outcome'] == 'skipped_ineligible'


def test_point_words_do_not_poison_real_segment_mapping(prod_shaped):
    from models.transcript_segment import TranscriptSegment

    lane = prod_shaped
    lane.payload['words'].append({'word': '.', 'timestamp': [6, 6]})
    point = TranscriptSegment(
        is_user=False,
        id='9033d5ea-76fb-5cb7-8988-64c32cbf1e4c',
        text='.',
        start=906,
        end=906,
        speaker_id=1,
        speaker_id_scope='final:batch:unit-a',
        person_id='resolver-person',
    )
    lane.conversation.transcript_segments.append(point)
    before = point.model_dump()
    result = run_prod(lane)
    assert lane.conversation.transcript_segments[0].is_user
    assert result['outcome'] == 'success'
    assert lane.conversation.transcript_segments[1].model_dump() == before


def test_record_origin_replays_legacy_committed_result_without_vad_spans(prod_shaped):
    del prod_shaped.payload['speech_spans']
    result = run_prod(prod_shaped)
    assert prod_shaped.gpu and prod_shaped.conversation.transcript_segments[0].is_user
    assert result['outcome'] == 'success'


@pytest.mark.parametrize('duration', [7.999, 7.995, 7.9, 8.1])
def test_sample_clock_tolerates_worker_metadata_rounding(prod_shaped, duration):
    lane = prod_shaped
    lane.items['unit-a'] = replace(lane.items['unit-a'], duration_seconds=duration)
    result = run_prod(lane)
    assert lane.gpu and lane.conversation.transcript_segments[0].is_user
    assert result['outcome'] == 'success'


def test_large_duration_disagreement_remains_a_failure(prod_shaped):
    lane = prod_shaped
    lane.items['unit-a'] = replace(lane.items['unit-a'], duration_seconds=7.8)
    result = run_prod(lane)
    assert result['outcome'] == 'failed_incomplete_coverage'
    assert result['reason'] == 'unit_duration'
    assert result['failing_unit'] == 'unit-a'
    assert not lane.gpu


def test_multipart_unit_uses_original_part_ids_and_offsets(prod_shaped, monkeypatch):
    from models.transcript_segment import TranscriptSegment

    lane = prod_shaped
    lane.binding = replace(lane.binding, record_origin=False)
    lane.items['unit-a'] = replace(lane.items['unit-a'], duration_seconds=140, requires_compute_admission=True)
    lane.audio['unit-a'] = b'\x01\0' * (140 * 16000)
    lane.payload.update(
        audio_seconds=140,
        speech_seconds=7,
        speech_spans=[{'start': 0, 'end': 3}, {'start': 130, 'end': 134}],
        words=[{'word': 'First.', 'timestamp': [0.2, 2.8]}, {'word': 'Last.', 'timestamp': [130.2, 133.8]}],
        diarization={'turns': [{'start': 0, 'end': 140, 'speaker': 'SPEAKER_00'}]},
    )
    lane.conversation.transcript_segments = [
        TranscriptSegment(
            is_user=False, id=sid, text=text, start=start, end=end, speaker_id=0, speaker_id_scope='final:batch:unit-a'
        )
        for sid, text, start, end in [
            ('98608d85-b3c4-5638-a12a-468466e8eeaf', 'First.', 900.2, 902.8),
            ('cf5bd53e-f3d2-5a8c-bedc-bb4336f19cdf', 'Last.', 1030.2, 1033.8),
        ]
    ]
    monkeypatch.setattr(
        batch,
        'load_reference',
        lambda *a, **kw: (
            lane.items['unit-a'],
            'gs://fake/result#1',
            lane.binding,
            ProjectionPolicy(authoritative_labels=True),
        ),
    )
    seen = []
    original = batch.run_final_pass

    def capture(pcm, words, *args, **kwargs):
        seen.extend(w['timestamp'] for w in words)
        return original(pcm, words, *args, **kwargs)

    monkeypatch.setattr(batch, 'run_final_pass', capture)
    assert run_prod(lane)['outcome'] == 'success'
    assert seen == [[0.2, 2.8], [130.2, 133.8]]
    assert all(s.is_user for s in lane.conversation.transcript_segments)


@pytest.mark.parametrize('kind,outcome', [('expired', 'skipped_expired'), ('merged', 'skipped_merged')])
def test_real_artifact_lifecycle_is_not_a_coverage_failure(prod_shaped, reference_store, monkeypatch, kind, outcome):
    lane = prod_shaped
    store, client = reference_store
    if kind == 'expired':
        for path, row in client.rows.items():
            if path[0].endswith('_artifacts'):
                row['cleanup_after'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    else:
        client.rows[(store.namespace + '_results', 'unit-a')]['projection_parts']['0'][
            'conversation_id'
        ] = 'synthetic-donor'
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(batch, 'load_reference', references.load_reference)
    result = run_prod(lane)
    assert result['outcome'] == outcome
    assert result['reason'] == outcome and result['failing_unit'] == 'unit-a'
    assert not lane.gpu


@pytest.mark.parametrize('distinct_conversations', [False, True])
def test_slot_saturation_requeues_without_waiting_on_shared_pool(
    prod_shaped, retry_state, monkeypatch, distinct_conversations
):
    import threading
    from concurrent.futures import ThreadPoolExecutor, wait
    from utils.conversations import final_pass_retry as retry

    slot = threading.BoundedSemaphore(1)
    assert slot.acquire()
    monkeypatch.setattr(batch, '_SLOTS', slot)
    cases = []
    for index in range(96):
        conversation = prod_shaped.conversation.model_copy(deep=True)
        if distinct_conversations:
            conversation.id = f'synthetic-conversation-{index}'
        cases.append(SimpleNamespace(**{**vars(prod_shaped), 'conversation': conversation}))
    before = batch_outcome_counts()
    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(run_prod, case) for case in cases]
        try:
            done, pending = wait(futures, timeout=5)
            assert not pending
            assert pool.submit(lambda: 'available').result(timeout=1) == 'available'
            assert {future.result()['outcome'] for future in done} == {'deferred_slot_busy'}
        finally:
            slot.release()
    count = 96 if distinct_conversations else 1
    assert len(retry_state.rows) == count
    assert len({(key, row['token']) for key, row in retry_state.wakes}) == count
    assert {row['attempts'] for row in retry_state.rows.values()} == {0}
    assert batch_outcome_counts() == before and not prod_shaped.gpu
    cases_by_id = {case.conversation.id: case for case in cases}

    def run_only(uid, cid, scope):
        with batch.terminal_metrics(False):
            return run_prod(cases_by_id[cid])

    monkeypatch.setattr(retry, 'run_only', run_only)
    for key, row in list(retry_state.rows.items()):
        retry_state.clock[0] = row['due_at'] + 1
        assert retry.consume(key, row['token'])['outcome'] == 'success'
    assert len(prod_shaped.gpu) == count
    assert {row['outcome'] for row in retry_state.rows.values()} == {'success'}
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == count


def test_slot_deferral_persistence_failure_propagates(prod_shaped, retry_state, monkeypatch):
    import threading

    slot = threading.BoundedSemaphore(1)
    assert slot.acquire()
    monkeypatch.setattr(batch, '_SLOTS', slot)
    monkeypatch.setattr(
        retry_state.store, '_mutate', lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic failure'))
    )
    before = batch_outcome_counts()
    try:
        with pytest.raises(RuntimeError):
            run_prod(prod_shaped)
    finally:
        slot.release()
    assert not retry_state.rows
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def _retry_counter_snapshot():
    return {}  # The retry fixture supplies its synthetic durable store.


def batch_outcome_counts():
    counts = {
        tuple(sample.labels.items()): sample.value
        for metric in batch.OUTCOMES.collect()
        for sample in metric.samples
        if sample.name.endswith('_total') and sample.labels['lane'] == 'batch'
    }
    for shard in _retry_counter_snapshot().values():
        for outcome, value in shard.items():
            labels = (('lane', 'batch'), ('outcome', outcome))
            counts[labels] = counts.get(labels, 0) + value
    return counts


@pytest.mark.parametrize('failure', ['none', 'unassigned', 'budget', 'diarizer'])
def test_exactly_one_terminal_outcome_per_conversation(prod_shaped, monkeypatch, failure):
    lane = prod_shaped
    lane.items['unit-b'] = replace(lane.items['unit-a'], segment_id='unit-b', capture_at=CAPTURE + 8)
    lane.audio['unit-b'] = b'\x02\0' * (8 * 16000)
    second = lane.conversation.transcript_segments[0].model_copy(deep=True)
    second.id = '4395ed2b-8f7d-5bd0-a816-39bb22221a63'
    second.speaker_id_scope = 'final:batch:unit-b'
    second.start, second.end = 908.2, 913.8
    lane.conversation.transcript_segments.append(second)
    if failure == 'unassigned':
        original = final.diarize_with_speech_compaction

        def gap(*args, **kwargs):
            result = original(*args, **kwargs)
            result['turns'] = []
            return result

        monkeypatch.setattr(final, 'diarize_with_speech_compaction', gap)
    elif failure == 'budget':
        monkeypatch.setattr(batch, '_reserve_budget', lambda _: False)
    elif failure == 'diarizer':
        monkeypatch.setattr(
            final,
            'diarize_with_speech_compaction',
            lambda *a, **kw: (_ for _ in ()).throw(ValueError('synthetic PRIVATE text')),
        )
    before = batch_outcome_counts()
    run_prod(lane)
    after = batch_outcome_counts()
    assert sum(after.values()) - sum(before.values()) == 1


def test_diagnostics_never_echo_arbitrary_exception_content(prod_shaped, monkeypatch, caplog):
    monkeypatch.setattr(
        prod_shaped.artifacts,
        'load_result',
        lambda *a, **kw: (_ for _ in ()).throw(ValueError('synthetic PRIVATE text')),
    )
    result = run_prod(prod_shaped)
    assert result['exception_type'] == 'ValueError' and result['reason'] == 'unclassified'
    assert 'PRIVATE' not in caplog.text


def test_owner_lab_stub_runs_real_units_assembly_and_runner(prod_shaped, monkeypatch):
    from testing.owner_lab import final_pass_repro as lab

    lane = prod_shaped
    calls = []
    original = batch.run_final_pass

    def runner(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(batch, 'run_final_pass', runner)
    # The lane fixture replaces compaction; restore the production path so the
    # lab's DiarizerBackend is actually consumed by the shared runner.
    from utils.stt.vad_compaction import diarize_with_speech_compaction

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize_with_speech_compaction)
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    result = lab.reproduce(UID, lane.conversation, {}, load_prints=lambda *a, **kw: {})
    assert result['outcome'] == 'success'
    assert result['segment_coverage'] == {'total': 1, 'required': 1, 'placed': 1}
    assert result['apply_calls'] == 1 and result['learn_calls'] == 0  # stub has no centroids
    assert result['changed_segments'] == 1 and result['speaker_count'] == 1
    assert calls and set(lane.reads) == {'unit-a'}
    assert UID not in str(result) and 'Hello' not in str(result)


def test_owner_lab_http_uses_real_http_diarizer_and_captures_learning(prod_shaped, monkeypatch, tmp_path):
    from testing.owner_lab import final_pass_repro as lab
    from utils.stt.vad_compaction import diarize_with_speech_compaction

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize_with_speech_compaction)
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'false')
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'http://synthetic.invalid')
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(batch.recurring_voices, 'learn', lambda *a, **kw: pytest.fail('real learning called'))
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'turns': [{'start': 0, 'end': 8, 'speaker': 'voice'}],
                'overlaps': [],
                'centroids': {'voice': {'embedding': [1.0, 0.0], 'evidence_seconds': 8}},
                'embedding_space': OMI_EMBEDDING_SPACE,
                'version': 'test',
                'provenance': {'backend': 'pyannote'},
            },
        )

    monkeypatch.setattr(httpx, 'post', post)
    result = lab.reproduce(UID, prod_shaped.conversation, {}, diarizer='http', load_prints=lambda *a, **kw: {})
    assert result['outcome'] == 'success'
    assert result['learn_calls'] == 1 and result['apply_calls'] == 1
    assert calls == ['http://synthetic.invalid/v2/diarization']


def test_result_duration_at_float_rounded_decode_boundary(prod_shaped):
    lane = prod_shaped
    lane.items['unit-a'] = replace(lane.items['unit-a'], duration_seconds=1)
    lane.audio['unit-a'] = b'\x01\0' * 17600
    lane.payload.update(
        audio_seconds=1.1,
        speech_seconds=1.1,
        speech_spans=[{'start': 0, 'end': 1.1}],
        words=[{'word': 'Hello there.', 'timestamp': [0.2, 0.8]}],
        diarization={'turns': [{'start': 0, 'end': 1.1, 'speaker': 'SPEAKER_00'}]},
    )
    assert run_prod(lane)['outcome'] == 'success'


def test_record_origin_still_refuses_malformed_present_vad(prod_shaped):
    prod_shaped.payload['speech_spans'] = [{'start': 2, 'end': 1}]
    result = run_prod(prod_shaped)
    assert result['outcome'] == 'failed_incomplete_coverage'
    assert result['reason'] == 'projection_vad_order'


def test_eof_word_uses_decoded_result_clock_not_rounded_admission(prod_shaped):
    lane = prod_shaped
    lane.items['unit-a'] = replace(lane.items['unit-a'], duration_seconds=7.9)
    lane.payload['words'] = [{'word': 'Hello there.', 'timestamp': [7.999, 8.0]}]
    lane.conversation.transcript_segments[0].start = 907.999
    lane.conversation.transcript_segments[0].end = 908
    result = run_prod(lane)
    assert lane.gpu and lane.conversation.transcript_segments[0].is_user
    assert result['outcome'] == 'success'


def test_owner_lab_cli_outputs_cases_and_success_rate_without_private_logs(prod_shaped, monkeypatch, capsys):
    import json
    import sys
    from types import ModuleType
    from testing.owner_lab import final_pass_repro as lab
    from database import conversations as db
    from utils.stt.vad_compaction import diarize_with_speech_compaction

    guard = ModuleType('testing.owner_lab.guard')
    reads = []
    guard.owner_uid = lambda path: reads.append(path) or UID
    guard.load_secret = lambda path: reads.append(path)
    guard.read_private = lambda path, kind: reads.append(path) or '["conversation", "synthetic-missing"]'
    monkeypatch.setitem(sys.modules, 'testing.owner_lab.guard', guard)
    row = prod_shaped.conversation.model_dump()

    def get(_uid, cid, **kw):
        print('synthetic PRIVATE transcript')  # Accidental library stdout must be suppressed too.
        return {**row, '_recovery_transcript_decoded': True} if cid == 'conversation' else None

    monkeypatch.setattr(db, 'get_conversation', get)
    monkeypatch.setattr(db, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {})
    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize_with_speech_compaction)
    with monkeypatch.context() as context:
        # main is a CLI process; restore its global logging suppression in this test process.
        import logging

        context.setattr(logging, 'disable', lambda level: None)
        lab.main(
            [
                '--uid-file',
                '/private/uid',
                '--secret-file',
                '/private/secret',
                '--conversations-file',
                '/private/selection',
                '--diarizer',
                'stub',
            ]
        )
    output = capsys.readouterr().out
    results = [json.loads(line) for line in output.splitlines()]
    assert [r['outcome'] for r in results[:-1]] == ['success', 'failed_load']
    assert results[-1]['success_rate'] == 0.5
    assert reads == ['/private/uid', '/private/secret', '/private/selection']
    assert 'PRIVATE' not in output and UID not in output and 'Hello' not in output


def test_vendor_recovery_result_reconstructs_the_same_stored_batch_segment(prod_shaped, monkeypatch):
    lane = prod_shaped
    monkeypatch.setenv('BATCH_VENDOR_SPEAKER_TURNS_ENABLED', 'true')
    lane.payload.update(recovery_version=1, words_provider='modulate')
    for word in lane.payload['words']:
        word['speaker'] = 'SPEAKER_00'
    lane.conversation.transcript_segments[0].stt_provider = 'modulate'
    result = run_prod(lane)
    assert lane.gpu and lane.conversation.transcript_segments[0].is_user
    assert result['outcome'] == 'success'


@pytest.mark.parametrize('geometry', ['parts', 'rollover', 'unreceipted_part', 'pending_part'])
def test_shared_unit_never_reads_or_diarizes_other_conversation_audio(
    prod_shaped, reference_store, monkeypatch, geometry
):
    store, client = reference_store
    client.rows[(store.namespace + '_jobs', 'unit-a')]['duration_seconds'] = 140
    parts = client.rows[(store.namespace + '_results', 'unit-a')]['projection_parts']
    other = {'conversation_id': 'synthetic-other-conversation', 'speaker_scope': 'final:batch:unit-a'}
    if geometry == 'parts':
        parts['1'] = other
    elif geometry == 'rollover':
        parts['0']['size_rollover_outputs'] = [{'conversation_id': 'conversation'}, other]
    elif geometry == 'unreceipted_part':
        parts['1'] = {}  # Cannot establish exclusive ownership of the whole PCM.
    else:
        client.rows[(store.namespace + '_results', 'unit-a')]['projection_part_count'] = 2
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(batch, 'load_reference', references.load_reference)
    monkeypatch.setattr(batch, 'artifacts_for', lambda _: prod_shaped.artifacts)
    monkeypatch.setattr(prod_shaped.artifacts, 'fetch_audio', lambda *a, **kw: pytest.fail('shared audio fetched'))
    monkeypatch.setattr(prod_shaped.artifacts, 'load_result', lambda *a, **kw: pytest.fail('shared result fetched'))
    monkeypatch.setattr(batch.recurring_voices, 'learn', lambda *a, **kw: pytest.fail('shared voice learned'))
    original = prod_shaped.conversation.model_copy(deep=True)
    before = batch_outcome_counts()
    result = run_prod(prod_shaped)
    assert result['outcome'] == 'skipped_shared_unit'
    assert result['reason'] == 'skipped_shared_unit' and result['failing_unit'] == 'unit-a'
    assert prod_shaped.conversation == original and not prod_shaped.gpu
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_centroid_without_conversation_assignments_is_never_learned(prod_shaped, monkeypatch):
    original = final.diarize_with_speech_compaction

    def diarize(*args, **kwargs):
        output = original(*args, **kwargs)
        # Strong evidence in staged PCM, but no assigned word in this conversation.
        output['centroids']['other-conversation-voice'] = {'embedding': [0.0, 1.0], 'evidence_seconds': 120}
        return output

    learned = []
    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize)
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(
        batch.recurring_voices, 'learn', lambda uid, c, centroids, *a, **kw: learned.append(centroids) or {}
    )
    assert run_prod(prod_shaped)['outcome'] == 'success'
    assert len(learned) == 1 and set(learned[0]) == {'voice'}


@pytest.mark.parametrize('reason', ['flag_off', 'non_cohort', 'non_batch'])
def test_ineligible_calls_are_outside_terminal_outcome_contract(prod_shaped, monkeypatch, reason):
    if reason == 'non_batch':
        prod_shaped.conversation.transcript_segments[0].speaker_id_scope = 'final:batch:sync:opaque'
    else:
        monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'false' if reason == 'flag_off' else 'true')
        if reason == 'non_cohort':
            monkeypatch.setenv('BATCH_FINAL_PASS_PERCENT', '0')
    before = batch_outcome_counts()
    assert run_prod(prod_shaped)['outcome'] == 'skipped_ineligible'
    assert batch_outcome_counts() == before
    assert not prod_shaped.reads and not prod_shaped.gpu


@pytest.mark.parametrize('outcome', ['success', 'failed_incomplete_coverage'])
def test_owner_lab_reproduce_does_not_change_default_registry(prod_shaped, monkeypatch, outcome):
    from prometheus_client import REGISTRY
    from testing.owner_lab import final_pass_repro as lab
    from utils.observability.fallback import record_fallback
    from utils.stt.vad_compaction import diarize_with_speech_compaction

    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize_with_speech_compaction)
    # Exercise real fallback metrics too, rather than the fixture's telemetry spy.
    monkeypatch.setattr(batch, 'record_fallback', record_fallback)
    monkeypatch.setattr(final, 'record_fallback', record_fallback)
    if outcome != 'success':
        monkeypatch.setattr(batch, 'load_reference', lambda *a, **kw: None)

    def snapshot():
        return {
            (metric.name, sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for metric in REGISTRY.collect()
            if not metric.name.startswith(('process_', 'python_gc_'))
            for sample in metric.samples
        }

    before = snapshot()
    result = lab.reproduce(UID, prod_shaped.conversation, {}, load_prints=lambda *a, **kw: {})
    assert result['outcome'] == outcome
    assert snapshot() == before
    # Restored production objects still observe future admitted invocations.
    batch.OUTCOMES.labels(lane='batch', outcome='success').inc()
    assert snapshot() != before


def test_enrichment_resolver_passes_retry_custody_to_batch(lane, retry_state):
    from utils.conversations import processing_speakers

    persisted = []
    assert processing_speakers.resolve_speakers_for_processing(UID, lane.conversation, on_persist=persisted.append)
    row = next(iter(retry_state.rows.values()))
    assert row['outcome'] is None and row['lease'] and lane.gpu
    assert not retry_state.store.terminal_counts()
    persisted[0](True)
    assert sum(row.get('success', 0) for row in retry_state.store.terminal_counts().values()) == 1


def test_missing_retry_custody_never_silently_drops_busy_pass(prod_shaped, monkeypatch):
    import threading

    slot = threading.BoundedSemaphore(1)
    assert slot.acquire()
    monkeypatch.setattr(batch, '_SLOTS', slot)
    try:
        with pytest.raises(RuntimeError, match='retry_custody_required'):
            batch.run_batch_final_pass(
                UID, prod_shaped.conversation, {}, load_prints=lambda *a: {}, apply=lambda *a, **kw: None, requeue=None
            )
    finally:
        slot.release()


def test_shared_units_count_one_conversation_and_each_omitted_unit(prod_shaped, monkeypatch):
    lane = prod_shaped
    for unit in ('unit-b', 'unit-c'):
        segment = lane.conversation.transcript_segments[0].model_copy(deep=True)
        segment.id, segment.speaker_id_scope = unit + '-segment', 'final:batch:' + unit
        lane.conversation.transcript_segments.append(segment)

    def reference(store, uid, unit, cid, **kwargs):
        if unit != 'unit-c':
            raise references.ReferenceUnavailable('skipped_shared_unit')
        return (
            replace(lane.items['unit-a'], segment_id='unit-c'),
            'gs://fake/result#1',
            lane.binding,
            ProjectionPolicy(),
        )

    monkeypatch.setattr(batch, 'load_reference', reference)
    monkeypatch.setattr(
        lane.artifacts, 'load_result', lambda *a, **kw: pytest.fail('whole-pass skip must read no artifacts')
    )
    original = lane.conversation.model_copy(deep=True)

    def counts():
        return {
            sample.labels['reason']: sample.value
            for metric in batch.UNIT_SKIPS.collect()
            for sample in metric.samples
            if sample.name.endswith('_total')
        }

    before_units, before_conversations = counts(), batch_outcome_counts()
    assert run_prod(lane)['outcome'] == 'skipped_shared_unit'
    assert lane.conversation == original and not lane.gpu
    after = counts()
    assert after['shared_unit'] - before_units.get('shared_unit', 0) == 2
    assert after['blocked_by_shared_unit'] - before_units.get('blocked_by_shared_unit', 0) == 1
    assert sum(batch_outcome_counts().values()) - sum(before_conversations.values()) == 1

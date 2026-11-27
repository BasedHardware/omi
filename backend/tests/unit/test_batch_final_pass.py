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
from models.conversation import Conversation, ConversationSpeakers
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

    monkeypatch.setattr(final, 'diarize', diarize)
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

    monkeypatch.setattr(final, 'diarize', failed)
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
    original = final.diarize

    def gap(*args, **kwargs):
        output = original(*args, **kwargs)
        output['turns'][0]['start'] = 4
        return output

    monkeypatch.setattr(final, 'diarize', gap)
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


def _v3_conversation_row(client, cid='v3-conversation'):
    client.rows[('users', UID, 'conversations', cid)] = {'id': cid, 'v3_recording_ids': ['conversation']}
    return cid


def test_v3_conversation_reads_units_projected_onto_its_source_recording(reference_store):
    # A conversations-v3 row copies its recording's projected segments; the unit's receipts keep naming the
    # recording. Before the fix every v3 row refused with skipped_merged (owner corpus 2026-11-26: 24 of 24).
    store, client = reference_store
    cid = _v3_conversation_row(client)
    before = deepcopy(client.rows)
    with pytest.raises(references.ReferenceUnavailable, match='skipped_merged'):
        references.load_reference(store, UID, 'unit-a', cid)
    assert references.load_reference(store, UID, 'unit-a', cid, source_ids=('conversation',)) is not None
    # A recording the row was not built from is still another conversation's audio.
    with pytest.raises(references.ReferenceUnavailable, match='skipped_merged'):
        references.load_reference(store, UID, 'unit-a', cid, source_ids=('other-recording',))
    assert client.rows == before


def test_v3_source_recording_keeps_shared_unit_and_privacy_fences(reference_store):
    store, client = reference_store
    cid = _v3_conversation_row(client)
    receipts = client.rows[('batch_pipeline_dev_results', 'unit-a')]['projection_parts']
    receipts['1'] = {'conversation_id': 'foreign', 'speaker_scope': 'final:batch:unit-a'}
    with pytest.raises(references.ReferenceUnavailable, match='skipped_shared_unit'):
        references.load_reference(store, UID, 'unit-a', cid, source_ids=('conversation',))
    del receipts['1']
    client.rows[('users', UID, 'conversations', 'conversation')]['deleted'] = True
    with pytest.raises(BatchPrivacyBlocked):
        references.load_reference(store, UID, 'unit-a', cid, source_ids=('conversation',))


def test_receipt_sources_are_the_rows_own_v3_recordings():
    assert batch.receipt_sources(SimpleNamespace(v3_recording_ids=['r2', 'r1', 'r1', None])) == ('r1', 'r2')
    assert batch.receipt_sources(SimpleNamespace(v3_recording_ids=None)) == ()
    assert batch.receipt_sources(SimpleNamespace()) == ()


def _recordings(monkeypatch, rows):
    monkeypatch.setattr(batch, 'source_recording_fence', lambda uid, rid: deepcopy(rows.get(rid)))


def _at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def test_v3_source_live_hold_reads_claims_minus_deleted_spans(monkeypatch):
    conversation = SimpleNamespace(id='mine', v3_recording_ids=['R'])
    _recordings(
        monkeypatch,
        {
            'R': {
                'claims': [
                    {'conversation_id': 'mine', 'start': _at(1010), 'end': _at(1020)},
                    {'conversation_id': 'sibling', 'start': _at(1020), 'end': _at(1030)},
                ],
                'deleted_spans': [{'start': _at(1014), 'end': _at(1016), 'conversation_id': 'mine'}],
            }
        },
    )
    assert batch.source_scope(UID, conversation).intervals == ((1010.0, 1014.0), (1016.0, 1020.0))


def test_only_own_speech_reaches_the_diarizer():
    # A source recording's unit: this conversation spoke at 2-4 s and 5-6 s (unit clock); a sibling at 10-14 s
    # and deleted speech sat at 20-22 s. Only the padded own-word stretches keep their samples.
    words = [{'timestamp': [2.0, 2.5]}, {'timestamp': [3.0, 4.0]}, {'timestamp': [5.0, 6.0]}]
    spans = batch.own_speech_spans(words)
    assert spans == [(1.75, 6.25)]
    pcm = b'\x01\x00' * (30 * 16000)
    masked = batch.masked_pcm(pcm, spans)
    assert len(masked) == len(pcm)
    at = lambda t: masked[int(t * 16000) * 2 : int(t * 16000) * 2 + 2]  # noqa: E731
    assert at(3) == at(5.5) == b'\x01\x00'
    assert at(1) == at(12) == at(21) == b'\x00\x00'
    turns = [{'start': 0, 'end': 30, 'speaker': 'A'}, {'start': 10, 'end': 14, 'speaker': 'B'}]
    assert batch.clip_turns(turns, spans) == [{'start': 1.75, 'end': 6.25, 'speaker': 'A'}]


@pytest.mark.parametrize('row', [None, {'deleted': True, 'claims': []}, {'is_locked': True}, {'claims': []}])
def test_v3_source_recording_gone_locked_or_unclaimed_refuses(monkeypatch, row):
    _recordings(monkeypatch, {'R': row} if row is not None else {})
    with pytest.raises(references.ReferenceUnavailable, match='skipped_merged'):
        batch.source_scope(UID, SimpleNamespace(id='mine', v3_recording_ids=['R']))


def test_v3_source_scope_fingerprint_changes_when_a_claim_or_deletion_changes(monkeypatch):
    rows = {'R': {'claims': [{'conversation_id': 'mine', 'start': _at(1010), 'end': _at(1020)}]}}
    _recordings(monkeypatch, rows)
    conversation = SimpleNamespace(id='mine', v3_recording_ids=['R'])
    first = batch.source_scope(UID, conversation)
    rows['R']['deleted_spans'] = [{'start': _at(1012), 'end': _at(1013)}]
    assert batch.source_scope(UID, conversation).fingerprint != first.fingerprint
    rows['R'] = {'claims': [{'conversation_id': 'mine', 'start': _at(1010), 'end': _at(1018)}]}
    assert batch.source_scope(UID, conversation).fingerprint != first.fingerprint
    assert batch.source_scope(UID, SimpleNamespace(id='legacy', v3_recording_ids=None)) is None


def test_appended_units_never_collide_with_later_native_units():
    # 0-5 s, a 2-6 s unit whose samples differ (appended), and a 6-7 s unit at its own clock.
    def unit(start, seconds, sample):
        item = SimpleNamespace(capture_at=1000.0 + start)
        words = [{'timestamp': [0.0, 0.5], 'text': 'w', 'segment_id': f's{start}'}]
        return item, sample * (seconds * 16000), words, lambda: True

    capacity = 7 * 32000
    stream = batch.UnitStream(
        1000.0,
        capacity,
        iter([unit(0, 5, b'\x01\x00'), unit(2, 4, b'\x02\x00'), unit(6, 1, b'\x03\x00')]),
        SimpleNamespace(timeout=lambda seconds: None),
    )
    pcm, words, checks = batch._assemble(stream)
    pcm = bytes(pcm)
    appended = capacity + batch.APPEND_GAP_BYTES
    assert pcm[: 5 * 32000] == b'\x01\x00' * (5 * 16000)
    assert pcm[6 * 32000 : 7 * 32000] == b'\x03\x00' * 16000  # the native unit stays at its own clock
    assert pcm[appended:] == b'\x02\x00' * (4 * 16000)
    assert [w['timestamp'][0] for w in words] == [0.0, appended / 32000, 6.0]
    assert len(checks) == 3


def test_v3_source_passes_learn_no_recurring_profile_and_get_a_fresh_obligation(monkeypatch):
    from utils.conversations import final_pass_retry as retry

    monkeypatch.setattr(retry, 'batch_unit_scope', lambda s: s.speaker_id_scope)
    segment = SimpleNamespace(id='s1', speaker_id_scope='final:batch:u1')
    legacy = SimpleNamespace(transcript_segments=[segment], v3_recording_ids=None)
    v3 = SimpleNamespace(transcript_segments=[segment], v3_recording_ids=['R'])
    assert retry.scope_key(legacy) != retry.scope_key(v3)
    assert retry.scope_key(v3) == retry.scope_key(
        SimpleNamespace(transcript_segments=[segment], v3_recording_ids=['R'])
    )
    source = __import__('inspect').getsource(batch._run)
    assert 'and not receipt_sources(conversation)' in source


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
    original = final.diarize

    def incompatible(*args, **kwargs):
        output = original(*args, **kwargs)
        output['embedding_space'] = 'incompatible'
        return output

    monkeypatch.setattr(final, 'diarize', incompatible)
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
    monkeypatch.setattr(final, 'diarize', lambda pcm, backend, *a, **kw: backend.diarize(pcm, **kw).model_dump())
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


def test_overlapping_incompatible_unit_clocks_append_after_timeline(lane):
    # unit-b's clock overlaps unit-a with different samples. Labels need each unit's words on its own audio,
    # so unit-b is appended after the timeline and the pass runs, instead of refusing the conversation
    # (9 of 24 owner v3 conversations refused this way on 2026-11-26).
    lane.items['unit-b'] = replace(lane.items['unit-b'], capture_at=CAPTURE + 4)
    metric = batch.OUTCOMES.labels(lane='batch', outcome='failed_incomplete_coverage')
    before = metric._value.get()
    assert all(s.is_user for s in resolve(lane))
    assert len(lane.gpu) == 1
    assert metric._value.get() == before


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

        monkeypatch.setattr(final, 'diarize', fail)
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
    monkeypatch.setattr(final, 'diarize', diarize)
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
        original = final.diarize

        def gap(*args, **kwargs):
            result = original(*args, **kwargs)
            result['turns'] = []
            return result

        monkeypatch.setattr(final, 'diarize', gap)
    elif failure == 'budget':
        monkeypatch.setattr(batch, '_reserve_budget', lambda _: False)
    elif failure == 'diarizer':
        monkeypatch.setattr(
            final,
            'diarize',
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
    # The lane fixture replaces the diarizer seam; restore the production path
    # so the lab's DiarizerBackend is actually consumed by the shared runner.
    from utils.stt.diarization import diarize

    monkeypatch.setattr(final, 'diarize', diarize)
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
    from utils.stt.diarization import diarize

    monkeypatch.setattr(final, 'diarize', diarize)
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
    from utils.stt.diarization import diarize

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
    monkeypatch.setattr(final, 'diarize', diarize)
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
    original = final.diarize

    def diarize(*args, **kwargs):
        output = original(*args, **kwargs)
        # Strong evidence in staged PCM, but no assigned word in this conversation.
        output['centroids']['other-conversation-voice'] = {'embedding': [0.0, 1.0], 'evidence_seconds': 120}
        return output

    learned = []
    monkeypatch.setattr(final, 'diarize', diarize)
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
    from utils.stt.diarization import diarize

    monkeypatch.setattr(final, 'diarize', diarize)
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


def _final_pass_with(evidence_seconds, vector, prints):
    from models.diarization import DiarizationResult

    class Backend:
        def diarize(self, pcm, **_):
            return DiarizationResult.model_validate(
                {
                    'turns': [{'start': 0.0, 'end': 4.0, 'speaker': 'SPEAKER_00'}],
                    'overlaps': [],
                    'centroids': {'SPEAKER_00': {'embedding': vector, 'evidence_seconds': evidence_seconds}},
                    'embedding_space': OMI_EMBEDDING_SPACE,
                    'version': 'test',
                    'provenance': {'backend': 'pyannote'},
                }
            )

    words = [{'timestamp': [0.5, 1.0], 'text': 'hi'}, {'timestamp': [1.5, 2.0], 'text': 'there'}]
    segments, _ = final.run_final_pass(
        b'\0\0' * 64000,
        words,
        None,
        {k: {'embedding': v} for k, v in prints.items()},
        deadline=time.monotonic() + 30,
        conversation_id='c',
        diarizer_backend=Backend(),
        record_outcome=False,
    )
    return segments


def test_final_pass_voice_without_enough_evidence_is_unknown_not_no_match():
    # Owner corpus 2026-11-26: on short v3 conversations the final pass labeled voices under the 5 s evidence
    # floor no_match, and apply_speaker_resolution cleared the resolver's correct owner labels with it.
    owner = [1.0] + [0.0] * 255
    stranger = [0.0, 1.0] + [0.0] * 254
    short = _final_pass_with(2.0, owner, {'user': owner})
    assert {s.speaker_identity_status for s in short} == {'unknown'}
    rejected = _final_pass_with(8.0, stranger, {'user': owner})
    assert {s.speaker_identity_status for s in rejected} == {'no_match'}
    named = _final_pass_with(8.0, owner, {'user': owner})
    assert all(s.is_user for s in named)


def test_unknown_final_pass_voice_keeps_the_resolvers_owner_label():
    conversation = Conversation(
        id='c',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        structured=Structured(),
        transcript_segments=[
            {'id': 's1', 'text': 'hi', 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'is_user': True, 'start': 0, 'end': 2}
        ],
    )
    stage.apply_speaker_resolution(conversation, {'s1': 3}, {}, {3: 'unknown'}, owner_voiceprint_available=True)
    assert conversation.transcript_segments[0].is_user is True
    stage.apply_speaker_resolution(conversation, {'s1': 3}, {}, {3: 'no_match'}, owner_voiceprint_available=True)
    assert conversation.transcript_segments[0].is_user is False


def test_v3_sources_kill_switch_restores_the_refusal(monkeypatch):
    from utils.conversations import final_pass_retry as retry

    monkeypatch.setattr(retry, 'batch_unit_scope', lambda s: s.speaker_id_scope)
    row = SimpleNamespace(
        id='mine',
        v3_recording_ids=['R'],
        transcript_segments=[SimpleNamespace(id='s1', speaker_id_scope='final:batch:u1')],
    )
    on_key = retry.scope_key(row)
    monkeypatch.setenv('BATCH_FINAL_PASS_V3_SOURCES_ENABLED', 'false')
    assert batch.receipt_sources(row) == ()
    assert batch.source_scope(UID, row) is None
    assert retry.scope_key(row) != on_key  # the legacy key, as before the change


def test_append_kill_switch_restores_the_clock_conflict_refusal(monkeypatch):
    monkeypatch.setenv('BATCH_FINAL_PASS_APPEND_CONFLICTING_UNITS_ENABLED', 'false')
    item = lambda start: SimpleNamespace(capture_at=1000.0 + start)  # noqa: E731
    stream = batch.UnitStream(
        1000.0,
        6 * 32000,
        iter(
            [(item(0), b'\x01\x00' * 5 * 16000, [], lambda: True), (item(2), b'\x02\x00' * 4 * 16000, [], lambda: True)]
        ),
        SimpleNamespace(timeout=lambda seconds: None),
    )
    with pytest.raises(batch.IncompleteCoverage, match='conflicting capture clocks'):
        batch._assemble(stream)


# ---- partial final pass on a resolved conversation (BATCH_FINAL_PASS_KEEP_RESOLVED_ON_PARTIAL_ENABLED) ----------


def _resolved_by(monkeypatch, ids, *, person_id=None, status='resolved'):
    """The resolver grouped the voices: conversation-scope ids, one identity per voice, and its status."""

    def resolver(uid, current, **kwargs):
        for segment, speaker_id in zip(current.transcript_segments, ids):
            segment.assign_resolved_speaker(speaker_id, f'final:batch:conversation:{current.id}')
            if segment.speaker_label_source != 'manual':
                segment.is_user, segment.person_id = person_id is None, person_id
                segment.speaker_label_source = 'auto'
        current.speaker_resolution = ConversationSpeakers(status=status, version=2, participant_speaker_ids=[])

    monkeypatch.setattr(stage, '_resolve', resolver)


def _turns(monkeypatch, *turns):
    """The final pass diarizes ``(start, end, voice)`` turns; voice ``A`` sounds like the owner, others do not."""
    original = final.diarize

    def diarize(*args, **kwargs):
        output = original(*args, **kwargs)
        output['turns'] = [{'start': start, 'end': end, 'speaker': voice} for start, end, voice in turns]
        output['centroids'] = {
            voice: {'embedding': [1.0, 0.0] if voice == 'A' else [0.0, 1.0], 'evidence_seconds': 12}
            for voice in {t[2] for t in turns}
        }
        return output

    monkeypatch.setattr(final, 'diarize', diarize)


@pytest.fixture
def results(monkeypatch):
    captured = []
    original = batch.run_batch_final_pass

    def run(*args, **kwargs):
        captured.append(original(*args, **kwargs))
        return captured[-1]

    monkeypatch.setattr(batch, 'run_batch_final_pass', run)
    return captured


def test_partial_pass_reuses_the_resolver_voice_and_keeps_resolved(lane, monkeypatch, results):
    _resolved_by(monkeypatch, [7, 7])
    _turns(monkeypatch, (4, 16, 'A'))  # 'Hello' of the first segment falls in a diarizer gap
    first, second = resolve(lane)
    assert results[-1]['outcome'] == 'failed_unassigned_words'
    assert results[-1]['partial_resolution'] == 'kept'
    # Before: the applied segment took a new id (8) beside the resolver's 7, one person as two numbers.
    assert (first.speaker_id, second.speaker_id) == (7, 7)
    assert {s.speaker_id_scope for s in (first, second)} == {'final:batch:conversation:conversation'}
    assert first.is_user and second.is_user
    resolution = lane.conversation.speaker_resolution
    assert resolution.status == 'resolved' and resolution.version == 2


@pytest.mark.parametrize('switch, prior', [('false', 'resolved'), ('true', 'unavailable')])
def test_kill_switch_off_or_unresolved_prior_keeps_new_ids_and_unavailable(lane, monkeypatch, results, switch, prior):
    monkeypatch.setenv('BATCH_FINAL_PASS_KEEP_RESOLVED_ON_PARTIAL_ENABLED', switch)
    _resolved_by(monkeypatch, [7, 7], status=prior)
    _turns(monkeypatch, (4, 16, 'A'))
    first, second = resolve(lane)
    assert results[-1]['partial_resolution'] == ('disabled' if switch == 'false' else 'not_resolved')
    assert (first.speaker_id, second.speaker_id) == (7, 8)
    assert lane.conversation.speaker_resolution.status == 'unavailable'


@pytest.mark.parametrize(
    'ids, turns, reason',
    [
        # Two final voices on one resolver voice: the final pass split it.
        ([7, 7], [(4, 8, 'A'), (8, 16, 'B')], 'split'),
        # Resolver voice 7 is mostly the final voice mapped onto 9: the final pass merged them.
        ([7, 9], [(4, 16, 'A')], 'merge'),
    ],
)
def test_ambiguous_mapping_falls_back_to_new_ids(lane, monkeypatch, results, ids, turns, reason):
    _resolved_by(monkeypatch, ids)
    _turns(monkeypatch, *turns)
    first, second = resolve(lane)
    assert results[-1]['partial_resolution'] == reason
    assert first.speaker_id == ids[0] and second.speaker_id == max(ids) + 1
    assert lane.conversation.speaker_resolution.status == 'unavailable'


def test_mapping_needs_a_clear_majority():
    scope = 'final:batch:conversation:c'
    stored = {
        'a': SimpleNamespace(speaker_id=7, speaker_id_scope=scope),
        'b': SimpleNamespace(speaker_id=9, speaker_id_scope=scope),
        'u': SimpleNamespace(speaker_id=0, speaker_id_scope='final:batch:unit'),
    }
    conversation = SimpleNamespace(id='c', speaker_resolution=ConversationSpeakers(status='resolved'))
    words = lambda *pairs: [{'segment_id': sid, 'speaker': voice} for sid, voice in pairs]  # noqa: E731
    assert batch._resolver_voice_mapping(conversation, stored, words(('a', 'A'), ('b', 'A'))) == (None, 'ambiguous')
    # Words outside the conversation scope belong to no resolver voice.
    assert batch._resolver_voice_mapping(conversation, stored, words(('a', 'A'), ('u', 'A'))) == (None, 'ambiguous')
    mapped = words(('a', 'A'), ('a', 'A'), ('u', 'A'), ('b', 'B'), ('b', None))
    assert batch._resolver_voice_mapping(conversation, stored, mapped) == ({'A': 7, 'B': 9}, 'mapped')


def test_identity_disagreement_on_one_number_falls_back(lane, monkeypatch, results):
    # The resolver named voice 7 a person; the final pass names it the owner. Reusing 7 would show one number with
    # two names, so the pass keeps today's new id.
    _resolved_by(monkeypatch, [7, 7], person_id='resolver-person')
    _turns(monkeypatch, (4, 16, 'A'))
    first, second = resolve(lane)
    assert results[-1]['partial_resolution'] == 'inconsistent'
    assert (first.speaker_id, first.person_id) == (7, 'resolver-person')
    assert second.speaker_id == 8 and second.is_user
    assert lane.conversation.speaker_resolution.status == 'unavailable'


def test_manual_segment_is_untouched_and_the_rest_keeps_resolved(lane, monkeypatch, results):
    sid = lane.conversation.transcript_segments[0].id
    lane.receipts['segments'] = {sid: {'is_user': True, 'person_id': None, 'source': 'manual', 'generation': 1}}
    _resolved_by(monkeypatch, [7, 7])
    _turns(monkeypatch, (0, 16, 'A'))
    manual, other = resolve(lane)
    assert results[-1]['outcome'] == 'success' and results[-1]['partial_resolution'] == 'kept'
    assert manual.speaker_label_source == 'manual' and manual.is_user and manual.speaker_id == 7
    # The receipt reserves the owner (joint naming), so the final voice is no_match; it still reuses voice 7.
    assert other.speaker_id == 7 and other.speaker_identity_status == 'no_match'
    assert lane.conversation.speaker_resolution.status == 'resolved'


# ---- mixed segments split at the voice change (BATCH_FINAL_PASS_SPLIT_MIXED_SEGMENTS_ENABLED) --------------------

from utils.conversations import final_pass_split as splitting  # noqa: E402

SIX = 'one two three four five six.'


def _six_words(lane):
    """Each unit says six one-second words; stored offsets stay unrelated to the audio clock."""
    lane.payload['words'] = [
        {'word': word, 'timestamp': [i * 1.2 + 0.1, i * 1.2 + 1.0]} for i, word in enumerate(SIX.split())
    ]
    segments = [s for item in lane.items.values() for s in projection_segments(item, lane.binding, lane.payload)]
    for i, segment in enumerate(segments):
        segment.start, segment.end = 900 + i * 8, 906 + i * 8
    lane.conversation.transcript_segments = segments
    return segments


def test_a_segment_with_two_voices_splits_at_the_voice_change(lane, monkeypatch, results):
    original = _six_words(lane)
    _turns(monkeypatch, (0, 3.65, 'A'), (3.65, 16, 'B'))  # unit-a: three owner words, then the other voice
    first, second, third = resolve(lane)
    assert results[-1]['outcome'] == 'success' and results[-1]['split_segments'] == 1
    assert first.id == original[0].id and second.id == splitting.split_segment_id(original[0].id, 1)
    assert (first.text, second.text, third.text) == ('One two three', 'four five six.', 'One two three four five six.')
    assert (first.start, first.end, second.start, second.end) == (900, pytest.approx(903.6), pytest.approx(903.6), 906)
    assert first.is_user and not second.is_user and not third.is_user
    assert first.speaker_id != second.speaker_id == third.speaker_id
    assert lane.conversation.speaker_resolution.status == 'resolved'


def test_a_later_pass_reads_the_pieces_back(lane, monkeypatch, results):
    from utils.conversations import final_pass_retry as retry

    _six_words(lane)
    _turns(monkeypatch, (0, 3.65, 'A'), (3.65, 16, 'B'))
    key = retry.scope_key(lane.conversation)
    before = [(s.id, s.text, s.start, s.end) for s in resolve(lane)]
    assert len(before) == 3 and retry.scope_key(lane.conversation) == key  # no new obligation for the same units
    after = resolve(lane)
    assert results[-1]['outcome'] == 'success', results[-1]
    assert results[-1]['split_segments'] == 0 and results[-1]['coverage']['unplaced'] == 0
    assert [(s.id, s.text, s.start, s.end) for s in after] == before
    assert after[0].is_user and not after[1].is_user


def test_kill_switch_restores_whole_segment_relabeling(lane, monkeypatch, results):
    monkeypatch.setenv('BATCH_FINAL_PASS_SPLIT_MIXED_SEGMENTS_ENABLED', 'false')
    original = _six_words(lane)
    _turns(monkeypatch, (0, 3.65, 'A'), (3.65, 16, 'B'))
    segments = resolve(lane)
    assert results[-1]['outcome'] == 'failed_unassigned_words'
    assert [s.id for s in segments] == [s.id for s in original]


def test_a_one_word_reply_is_its_own_piece(lane, monkeypatch, results):
    original = _six_words(lane)
    _turns(monkeypatch, (0, 1.05, 'B'), (1.05, 16, 'A'))  # the other voice says one word first
    first, second, third = resolve(lane)
    assert results[-1]['outcome'] == 'success' and results[-1]['split_segments'] == 1
    assert (first.text, second.text) == ('One', 'two three four five six.')
    assert (
        not first.is_user
        and second.is_user
        and third.is_user
        and second.id == splitting.split_segment_id(original[0].id, 1)
    )


def test_runs_beyond_the_piece_cap_keep_the_segment_whole(lane, monkeypatch, results):
    monkeypatch.setattr(splitting, 'MAX_PIECES', 2)
    original = _six_words(lane)
    _turns(monkeypatch, (0, 1.05, 'A'), (1.05, 2.35, 'B'), (2.35, 16, 'A'))
    segments = resolve(lane)
    assert results[-1]['split_refusals'] == {'too_many_voices': 1}
    assert [s.id for s in segments] == [s.id for s in original]


def test_manual_and_translated_segments_never_split(lane, monkeypatch, results):
    from models.transcript_segment import Translation

    original = _six_words(lane)
    lane.receipts['segments'] = {
        original[0].id: {'is_user': True, 'person_id': None, 'source': 'manual', 'generation': 1}
    }
    original[1].translations = [Translation(lang='de', text='eins zwei drei vier fünf sechs.')]
    _turns(monkeypatch, (0, 3.65, 'A'), (3.65, 11.25, 'B'), (11.25, 16, 'A'))
    segments = resolve(lane)
    assert results[-1]['split_segments'] == 0
    assert results[-1]['split_refusals'] == {'manual': 1, 'translated': 1}
    assert [s.id for s in segments] == [s.id for s in original]


def test_plan_runs_fills_gaps_and_absorbs_short_runs(monkeypatch):
    monkeypatch.setattr(splitting, 'MIN_RUN_WORDS', 3)
    word = lambda voice, start, end=None: {'speaker': voice, 'timestamp': [start, end or start + 0.9]}  # noqa: E731
    words = [word(None, 0), word('A', 1), word('A', 2), word('A', 3), word('B', 4), word('B', 5), word('B', 6)]
    assert [(r.voice, r.first, r.last) for r in splitting.plan_runs(words)] == [('A', 0, 3), ('B', 4, 6)]
    brief = [word('A', 0), word('A', 1), word('A', 2), word('B', 3), word('A', 4), word('A', 5)]
    assert [(r.voice, r.first, r.last) for r in splitting.plan_runs(brief)] == [('A', 0, 5)]
    assert splitting.plan_runs([word(None, 0)]) is None


def test_words_that_do_not_spell_the_text_never_split():
    from models.transcript_segment import TranscriptSegment

    segment = TranscriptSegment(id='s', text='one two three four five six', start=0, end=6, is_user=False)
    words = [
        {'text': t, 'speaker': v, 'timestamp': [i, i + 0.9]}
        for i, (t, v) in enumerate(zip('a b c d e f'.split(), 'AAABBB'))
    ]
    assert splitting.split_segment(segment, words, splitting.plan_runs(words)) is None

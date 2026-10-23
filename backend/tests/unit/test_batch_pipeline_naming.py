"""Bounded Omi-space evidence follows real worker paths outside the GPU lock."""

from types import SimpleNamespace
from dataclasses import replace
from utils.stt.batch_naming import NamingSnapshot, naming_decisions, snapshot_voiceprints
from utils.batch_pipeline.contracts import ProjectionBinding


def snapshot(**kwargs):
    return NamingSnapshot(owner_id='owner', privacy_generation=0, owner_profile={'speaker_embedding': [1, 0]}, **kwargs)


import threading

import numpy as np
import pytest

from config.batch_pipeline_providers import ProviderConfig
from diarizer import batch_pipeline as module
from diarizer.batch_pipeline import PipelineWorker

# Collect pure production imports before the per-test CPU budget, matching the
# file-isolated backend contract rather than charging one test for cold schemas.
from database import batch_pipeline_projection_session as projection_module
from database.batch_pipeline_projection_session import ProjectionSession
from database.conversations import encode_conversation_for_write
from models.transcript_segment import TranscriptSegment
from utils.batch_pipeline.projection import build_incoming
from utils.speakers import processing
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.stt.voice_centroids import (
    COMMUNITY_MODEL_REVISION,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    EMBEDDING_SPACE,
    select_evidence,
    pool_centroids,
)

RATE = 16000


def item(key='one', seconds=40):
    return WorkItem(key, 'synthetic-owner', 100, 'local://synthetic', seconds, Priority.DEEP)


def test_selection_removes_overlap_and_bounds_each_voice():
    turns = [{'speaker': 'a', 'start': i, 'end': i + 20} for i in (0, 30, 60, 90)]
    selected = select_evidence(turns, [{'start': 0, 'end': 19}], duration_seconds=120)
    assert selected == {'a': [(30, 40), (60, 70), (90, 100)]}
    assert select_evidence([{'speaker': 'a', 'start': 0, 'end': 0.4}]) == {}


def test_pooling_normalizes_duration_weighting_and_rejects_bad_vectors():
    result = pool_centroids([([3, 0], 2), ([0, 4], 1), ([float('nan'), 0], 9)])
    assert result['evidence_seconds'] == 3
    np.testing.assert_allclose(result['embedding'], np.array([2, 1]) / np.sqrt(5))
    assert pool_centroids([([0, 0], 2)]) is None


def worker(*, packed=False, silent=False, short=False, extractor=None, io_concurrency=2):
    lock, saved, calls = threading.Lock(), {}, []
    samples = np.ones(40 * RATE, dtype=np.float32)
    words = SimpleNamespace(
        transcribe_batch=lambda clips: [[{'word': 'synthetic', 'timestamp': [1, 2]}] for _ in clips]
    )
    turns = {'turns': [{'speaker': 'a', 'start': 0, 'end': 40}], 'overlaps': [{'start': 10, 'end': 15}]}

    def model(stage, value):
        assert lock.locked(), stage
        calls.append(stage)
        return value

    def extract(clip):
        assert not lock.locked()
        assert np.shares_memory(clip, samples)
        assert 0.5 * RATE <= len(clip) <= 10 * RATE
        calls.append('embedding')
        return np.array([1, 0]) if extractor is None else extractor(clip)

    def persist(unit, payload):
        assert not lock.locked()
        calls.append('persist')
        saved[unit.segment_id] = payload
        return 'artifact://synthetic'

    flight = None
    if packed:
        flight = SimpleNamespace(
            segment=lambda clips: model('packed_segment', [object() for _ in clips]),
            vad_spans=lambda audio, feature: model('packed_vad', [(0, 40)]),
            diarize_many=lambda units: model('packed_diarize', [dict(turns) for _ in units]),
        )
    instance = PipelineWorker(
        decode=lambda unit: samples,
        vad=lambda audio: model('vad', [] if silent else [(0, 40)]),
        words_providers={'synthetic': words},
        diarizers={'pyannote': lambda audio: model('diarize', dict(turns))},
        persist=persist,
        config=ProviderConfig(words='synthetic', window_seconds=30, context_seconds=2),
        gpu_lock=lock,
        io_concurrency=io_concurrency,
        flight_models=flight,
        centroid_extractor=extract,
        single_speaker=(lambda *args: SimpleNamespace(coverage=1.0, speaker_ids={'a': 1})) if short else None,
    )
    return instance, saved, calls


@pytest.mark.parametrize('path', ['serial', 'packed', 'skipped', 'silence'])
def test_all_worker_paths_publish_bounded_compatible_evidence_outside_lock(monkeypatch, path):
    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'true')
    monkeypatch.setattr(module, 'diarize_speech_only_enabled', lambda: False)
    instance, saved, calls = worker(packed=path == 'packed', short=path == 'skipped', silent=path == 'silence')
    results = instance.process_batch([item()])
    assert len(results) == 1
    payload = saved['one']['diarization']
    assert payload['embedding_space'] == EMBEDDING_SPACE
    assert payload['provenance']['model_revision'] == COMMUNITY_MODEL_REVISION
    assert payload['provenance']['embedding_model'] == EMBEDDING_MODEL
    assert payload['provenance']['embedding_revision'] == EMBEDDING_REVISION
    if path == 'silence':
        assert payload['centroids'] == {} and 'embedding' not in calls
    else:
        assert len(payload['centroids']) == 1
        assert payload['centroids'][next(iter(payload['centroids']))]['evidence_seconds'] <= 30
        assert calls.count('embedding') <= 3
    if path == 'packed':
        assert 'packed_diarize' in calls and 'diarize' not in calls
    if path == 'skipped':
        assert 'diarize' not in calls


def test_embedding_failure_keeps_transcript_anonymous_and_uses_shared_fallback(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'true')
    events = []
    monkeypatch.setattr(module, 'record_fallback', lambda **kw: events.append(kw))

    def fail(_):
        raise RuntimeError('private provider body must not leak')

    instance, saved, _ = worker(extractor=fail)
    assert len(instance.process_batch([item()])) == 1
    payload = saved['one']['diarization']
    assert payload['centroids'] == {} and payload['centroid_outcome'] == 'partial'
    assert any(event['to_mode'] == 'unlabeled' and event['outcome'] == 'degraded' for event in events)


def test_kill_off_retains_existing_locked_persistence_and_never_extracts(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'false')
    instance, saved, calls = worker()
    original = instance.persist

    def legacy_persist(unit, payload):
        assert instance._lock.locked()
        saved[unit.segment_id] = payload
        return 'artifact://legacy'

    instance.persist = legacy_persist
    assert len(instance.process_batch([item()])) == 1
    assert 'embedding' not in calls
    assert 'centroids' not in saved['one']['diarization']


@pytest.mark.parametrize('concurrency', [1, 2])
def test_persistence_failure_is_retryable_and_does_not_leave_leaf_jobs(monkeypatch, concurrency):
    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'true')
    instance, _, _ = worker(io_concurrency=concurrency)
    completed = []

    def persist(unit, payload):
        completed.append(unit.segment_id)
        if unit.segment_id == 'bad':
            raise OSError('private storage details')
        return 'artifact://healthy'

    instance.persist = persist
    results = instance.process_batch([item('bad'), item('good')])
    assert [result.segment_id for result in results] == ['good']
    assert set(completed) == {'bad', 'good'}
    assert instance.counts['failed'] == 1


def test_newly_discovered_manual_owner_withdraws_only_new_automatic_owner_without_retry(monkeypatch):

    session = object.__new__(projection_module.ProjectionSession)
    session.incoming_segment_ids = {'new-auto', 'new-manual'}
    session.guard = lambda *_: None
    session.loaded_naming_snapshot = lambda: snapshot(manual_receipt={'speakers': {'7': {'is_user': True}}})
    rows = [
        {
            'id': 'new-auto',
            'speaker_id': 0,
            'is_user': True,
            'speaker_match_source': 'final_centroid:batch-v1',
            'speaker_label_source': 'auto',
        },
        {
            'id': 'old-auto',
            'speaker_id': 1,
            'is_user': True,
            'speaker_match_source': 'final_centroid:batch-v1',
            'speaker_label_source': 'auto',
        },
        {
            'id': 'new-manual',
            'speaker_id': 7,
            'is_user': True,
            'speaker_match_source': None,
            'speaker_label_source': 'manual',
        },
    ]
    planned = {
        'id': 'candidate',
        'transcript_segments': rows,
        'manual_speaker_assignments': {'speakers': {'7': {'is_user': True, 'generation': 1}}},
    }
    session.validate_plan(object(), planned)
    by_id = {s['id']: s for s in planned['transcript_segments']}
    assert by_id['new-auto']['is_user'] is False
    assert by_id['new-auto']['speaker_identity_status'] == 'ambiguous'
    assert by_id['old-auto']['is_user'] is True
    assert by_id['new-manual']['is_user'] is True
    assert by_id['new-manual']['speaker_label_source'] == 'manual'


def test_missing_manual_receipt_does_not_fabricate_reservation():

    session = object.__new__(ProjectionSession)
    session.binding = ProjectionBinding('owner', 'job', 'content', ('unit',))
    session._naming_guard_snapshots = {'user': {'speaker_embedding': [1, 0]}, 'conversations': {'a': {}}}
    assert session.loaded_naming_snapshot().manual_receipt == {}


def test_snapshot_revocation_fence_runs_inside_guard(monkeypatch):

    session = object.__new__(projection_module.ProjectionSession)
    session.binding = ProjectionBinding('owner', 'job', 'content', ('unit',))
    session.client = object()
    session._naming_snapshot = None
    session._naming_guard_snapshots = {}

    def privacy(*args, snapshots, **kwargs):
        snapshots['user'] = {'speaker_embedding': [1, 0]}
        return 0

    monkeypatch.setattr(projection_module, 'assert_batch_write_allowed', privacy)
    monkeypatch.setattr(projection_module, 'lever_enabled', lambda *_: False)
    session.guard(object())
    session.freeze_naming_snapshot(replace(snapshot(), validate=lambda *_: False))
    with pytest.raises(projection_module.ProjectionBlocked, match='enrollment revoked'):
        session.guard(object())


@pytest.mark.parametrize(
    'receipt,expected',
    [
        ({}, (True, None)),
        (
            {'segments': {'new': {'generation': 1, 'is_user': False, 'person_id': 'manual-person'}}},
            (False, 'manual-person'),
        ),
        (
            {
                'segments': {
                    'new': {'generation': 1, 'is_user': False, 'person_id': None, 'rejection': {'kind': 'not_me'}}
                }
            },
            (False, None),
        ),
    ],
)
def test_evidence_abstention_preserves_batch_identity_and_manual_receipts_dominate(monkeypatch, receipt, expected):

    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '0')
    monkeypatch.setattr(processing, '_roster', lambda *_: [])
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **k: None)
    segment = TranscriptSegment(
        id='new',
        text='synthetic',
        start=2,
        end=5,
        is_user=True,
        speaker_id=0,
        speaker_id_scope='final:batch:unit',
        speaker_match_source='final_centroid:batch-v1',
        speaker_label_source='auto',
    )
    conversation = SimpleNamespace(id='conversation', transcript_segments=[segment], source='omi')
    token = processing.begin()
    processing.reason('no_audio')
    processing.finish(token, 'synthetic-owner', conversation, receipt)
    assert (segment.is_user, segment.person_id) == expected


def test_forged_source_strings_do_not_create_identity_evidence(monkeypatch):

    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '0')
    monkeypatch.setattr(processing, '_roster', lambda *_: [])
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **k: None)
    segment = TranscriptSegment(
        id='forged',
        text='synthetic',
        start=2,
        end=5,
        is_user=False,
        speaker_id=0,
        speaker_id_scope='final:batch:forged',
        speaker_match_source='final_centroid:batch-v1',
    )
    conversation = SimpleNamespace(id='conversation', transcript_segments=[segment], source='omi')
    token = processing.begin()
    processing.finish(token, 'synthetic-owner', conversation, {})
    assert segment.is_user is False and segment.person_id is None


def evidence():
    return {
        'embedding_space': EMBEDDING_SPACE,
        'provenance': {
            'model_revision': COMMUNITY_MODEL_REVISION,
            'embedding_model': EMBEDDING_MODEL,
            'embedding_revision': EMBEDDING_REVISION,
        },
        'centroids': {
            'a': {'embedding': [1, 0], 'evidence_seconds': 8},
            'b': {'embedding': [0, 1], 'evidence_seconds': 8},
        },
    }


def test_owner_first_people_require_loaded_entitlement_and_revocation_fence():
    person = {'id': 'person', 'speaker_embedding': [0, 1], 'speech_samples': ['synthetic'], 'speech_samples_version': 3}
    base = snapshot(people=(person,), named_allowed=True)
    decisions = naming_decisions(evidence(), base, owner_id='owner', privacy_generation=0)
    assert decisions['a'].person_id == 'user'
    assert decisions['b'].person_id is None
    authorized = replace(base, validate=lambda *_: True)
    decisions = naming_decisions(evidence(), authorized, owner_id='owner', privacy_generation=0)
    assert decisions['b'].person_id == 'person'
    revoked = replace(authorized, people=({**person, 'revoked_at': 'synthetic'},))
    assert naming_decisions(evidence(), revoked, owner_id='owner', privacy_generation=0)['b'].person_id is None
    assert naming_decisions(evidence(), authorized, owner_id='other', privacy_generation=0) == {}
    assert naming_decisions(evidence(), authorized, owner_id='owner', privacy_generation=1) == {}


def test_naming_requires_immutable_compatible_provenance_and_manual_owner_wins():
    payload = evidence()
    payload['provenance']['embedding_revision'] = 'incompatible'
    assert naming_decisions(payload, snapshot(), owner_id='owner', privacy_generation=0) == {}
    reserved = snapshot(manual_receipt={'speakers': {'4': {'generation': 1, 'is_user': True}}})
    assert naming_decisions(evidence(), reserved, owner_id='owner', privacy_generation=0)['a'].person_id is None
    assert naming_decisions(evidence(), None, owner_id='owner', privacy_generation=0) == {}


def test_faithful_turns_use_max_overlap_preserve_clocks_and_strict_two_second_boundary():
    from utils.conversations.final_pass_assignment import build_turns

    words = [
        {'word': 'synthetic', 'timestamp': [3, 4]},
        {'word': 'joined', 'timestamp': [5.9, 6]},
        {'word': 'boundary', 'timestamp': [8, 9]},
        {'word': 'other', 'timestamp': [9, 10]},
        {'word': 'gap', 'timestamp': [12, 13]},
    ]
    turns = [{'speaker': 'a', 'start': 3, 'end': 9}, {'speaker': 'b', 'start': 9, 'end': 11}]
    actual = build_turns(words, turns, scope='final:batch:unit', id_namespace='batch:unit:')
    assert [s.text for s in actual] == ['synthetic joined', 'boundary', 'other', 'gap']
    assert [(s.start, s.end) for s in actual] == [(3, 6), (8, 9), (9, 10), (12, 13)]
    assert [s.speaker for s in actual] == ['a', 'a', 'b', None]
    assert actual[-1].speaker_match_source == 'batch_abstention'
    assert [s.id for s in actual] == [
        s.id for s in build_turns(words, turns, scope='final:batch:unit', id_namespace='batch:unit:')
    ]


def test_owner_enrollment_change_is_fenced_before_write(monkeypatch):

    session = object.__new__(projection_module.ProjectionSession)
    session.binding = ProjectionBinding('owner', 'job', 'content', ('unit',))
    session.client = object()
    session._naming_snapshot = None
    session._naming_guard_snapshots = {'user': {'speaker_embedding': [1, 0]}}
    session.freeze_naming_snapshot(session.loaded_naming_snapshot())

    def privacy(*args, snapshots, **kwargs):
        snapshots['user'] = {'speaker_embedding': [0, 1]}
        return 0

    monkeypatch.setattr(projection_module, 'assert_batch_write_allowed', privacy)
    monkeypatch.setattr(projection_module, 'lever_enabled', lambda *_: False)
    with pytest.raises(projection_module.ProjectionBlocked, match='snapshot changed'):
        session.guard(object())


def test_production_projection_publishes_named_owner_and_anonymous_voice_with_capture_clocks(monkeypatch):

    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'true')
    payload = {
        'audio_seconds': 40,
        'words': [{'word': 'synthetic', 'timestamp': [3, 4]}, {'word': 'other', 'timestamp': [9, 10]}],
        'diarization': {
            **evidence(),
            'turns': [{'speaker': 'a', 'start': 0, 'end': 8}, {'speaker': 'b', 'start': 8, 'end': 20}],
        },
    }
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('one',), record_origin=True)
    authorized = replace(snapshot(), owner_id='synthetic-owner')
    incoming = build_incoming(item(), binding, payload, naming_snapshot=authorized)
    segments = incoming['transcript_segments']
    assert [(s['start'], s['end']) for s in segments] == [(3, 4), (9, 10)]
    assert [(s['is_user'], s['person_id']) for s in segments] == [(True, None), (False, None)]
    assert {s['speaker_id_scope'] for s in segments} == {'final:batch:one'}
    assert segments[0]['speaker_label_source'] == 'auto'
    assert 'centroids' not in incoming and '_batch_voice_evidence' not in incoming


def test_hosted_embedding_encodes_bounded_pcm_for_existing_v2_endpoint(monkeypatch):
    import io
    import wave
    from diarizer.batch_pipeline_models import HostedCentroidEmbedding
    from utils.stt import speaker_embedding

    calls = []

    def extract(body, *, timeout):
        with wave.open(io.BytesIO(body), 'rb') as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, RATE, RATE)
        calls.append(timeout)
        return np.array([1, 0])

    monkeypatch.setattr(speaker_embedding, 'extract_embedding_from_bytes', extract)
    np.testing.assert_equal(HostedCentroidEmbedding()(np.zeros(RATE, dtype=np.float32)), [1, 0])
    assert calls == [30.0]
    with pytest.raises(ValueError, match='bounded evidence'):
        HostedCentroidEmbedding()(np.zeros(11 * RATE))


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_loaded_manual_owner_receipt_decodes_actual_storage_encoding(monkeypatch, level):
    from utils.manual_speaker_assignments import manual_owner_reserved

    monkeypatch.setenv('ENCRYPTION_SECRET', '01' * 32)
    encoded = encode_conversation_for_write(
        'owner', {'manual_speaker_assignments': {'speakers': {'7': {'generation': 1, 'is_user': True}}}}, level
    )
    assert not isinstance(encoded['manual_speaker_assignments'], dict)
    session = object.__new__(ProjectionSession)
    session.binding = ProjectionBinding('owner', 'job', 'content', ('unit',))
    session._naming_guard_snapshots = {'user': {'speaker_embedding': [1, 0]}, 'conversations': {'canonical': encoded}}
    assert manual_owner_reserved(session.loaded_naming_snapshot().manual_receipt)
    decisions = naming_decisions(evidence(), session.loaded_naming_snapshot(), owner_id='owner', privacy_generation=0)
    assert decisions['a'].person_id is None


def test_explicit_archive_enrichment_uses_serving_hook_and_preserves_original():
    from copy import deepcopy

    instance, saved, _ = worker()
    samples = np.zeros(40 * RATE, dtype=np.float32)
    original = {
        'audio_seconds': 40,
        'speech_seconds': 40,
        'speech_spans': [{'start': 0, 'end': 40}],
        'words': [{'word': 'synthetic', 'timestamp': [1, 2]}],
        'diarization': {
            'turns': [{'speaker': 'a', 'start': 0, 'end': 40}],
            'provenance': {'model_revision': COMMUNITY_MODEL_REVISION},
        },
    }
    before = deepcopy(original)
    enriched = PipelineWorker.enrich_result(item(), original, samples, centroid_extractor=lambda _: [1, 0])
    assert original == before
    assert enriched['diarization']['centroids']['a']['evidence_seconds'] <= 30
    assert enriched['words'] == original['words']
    original['diarization']['provenance']['model_revision'] = 'wrong'
    with pytest.raises(ValueError, match='incompatible inference'):
        PipelineWorker.enrich_result(item(), original, samples, centroid_extractor=lambda _: [1, 0])


def test_explicit_enrichment_obeys_live_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'false')
    original = {'synthetic': 'unchanged'}

    def forbidden(_):
        raise AssertionError('disabled extraction must not run')

    assert PipelineWorker.enrich_result(item(), original, np.zeros(RATE), centroid_extractor=forbidden) == original

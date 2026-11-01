"""Vendor-route speaker turns join the GPU unit scope, centroids and resolver (synthetic only)."""

import asyncio
from datetime import datetime, timezone
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import batch_conversation_speakers as flags
from config.batch_conversation_speakers import vendor_speaker_authority
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from tests.unit.test_batch_voice_evidence import CID, UID, VECTOR, persist, setup_prepare, state
from utils.batch_pipeline import projection, provider_stt, voice_evidence as evidence
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from config.policy import ProjectionPolicy
from utils.batch_pipeline.projection_parts import split_result
from utils.conversations import speaker_resolution as stage
from utils.conversations import sync_off_speakers

UTTERANCES = [
    {'word': 'Hello there.', 'timestamp': [0.0, 1.5], 'speaker': 'SPEAKER_00'},
    {'word': 'And again.', 'timestamp': [1.5, 2.0], 'speaker': 'SPEAKER_00'},
    {'word': 'Hi.', 'timestamp': [2.5, 3.0], 'speaker': 'SPEAKER_01'},
    {'word': 'Later.', 'timestamp': [4.0, 4.6], 'speaker': 'SPEAKER_00'},
]


def vendor_payload(duration=5.0, turns=None):
    words = [dict(word) for word in UTTERANCES]
    return {
        'audio_seconds': duration,
        'speech_seconds': duration,
        'speech_spans': [{'start': 0.0, 'end': duration}],
        'words': words,
        'diarization': {'turns': provider_stt.vendor_turns(words, duration) if turns is None else turns},
        'words_provider': 'modulate',
        'language': 'en',
        'recovery_version': 1,
    }


@pytest.fixture(autouse=True)
def switch_default(monkeypatch):
    monkeypatch.delenv(flags.VENDOR_SPEAKER_TURNS_ENV, raising=False)


def test_turns_merge_touching_records_and_never_span_pauses():
    assert provider_stt.vendor_turns(UTTERANCES, 5.0) == [
        {'start': 0.0, 'end': 2.0, 'speaker': 'SPEAKER_00'},
        {'start': 2.5, 'end': 3.0, 'speaker': 'SPEAKER_01'},
        {'start': 4.0, 'end': 4.6, 'speaker': 'SPEAKER_00'},
    ]


def test_turns_skip_point_words_invalid_labels_and_clamp_to_pcm():
    words = [
        {'word': 'point', 'timestamp': [1.0, 1.0], 'speaker': 'SPEAKER_00'},
        {'word': 'odd', 'timestamp': [1.0, 2.0], 'speaker': 'SPEAKER_9998'},
        {'word': 'none', 'timestamp': [2.0, 3.0]},
        {'word': 'tail', 'timestamp': [3.0, 5.005], 'speaker': 'SPEAKER_02'},
    ]
    assert provider_stt.vendor_turns(words, 5.0) == [{'start': 3.0, 'end': 5.0, 'speaker': 'SPEAKER_02'}]


@pytest.mark.parametrize('switch', [None, 'false'])
def test_provider_payload_carries_vendor_turns_unless_killed(monkeypatch, switch):
    if switch:
        monkeypatch.setenv(flags.VENDOR_SPEAKER_TURNS_ENV, switch)

    async def vendor(service, wav, duration, language):
        return [{'text': w['word'], 'timestamp': w['timestamp'], 'speaker': w['speaker']} for w in UTTERANCES], 'en'

    monkeypatch.setattr(provider_stt, '_vendor_words', vendor)
    item = WorkItem('unit', UID, 1700000000.0, 'gs://synthetic/pcm', 5.0, Priority.FRESH)
    inspected = (b'\0\0' * 16000 * 5, 5.0, [{'start': 0.0, 'end': 5.0}])
    payload = asyncio.run(provider_stt.transcribe_async(item, 'en', inspected, service='modulate'))
    assert payload['recovery_version'] == 1
    assert payload['diarization']['turns'] == ([] if switch else provider_stt.vendor_turns(payload['words'], 5.0))
    assert [w['speaker'] for w in payload['words']] == [w['speaker'] for w in UTTERANCES]


def build(monkeypatch, payload):
    from utils.conversations import deterministic_minimum
    from utils.sync import intake_completion

    monkeypatch.setattr(deterministic_minimum, 'build_deterministic_minimum_structured', lambda *a, **k: Structured())
    monkeypatch.setattr(intake_completion, 'apply_capture_evidence_dark_write', lambda *a: None)
    monkeypatch.setattr(projection, 'cap_dispatch_enabled', lambda *a: False)
    item = WorkItem('unit', UID, 1700000000.0, 'gs://synthetic/pcm', payload['audio_seconds'], Priority.FRESH)
    binding = ProjectionBinding(item.owner_id, 'job', 'content', (item.segment_id,))
    part, partition = split_result(item, payload)[0]
    policy = ProjectionPolicy(authoritative_labels=True)
    return projection.build_incoming(part, binding, partition, batch_segment_id=item.segment_id, policy=policy)


def test_vendor_turns_project_as_authoritative_unit_with_vendor_labels(monkeypatch):
    segments = build(monkeypatch, vendor_payload())['transcript_segments']
    assert {s['speaker_id_scope'] for s in segments} == {'final:batch:unit'}
    assert {s['speaker_match_source'] for s in segments} == {'batch_vendor'}
    assert {s['speaker'] for s in segments} == {'SPEAKER_00', 'SPEAKER_01'}
    assert not any(s['is_user'] or s['person_id'] for s in segments)


@pytest.mark.parametrize('killed', [False, True])
def test_words_only_or_killed_vendor_units_keep_todays_sync_scope(monkeypatch, killed):
    if killed:
        monkeypatch.setenv(flags.VENDOR_SPEAKER_TURNS_ENV, 'false')
    payload = vendor_payload(turns=None if killed else [])
    assert not vendor_speaker_authority(payload)
    segments = build(monkeypatch, payload)['transcript_segments']
    scopes = {s['speaker_id_scope'] for s in segments}
    assert len(scopes) == 1 and next(iter(scopes)).startswith('sync:')  # the split part's own scope
    assert {s['speaker_match_source'] for s in segments} == {None}
    assert {s['speaker'] for s in segments} == {'SPEAKER_00', 'SPEAKER_01'}


def test_recovered_units_without_turns_stay_outside_voice_authority():
    payload = vendor_payload(turns=[])
    assert not vendor_speaker_authority(payload)
    assert not vendor_speaker_authority({**vendor_payload(), 'recovery_version': None})


@pytest.mark.parametrize('killed', [False, True])
def test_sync_off_evidence_is_extracted_from_vendor_turns_unless_killed(monkeypatch, killed):
    if killed:
        monkeypatch.setenv(flags.VENDOR_SPEAKER_TURNS_ENV, 'false')
    _, _, objects, item, projector, embedding = setup_prepare(monkeypatch)
    projector.load_result.return_value = vendor_payload(duration=10.0)
    evidence.prepare(projector, item, SimpleNamespace(private_cloud_sync_enabled=False), CID)
    if killed:
        projector.fetch_audio.assert_not_called()
        embedding.assert_not_called()
        assert not objects.objects
    else:
        projector.fetch_audio.assert_called_once()
        assert embedding.call_count == 2  # one exclusive clip per vendor label
        assert objects.uploads == 1


def vendor_conversation(units, scope):
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
                speaker_id=0,  # every unit's own SPEAKER_00, before resolution
                is_user=False,
                start=i * 2,
                end=i * 2 + 2,
                stt_provider='modulate',
                speaker_match_source='batch_vendor' if scope == 'final:batch:' else None,
                speaker_id_scope=f'{scope}{unit}',
            )
            for i, unit in enumerate(units)
        ],
    )


@pytest.mark.parametrize('scope', ['final:batch:', 'sync:'])
def test_sync_off_vendor_units_link_across_the_conversation(monkeypatch, scope):
    """Three vendor units, each saying SPEAKER_00: with turns they resolve to one owner voice;
    today's words-only `sync:` units have no evidence and stay three unlinked unit voices."""
    store, artifacts, objects, capture = state()
    units = [f'unit{i}' for i in range(3)]
    for i, unit in enumerate(units):
        persist(store, artifacts, capture + i, unit)
    conversation = vendor_conversation(units, scope)
    monkeypatch.setattr(stage.speaker_evidence, '_roster', lambda *a: [])
    monkeypatch.setattr(stage.speaker_evidence.storage, 'store_evidence', lambda *a, **kw: None)
    monkeypatch.setattr(
        sync_off_speakers,
        'load_vectors',
        lambda uid, conv, deadline: evidence.load_vectors(uid, conv, deadline, store=store, artifacts=artifacts),
    )
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(stage, 'resolution_enabled', lambda: True)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda uid, **kw: {'user': VECTOR})
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', lambda *a: pytest.fail('no durable cache'))
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', lambda *a, **kw: pytest.fail('no audio_files'))
    vectors, _, _ = evidence.load_vectors(UID, conversation, time.monotonic() + 10, store=store, artifacts=artifacts)
    stage.resolve_speakers_for_processing(UID, conversation)
    voices = {(s.speaker_id_scope, s.speaker_id) for s in conversation.transcript_segments}
    if scope == 'sync:':
        assert not vectors
        assert len(voices) == 3 and not any(s.is_user for s in conversation.transcript_segments)
        return
    assert set(vectors) == {'s0', 's1', 's2'}
    assert voices == {(f'final:batch:conversation:{CID}', next(iter(voices))[1])}
    assert all(s.is_user for s in conversation.transcript_segments)


def test_switch_defaults_on_and_turns_off_on_false_words(monkeypatch):
    assert flags.vendor_turns_enabled()
    monkeypatch.setenv(flags.VENDOR_SPEAKER_TURNS_ENV, 'false')
    assert not flags.vendor_turns_enabled()
    monkeypatch.setenv(flags.VENDOR_SPEAKER_TURNS_ENV, 'garbage')
    assert flags.vendor_turns_enabled()

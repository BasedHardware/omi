"""Exercise the serving changes at the actual finalize entrypoint."""

import uuid

import pytest

from config.owner_recognition_diagnostics import REASONS
from utils.conversations import speaker_resolution as stage
from utils.speakers import processing
from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    _conversation,
    _install_audio,
    _capture_shifted_conversation,
    STARTED,
)
from models.audio_file import AudioFile, ChunkSpan


@pytest.fixture(autouse=True)
def explicit_shadow_storage_sample(monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '100')


@pytest.fixture(autouse=True)
def evidence_store(monkeypatch):
    rows = []
    monkeypatch.setattr(
        processing.storage, 'store_evidence', lambda _account, _cid, evidence, **kwargs: rows.append(evidence)
    )
    return rows


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_batch_linking_is_independent_of_evidence_mode(env, monkeypatch, evidence_store, mode):
    _, diarizer = env
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '0')
    plan = [0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['sync:a', 'sync:b', 'sync:c', 'final:batch:d'])
    tail = conversation.transcript_segments[-1]
    tail.audio_source = {
        'type': 'sync',
        'start': STARTED.timestamp() + tail.start,
        'end': STARTED.timestamp() + tail.end,
    }
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert diarizer.calls == 4
    if mode != 'off':
        assert len(evidence_store[-1].clusters) == 2
        assert conversation.speaker_resolution.status == 'resolved'


def test_batch_diagnostic_reason_is_truthful_unflagged(env, monkeypatch):
    monkeypatch.setenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', 'false')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    reasons = []
    monkeypatch.setattr(stage.owner_diagnostics, 'resolver_reason', reasons.append)
    conversation = _conversation([0], scopes=['final:batch:d'])
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert reasons[-1] == 'batch_authoritative'
    assert 'batch_authoritative' in REASONS


@pytest.mark.parametrize('mode,embeddings', [('shadow', 0), ('serve', 4)])
def test_uncovered_tail_does_not_block_proven_audio_in_serve(env, monkeypatch, evidence_store, mode, embeddings):
    _, diarizer = env
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '0')
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan[:4], offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    origin = STARTED.timestamp()
    conversation.audio_files = [
        AudioFile(
            id='af',
            uid=str(uuid.uuid4()),
            conversation_id='c1',
            chunk_timestamps=[origin + 180.0],
            duration=16.0,
            chunk_spans=[ChunkSpan(start=origin + 180.0, end=origin + 196.0)],
        )
    ]
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert diarizer.calls == embeddings
    assert conversation.speaker_resolution.status == 'unavailable'
    if mode == 'serve':
        assert evidence_store[-1].status == 'partial'
        assert 'no_voice_evidence' in evidence_store[-1].abstentions


def test_manual_receipt_remains_authority_for_batch_in_serve(env, monkeypatch, evidence_store):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    _install_audio(monkeypatch, [0, 1])
    conversation = _conversation([0, 1], scopes=['sync:a', 'final:batch:b'])
    receipt = {'generation': 1, 'segments': {'s1': {'is_user': True, 'person_id': None, 'generation': 1}}}
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: receipt)
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert conversation.transcript_segments[1].is_user
    assert any(c.source == 'manual' and c.probability == 1 for v in evidence_store[-1].clusters for c in v.candidates)


def test_unproven_batch_scope_stays_anonymous_beside_resolved_sync(env, monkeypatch, evidence_store):
    _, diarizer = env
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    plan = [0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['sync:a', 'sync:b', 'sync:c', 'final:batch:d'])
    conversation.transcript_segments[-1].audio_alignment = 'unplaced'
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert diarizer.calls == 3
    assert evidence_store[-1].status == 'partial'
    assert 'no_compatible_centroid' in evidence_store[-1].abstentions
    assert conversation.transcript_segments[-1].speaker_id_scope == 'final:batch:d'
    assert not conversation.transcript_segments[-1].is_user


def test_all_batch_with_compatible_windows_preserves_distinct_pyannote_labels(env, monkeypatch, evidence_store):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setattr(stage, 'authoritative_for', lambda _: True)
    plan = [0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['final:batch:d'] * 4)
    for segment in conversation.transcript_segments:
        segment.audio_source = {
            'type': 'sync',
            'start': STARTED.timestamp() + segment.start,
            'end': STARTED.timestamp() + segment.end,
        }
    stage.resolve_speakers_for_processing(str(uuid.uuid4()), conversation)
    assert evidence_store[-1].status == 'resolved'
    assert len(evidence_store[-1].clusters) == 4


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('window_start,allowed', [(0.0, True), (11.0, False)])
def test_decoded_overlap_refuses_only_affected_windows_in_all_modes(monkeypatch, mode, window_start, allowed):
    from types import SimpleNamespace
    from utils.conversations.audio_placement import AudioPlacement

    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    origin = STARTED.timestamp()
    chunks = [
        dict(
            path=str(i),
            timestamp=origin + start,
            generation=1,
            span={'start': origin + start, 'samples': 4 * 16000, 'sample_rate': 16000},
        )
        for i, start in enumerate((0, 10, 12))
    ]
    session = SimpleNamespace(
        deadline=float('inf'),
        in_budget=lambda: True,
        chunks=chunks,
        limit_hit=False,
        fetch=lambda path: b'\0\0' * (4 * 16000),
    )
    monkeypatch.setattr(stage, 'AudioChunkReadSession', lambda *args: session)
    files = [
        dict(chunk_timestamps=[c['timestamp']], chunk_spans=[dict(start=c['timestamp'], end=c['timestamp'] + 4.0)])
        for c in chunks
    ]
    segment = _conversation([0]).transcript_segments[0]
    placements = {segment.id: AudioPlacement((origin + window_start, origin + window_start + 3.0), 'v2')}
    result = stage._verified_read_session(
        str(uuid.uuid4()), _conversation([0]), files, [segment], placements, float('inf')
    )
    assert (result is session) is allowed
    if allowed:
        assert result.verified_segment_ids == {segment.id}

"""Batch constraints survive the real storage boundary, including sidecar loss."""

import numpy as np
import pytest

from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE, has_batch_authority
from database import conversations as db
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from tests.unit.test_conversation_speaker_resolution_stage import (
    STARTED,
    _conversation,
    _span_manifest,
    env,
)
from utils.conversations import speaker_resolution as stage
from utils.conversations.speaker_grouping_shadow import batch_provider_keys
from utils.stt.conversation_speakers import resolve_conversation_speakers


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('evidence_mode', ['off', 'serve'])
def test_long_batch_storage_roundtrip_retains_partition_and_accepts_new_units(monkeypatch, env, level, evidence_mode):
    from utils.speakers import processing as evidence_processing

    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', evidence_mode)
    monkeypatch.delenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', raising=False)
    monkeypatch.setattr(evidence_processing, '_roster', lambda *_: [])
    monkeypatch.setattr(evidence_processing.storage, 'store_evidence', lambda *a, **kw: None)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {})
    store, diarizer = env
    conv = _conversation([0, 1] * 150, seconds=2, scopes=[f'final:batch:unit{i // 75}' for i in range(300)])
    for i, segment in enumerate(conv.transcript_segments):
        segment.speaker_id = (i // 75) * 2 + i % 2
    origin = STARTED.timestamp()
    conv.audio_files = [_span_manifest(origin, [(origin, origin + 604)])]
    vectors = {s.id: (1.8, np.array([1, 0.1 if i % 2 else -0.1])) for i, s in enumerate(conv.transcript_segments)}
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    before = [s.speaker_id for s in conv.transcript_segments]
    assert len(set(before)) == 2
    assert all(s.speaker_id_scope == f'{BATCH_CONVERSATION_SCOPE}c1' for s in conv.transcript_segments)

    stored = db.encode_conversation_for_write('synthetic', conv.model_dump(), level)
    rows = db.decode_transcript_segments_verified('synthetic', stored['transcript_segments'], True)
    assert all('provider_speaker' not in s for s in rows)  # >256 sidecars are deliberately dropped.
    conv = Conversation(**{**conv.model_dump(), 'transcript_segments': rows})
    assert has_batch_authority(conv.transcript_segments)
    # Even wildly inconsistent cached clips cannot split a prior must-link;
    # identical clips across prior voices cannot collapse their cannot-link.
    vectors = {s.id: (1.8, np.array([1, i % 3 - 1])) for i, s in enumerate(conv.transcript_segments)}
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    after = [s.speaker_id for s in conv.transcript_segments]
    assert len(set(after)) == 2
    assert all((before[i] == before[0]) == (after[i] == after[0]) for i in range(300))

    # A fresh upload can join a frozen group without joining the two old groups.
    fresh = TranscriptSegment(
        id='fresh',
        text='synthetic',
        start=600,
        end=601.8,
        speaker_id=8,
        speaker_id_scope='final:batch:fresh',
        is_user=False,
    )
    conv.transcript_segments.append(fresh)
    vectors['fresh'] = (1.8, np.array([1, 0]))
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    assert len({s.speaker_id for s in conv.transcript_segments}) == 2
    assert diarizer.calls == 0


def test_partial_marker_loss_uses_whole_snapshot_and_invalid_marker_abstains():
    segments = _conversation([0] * 4, scopes=[f'{BATCH_CONVERSATION_SCOPE}c1'] * 4).transcript_segments
    for s, voice in zip(segments, [0, 0, 1, 1]):
        s.speaker_id = voice
        s.provider_speaker = {'scope': f'final:batch:unit{s.id}', 'id': 0}
    segments[0].provider_speaker = None
    segments[3].provider_speaker = {'scope': 'ambiguous', 'id': -1}
    keys = batch_provider_keys(segments)
    assert keys['s0'] == keys['s1']
    assert keys['s0'] != keys['s2']
    assert 's3' not in keys
    result = resolve_conversation_speakers(
        segments,
        {s.id: [1, 0] for s in segments},
        grouping='batch_authoritative',
        provider_keys=keys,
        abstained_segment_ids={'s3'},
    )
    assert result.speaker_ids['s0'] == result.speaker_ids['s1']
    assert result.speaker_ids['s0'] != result.speaker_ids['s2']
    assert 's3' not in result.speaker_ids

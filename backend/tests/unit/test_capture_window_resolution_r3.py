"""Local continuous sync/v2 edge replay against the exact pre-R2 stage."""

import io
import subprocess
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from models.conversation import AudioTimelineProvenance
from tests.unit.test_capture_window_resolution_r2 import verified_audio
from tests.unit.test_conversation_speaker_resolution_stage import (
    SR,
    STARTED,
    _conversation,
    _patch_stage_deps,
    _span_manifest,
    env,
    stage,
)
from utils.other.audio_chunks import AudioChunkReadSession


@pytest.fixture(scope='module')
def base_stage():
    # Load local Git source outside the 0.30 s call-phase guard, without ref edits.
    source = subprocess.run(
        ['git', 'show', '0a435947a9:backend/utils/conversations/speaker_resolution.py'],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType('capture_resolution_pre_r2')
    exec(compile(source, 'speaker_resolution_pre_r2.py', 'exec'), module.__dict__)
    return module


def _input(scope, duration):
    conversation = _conversation([0], seconds=duration + 0.2, scopes=['sync:offline'])
    conversation.transcript_segments[0].end = duration
    if scope == 'v2':
        conversation.audio_timeline = AudioTimelineProvenance(version=2)
    return conversation


@pytest.mark.parametrize('scope', ['sync', 'v2'])
@pytest.mark.parametrize(
    'duration,extents',
    [
        (1.2, [(0, 1.2)]),
        (1.2, [(0.0005, 1.2)]),
        (1.2, [(0, 1.1995)]),
        (1.2, [(0.0005, 1.1995)]),
        (1.2, [(0, 0.6), (0.6, 1.1995)]),
        (1.0005, [(0, 1.0)]),
        (1.0005, [(0, 0.9996)]),
    ],
)
def test_continuous_sync_v2_edges_no_worse_than_base(
    env, verified_audio, base_stage, monkeypatch, scope, duration, extents
):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = _input(scope, duration)
    session = verified_audio(conversation, extents)
    # Placement and manifest prove the requested window. The actual listed/
    # decoded edges differ only within the pre-existing coverage tolerance.
    origin = STARTED.timestamp()
    declared = [(origin + s, origin + e) for s, e in extents]
    declared[0] = (origin, declared[0][1])
    declared[-1] = (declared[-1][0], origin + duration)
    conversation.audio_files = [_span_manifest(origin, declared)]
    clips = []

    def embed(wav, **kwargs):
        with wave.open(io.BytesIO(wav)) as reader:
            clips.append(reader.readframes(reader.getnframes()))
        return np.ones(64)

    base_store = {}
    _patch_stage_deps(monkeypatch, base_stage, base_store, embed)
    monkeypatch.setattr(base_stage, 'AudioChunkReadSession', lambda *args: session)
    monkeypatch.setattr(base_stage, 'iter_audio_chunk_pcm', stage.iter_audio_chunk_pcm)
    base_conversation = conversation.model_copy(deep=True)
    base_stage.resolve_speakers_for_processing('offline', base_conversation)
    base_clips = list(clips)
    clips.clear()
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', embed)
    stage.resolve_speakers_for_processing('offline', conversation)

    enough_pcm = sum(round((e - s) * SR) for s, e in extents) >= SR
    assert len(clips) == int(enough_pcm)
    assert len(clips) >= len(base_clips)
    if base_clips:
        assert conversation.speaker_resolution.status == base_conversation.speaker_resolution.status == 'resolved'
        assert env[0]['c1'] == base_store['c1']
        assert clips == base_clips
    if clips:
        expected = base_clips[0] if base_clips else b''.join(session.cache[c['path']][0] for c in session.chunks)
        assert clips == [expected]
        assert len(clips[0]) >= SR * 2
    else:
        assert conversation.speaker_resolution.status != 'resolved'


@pytest.mark.parametrize('scope', ['sync', 'v2'])
@pytest.mark.parametrize('gap', [0.0005, 0.01])
def test_sync_v2_internal_gaps_refuse_even_with_tolerated_edges(env, verified_audio, monkeypatch, scope, gap):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = _input(scope, 2.4)
    verified_audio(conversation, [(0, 1.2), (1.2 + gap, 2.3995)])
    stage.resolve_speakers_for_processing('offline', conversation)
    assert env[1].calls == 0
    assert conversation.speaker_resolution.status != 'resolved'


@pytest.mark.parametrize('edge', ['leading', 'trailing'])
@pytest.mark.parametrize('missing', [0.001, 0.0011])
def test_clip_edge_tolerance_is_bounded(edge, missing):
    session = AudioChunkReadSession('offline', 'local')
    start = missing if edge == 'leading' else 0
    samples = round((2 - missing) * SR)
    pcm = np.full(samples, 1000, dtype=np.int16).tobytes()
    session._chunks = [dict(path='local', timestamp=start, generation=1)]
    session.cache['local'] = (pcm, 'none')
    clip, reason = stage._verified_clip(session, 0, 2)
    if missing <= 0.001:
        assert clip == pcm and reason == 'none'
    else:
        assert clip is None

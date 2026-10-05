"""Exact-base additive policy and inward half-open PCM assembly, entirely local."""

import io
import os
import random
import subprocess
import sys
import time
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from tests.unit.test_capture_window_resolution_r2 import verified_audio
from tests.unit.test_capture_window_resolution_r3 import base_stage, _input
from tests.unit.test_conversation_speaker_resolution_stage import (
    FakeDiarizer,
    SR,
    STARTED,
    _patch_stage_deps,
    env,
    stage,
)
from utils.conversations.audio_placement import AudioPlacement
from utils.other.audio_chunks import AudioChunkReadSession


@pytest.fixture(scope='module')
def previous_stage():
    source = subprocess.run(
        ['git', 'show', 'cec8675d35:backend/utils/conversations/speaker_resolution.py'],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType('capture_resolution_pre_r4')
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, module.__name__, module)
        exec(compile(source, 'speaker_resolution_pre_r4.py', 'exec'), module.__dict__)
        yield module


@pytest.fixture(autouse=True)
def red_stage(monkeypatch, previous_stage):
    if os.environ.get('OMI_CAPTURE_R4_RED') == '1':
        monkeypatch.setattr(
            previous_stage,
            'extract_embedding_from_bytes',
            lambda *args, **kwargs: stage.extract_embedding_from_bytes(*args, **kwargs),
        )
        monkeypatch.setattr(stage, '_embed_missing', previous_stage._embed_missing)
        monkeypatch.setattr(stage, '_verified_clip', previous_stage._verified_clip)


class SampleDiarizer(FakeDiarizer):
    """Mixed sample voices produce different vectors; also retain the exact PCM."""

    def __init__(self):
        super().__init__()
        self.clips = []

    def __call__(self, wav, **kwargs):
        with wave.open(io.BytesIO(wav)) as reader:
            self.clips.append(reader.readframes(reader.getnframes()))
        return super().__call__(wav, **kwargs)


def _scoped_input(scope, duration):
    conversation = _input(scope, duration)
    if scope == 'live':
        segment = conversation.transcript_segments[0]
        segment.speaker_id_scope = 'live:offline'
        segment.audio_capture_start = STARTED.timestamp()
        segment.audio_capture_end = STARTED.timestamp() + duration
    return conversation


def _voices(session):
    for index, chunk in enumerate(session.chunks):
        pcm = session.cache[chunk['path']][0]
        # Distinct voices inside and across chunks, so evidence replacement is
        # observable acoustically, not just in the recorded byte comparison.
        values = np.full(len(pcm) // 2, (index % 4 + 1) * 1000, dtype=np.int16)
        values[len(values) // 3 : len(values) // 2] = ((index + 1) % 4 + 1) * 1000
        session.cache[chunk['path']] = (values.tobytes(), 'none')


def _base_resolution(monkeypatch, base_stage, conversation, session):
    store, diarizer = {}, SampleDiarizer()
    _patch_stage_deps(monkeypatch, base_stage, store, diarizer)
    monkeypatch.setattr(base_stage, 'AudioChunkReadSession', lambda *args: session)
    monkeypatch.setattr(base_stage, 'iter_audio_chunk_pcm', stage.iter_audio_chunk_pcm)
    old = conversation.model_copy(deep=True)
    base_stage.resolve_speakers_for_processing('offline', old)
    return old, store, diarizer


@pytest.mark.parametrize('scope', ['sync', 'v2', 'live'])
@pytest.mark.parametrize('seed', range(64))
def test_randomized_base_embedding_is_byte_identical(env, verified_audio, base_stage, monkeypatch, scope, seed):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    rng = random.Random(seed)
    extents = []
    start = 0.0
    for _ in range(rng.randint(1, 6)):
        end = start + rng.randint(SR * 2, SR * 22) / SR
        extents.append((start, end))
        # Includes tolerated gaps, fractional grids, roundoff-sized gaps, and
        # exactly adjacent chunks. Overlapping span manifests are ambiguous
        # at placement; spanless tolerated overlaps are tested below.
        start = end + rng.choice([0, 0, 0.0005, 0.0003, 0.25 / SR, 0.4 / SR, 1e-7])
    duration = extents[-1][1]
    conversation = _scoped_input(scope, duration)
    segment = conversation.transcript_segments[0]
    segment.start = rng.choice([0, 0.49 / SR, 0.8 / SR])
    segment.end -= rng.choice([0, 0.49 / SR, 0.0005])
    if scope == 'live':
        segment.audio_capture_start += segment.start
        segment.audio_capture_end = STARTED.timestamp() + segment.end
    session = verified_audio(conversation, extents)
    _voices(session)
    old, store, diarizer = _base_resolution(monkeypatch, base_stage, conversation, session)
    assert len(diarizer.clips) == 1  # every generated case exercises the implication
    candidate = SampleDiarizer()
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', candidate)
    stage.resolve_speakers_for_processing('offline', conversation)
    assert len(candidate.clips) == len(diarizer.clips)
    assert all(a == b for a, b in zip(candidate.clips, diarizer.clips))
    assert env[0] == store  # durations, vectors, bare/span keys and format
    assert conversation.model_dump() == old.model_dump()


@pytest.mark.parametrize('scope', ['sync', 'v2', 'live'])
@pytest.mark.parametrize('extents', [[(0, 1.3), (1.3005, 2.4)], [(0, 6), (6, 12)]])
def test_base_resolved_identity_survives_cache_hit_and_miss(
    env, verified_audio, base_stage, monkeypatch, scope, extents
):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = _scoped_input(scope, extents[-1][1])
    session = verified_audio(conversation, extents)
    for index, chunk in enumerate(session.chunks):
        pcm = session.cache[chunk['path']][0]
        session.cache[chunk['path']] = (np.full(len(pcm) // 2, (index + 1) * 1000, dtype='<i2').tobytes(), 'none')
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: np.eye(8, 64)[0].tolist())
    old, store, diarizer = _base_resolution(monkeypatch, base_stage, conversation, session)
    assert old.speaker_resolution.status == 'resolved' and len(diarizer.clips) == 1
    if extents[-1][1] == 12:
        # The review's two distinct voices: base selects voice 2, while
        # replacing it with the concatenation would choose enrolled voice 1.
        from utils.speaker_tag_prompts.clips import pcm_to_wav

        combined = b''.join(session.cache[c['path']][0] for c in session.chunks)
        assert SampleDiarizer()(pcm_to_wav(combined, SR)).argmax() == 0
        assert next(iter(base_stage.decode_cache(store['c1']).values()))[1].argmax() == 1
        assert not old.transcript_segments[0].is_user
    candidate = SampleDiarizer()
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', candidate)
    env[0].update(store)
    cached = old.model_copy(deep=True)
    stage.resolve_speakers_for_processing('offline', cached)
    assert not candidate.clips
    assert cached.model_dump() == old.model_dump()
    env[0].clear()  # download returns no bytes: ordinary miss, no invalidation
    stage.resolve_speakers_for_processing('offline', cached)
    assert len(candidate.clips) == len(diarizer.clips)
    assert all(a == b for a, b in zip(candidate.clips, diarizer.clips))
    assert cached.model_dump() == old.model_dump()
    assert env[0] == store


@pytest.mark.parametrize('scope', ['sync', 'v2', 'live'])
def test_two_short_chunks_are_strictly_additive(env, verified_audio, base_stage, monkeypatch, scope):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = _scoped_input(scope, 1.2)
    session = verified_audio(conversation, [(0, 0.6), (0.6, 1.2)])
    _voices(session)
    old, _, diarizer = _base_resolution(monkeypatch, base_stage, conversation, session)
    assert not diarizer.clips and old.speaker_resolution.status != 'resolved'
    candidate = SampleDiarizer()
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', candidate)
    stage.resolve_speakers_for_processing('offline', conversation)
    assert candidate.clips == [b''.join(session.cache[c['path']][0] for c in session.chunks)]
    assert conversation.speaker_resolution.status == 'resolved'


def _local_session(origin, grids):
    session = AudioChunkReadSession('offline', 'local')
    session._chunks = []
    for index, (offset, samples) in enumerate(grids):
        path = f'local-{index}'
        session._chunks.append(dict(path=path, timestamp=origin + offset, generation=index + 1))
        values = ((np.arange(samples, dtype=np.int32) + index * 7001) % 30000).astype('<i2')
        session.cache[path] = (values.tobytes(), 'none')
    return session


@pytest.mark.parametrize('origin', [0.0, STARTED.timestamp()])
@pytest.mark.parametrize('fraction', [0, 0.01, 0.49, 0.5, 0.99])
def test_inward_half_open_fractional_start_and_end(origin, fraction):
    session = _local_session(origin, [(0, 2 * SR + 2)])
    start, end = origin + fraction / SR, origin + 2 + fraction / SR
    clip, reason = stage._verified_clip(session, start, end)
    pcm = session.cache['local-0'][0]
    first = 0 if fraction == 0 else 1
    assert reason == 'none'
    identical = clip == pcm[first * 2 : 2 * SR * 2]
    assert identical


@pytest.mark.parametrize('origin', [0.0, STARTED.timestamp()])
@pytest.mark.parametrize('overlap', [0, 0.1 / SR, 0.4 / SR, 0.9 / SR, 0.0005])
@pytest.mark.parametrize('fraction', [0, 0.2, 0.49, 0.8])
def test_inward_mixed_grids_enforce_integer_budget(monkeypatch, origin, overlap, fraction):
    # R2.3's exact counterexample is origin=0, overlap=.4/SR, fraction=.2
    # (the middle-15-second window starts at 2.5000125).
    session = _local_session(origin, [(0, SR * 15 // 2), (7.5 - overlap, SR * 13)])
    start, end = origin + fraction / SR, origin + 20 + fraction / SR
    conversation = _input('sync', 20)
    monkeypatch.setattr(stage, 'AudioChunkReadSession', lambda *args: session)
    placement = AudioPlacement((start, end), 'sync')
    files = [dict(chunk_timestamps=[c['timestamp'] for c in session.chunks])]
    assert (
        stage._verified_read_session(
            'offline',
            conversation,
            files,
            conversation.transcript_segments,
            {'s0': placement},
            time.monotonic() + 45,
        )
        is session
    )
    clip, reason = stage._verified_clip(session, start, end)
    samples = len(clip) // 2 if clip is not None else 0
    assert reason == 'none' and SR <= samples <= 240000
    # Explicit expected cuts on each grid, independent of production helper.
    window_start, window_end = (start + end) / 2 - 7.5, (start + end) / 2 + 7.5
    pieces = []
    position = window_start
    import math

    for chunk in session.chunks:
        chunk_start = chunk['timestamp']
        pcm = session.cache[chunk['path']][0]
        stop = min(window_end, chunk_start + len(pcm) / (2 * SR))
        cuts = []
        for bound, is_end in [(position, False), (stop, True)]:
            relative = (bound - chunk_start) * SR
            # At epoch scale, exact lattice points can be represented just
            # either side. Fractional .1/.2/.4/.49/.8/.9 points cannot snap.
            nearest = round(relative)
            if abs(relative - nearest) < 0.01:
                relative = nearest
            cuts.append(math.floor(relative) if is_end else math.ceil(relative))
        pieces.append(pcm[max(0, cuts[0]) * 2 : cuts[1] * 2])
        position = stop
    identical = clip == b''.join(pieces)[: 240000 * 2]
    assert identical


@pytest.mark.parametrize('origin', [0.0, STARTED.timestamp()])
@pytest.mark.parametrize('gap', [1e-7, 0.0005])
def test_only_float_roundoff_gap_can_assemble(origin, gap):
    session = _local_session(origin, [(0, int(0.6 * SR)), (0.6 + gap, int(0.6 * SR))])
    clip, reason = stage._verified_clip(session, origin, origin + 1.2 + gap)
    if gap < 1e-6:
        assert clip is not None and SR * 2 <= len(clip) <= int(1.2 * SR) * 2
    else:
        assert clip is None and reason == 'chunk_boundary'


@pytest.mark.parametrize('scope', ['sync', 'v2', 'live'])
@pytest.mark.parametrize('seed', range(16))
def test_additive_batch_order_on_admitted_overlapping_grids(env, base_stage, monkeypatch, scope, seed):
    from contextlib import nullcontext

    rng = random.Random(seed)
    origin = rng.choice([0.0, STARTED.timestamp()])
    overlap = rng.choice([0.1 / SR, 0.4 / SR, 0.9 / SR, 0.0003])
    session = _local_session(origin, [(0, 4 * SR), (4 - overlap, 6 * SR)])
    _voices(session)
    conversation = _input(scope, 10)
    template = conversation.transcript_segments[0]
    windows = [(origin, origin + 2), (origin + 2, origin + 6 - overlap), (origin + 6, origin + 9)]
    conversation.transcript_segments = []
    for index, (start, end) in enumerate(windows):
        segment = template.model_copy(deep=True)
        segment.id, segment.start, segment.end = f's{index}', start - origin, end - origin
        conversation.transcript_segments.append(segment)
    placements = {
        s.id: AudioPlacement(w, 'capture_span' if scope == 'live' else scope)
        for s, w in zip(conversation.transcript_segments, windows)
    }
    keys = {
        s.id: f'capture-span:{s.id}:{w[0]!r}:{w[1]!r}' if scope == 'live' else s.id
        for s, w in zip(conversation.transcript_segments, windows)
    }
    files = [dict(chunk_timestamps=[c['timestamp'] for c in session.chunks])]
    monkeypatch.setattr(stage, 'AudioChunkReadSession', lambda *args: session)
    assert (
        stage._verified_read_session(
            'offline',
            conversation,
            files,
            conversation.transcript_segments,
            placements,
            time.monotonic() + 45,
        )
        is session
    )

    def iterate(uid, cid, wanted, **kwargs):
        for index, chunk in enumerate(session.chunks):
            following = session.chunks[index + 1]['timestamp'] if index + 1 < len(session.chunks) else None
            if wanted(chunk['timestamp'], following):
                yield chunk['timestamp'], session.cache[chunk['path']][0]

    def forbid(*args, **kwargs):
        raise AssertionError('embeddable base clips require neither assembly nor storage reads')

    monkeypatch.setattr(stage.httpx, 'Client', lambda **kwargs: nullcontext(None))
    monkeypatch.setattr(base_stage, 'iter_audio_chunk_pcm', iterate)
    monkeypatch.setattr(session, 'fetch', forbid)
    monkeypatch.setattr(stage, '_verified_clip', forbid)
    old_cache, new_cache = {}, {}
    old_diarizer, new_diarizer = SampleDiarizer(), SampleDiarizer()
    monkeypatch.setattr(base_stage, 'extract_embedding_from_bytes', old_diarizer)
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', new_diarizer)
    args = ('offline', conversation, conversation.transcript_segments)
    kwargs = dict(placements=placements, keys=keys, session=session)
    assert base_stage._embed_missing(*args, old_cache, time.monotonic() + 45, **kwargs)[0] == 3
    assert stage._embed_missing(*args, new_cache, time.monotonic() + 45, **kwargs)[0] == 3
    assert len(new_diarizer.clips) == len(old_diarizer.clips)
    assert all(a == b for a, b in zip(new_diarizer.clips, old_diarizer.clips))
    assert stage.encode_cache(new_cache) == base_stage.encode_cache(old_cache)

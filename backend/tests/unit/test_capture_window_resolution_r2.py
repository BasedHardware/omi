"""Offline real placement/inventory and bounded no-embeddings diagnostics."""

import logging
from contextlib import nullcontext

import numpy as np
import pytest

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    stage,
    _conversation,
    _span_manifest,
    STARTED,
    SR,
)
from models.conversation import AudioTimelineProvenance
from utils.other.audio_chunks import AudioChunkReadSession
from utils.metrics import OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL as REASONS


@pytest.fixture
def verified_audio(monkeypatch):
    monkeypatch.setattr(stage.httpx, 'Client', lambda **kwargs: nullcontext(None))

    def install(conversation, extents):
        origin = STARTED.timestamp()
        session = AudioChunkReadSession('offline', conversation.id)
        session._chunks = []
        for index, (start, end) in enumerate(extents):
            path = f'offline-{index}'
            samples = round((end - start) * SR)
            pcm = np.full(samples, 1000, dtype=np.int16).tobytes()
            session._chunks.append(
                dict(
                    path=path,
                    generation=1,
                    timestamp=origin + start,
                    span=dict(start=origin + start, samples=samples, sample_rate=SR),
                )
            )
            session.cache[path] = (pcm, 'none')
        conversation.audio_files = [_span_manifest(origin, [(origin + s, origin + e) for s, e in extents])]
        monkeypatch.setattr(stage, 'AudioChunkReadSession', lambda *args: session)

        def iterate(uid, cid, wanted, sample_rate=SR, **kwargs):
            for i, chunk in enumerate(session.chunks):
                next_start = session.chunks[i + 1]['timestamp'] if i + 1 < len(session.chunks) else None
                if wanted(chunk['timestamp'], next_start):
                    yield chunk['timestamp'], session.cache[chunk['path']][0]

        monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', iterate)
        return session

    return install


def live_window():
    conversation = _conversation([0], seconds=1.4, scopes=['live:offline'])
    conversation.transcript_segments[0].audio_capture_start = STARTED.timestamp()
    conversation.transcript_segments[0].audio_capture_end = STARTED.timestamp() + 1.2
    return conversation


@pytest.mark.parametrize('scope', ['live', 'sync', 'v2'])
def test_adjacent_verified_chunks_embed(env, verified_audio, monkeypatch, scope):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = live_window()
    if scope == 'sync':
        conversation.transcript_segments[0].speaker_id_scope = 'sync:offline'
    if scope == 'v2':
        conversation.audio_timeline = AudioTimelineProvenance(version=2)
    verified_audio(conversation, [(0, 0.6), (0.6, 1.2)])
    stage.resolve_speakers_for_processing('offline', conversation)
    assert env[1].calls == 1
    assert conversation.speaker_resolution.status == 'resolved'


@pytest.mark.parametrize(
    'reason',
    [
        'all_short',
        'no_eligible',
        'clip_too_short',
        'embed_failed',
        'budget',
        'max_embeddings',
        'invalid_vector',
        'missing_vector',
        'no_clip',
        'chunk_boundary',
    ],
)
def test_no_embeddings_reason_real_stage(env, verified_audio, monkeypatch, caplog, reason):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = live_window()
    verified_audio(conversation, [(0, 1.2)])
    if reason == 'all_short':
        conversation.transcript_segments[0].end = 0.2
    elif reason == 'no_eligible':
        conversation.transcript_segments[0].speaker_id = -2
    elif reason == 'clip_too_short':
        conversation.transcript_segments[0].end = 1.0005
        conversation.transcript_segments[0].audio_capture_end = STARTED.timestamp() + 0.9996
        verified_audio(conversation, [(0, 0.9996)])
    elif reason == 'embed_failed':
        env[1].fail = True
    elif reason == 'max_embeddings':
        monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '0')
    elif reason == 'invalid_vector':
        monkeypatch.setattr(stage, 'extract_embedding_from_bytes', lambda *a, **kw: np.zeros(64))
    elif reason == 'budget':
        real = stage._embed_missing
        monkeypatch.setattr(stage, '_embed_missing', lambda *a, **kw: real(*a[:4], 0, **kw))
    elif reason == 'missing_vector':
        monkeypatch.setattr(stage, '_embed_missing', lambda *a, **kw: (1, 'complete'))
    elif reason == 'chunk_boundary':
        monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
        conversation.transcript_segments[0].speaker_id_scope = 'sync:offline'
        verified_audio(conversation, [(0, 0.6), (0.6, 1.2)])
    elif reason == 'no_clip':
        real = stage._verified_read_session

        def admit(*args):
            session = real(*args)
            session._chunks = []
            return session

        monkeypatch.setattr(stage, '_verified_read_session', admit)
    counter = REASONS.labels(outcome='no_embeddings', reason=reason)
    before = counter._value.get()
    with caplog.at_level(logging.INFO, logger=stage.__name__):
        stage.resolve_speakers_for_processing('offline', conversation)
    assert counter._value.get() == before + 1
    lines = [r.getMessage() for r in caplog.records if 'event=conversation_speaker_resolution ' in r.getMessage()]
    assert len(lines) == 1
    assert f'reason={reason}' in lines[0]
    for field in (
        'stop',
        'embeddable',
        'pending',
        'cache_hits',
        'new_embeddings',
        'valid_vectors',
        'clip_skips',
        'embed_failures',
    ):
        assert f'{field}=' in lines[0]
    assert 'uid=' not in lines[0] and 'conversation=' not in lines[0] and 'offline' not in lines[0]


@pytest.mark.parametrize('gap', [0.0005, 0.01])
def test_verified_chunks_never_bridge_missing_extent(env, verified_audio, monkeypatch, gap):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = live_window()
    verified_audio(conversation, [(0, 0.6), (0.6 + gap, 1.2)])
    stage.resolve_speakers_for_processing('offline', conversation)
    assert env[1].calls == 0
    assert conversation.speaker_resolution.status != 'resolved'


def test_verified_clip_bounded_and_exact_original_pcm(env, verified_audio, monkeypatch):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    conversation = live_window()
    conversation.transcript_segments[0].end = 20
    conversation.transcript_segments[0].audio_capture_end = STARTED.timestamp() + 20
    session = verified_audio(conversation, [(0, 10), (10, 20)])
    session.cache['offline-1'] = (np.full(10 * SR, 2000, dtype=np.int16).tobytes(), 'none')
    observed = []

    def embed(wav, **kwargs):
        import io
        import wave

        with wave.open(io.BytesIO(wav)) as reader:
            observed.append(np.frombuffer(reader.readframes(reader.getnframes()), dtype=np.int16))
        return np.ones(64)

    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', embed)
    stage.resolve_speakers_for_processing('offline', conversation)
    # The exact base midpoint clip embeds ten seconds from the second chunk;
    # additive recovery must never replace it with a longer mixed-voice clip.
    assert len(observed) == 1 and len(observed[0]) == 10 * SR
    assert observed[0].tobytes() == session.cache['offline-1'][0]


@pytest.mark.parametrize('scope', ['sync', 'v2'])
def test_span_off_legacy_clip_behavior_and_cache_keys(env, verified_audio, monkeypatch, scope):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    conversation = live_window()
    conversation.transcript_segments[0].speaker_id_scope = 'sync:offline'
    if scope == 'v2':
        conversation.audio_timeline = AudioTimelineProvenance(version=2)
        conversation.transcript_segments[0].speaker_id_scope = 'conversation:c1'
        conversation.transcript_segments[0].audio_source = dict(
            type='sync', start=STARTED.timestamp(), end=STARTED.timestamp() + 1.2
        )
    verified_audio(conversation, [(0, 0.6), (0.6, 1.2)])
    stage.resolve_speakers_for_processing('offline', conversation)
    assert env[1].calls == 0 and not env[0]
    verified_audio(conversation, [(0, 1.2)])
    stage.resolve_speakers_for_processing('offline', conversation)
    assert env[1].calls == 1 and set(stage.decode_cache(env[0]['c1'])) == {'s0'}

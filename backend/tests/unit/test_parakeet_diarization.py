"""Unit tests for the basic online diarization in ParakeetStreamingSocket.

The embedding service is mocked — these assert the clustering/fallback logic only
(same voice -> same SPEAKER_N across windows, new voice -> new label, short or
disabled clips fall back safely), not the hosted embedding model itself.
"""

import asyncio
import os

import numpy as np

os.environ.setdefault('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://fake')  # enables _diarize
os.environ.setdefault('DEEPGRAM_API_KEY', 'x')

import utils.stt.streaming as st  # noqa: E402


def _dir_vec(idx: int, rng) -> np.ndarray:
    """A unit direction in dim `idx` plus small within-speaker noise -> (1, 256)."""
    v = np.zeros((1, 256), np.float32)
    v[0, idx] = 1.0
    return v + 0.01 * rng.standard_normal((1, 256)).astype(np.float32)


def _make_socket(diarize=True):
    sock = st.ParakeetStreamingSocket(lambda segs: None, 'http://fake', 16000)
    sock._diarize = diarize
    return sock


def _patch_embeddings(monkeypatch, seq):
    calls = {'i': 0}

    async def fake_embed(audio_data, filename="audio.wav"):
        v = seq[calls['i']]
        calls['i'] += 1
        return v

    monkeypatch.setattr(st, 'async_extract_embedding_from_bytes', fake_embed)
    return calls


def test_clusters_two_speakers_stably(monkeypatch):
    rng = np.random.default_rng(0)
    seq = [_dir_vec(0, rng), _dir_vec(0, rng), _dir_vec(1, rng), _dir_vec(0, rng), _dir_vec(1, rng)]
    _patch_embeddings(monkeypatch, seq)
    sock = _make_socket()
    long_pcm = b'\x01\x00' * 16000  # 1s, above the 0.6s embed threshold

    got = [asyncio.run(sock._assign_speaker(long_pcm)) for _ in range(5)]
    assert got == [0, 0, 1, 0, 1]


def test_short_clip_inherits_last_speaker_without_embedding(monkeypatch):
    rng = np.random.default_rng(1)
    calls = _patch_embeddings(monkeypatch, [_dir_vec(1, rng)])
    sock = _make_socket()
    asyncio.run(sock._assign_speaker(b'\x01\x00' * 16000))  # speaker 0 (first), consumes 1 call
    before = calls['i']

    short = b'\x01\x00' * (16000 // 10)  # 0.1s < 0.6s threshold
    spk = asyncio.run(sock._assign_speaker(short))
    assert spk == sock._last_speaker
    assert calls['i'] == before  # no embedding call for a too-short clip


def test_diarization_disabled_returns_zero():
    sock = _make_socket(diarize=False)
    assert asyncio.run(sock._assign_speaker(b'\x01\x00' * 16000)) == 0


def test_embedding_failure_falls_back_to_last_speaker(monkeypatch):
    async def boom(audio_data, filename="audio.wav"):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(st, 'async_extract_embedding_from_bytes', boom)
    sock = _make_socket()
    sock._last_speaker = 2
    assert asyncio.run(sock._assign_speaker(b'\x01\x00' * 16000)) == 2  # never drops the segment


def test_slice_pcm_bounds():
    sock = _make_socket()
    pcm = b'\x00\x00' * 16000  # 1s @ 16kHz int16
    assert len(sock._slice_pcm(pcm, 0.0, 0.5)) == 16000  # 0.5s -> 8000 samples * 2 bytes
    assert sock._slice_pcm(pcm, 0.9, 0.1) == b''  # inverted window -> empty
    assert len(sock._slice_pcm(pcm, 0.5, 99.0)) == 16000  # clamps to buffer end

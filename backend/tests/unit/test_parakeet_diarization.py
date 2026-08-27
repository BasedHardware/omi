"""Unit tests for the basic online diarization in ParakeetStreamingSocket.

The embedding service is mocked — these assert the clustering/fallback logic only
(same voice -> same SPEAKER_N across windows, new voice -> new label, short or
disabled clips fall back safely), not the hosted embedding model itself.
"""

import asyncio
import os

import numpy as np
import pytest

os.environ.setdefault('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://fake')  # enables _diarize
os.environ.setdefault('DEEPGRAM_API_KEY', 'x')

import utils.stt.streaming as st  # noqa: E402
from utils.stt.speaker_clustering import SPEAKER_CLUSTERING_THRESHOLD  # noqa: E402
from utils.stt.speaker_embedding import SPEAKER_MATCH_THRESHOLD  # noqa: E402


def _cosine_distance(a, b):
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 1.0
    return float(1.0 - np.sum(a * b) / denom)


@pytest.fixture(autouse=True)
def _patch_compare_embeddings(monkeypatch):
    monkeypatch.setattr(st, 'compare_embeddings', _cosine_distance)


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


def test_clustering_threshold_is_separate_from_enrollment_verification():
    assert SPEAKER_MATCH_THRESHOLD == 0.45
    assert SPEAKER_CLUSTERING_THRESHOLD == 0.60


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


def test_online_clustering_merges_to_nearest_after_eight_speakers(monkeypatch):
    embeddings = [np.eye(9, dtype=np.float32)[index].reshape(1, -1) for index in range(9)]
    _patch_embeddings(monkeypatch, embeddings)
    sock = _make_socket()
    long_pcm = b'\x01\x00' * 16000

    assigned = [asyncio.run(sock._assign_speaker(long_pcm)) for _ in embeddings]

    assert assigned[:8] == list(range(8))
    assert assigned[8] == 0
    assert len(sock._spk_centroids) == 8


def test_clustering_boundary_at_exactly_the_threshold_creates_a_new_speaker():
    # The clustering boundary is strict: a clip at exactly 0.60 cosine distance
    # is NOT the same speaker and must open a new centroid (while capacity
    # remains). Pinning the exact boundary keeps future refactors from quietly
    # turning < into <= and re-merging borderline speakers.
    decision = st.select_speaker_cluster('emb', ['centroid'], lambda _a, _b: SPEAKER_CLUSTERING_THRESHOLD)
    just_inside = st.select_speaker_cluster('emb', ['centroid'], lambda _a, _b: SPEAKER_CLUSTERING_THRESHOLD - 1e-9)

    index, create_new, _distance, capped = decision
    assert (index, create_new, capped) == (1, True, False)
    assert just_inside[1] is False  # strictly below the threshold merges


def test_enrollment_boundary_at_exactly_the_threshold_is_not_a_match(monkeypatch):
    # Voiceprint verification is equally strict at its own 0.45 operating
    # point: exactly at the threshold the answer is "not the same speaker".
    from utils.stt import speaker_embedding

    monkeypatch.setattr(speaker_embedding, 'compare_embeddings', lambda _a, _b: SPEAKER_MATCH_THRESHOLD)
    same, distance = speaker_embedding.is_same_speaker('a', 'b')
    assert same is False
    assert distance == SPEAKER_MATCH_THRESHOLD


def test_cap_merge_is_reported_and_does_not_drift_the_centroid(monkeypatch):
    # When the eighth centroid is full, a ninth distinct voice is force-merged
    # into the nearest centroid. That merge misattributes the segment, so it
    # must be observable (shared fallback telemetry) and must not update the
    # winning centroid's running mean — folding a >0.60 embedding into a mean
    # would drag that centroid toward the wrong speaker and chain further
    # misattributions.
    embeddings = [np.eye(9, dtype=np.float32)[index].reshape(1, -1) for index in range(9)]
    _patch_embeddings(monkeypatch, embeddings + [embeddings[0]])
    fallbacks = []
    monkeypatch.setattr(st, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    sock = _make_socket()
    long_pcm = b'\x01\x00' * 16000

    assigned = [asyncio.run(sock._assign_speaker(long_pcm)) for _ in embeddings]
    again = asyncio.run(sock._assign_speaker(long_pcm))  # speaker 0 keeps its own identity

    assert assigned[8] == 0
    assert len(fallbacks) == 1
    assert fallbacks[0]['reason'] == 'capacity_full'
    assert fallbacks[0]['outcome'] == 'degraded'
    # The forced merge left centroid 0 exactly on its own first embedding...
    np.testing.assert_array_equal(sock._spk_centroids[0], embeddings[0])
    # ...so speaker 0's next clip still lands on speaker 0 deterministically.
    assert again == 0


def test_rare_owner_is_not_fragmented_among_many_speakers(monkeypatch):
    # The conference-call shape: several distinct voices, clean audio, and the
    # owner only speaking occasionally. If each rare owner turn opened a new
    # centroid, the owner's transcript would fragment across several speaker
    # labels — the mislabelling failure users actually notice. Within-speaker
    # distance must stay comfortably under the 0.60 clustering threshold.
    rng = np.random.default_rng(7)
    order = [0, 1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6, 1, 2, 0]
    _patch_embeddings(monkeypatch, [_dir_vec(index, rng) for index in order])
    sock = _make_socket()
    long_pcm = b'\x01\x00' * 16000

    assigned = [asyncio.run(sock._assign_speaker(long_pcm)) for _ in order]

    owner_turns = [index for index, speaker in enumerate(order) if speaker == 0]
    owner_ids = {assigned[index] for index in owner_turns}
    assert len(owner_ids) == 1  # first and last owner turn share one identity
    # Nobody else was relabeled into the owner's identity.
    assert assigned[owner_turns[0]] not in {assigned[i] for i, s in enumerate(order) if s != 0}


def test_slice_pcm_bounds():
    sock = _make_socket()
    pcm = b'\x00\x00' * 16000  # 1s @ 16kHz int16
    assert len(sock._slice_pcm(pcm, 0.0, 0.5)) == 16000  # 0.5s -> 8000 samples * 2 bytes
    assert sock._slice_pcm(pcm, 0.9, 0.1) == b''  # inverted window -> empty
    assert len(sock._slice_pcm(pcm, 0.5, 99.0)) == 16000  # clamps to buffer end

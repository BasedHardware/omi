"""Offline agglomerative clustering in parakeet batch diarization.

The embedding model and the audio slicer are mocked; `_diarize_segments` itself
runs unmodified, so these assert the real eligibility, clustering, constraint and
label-assignment behavior rather than a reimplementation of it.

Voices are hand-placed unit vectors in a 256-dim space, so every distance below
is arithmetic rather than luck: `_voice_at` positions two voices at a chosen
angle to each other, and `_voice` gives each speaker its own dimension.
"""

import math
import os
import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

os.environ.setdefault('PARAKEET_INFERENCE_MODE', 'nemo')
os.environ.setdefault('PARAKEET_STREAM_MODEL', '')
os.environ.setdefault('PARAKEET_DEVICE', 'cpu')
os.environ.setdefault('PARAKEET_TORCH_COMPILE', 'false')
os.environ.setdefault('PARAKEET_CUDA_GRAPHS', 'false')

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'parakeet'))

import transcribe  # noqa: E402
from speaker_math import SPEAKER_CLUSTERING_THRESHOLD  # noqa: E402

# Chosen against SPEAKER_AHC_THRESHOLD (0.55) to form a chain:
#   d(A,B) = 1-cos(45) = 0.293  -> under the cut
#   d(B,C) = 1-cos(55) = 0.426  -> under the cut
#   d(A,C) = 1-cos(100) = 1.174 -> over the cut
# Order-dependent greedy matching resolves this chain differently depending on
# which end it starts from; average linkage does not.
VOICE_A_DEG = 0.0
VOICE_B_DEG = 45.0
VOICE_C_DEG = 100.0


def _voice_at(angle_deg: float) -> np.ndarray:
    """A unit embedding at `angle_deg` in the first two dimensions."""
    radians = math.radians(angle_deg)
    vector = np.zeros((1, 256), dtype=np.float32)
    vector[0, 0] = math.cos(radians)
    vector[0, 1] = math.sin(radians)
    return vector


def _voice(index: int) -> np.ndarray:
    """Distinct speaker `index`; any two sit ~1.0 apart, far above the threshold.

    Each voice owns a dimension, so different indices are near-orthogonal. The
    small shared component on the last dimension makes every pairwise distance
    slightly different: without it the dendrogram has tied merge heights, and a
    `maxclust` cut cannot split a tie into an exact cluster count.
    """
    vector = np.zeros((1, 256), dtype=np.float32)
    vector[0, index] = 1.0
    vector[0, 255] = 0.02 * (index + 1)
    return vector


def _write_wav(path: Path, duration_s: float = 30.0, sample_rate: int = 16000) -> None:
    frames = b''.join(struct.pack('<h', 0) for _ in range(int(duration_s * sample_rate)))
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def _diarize(tmp_path, spans, **constraints):
    """Run `_diarize_segments` over `spans` and return the assigned speaker labels.

    `spans` is a list of `(start, end, embedding_or_None)`. The audio slicer is
    replaced by one that encodes the segment start into its payload, so each
    segment resolves to its own embedding regardless of the order the production
    code walks them in.
    """
    wav_path = tmp_path / 'audio.wav'
    _write_wav(wav_path)

    embedding_by_start = {round(float(start), 3): embedding for start, _end, embedding in spans}

    def fake_extract(_audio_bytes, start, _end):
        # Padded past the 1000-byte guard; the prefix carries the segment start.
        return f'{start:.3f}'.encode().ljust(2000, b'\x00')

    def fake_embedding(wav_bytes):
        return embedding_by_start[round(float(wav_bytes.rstrip(b"\x00").decode()), 3)]

    base = {
        'text': 'hello',
        'segments': [{'text': 'hello', 'start': float(start), 'end': float(end)} for start, end, _ in spans],
    }

    with patch.object(transcribe, '_extract_segment_wav', fake_extract), patch.object(
        transcribe, '_get_embedding', fake_embedding
    ), patch.object(transcribe, 'SPEAKER_EMBEDDING_URL', 'http://fake'):
        result = transcribe._diarize_segments(str(wav_path), base, **constraints)

    return [segment['speaker'] for segment in result['segments']]


def _partition(labels):
    """Group segment indices by speaker label, ignoring the label names."""
    groups = {}
    for index, label in enumerate(labels):
        groups.setdefault(label, []).append(index)
    return sorted(tuple(indices) for indices in groups.values())


class TestOrderIndependence:
    def test_chain_partition_is_identical_under_reversed_arrival(self, tmp_path):
        """The same three voices must partition the same way in either order.

        This is the regression: online centroid matching walked segments in time
        order and folded each match into a running mean, so the A-B-C chain
        resolved to {A,B},{C} arriving forwards and {B,C},{A} arriving backwards.
        """
        forward = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice_at(VOICE_A_DEG)),
                (3.0, 5.0, _voice_at(VOICE_B_DEG)),
                (6.0, 8.0, _voice_at(VOICE_C_DEG)),
            ],
        )
        backward = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice_at(VOICE_C_DEG)),
                (3.0, 5.0, _voice_at(VOICE_B_DEG)),
                (6.0, 8.0, _voice_at(VOICE_A_DEG)),
            ],
        )

        # Forward is [A, B, C]; backward is [C, B, A]. Re-index backward onto the
        # forward voice order so the two partitions are directly comparable.
        backward_by_voice = [backward[2], backward[1], backward[0]]

        assert _partition(forward) == _partition(backward_by_voice)
        # A and B pair off; C stands alone, at both arrival orders.
        assert _partition(forward) == [(0, 1), (2,)]

    def test_shuffled_arrival_of_orthogonal_voices_preserves_grouping(self, tmp_path):
        voices = [_voice(index) for index in range(3)]
        interleaved = _diarize(
            tmp_path,
            [
                (0.0, 2.0, voices[0]),
                (3.0, 5.0, voices[1]),
                (6.0, 8.0, voices[2]),
                (9.0, 11.0, voices[0]),
                (12.0, 14.0, voices[1]),
            ],
        )
        assert _partition(interleaved) == [(0, 3), (1, 4), (2,)]


class TestMultiSpeakerSeparation:
    def test_three_distinct_voices_get_three_labels(self, tmp_path):
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(0)),
                (3.0, 5.0, _voice(1)),
                (6.0, 8.0, _voice(2)),
            ],
        )
        assert len(set(labels)) == 3

    def test_first_voice_heard_is_speaker_0(self, tmp_path):
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(1)),
                (3.0, 5.0, _voice(0)),
                (6.0, 8.0, _voice(1)),
            ],
        )
        assert labels[0] == 'SPEAKER_0'
        assert labels[2] == 'SPEAKER_0'
        assert labels[1] == 'SPEAKER_1'

    def test_repeat_of_one_voice_stays_single_speaker(self, tmp_path):
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice_at(VOICE_A_DEG)),
                (3.0, 5.0, _voice_at(VOICE_A_DEG)),
                (6.0, 8.0, _voice_at(VOICE_A_DEG)),
            ],
        )
        assert labels == ['SPEAKER_0', 'SPEAKER_0', 'SPEAKER_0']


class TestSpeakerConstraints:
    def test_num_speakers_forces_exact_partition_size(self, tmp_path):
        spans = [
            (0.0, 2.0, _voice(0)),
            (3.0, 5.0, _voice(1)),
            (6.0, 8.0, _voice(2)),
        ]
        assert len(set(_diarize(tmp_path, spans, num_speakers=2))) == 2
        assert len(set(_diarize(tmp_path, spans, num_speakers=3))) == 3

    def test_num_speakers_is_clamped_to_available_segments(self, tmp_path):
        labels = _diarize(
            tmp_path,
            [(0.0, 2.0, _voice(0)), (3.0, 5.0, _voice(1))],
            num_speakers=9,
        )
        assert len(set(labels)) == 2

    def test_max_speakers_caps_a_partition_the_threshold_would_split_further(self, tmp_path):
        spans = [(float(i * 3), float(i * 3 + 2), _voice(i)) for i in range(4)]
        assert len(set(_diarize(tmp_path, spans))) == 4
        assert len(set(_diarize(tmp_path, spans, max_speakers=2))) == 2

    def test_min_speakers_splits_a_partition_the_threshold_would_merge(self, tmp_path):
        spans = [
            (0.0, 2.0, _voice_at(VOICE_A_DEG)),
            (3.0, 5.0, _voice_at(VOICE_A_DEG)),
        ]
        assert len(set(_diarize(tmp_path, spans))) == 1
        assert len(set(_diarize(tmp_path, spans, min_speakers=2))) == 2

    def test_num_speakers_takes_precedence_over_min_and_max(self, tmp_path):
        spans = [(float(i * 3), float(i * 3 + 2), _voice(i)) for i in range(4)]
        labels = _diarize(tmp_path, spans, num_speakers=3, min_speakers=1, max_speakers=2)
        assert len(set(labels)) == 3


class TestShortAndFailedSegments:
    def test_short_segment_inherits_nearest_clustered_segment_in_time(self, tmp_path):
        """A sub-threshold clip follows the voice next to it, not the newest cluster.

        The online path assigned `SPEAKER_{len(centroids) - 1}` — whichever speaker
        was created most recently — so a short clip beside speaker 0 was labelled
        with speaker 1 purely because speaker 1 had been seen more recently.
        """
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(0)),
                (2.1, 2.4, None),  # 0.3s, below MIN_SEGMENT_DURATION
                (10.0, 12.0, _voice(1)),
            ],
        )
        assert labels[1] == labels[0]
        assert labels[1] != labels[2]

    def test_non_finite_embedding_is_excluded_from_clustering(self, tmp_path):
        broken = np.full((1, 256), np.nan, dtype=np.float32)
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(0)),
                (3.0, 5.0, broken),
                (6.0, 8.0, _voice(1)),
            ],
        )
        # Two real voices still separate, and the broken segment inherits a
        # neighbour instead of poisoning the linkage matrix with NaN.
        assert labels[0] != labels[2]
        assert labels[1] in {labels[0], labels[2]}

    def test_zero_vector_embedding_is_excluded_from_clustering(self, tmp_path):
        zero = np.zeros((1, 256), dtype=np.float32)
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(0)),
                (3.0, 5.0, zero),
                (6.0, 8.0, _voice(1)),
            ],
        )
        assert labels[0] != labels[2]

    def test_all_segments_short_fall_back_to_speaker_0(self, tmp_path):
        labels = _diarize(tmp_path, [(0.0, 0.3, None), (1.0, 1.2, None)])
        assert labels == ['SPEAKER_0', 'SPEAKER_0']

    def test_single_embeddable_segment_is_speaker_0(self, tmp_path):
        labels = _diarize(tmp_path, [(0.0, 2.0, _voice_at(VOICE_A_DEG))])
        assert labels == ['SPEAKER_0']

    def test_missing_embedding_does_not_break_the_partition(self, tmp_path):
        labels = _diarize(
            tmp_path,
            [
                (0.0, 2.0, _voice(0)),
                (3.0, 5.0, None),  # long enough to embed, but the model returns nothing
                (6.0, 8.0, _voice(1)),
            ],
        )
        assert labels[0] != labels[2]
        assert labels[1] in {labels[0], labels[2]}


class TestDiarizationGating:
    def test_no_embedding_source_labels_everything_speaker_0(self, tmp_path):
        wav_path = tmp_path / 'audio.wav'
        _write_wav(wav_path)
        base = {'text': 'hi', 'segments': [{'text': 'hi', 'start': 0.0, 'end': 2.0}]}

        worker = MagicMock()
        worker.is_ready = False
        with patch.object(transcribe, '_gpu_worker', worker), patch.object(transcribe, 'SPEAKER_EMBEDDING_URL', ''):
            result = transcribe._diarize_segments(str(wav_path), base)

        assert result['segments'][0]['speaker'] == 'SPEAKER_0'


class TestClusteringThresholdContract:
    def test_batch_cut_is_separate_from_the_online_clustering_threshold(self):
        # AHC cuts on cophenetic merge height — the mean distance between two whole
        # clusters — not on distance to a drifting centroid, so the batch path owns
        # its own tuned constant. The streaming path's threshold must not move with it.
        assert transcribe.SPEAKER_AHC_THRESHOLD == 0.55
        assert SPEAKER_CLUSTERING_THRESHOLD == 0.60

    def test_the_cut_constant_is_what_actually_partitions(self, tmp_path, monkeypatch):
        # Two voices 0.293 apart: merged under the shipped 0.55 cut, split once the
        # cut drops below their distance. Proves the constant is load-bearing.
        spans = [(0.0, 2.0, _voice_at(VOICE_A_DEG)), (3.0, 5.0, _voice_at(VOICE_B_DEG))]
        assert len(set(_diarize(tmp_path, spans))) == 1

        monkeypatch.setattr(transcribe, 'SPEAKER_AHC_THRESHOLD', 0.20)
        assert len(set(_diarize(tmp_path, spans))) == 2

    def test_voices_inside_the_threshold_merge_and_outside_it_split(self, tmp_path):
        assert 1 - math.cos(math.radians(VOICE_B_DEG)) < transcribe.SPEAKER_AHC_THRESHOLD
        assert 1 - math.cos(math.radians(VOICE_C_DEG)) > transcribe.SPEAKER_AHC_THRESHOLD

        merged = _diarize(
            tmp_path,
            [(0.0, 2.0, _voice_at(VOICE_A_DEG)), (3.0, 5.0, _voice_at(VOICE_B_DEG))],
        )
        split = _diarize(
            tmp_path,
            [(0.0, 2.0, _voice_at(VOICE_A_DEG)), (3.0, 5.0, _voice_at(VOICE_C_DEG))],
        )

        assert len(set(merged)) == 1
        assert len(set(split)) == 2

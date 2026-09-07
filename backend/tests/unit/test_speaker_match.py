"""The enrolled-voiceprint decision policy shared by the live socket and the sync pipeline.

The numbers behind these tests come from the offline bench on real enrollments
(scripts/speaker_id_bench). Same-user cross-session audio sits at a cosine distance of
~0.4-0.55 from its voiceprint, other users at ~0.93, and the owner's own taught
household members as close as 0.43 — so the policy is "under the threshold AND clearly
nearest", decided on a few seconds of evidence rather than the first short clip.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402
import math  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from models.transcript_segment import SpeakerIdentityStatus  # noqa: E402
from utils.stt.speaker_match import (  # noqa: E402
    SPEAKER_MATCH_MARGIN,
    SPEAKER_MATCH_MAX_CLIPS,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    SPEAKER_MATCH_THRESHOLD,
    mean_embedding,
    select_speaker_match,
)


class TestSelectSpeakerMatch:
    def test_cross_session_owner_distance_is_accepted(self):
        # Median same-user, different-session distance measured in the bench.
        decision = select_speaker_match({'user': 0.53})
        assert decision.person_id == 'user'
        assert decision.accepted is True
        assert math.isinf(decision.runner_up_distance)

    def test_other_user_distance_is_rejected(self):
        decision = select_speaker_match({'user': 0.93})
        assert decision.person_id is None
        assert decision.best_id == 'user'
        assert decision.best_distance == 0.93

    def test_exactly_at_threshold_is_not_a_match(self):
        assert select_speaker_match({'user': SPEAKER_MATCH_THRESHOLD}).accepted is False

    def test_nearest_candidate_wins_when_clearly_nearest(self):
        decision = select_speaker_match({'user': 0.60, 'sarah': 0.40, 'alex': 0.90})
        assert decision.person_id == 'sarah'
        assert decision.best_distance == 0.40
        assert decision.runner_up_distance == 0.60

    def test_ambiguous_household_is_not_guessed(self):
        # Owner and a taught person both under the threshold, within the margin of
        # each other: guessing would misattribute one household member as another.
        close = 0.43 + SPEAKER_MATCH_MARGIN / 2
        decision = select_speaker_match({'user': 0.43, 'sarah': close})
        assert decision.person_id is None
        assert decision.best_id == 'user'

    def test_margin_is_measured_against_any_runner_up_not_only_accepted_ones(self):
        # The runner-up may itself be over the threshold; it still has to be `margin`
        # farther away than the winner. Values chosen to sit clearly either side of
        # the 0.10 margin rather than exactly on it.
        assert select_speaker_match({'user': 0.60, 'sarah': 0.69}).accepted is False
        assert select_speaker_match({'user': 0.60, 'sarah': 0.71}).person_id == 'user'

    def test_nan_distances_never_match(self):
        assert select_speaker_match({'user': float('nan')}).best_id is None
        assert select_speaker_match({'user': float('nan'), 'sarah': 0.3}).person_id == 'sarah'

    def test_empty_candidates(self):
        decision = select_speaker_match({})
        assert decision.person_id is None
        assert decision.best_id is None

    def test_tie_keeps_insertion_order(self):
        assert select_speaker_match({'first': 0.2, 'second': 0.2}, margin=0.0).person_id == 'first'

    def test_custom_threshold_and_margin(self):
        assert select_speaker_match({'user': 0.5}, threshold=0.45).accepted is False
        assert select_speaker_match({'user': 0.3, 'sarah': 0.35}, margin=0.0).person_id == 'user'


class TestMeanEmbedding:
    def test_centroid_is_unit_length_and_between_inputs(self):
        a = np.array([[1.0, 0.0]], dtype=np.float32)
        b = np.array([[0.0, 1.0]], dtype=np.float32)
        centroid = mean_embedding([a, b])
        assert centroid.shape == (1, 2)
        assert np.linalg.norm(centroid) == pytest.approx(1.0)
        assert centroid[0, 0] == pytest.approx(centroid[0, 1])

    def test_single_embedding_is_normalised_copy(self):
        a = np.array([[3.0, 4.0]], dtype=np.float32)
        np.testing.assert_allclose(mean_embedding([a]), [[0.6, 0.8]])

    def test_accepts_flat_vectors(self):
        assert mean_embedding([np.ones(4, dtype=np.float32)]).shape == (1, 4)

    def test_zero_centroid_does_not_divide_by_zero(self):
        a = np.array([[1.0, 0.0]], dtype=np.float32)
        assert not np.isnan(mean_embedding([a, -a])).any()


# ─── Live socket: evidence accumulation ───────────────────────────────────────


class _AudioRingBuffer:
    def get_time_range(self):
        return 0.0, 60.0

    def extract(self, _start, _end):
        return b'\x00\x00' * 32000


def _live_matcher(monkeypatch, clip_embeddings):
    import routers.listen.speakers as speakers_mod

    emitted = []
    host = SimpleNamespace(
        state=SimpleNamespace(audio_ring_buffer=_AudioRingBuffer(), speaker_map_dirty=False),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        request=SimpleNamespace(sample_rate=16000),
        emit_speaker_suggestion=lambda *args: emitted.append(args),
    )
    matcher = speakers_mod.SpeakerMatcher(host)
    matcher.person_embeddings = {
        'user': {'embedding': np.array([[1.0, 0.0]], dtype=np.float32), 'name': 'User'},
        'p1': {'embedding': np.array([[0.0, 1.0]], dtype=np.float32), 'name': 'Sarah'},
    }
    queue = list(clip_embeddings)
    monkeypatch.setattr(speakers_mod, 'extract_embedding_from_bytes', lambda _audio, _name: queue.pop(0))
    return matcher, host, emitted


def _segment(seg_id, start, seconds):
    return {'id': seg_id, 'duration': seconds, 'abs_start': start, 'abs_end': start + seconds}


def test_short_clips_are_pooled_before_a_live_decision(monkeypatch):
    """Two 2.5 s clips: the first is only evidence, the second (5 s total) decides."""
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [owner, owner])

    asyncio.run(matcher.match(1, _segment('s1', 0.0, 2.5)))
    assert 's1' not in matcher.segment_identity_status
    assert 1 not in matcher.speaker_to_person
    assert host.state.speaker_map_dirty is False

    asyncio.run(matcher.match(1, _segment('s2', 3.0, 2.5)))
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher.segment_identity_status['s2'] == SpeakerIdentityStatus.user
    assert emitted == [(1, 'user', 'User', 's2')]


def test_one_long_clip_decides_immediately(monkeypatch):
    sarah = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _host, emitted = _live_matcher(monkeypatch, [sarah])

    asyncio.run(matcher.match(2, _segment('s1', 0.0, SPEAKER_MATCH_MIN_EVIDENCE_SECONDS)))

    assert matcher.speaker_to_person[2] == ('p1', 'Sarah')
    assert matcher.segment_identity_status['s1'] == SpeakerIdentityStatus.not_user
    assert emitted == [(2, 'p1', 'Sarah', 's1')]


def test_decision_uses_the_centroid_not_the_latest_clip(monkeypatch):
    """One noisy clip pointing at Sarah is outvoted by two owner clips in the window."""
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _host, _emitted = _live_matcher(monkeypatch, [owner, owner, noisy])

    for index, start in enumerate((0.0, 3.0, 6.0)):
        asyncio.run(matcher.match(1, _segment(f's{index}', start, 2.0)))

    # Window is [owner, owner, noisy] -> centroid leans owner; distance to 'user' is
    # 1 - cos(~35°) ≈ 0.18 and to Sarah ≈ 0.55, so the owner wins with margin.
    assert matcher.speaker_to_person[1] == ('user', 'User')


def test_window_is_bounded(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _host, _emitted = _live_matcher(monkeypatch, [owner] * (SPEAKER_MATCH_MAX_CLIPS + 2))
    for index in range(SPEAKER_MATCH_MAX_CLIPS + 2):
        asyncio.run(matcher.match(1, _segment(f's{index}', index * 3.0, 2.0)))
    assert len(matcher.speaker_evidence[1]) == SPEAKER_MATCH_MAX_CLIPS


def test_ambiguous_live_evidence_is_recorded_as_no_match(monkeypatch):
    between = np.array([[1.0, 1.0]], dtype=np.float32) / np.sqrt(2)
    matcher, host, emitted = _live_matcher(monkeypatch, [between])

    asyncio.run(matcher.match(1, _segment('s1', 0.0, 6.0)))

    assert matcher.segment_identity_status['s1'] == SpeakerIdentityStatus.no_match
    assert 1 not in matcher.speaker_to_person
    assert host.state.speaker_map_dirty is True
    assert emitted == []


def test_clear_forgets_evidence(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _host, _emitted = _live_matcher(monkeypatch, [owner])
    asyncio.run(matcher.match(1, _segment('s1', 0.0, 2.0)))
    assert matcher.speaker_evidence
    matcher.clear()
    assert matcher.speaker_evidence == {}

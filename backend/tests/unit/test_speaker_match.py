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

from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment  # noqa: E402
from routers.listen.transcripts import TranscriptProcessor  # noqa: E402
from utils.observability.owner_recognition import LIVE_SPEAKER_DECISIONS  # noqa: E402
from utils.stt.speaker_match import (  # noqa: E402
    OWNER_NEAR_MISS_THRESHOLD,
    SPEAKER_MATCH_MARGIN,
    SPEAKER_MATCH_MAX_CLIPS,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    SPEAKER_MATCH_THRESHOLD,
    SpeakerMatchDecision,
    arbitrate_owner_matches,
    mean_embedding,
    owner_near_miss,
    select_speaker_match,
)


async def _no_owner_name():
    """The listen coordinator's owner-name veto, resolved to "no owner name known"."""
    return None


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


@pytest.mark.parametrize(
    'distance,pending',
    [
        (math.nextafter(SPEAKER_MATCH_THRESHOLD, -math.inf), False),
        (SPEAKER_MATCH_THRESHOLD, True),
        (math.nextafter(OWNER_NEAR_MISS_THRESHOLD, -math.inf), True),
        (OWNER_NEAR_MISS_THRESHOLD, False),
        (0.737, False),
        (math.inf, False),
        (math.nan, False),
    ],
)
def test_owner_near_miss_distance_boundaries(distance, pending):
    decision = select_speaker_match({'user': distance})
    assert owner_near_miss(decision) is pending
    assert decision.accepted is (distance < SPEAKER_MATCH_THRESHOLD)


@pytest.mark.parametrize('runner_up,pending', [(0.75, False), (math.nextafter(0.75, math.inf), True)])
def test_owner_near_miss_uses_the_incumbent_margin_boundary(runner_up, pending):
    # The exact subtraction matters: 0.75 - 0.65 rounds below 0.10.
    decision = select_speaker_match({'user': 0.65, 'peer': runner_up})
    assert owner_near_miss(decision) is pending
    assert not decision.accepted


@pytest.mark.parametrize(
    'decision',
    [
        SpeakerMatchDecision('user', 'user', 0.67, math.inf),
        SpeakerMatchDecision(None, 'peer', 0.67, math.inf),
        SpeakerMatchDecision(None, None, math.inf, math.inf),
        SpeakerMatchDecision(None, 'user', 0.67, math.inf, owner_contended=True),
        SpeakerMatchDecision(None, 'user', 0.67, 0.70),
    ],
)
def test_owner_near_miss_never_overrides_accepts_people_or_contention(decision):
    assert not owner_near_miss(decision)


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
        return b'\x00\x00' * round((_end - _start) * 16000)


def _live_matcher(monkeypatch, clip_embeddings):
    import routers.listen.speakers as speakers_mod

    emitted = []
    host = SimpleNamespace(
        state=SimpleNamespace(audio_ring_buffer=_AudioRingBuffer(), speaker_map_dirty=False),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        request=SimpleNamespace(sample_rate=16000),
        emit_speaker_suggestion=lambda *args, **kwargs: emitted.append(args),
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


def test_live_owner_near_miss_stays_pending_then_accepts_fresh_evidence(monkeypatch):
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'true')
    matcher, _host, emitted = _live_matcher(monkeypatch, [_cold_start_vector(0.67), _cold_start_vector(0.40)])
    matcher.person_embeddings.pop('p1')
    pending_counter = LIVE_SPEAKER_DECISIONS.labels(target='owner', decision='pending')._value
    rejected_counter = LIVE_SPEAKER_DECISIONS.labels(target='owner', decision='rejected')._value
    pending_before, rejected_before = pending_counter.get(), rejected_counter.get()

    asyncio.run(matcher.match(1, _segment('near', 0, 5)))
    assert 1 not in matcher.speaker_to_person
    assert matcher.voice_identity_status[1] == SpeakerIdentityStatus.unknown
    assert matcher.segment_identity_status['near'] == SpeakerIdentityStatus.unknown
    assert matcher.match_scores[0]['status'] == 'unknown'
    assert matcher.match_scores[0]['decision'] == 'pending'
    assert matcher.match_scores[0]['accepted_person_id'] is None
    assert emitted == []
    assert pending_counter.get() == pending_before + 1
    assert rejected_counter.get() == rejected_before

    asyncio.run(matcher.match(1, _segment('fresh', 6, 5)))
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher.voice_identity_status[1] == SpeakerIdentityStatus.user
    assert matcher.match_scores[0]['decision'] == 'accepted'
    assert emitted == [(1, 'user', 'User', 'fresh')]


def test_live_owner_outside_calibrated_band_remains_no_match(monkeypatch):
    matcher, _host, emitted = _live_matcher(monkeypatch, [_cold_start_vector(0.737)])
    matcher.person_embeddings.pop('p1')
    asyncio.run(matcher.match(1, _segment('far', 0, 10)))
    assert matcher.voice_identity_status[1] == SpeakerIdentityStatus.no_match
    assert 1 not in matcher.speaker_to_person
    assert emitted == []


def test_provider_failover_reconciles_one_owner_across_epoch_ids(monkeypatch):
    # Both clips independently match the owner at 0.53/0.54. Their in-session
    # vectors are close; provider epoch IDs alone must not create contention.
    clips = [
        np.array([[0.47, np.sqrt(1 - 0.47**2)]], dtype=np.float32),
        np.array([[0.46, np.sqrt(1 - 0.46**2)]], dtype=np.float32),
    ]
    matcher, _host, _emitted = _live_matcher(monkeypatch, clips)
    matcher.person_embeddings.pop('p1')
    first = dict(_segment('before', 0, 6), speaker_id_scope='connection:0')
    second = dict(_segment('after', 7, 6), speaker_id_scope='connection:1')

    asyncio.run(matcher.match(1, first))
    asyncio.run(matcher.match(2, second))

    assert matcher.speaker_to_person[1][0] == 'user'
    assert matcher.speaker_to_person[2][0] == 'user'
    assert matcher.voice_identity_status[1] == matcher.voice_identity_status[2] == SpeakerIdentityStatus.user


def test_manual_owner_receipt_reserves_live_owner_without_embedding(monkeypatch):
    from routers.listen import speakers as speakers_mod

    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _emitted = _live_matcher(monkeypatch, [owner])
    matcher._profile_conversation_id = 'c'

    async def receipt(_fn, _uid, _conversation_id):
        return {'segments': {'manual': {'is_user': True, 'person_id': None}}}

    host.request.uid = 'u'
    host.persistence = SimpleNamespace(call=receipt)
    monkeypatch.setattr(speakers_mod.conversations_db, 'get_manual_speaker_receipt', lambda *_: {})
    asyncio.run(matcher.match(2, _segment('automatic', 0, 6)))

    assert 2 not in matcher.speaker_to_person
    assert matcher.voice_identity_status[2] == SpeakerIdentityStatus.ambiguous


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


@pytest.mark.parametrize('second_start,second_seconds', [(0.0, 3.0), (1.0, 3.0)])
def test_overlapping_updates_do_not_count_as_new_evidence(monkeypatch, second_start, second_seconds):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _host, emitted = _live_matcher(monkeypatch, [owner] * 3)
    asyncio.run(matcher.match(1, _segment('s1', 0.0, 3.0)))
    asyncio.run(matcher.match(1, _segment('s1', second_start, second_seconds)))
    assert emitted == []
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 3.0
    # A growing update contains a genuinely new two-second tail.
    asyncio.run(matcher.match(1, _segment('s1', 0.0, 5.0)))
    assert emitted == [(1, 'user', 'User', 's1')]
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5.0


def test_three_clips_still_require_five_seconds(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [owner] * 3)
    host.limits.speaker_id_min_audio = 1.0
    for index in range(3):
        asyncio.run(matcher.match(1, _segment(str(index), index * 2.0, 1.0)))
    assert emitted == []
    assert not matcher.segment_identity_status


def test_concurrent_updates_preserve_the_first_accepted_identity(monkeypatch):
    import routers.listen.speakers as speakers_mod

    async def scenario():
        owner = np.array([[1.0, 0.0]], dtype=np.float32)
        sarah = np.array([[0.0, 1.0]], dtype=np.float32)
        matcher, _host, emitted = _live_matcher(monkeypatch, [])
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def embed(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
                return owner
            return sarah

        monkeypatch.setattr(speakers_mod, 'run_blocking', embed)
        first = asyncio.create_task(matcher.match(1, _segment('s1', 0.0, 5.0)))
        await entered.wait()
        second = asyncio.create_task(matcher.match(1, _segment('s2', 6.0, 5.0)))
        release.set()
        await asyncio.gather(first, second)
        assert calls == 1
        assert emitted == [(1, 'user', 'User', 's1')]
        assert matcher.speaker_to_person[1] == ('user', 'User')

    asyncio.run(scenario())


def test_clear_invalidates_inflight_embeddings(monkeypatch):
    import routers.listen.speakers as speakers_mod

    async def scenario():
        owner = np.array([[1.0, 0.0]], dtype=np.float32)
        matcher, _host, emitted = _live_matcher(monkeypatch, [])
        entered = asyncio.Event()
        release = asyncio.Event()

        async def embed(*args):
            entered.set()
            await release.wait()
            return owner

        monkeypatch.setattr(speakers_mod, 'run_blocking', embed)
        pending = asyncio.create_task(matcher.match(1, _segment('s1', 0.0, 5.0)))
        await entered.wait()
        matcher.clear()
        release.set()
        await pending
        assert not matcher.speaker_evidence
        assert emitted == []

    asyncio.run(scenario())


def test_in_flight_match_does_not_paint_the_next_conversation(monkeypatch):
    import routers.listen.speakers as speakers_mod

    async def scenario():
        owner = np.array([[1.0, 0.0]], dtype=np.float32)
        matcher, host, emitted = _live_matcher(monkeypatch, [])
        host.state.speaker_id_enabled = False
        matcher._profile_conversation_id = 'old'
        entered = asyncio.Event()
        release = asyncio.Event()

        async def embed(*args):
            entered.set()
            await release.wait()
            return owner

        monkeypatch.setattr(speakers_mod, 'run_blocking', embed)
        pending = asyncio.create_task(matcher.match(1, _segment('s1', 0.0, 5.0)))
        await entered.wait()
        held_lock = matcher._speaker_locks[1]
        await matcher.refresh_for_conversation('next')
        assert matcher._speaker_locks[1] is held_lock
        release.set()
        await pending
        assert matcher.speaker_to_person == {}
        assert matcher._profile_conversation_id == 'next'
        assert emitted == []

    asyncio.run(scenario())


def test_empty_profile_session_keeps_matcher_loop_until_refresh_queues_match(monkeypatch):
    async def scenario():
        matcher, host, _ = _live_matcher(monkeypatch, [])
        host.state.speaker_id_enabled = True
        host.state.speaker_id_done = asyncio.Event()
        host.state.active = True
        matcher._profile_conversation_id = 'c1'
        matcher.person_embeddings = {}
        spawned = []

        def spawn(coro, *, name):
            spawned.append(name)
            task = asyncio.create_task(coro)
            task.cancel()
            return task

        host.spawn = spawn

        async def load_profiles():
            matcher.person_embeddings = {'p1': {'embedding': np.array([[1.0, 0.0]], dtype=np.float32), 'name': 'Alex'}}

        monkeypatch.setattr(matcher, '_load_profiles', load_profiles)
        runner = asyncio.create_task(matcher.load_and_run())
        try:
            for _ in range(20):
                if not host.state.speaker_id_done.is_set():
                    break
                await asyncio.sleep(0.01)
            assert not host.state.speaker_id_done.is_set()
            await matcher.refresh_for_conversation('c2')
            assert 'p1' in matcher.person_embeddings
            matcher.queue.put_nowait(
                {
                    'id': 's1',
                    'conversation_id': 'c2',
                    'speaker_id': 1,
                    'abs_start': 0.0,
                    'abs_end': 5.0,
                    'duration': 5.0,
                }
            )
            for _ in range(50):
                if spawned:
                    break
                await asyncio.sleep(0.02)
            assert spawned == ['speaker_match']
        finally:
            host.state.active = False
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_speaker_detection_reads_person_embeddings_live():
    from unittest.mock import patch

    async def scenario():
        queue = asyncio.Queue()
        speakers = SimpleNamespace(
            speaker_to_person={},
            person_embeddings={},
            queue=queue,
            resolve_owner_name=_no_owner_name,
        )
        processor = object.__new__(TranscriptProcessor)
        processor.host = SimpleNamespace(
            speakers=speakers,
            state=SimpleNamespace(
                speaker_id_enabled=True,
                current_conversation_id='c2',
                first_audio_byte_timestamp=0.0,
            ),
            language='en',
            persistence=SimpleNamespace(call=lambda *a, **k: None),
            request=SimpleNamespace(uid='u', create_speakers=False),
        )
        processor.suggested_segments = set()
        segment = TranscriptSegment(
            id='s1',
            speaker='SPEAKER_00',
            speaker_id=1,
            text='synthetic speech',
            start=0.0,
            end=3.0,
            is_user=False,
        )
        with patch('routers.listen.transcripts.detect_speaker_introduction', return_value=None):
            await processor._speaker_detection([segment], 0.0)
            assert queue.empty()
            speakers.person_embeddings = {'p1': {'name': 'Alex'}}
            await processor._speaker_detection([segment], 0.0)
        item = queue.get_nowait()
        assert item['conversation_id'] == 'c2'
        assert item['speaker_id'] == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    'scores,owner',
    [
        ([0.631, 0.645], None),
        ([0.64, 0.70], None),
        ([0.40, 0.63], 0),
        ([0.53, 0.73], 0),
        ([0.53], 0),
        ([0.73, 0.87, 1.05], None),
    ],
)
def test_cold_start_arbitrates_voices_without_retuning_recall(scores, owner):
    rows = {i: {'user': score} for i, score in enumerate(scores)}
    decisions = arbitrate_owner_matches(rows, {i: select_speaker_match(row) for i, row in rows.items()})
    assert [i for i, d in decisions.items() if d.accepted] == ([] if owner is None else [owner])
    if scores == [0.631, 0.645]:
        assert all(d.owner_contended for d in decisions.values())


@pytest.mark.parametrize(
    'status', [SpeakerIdentityStatus.no_match, SpeakerIdentityStatus.ambiguous, SpeakerIdentityStatus.unknown]
)
@pytest.mark.parametrize(
    'source,match_source,clear',
    [
        ('auto', 'live_embedding', True),
        (None, 'live_embedding', True),
        ('manual', 'live_embedding', False),
        ('carried', 'live_embedding', False),
        (None, None, False),
        ('auto', 'channel', False),
    ],
)
@pytest.mark.parametrize('was_owner', [False, True])
def test_rejected_identity_projection_preserves_manual_and_channel_authority(
    status, source, match_source, clear, was_owner
):
    segment = TranscriptSegment(
        id='s',
        text='synthetic',
        speaker_id=0,
        start=0,
        end=5,
        is_user=was_owner,
        person_id=None if was_owner else 'peer',
        speaker_label_source=source,
        speaker_match_source=match_source,
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        speakers=SimpleNamespace(
            segment_assignments={},
            speaker_to_person={},
            voice_identity_status={0: status},
            segment_identity_status={},
        )
    )
    processor._apply_speaker_identity_statuses([segment])
    rendered = segment.model_dump()
    assert rendered['is_user'] is (False if clear else was_owner)
    assert rendered['person_id'] == (None if clear or was_owner else 'peer')


def _cold_start_vector(distance, sign=1):
    # Unit vectors at measured cosine distances; opposite residual directions
    # keep the two voices distinct under in-session clustering.
    cosine = 1 - distance
    return np.array([[cosine, sign * np.sqrt(1 - cosine**2)]], dtype=np.float32)


@pytest.mark.parametrize('source', ['auto', 'manual', 'carried'])
@pytest.mark.parametrize('next_person', ['user', 'peer'])
def test_identity_projection_corrects_only_automatic_positive_labels(source, next_person):
    was_owner = next_person == 'peer'
    segment = TranscriptSegment(
        id='s',
        text='synthetic',
        speaker_id=0,
        start=0,
        end=5,
        is_user=was_owner,
        person_id=None if was_owner else 'peer',
        speaker_label_source=source,
        speaker_match_source='live_embedding',
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        speakers=SimpleNamespace(
            segment_assignments={},
            speaker_to_person={0: (next_person, 'Name')},
            voice_identity_status={},
            segment_identity_status={},
        )
    )
    processor._apply_speaker_identity_statuses([segment])
    rendered = segment.model_dump()
    expected_owner = next_person == 'user' if source == 'auto' else was_owner
    assert rendered['is_user'] is expected_owner
    assert rendered['person_id'] == (None if expected_owner else 'peer')


@pytest.mark.parametrize('reverse', [False, True])
def test_live_cold_start_retracts_previous_owner_and_projects_all_segments(monkeypatch, reverse):
    vectors = [_cold_start_vector(0.631), _cold_start_vector(0.645, -1)]
    matcher, host, _ = _live_matcher(monkeypatch, vectors[::-1] if reverse else vectors)
    del matcher.person_embeddings['p1']
    segments = [
        TranscriptSegment(id=f's{i}', text='synthetic', speaker_id=i // 2, is_user=False, start=i * 6, end=i * 6 + 6)
        for i in range(4)
    ]
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(speakers=matcher)
    from utils.speaker_assignment import process_speaker_assigned_segments

    asyncio.run(matcher.match(0, _segment('s0', 0, 6)))
    process_speaker_assigned_segments(segments, matcher.segment_assignments, matcher.speaker_to_person)
    processor._apply_speaker_identity_statuses(segments)
    assert all(s.is_user for s in segments[:2])
    asyncio.run(matcher.match(1, _segment('s2', 12, 6)))
    processor._apply_speaker_identity_statuses(segments)
    assert matcher.speaker_to_person == {}
    assert all(not s.is_user and s.person_id is None for s in segments)
    assert all(s.speaker_identity_status == SpeakerIdentityStatus.ambiguous for s in segments)
    assert all(TranscriptSegment(**s.model_dump()).speaker_identity_status == 'ambiguous' for s in segments)
    matcher.clear()
    assert not matcher.voice_identity_status and not matcher._voice_distances


@pytest.mark.parametrize('reverse', [False, True])
def test_live_clear_owner_wins_regardless_of_arrival_order(monkeypatch, reverse):
    vectors = [_cold_start_vector(0.53), _cold_start_vector(0.645, -1)]
    matcher, _, _ = _live_matcher(monkeypatch, vectors[::-1] if reverse else vectors)
    del matcher.person_embeddings['p1']
    asyncio.run(matcher.match(0, _segment('a', 0, 6)))
    asyncio.run(matcher.match(1, _segment('b', 6, 6)))
    assert matcher.speaker_to_person == {int(reverse): ('user', 'User')}


def test_known_household_member_does_not_contend_for_the_owner():
    rows = {0: {'user': 0.53, 'person': 0.90}, 1: {'user': 0.43, 'person': 0.20}}
    result = arbitrate_owner_matches(rows, {i: select_speaker_match(row) for i, row in rows.items()})
    assert result[0].person_id == 'user'
    assert result[1].person_id == 'person'


def test_subsecond_live_fragments_reach_owner_transcript(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [owner] * 6)
    for index in range(15):
        # Real provider fragments, not merged text: 7.5 distinct speech seconds.
        fragment = _segment(f's{index}', index * 0.5, 0.5)
        fragment['speaker_id'] = 1
        fragment['speaker_id_scope'] = 'socket:0'
        asyncio.run(matcher.match(1, fragment))
    from utils.speaker_assignment import process_speaker_assigned_segments

    rendered = TranscriptSegment(id='reply', text='Okay', speaker_id=1, is_user=False, start=8.0, end=8.5)
    process_speaker_assigned_segments([rendered], matcher.segment_assignments, matcher.speaker_to_person)
    assert rendered.model_dump()['is_user'] is True
    assert rendered.speaker_label_source == 'auto'
    assert len(emitted) == 1


def test_repeated_tiny_fragment_cannot_mint_owner_evidence(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _, emitted = _live_matcher(monkeypatch, [owner] * 20)
    for _ in range(20):
        asyncio.run(matcher.match(1, _segment('same', 0.0, 0.5)))
    assert 1 not in matcher.speaker_to_person
    assert not emitted

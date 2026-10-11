import pytest
import asyncio
import math
from types import SimpleNamespace

import numpy as np

import routers.listen.speakers as speakers_mod
from config.speaker_prior import pinned_speaker_prior_enabled
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from routers.listen.transcripts import TranscriptProcessor
from utils.sync import speaker_identity as sync_mod
from utils.stt.speaker_match import (
    SPEAKER_MATCH_MARGIN,
    SPEAKER_MATCH_THRESHOLD,
    SpeakerMatchDecision,
    match_level,
    pinned_near_miss,
    select_speaker_match,
    voice_candidates,
)

T, M = SPEAKER_MATCH_THRESHOLD, SPEAKER_MATCH_MARGIN


def decide(distances):
    return select_speaker_match(distances)


def test_flag_defaults_off_and_reads_only_true():
    assert pinned_speaker_prior_enabled({}) is False
    assert pinned_speaker_prior_enabled({'PINNED_SPEAKER_PRIOR_ENABLED': 'TRUE '}) is True
    assert pinned_speaker_prior_enabled({'PINNED_SPEAKER_PRIOR_ENABLED': '1'}) is False


def test_distance_just_above_threshold_on_a_pinned_person_is_a_near_miss():
    distances = {'maya': T + 0.03, 'sam': T + 0.30}
    decision = decide(distances)
    assert not decision.accepted
    assert pinned_near_miss(decision, {'maya'}) == 'maya'
    # Not pinned: nothing.
    assert pinned_near_miss(decision, set()) is None
    # Too far above the threshold: nothing.
    assert pinned_near_miss(decide({'maya': T + 0.06}), {'maya'}) is None


def test_margin_just_short_on_a_pinned_person_is_a_near_miss():
    distances = {'maya': T - 0.2, 'jordan': T - 0.2 + M - 0.02}
    decision = decide(distances)
    assert not decision.accepted
    assert pinned_near_miss(decision, {'maya'}) == 'maya'
    assert pinned_near_miss(decide({'maya': 0.3, 'jordan': 0.31}), {'maya'}) is None


def test_prior_never_changes_an_accept_or_an_owner_contention():
    accepted = decide({'maya': 0.3})
    assert accepted.accepted and pinned_near_miss(accepted, {'maya'}) is None
    contended = SpeakerMatchDecision(None, 'maya', T + 0.01, math.inf, owner_contended=True)
    assert pinned_near_miss(contended, {'maya'}) is None


def test_match_levels():
    assert match_level(T - 0.01) == 3
    assert match_level(T + 0.05) == 2
    assert match_level(T + 0.15) == 1
    assert match_level(T + 0.25) is None
    assert match_level(float('nan')) is None and match_level(math.inf) is None


def test_voice_candidates_rank_by_level_then_pinned_and_flag_the_suggestion():
    distances = {'user': 0.2, 'sam': T + 0.02, 'jordan': T + 0.08, 'alex': T + 0.12, 'priya': T + 0.5}
    decision = decide({k: v for k, v in distances.items() if k != 'user'})
    candidates = voice_candidates(distances, decision, {'jordan'}, exclude=('user',))
    assert [c['person_id'] for c in candidates] == ['jordan', 'sam', 'alex']
    assert [c['level'] for c in candidates] == [2, 2, 1]
    assert not any(c.get('suggest') for c in candidates)
    near = voice_candidates({'sam': T + 0.02}, decide({'sam': T + 0.02}), {'sam'})
    assert near == [{'person_id': 'sam', 'level': 2, 'suggest': True}]


# ─── Injection points ─────────────────────────────────────────────────────────

NEAR = np.array([[0.0, 0.33, float(np.sqrt(1 - 0.33**2))]], dtype=np.float32)  # 0.67 from p1


class _Ring:
    def get_time_range(self):
        return 0.0, 60.0

    def extract(self, start, end):
        return b'\x00\x00' * round((end - start) * 16000)


def _live(monkeypatch, *, pinned, enabled):
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'true' if enabled else 'false')
    emitted = []
    host = SimpleNamespace(
        state=SimpleNamespace(audio_ring_buffer=_Ring(), speaker_map_dirty=False),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        request=SimpleNamespace(sample_rate=16000),
        emit_speaker_suggestion=lambda *args, **kwargs: emitted.append((args, kwargs)),
    )
    matcher = speakers_mod.SpeakerMatcher(host)
    matcher.person_embeddings = {
        'user': {'embedding': np.array([[1.0, 0.0, 0.0]], dtype=np.float32), 'name': 'User'},
        'p1': {'embedding': np.array([[0.0, 1.0, 0.0]], dtype=np.float32), 'name': 'Maya', 'pinned': pinned},
    }
    monkeypatch.setattr(speakers_mod, 'extract_embedding_from_bytes', lambda _audio, _name: NEAR)
    return matcher, emitted


def _clip(seg_id):
    return {'id': seg_id, 'duration': 6.0, 'abs_start': 0.0, 'abs_end': 6.0}


def test_live_pinned_near_miss_is_a_suggestion_never_a_label(monkeypatch):
    matcher, emitted = _live(monkeypatch, pinned=True, enabled=True)
    asyncio.run(matcher.match(3, _clip('s1')))
    assert 3 not in matcher.speaker_to_person
    assert matcher.voice_identity_status[3] == SpeakerIdentityStatus.no_match
    assert emitted == [((3, '', 'Maya', 's1'), {'suggested_person_id': 'p1'})]
    assert matcher.voice_candidates[3] == [{'person_id': 'p1', 'level': 2, 'suggest': True}]
    # The same suggestion is not repeated for the voice.
    asyncio.run(matcher.match(3, _clip('s2')))
    assert len(emitted) == 1


def test_live_prior_off_or_unpinned_emits_nothing(monkeypatch):
    for pinned, enabled in ((True, False), (False, True)):
        matcher, emitted = _live(monkeypatch, pinned=pinned, enabled=enabled)
        asyncio.run(matcher.match(3, _clip('s1')))
        assert emitted == [] and 3 not in matcher.speaker_to_person
        assert matcher.voice_candidates.get(3, [{}])[0].get('suggest') is None


def test_sync_pinned_near_miss_is_recorded_on_segments_not_labeled(monkeypatch):
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'true')
    deps = sync_mod.SpeakerIdentityDependencies(
        speaker_embedding_configured=lambda: True,
        extract_embedding_from_bytes=lambda _audio, _name: NEAR,
        collect_speaker_audio=lambda _audio, spans: SimpleNamespace(clips=[(b'wav', 6.0)], available_seconds=6.0),
        detect_speaker_from_text=lambda *args, **kwargs: None,
    )
    cache = {
        'user': {'embedding': np.array([[1.0, 0.0, 0.0]], dtype=np.float32), 'name': 'User'},
        'p1': {'embedding': np.array([[0.0, 1.0, 0.0]], dtype=np.float32), 'name': 'Maya', 'pinned': True},
    }
    segments = [TranscriptSegment(id='a', text='hello there', speaker_id=2, is_user=False, start=0, end=6)]
    sync_mod.identify_speakers_for_segments(segments, b'audio', cache, 'u', 'en', dependencies=deps)
    assert segments[0].person_id is None and not segments[0].is_user
    assert segments[0].voice_candidates == [{'person_id': 'p1', 'level': 2, 'suggest': True}]
    assert segments[0].model_dump()['voice_candidates'][0]['suggest'] is True


def test_live_candidates_are_stamped_only_on_unlabeled_segments():
    candidates = [{'person_id': 'p1', 'level': 2, 'suggest': True}]
    speakers = SimpleNamespace(
        segment_assignments={},
        speaker_to_person={},
        voice_identity_status={3: SpeakerIdentityStatus.no_match},
        segment_identity_status={},
        voice_candidates={3: candidates},
    )
    unlabeled = TranscriptSegment(id='a', text='hi', speaker_id=3, is_user=False, start=0, end=1)
    manual = TranscriptSegment(id='b', text='hi', speaker_id=3, is_user=False, person_id='p9', start=1, end=2)
    TranscriptProcessor._apply_speaker_identity_statuses(
        SimpleNamespace(host=SimpleNamespace(speakers=speakers)), [unlabeled, manual]
    )
    assert unlabeled.voice_candidates == candidates and manual.voice_candidates is None


def test_live_near_miss_excludes_a_person_already_assigned_to_another_voice(monkeypatch):
    matcher, emitted = _live(monkeypatch, pinned=True, enabled=True)
    matcher.speaker_to_person[9] = ('p1', 'Maya')
    asyncio.run(matcher.match(3, _clip('s1')))
    assert emitted == []
    assert matcher.voice_candidates[3] == []


def test_sync_candidates_exclude_a_person_already_manually_assigned(monkeypatch):
    monkeypatch.setenv('PINNED_SPEAKER_PRIOR_ENABLED', 'true')
    deps = sync_mod.SpeakerIdentityDependencies(
        speaker_embedding_configured=lambda: True,
        extract_embedding_from_bytes=lambda _audio, _name: NEAR,
        collect_speaker_audio=lambda _audio, spans: SimpleNamespace(clips=[(b'wav', 6.0)], available_seconds=6.0),
        detect_speaker_from_text=lambda *args, **kwargs: None,
    )
    cache = {'p1': {'embedding': np.array([[0.0, 1.0, 0.0]], dtype=np.float32), 'name': 'Maya', 'pinned': True}}
    segments = [
        TranscriptSegment(id='manual', text='Maya', speaker_id=1, is_user=False, person_id='p1', start=0, end=7),
        TranscriptSegment(id='unknown', text='someone', speaker_id=2, is_user=False, start=7, end=13),
    ]
    sync_mod.identify_speakers_for_segments(segments, b'audio', cache, 'u', dependencies=deps)
    assert segments[0].person_id == 'p1'
    assert segments[1].person_id is None and segments[1].voice_candidates == []


def test_live_owner_and_named_auto_accepts_are_identical_with_prior_on_or_off(monkeypatch):
    for vector, expected in (([1.0, 0.0, 0.0], 'user'), ([0.0, 1.0, 0.0], 'p1')):
        observed = []
        for enabled in (False, True):
            matcher, emitted = _live(monkeypatch, pinned=True, enabled=enabled)
            monkeypatch.setattr(
                speakers_mod, 'extract_embedding_from_bytes', lambda _audio, _name: np.array([vector], dtype=np.float32)
            )
            asyncio.run(matcher.match(3, _clip('s1')))
            assert matcher.speaker_to_person[3][0] == expected
            observed.append((dict(matcher.speaker_to_person), dict(matcher.voice_identity_status), emitted))
        assert observed[0] == observed[1]


def test_sync_candidates_survive_both_parent_serializations():
    from datetime import datetime, timezone
    from models.conversation import Conversation, CreateConversation, Structured

    segment = TranscriptSegment(id='s1', text='hello', speaker_id=2, is_user=False, start=0, end=6)
    segment.voice_candidates = [{'person_id': 'p1', 'level': 2, 'suggest': True}]
    now = datetime.now(timezone.utc)
    create = CreateConversation(started_at=now, finished_at=now, transcript_segments=[segment])
    incoming = Conversation(
        id='c1', created_at=now, structured=Structured(title='Test', overview=''), **create.model_dump()
    )
    assert incoming.model_dump()['transcript_segments'][0]['voice_candidates'] == segment.voice_candidates
    assert incoming.model_dump(mode='json')['transcript_segments'][0]['voice_candidates'] == segment.voice_candidates
    # Flag-off records and the public schema keep their prior shape.
    segment.voice_candidates = None
    assert 'voice_candidates' not in create.model_dump()['transcript_segments'][0]
    for mode in ('validation', 'serialization'):
        schema = TranscriptSegment.model_json_schema(mode=mode)
        assert 'text' in schema['properties'] and 'voice_candidates' not in schema['properties']


def test_live_retracts_a_near_match_when_later_audio_no_longer_matches(monkeypatch):
    matcher, emitted = _live(monkeypatch, pinned=True, enabled=True)
    asyncio.run(matcher.match(3, _clip('s1')))
    assert matcher._suggested_person[3] == 'p1'
    matcher._voice_distances[3] = {'p1': T + 0.5}
    matcher._offer_pinned_suggestion(3, decide(matcher._voice_distances[3]), {'p1'}, 's2', set())
    assert 3 not in matcher._suggested_person
    assert emitted[-1] == ((3, '', '', 's2'), {'retracted': True})
    assert matcher.voice_candidates[3] == []
    matcher._offer_pinned_suggestion(3, decide(matcher._voice_distances[3]), {'p1'}, 's3', set())
    assert len(emitted) == 2


def test_live_later_audio_retracts_the_emitted_near_match(monkeypatch):
    matcher, emitted = _live(monkeypatch, pinned=True, enabled=True)
    asyncio.run(matcher.match(3, _clip('s1')))
    monkeypatch.setattr(
        speakers_mod,
        'extract_embedding_from_bytes',
        lambda _audio, _name: np.array([[0.0, -1.0, 0.0]], dtype=np.float32),
    )
    asyncio.run(matcher.match(3, {'id': 's2', 'duration': 6.0, 'abs_start': 6.0, 'abs_end': 12.0}))
    assert 3 not in matcher.speaker_to_person
    assert 3 not in matcher._suggested_person
    assert emitted[-1] == ((3, '', '', 's2'), {'retracted': True})


def test_live_replaces_a_near_match_for_the_same_speaker(monkeypatch):
    matcher, emitted = _live(monkeypatch, pinned=True, enabled=True)
    asyncio.run(matcher.match(3, _clip('s1')))
    matcher.person_embeddings['p2'] = {'name': 'Sam', 'pinned': True}
    matcher._voice_distances[3] = {'p2': T + 0.02, 'p1': T + 0.5}
    matcher._offer_pinned_suggestion(3, decide(matcher._voice_distances[3]), {'p1', 'p2'}, 's2', set())
    assert matcher._suggested_person[3] == 'p2'
    assert emitted[-1] == ((3, '', 'Sam', 's2'), {'suggested_person_id': 'p2'})


@pytest.fixture(autouse=True)
def paid_named_speaker_entitlement(monkeypatch):
    from utils.sync import speaker_identity
    from routers.listen import speakers

    monkeypatch.setattr(speaker_identity, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', lambda uid: True)

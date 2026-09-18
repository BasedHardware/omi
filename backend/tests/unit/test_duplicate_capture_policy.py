"""Duplicate-capture policy (#3244): device-on-phone + macOS microphone in one room.

Behavioral coverage of `utils.conversations.duplicate_capture` through its
public API with synthetic captures. The noisy-copy fixtures model what two
microphones and two STT passes over the same speech actually produce (word
level disagreement, not identical text), and the #5388 fixtures model two
captures that share a time window but not their audio.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from utils.conversations.duplicate_capture import (
    MIN_CANDIDATE_WORDS,
    MIN_TRANSCRIPT_CONTAINMENT,
    MIN_WINDOW_COVERAGE,
    CaptureRecord,
    bigram_containment,
    capture_record,
    find_duplicate_capture,
    is_primary_eligible,
    same_capture_client,
    transcript_words,
    window_coverage,
)

T0 = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)

_USER_TURNS = [
    'okay so the plan for the pendant firmware release is to ship the codec fix first',
    'i think we should also bump the advertised battery estimate once the new curve lands',
    'let me write the release notes tonight and send them to the hardware channel',
    'we still need someone to verify the pairing flow on the older android builds',
]
_REMOTE_TURNS = [
    'that works for me but the app team wants the opus change behind a flag',
    'the battery curve is not validated yet so keep the estimate where it is',
    'i can take the android pairing pass tomorrow morning before standup',
    'and remember the store listing screenshots are due by the end of the week',
]


def _interleave(*turn_lists: list[str]) -> str:
    turns: list[str] = []
    for group in zip(*turn_lists):
        turns.extend(group)
    return ' '.join(turns)


ROOM_TEXT = _interleave(_USER_TURNS, _REMOTE_TURNS)
OTHER_ROOM_TEXT = (
    'the quarterly numbers came in above forecast because renewals held up better than we modeled '
    'marketing wants a bigger event budget for the conference season and finance is pushing back '
    'we agreed to revisit hiring for the support team after the next board meeting closes '
    'someone should follow up with the vendor about the invoice discrepancy from last month'
)


def _noisy(text: str, *, rate: float, seed: int) -> str:
    """Substitute a fraction of words, the way a second far-field microphone misses them."""
    rng = random.Random(seed)
    words = text.split()
    for index in range(len(words)):
        if rng.random() < rate:
            words[index] = f'garbled{index}'
    return ' '.join(words)


def _segments(text: str, *, seconds: float) -> list[dict]:
    words = text.split()
    half = len(words) // 2
    return [
        {'text': ' '.join(words[:half]), 'start': 0.0, 'end': seconds / 2},
        {'text': ' '.join(words[half:]), 'start': seconds / 2, 'end': seconds},
    ]


def _record(
    conversation_id: str,
    text: str,
    *,
    start: datetime = T0,
    seconds: float = 300.0,
    created_at: datetime | None = None,
    status: str = 'completed',
    source: str = 'omi',
    device: str | None = 'phone-hash',
    platform: str | None = 'ios',
    discarded: bool = False,
) -> CaptureRecord:
    return CaptureRecord(
        conversation_id=conversation_id,
        created_at=created_at or start,
        started_at=start,
        finished_at=start + timedelta(seconds=seconds),
        status=status,
        words=transcript_words(_segments(text, seconds=seconds)),
        source=source,
        client_device_id=device,
        client_platform=platform,
        discarded=discarded,
    )


def _desktop(conversation_id: str, text: str, **overrides) -> CaptureRecord:
    overrides.setdefault('source', 'desktop')
    overrides.setdefault('device', 'mac-hash')
    overrides.setdefault('platform', 'macos')
    return _record(conversation_id, text, **overrides)


class TestSameRoomDuplicateIsFolded:
    def test_device_capture_finalizing_after_the_mac_is_folded_into_it(self):
        mac = _desktop('mac-conv', _noisy(ROOM_TEXT, rate=0.15, seed=1))
        pendant = _record('pendant-conv', ROOM_TEXT, created_at=T0 + timedelta(seconds=3))

        match = find_duplicate_capture(pendant, [mac])

        assert match is not None
        assert match.primary_conversation_id == 'mac-conv'
        assert match.window_coverage == pytest.approx(1.0)
        assert match.transcript_containment >= MIN_TRANSCRIPT_CONTAINMENT

    def test_far_field_disagreement_of_a_quarter_of_the_words_still_matches(self):
        mac = _desktop('mac-conv', ROOM_TEXT)
        pendant = _record('pendant-conv', _noisy(ROOM_TEXT, rate=0.25, seed=7))

        assert find_duplicate_capture(pendant, [mac]) is not None

    def test_a_small_start_offset_between_the_two_sessions_is_tolerated(self):
        mac = _desktop('mac-conv', ROOM_TEXT, start=T0, seconds=300)
        pendant = _record('pendant-conv', ROOM_TEXT, start=T0 + timedelta(seconds=20), seconds=300)

        match = find_duplicate_capture(pendant, [mac])

        assert match is not None
        assert MIN_WINDOW_COVERAGE <= match.window_coverage < 1.0

    def test_the_best_carrying_primary_wins_when_several_qualify(self):
        weak = _desktop('mac-weak', _noisy(ROOM_TEXT, rate=0.3, seed=3), device='mac-a')
        strong = _desktop('mac-strong', ROOM_TEXT, device='mac-b')
        pendant = _record('pendant-conv', ROOM_TEXT)

        match = find_duplicate_capture(pendant, [weak, strong])

        assert match is not None and match.primary_conversation_id == 'mac-strong'


class TestDistinctSimultaneousCapturesAreKept:
    """#5388: a pendant in the room plus a headphone meeting on the laptop hold different speech."""

    def test_pendant_hearing_only_the_user_is_not_folded_into_a_remote_only_capture(self):
        web = _desktop('web-conv', ' '.join(_REMOTE_TURNS * 2), source='web', platform='web', device='browser-hash')
        pendant = _record('pendant-conv', ' '.join(_USER_TURNS * 2))

        assert find_duplicate_capture(pendant, [web]) is None

    def test_an_unrelated_conversation_in_the_same_window_is_not_a_duplicate(self):
        mac = _desktop('mac-conv', OTHER_ROOM_TEXT)
        pendant = _record('pendant-conv', ROOM_TEXT)

        assert find_duplicate_capture(pendant, [mac]) is None
        assert bigram_containment(pendant.words, mac.words) < MIN_TRANSCRIPT_CONTAINMENT

    def test_a_capture_that_kept_running_after_the_other_stopped_is_kept(self):
        """Speech recorded after the laptop stopped exists nowhere else."""
        mac = _desktop('mac-conv', ROOM_TEXT, seconds=300)
        longer = ROOM_TEXT + ' ' + OTHER_ROOM_TEXT
        pendant = _record('pendant-conv', longer, seconds=600)

        overlap, coverage = window_coverage(pendant, mac)
        assert overlap == pytest.approx(300.0)
        assert coverage == pytest.approx(0.5)
        assert find_duplicate_capture(pendant, [mac]) is None

    def test_a_short_scrap_is_left_to_the_discard_gate(self):
        mac = _desktop('mac-conv', ROOM_TEXT)
        scrap_text = ' '.join(ROOM_TEXT.split()[: MIN_CANDIDATE_WORDS - 1])
        scrap = _record('pendant-conv', scrap_text, seconds=20)

        assert len(scrap.words) < MIN_CANDIDATE_WORDS
        assert find_duplicate_capture(scrap, [mac]) is None

    def test_the_same_capture_client_never_folds_into_itself(self):
        """A reconnecting phone must not be treated as a second device."""
        earlier = _record('pendant-a', ROOM_TEXT)
        later = _record('pendant-b', ROOM_TEXT, created_at=T0 + timedelta(seconds=5))

        assert same_capture_client(earlier, later)
        assert find_duplicate_capture(later, [earlier]) is None

    def test_legacy_rows_without_a_device_hash_compare_platform_and_source(self):
        a = _record('a', ROOM_TEXT, device=None, platform=None, source='omi')
        b = _record('b', ROOM_TEXT, device=None, platform=None, source='omi')
        c = _record('c', ROOM_TEXT, device=None, platform='macos', source='desktop')

        assert same_capture_client(a, b)
        assert not same_capture_client(a, c)


class TestExactlyOneSideYields:
    """Two sessions that time out on the same silence finalize together."""

    def test_the_later_created_processing_capture_yields_to_the_earlier_one(self):
        earlier = _desktop('mac-conv', ROOM_TEXT, status='processing', created_at=T0)
        later = _record('pendant-conv', ROOM_TEXT, status='processing', created_at=T0 + timedelta(seconds=2))

        assert find_duplicate_capture(later, [earlier]) is not None
        assert find_duplicate_capture(earlier, [later]) is None

    def test_a_completed_counterpart_is_primary_even_when_created_later(self):
        later_but_done = _desktop('mac-conv', ROOM_TEXT, status='completed', created_at=T0 + timedelta(seconds=30))
        earlier = _record('pendant-conv', ROOM_TEXT, status='processing', created_at=T0)

        match = find_duplicate_capture(earlier, [later_but_done])

        assert match is not None and match.primary_conversation_id == 'mac-conv'

    def test_in_progress_and_discarded_rows_cannot_be_primaries(self):
        live = _desktop('mac-live', ROOM_TEXT, status='in_progress')
        gone = _desktop('mac-gone', ROOM_TEXT, status='completed', discarded=True)
        pendant = _record('pendant-conv', ROOM_TEXT, created_at=T0 + timedelta(seconds=5))

        assert not is_primary_eligible(pendant, live)
        assert not is_primary_eligible(pendant, gone)
        assert find_duplicate_capture(pendant, [live, gone]) is None

    def test_a_row_never_matches_its_own_id(self):
        me = _record('same-id', ROOM_TEXT, status='processing')
        stored_copy = _desktop('same-id', ROOM_TEXT, status='processing')

        assert not is_primary_eligible(me, stored_copy)

    def test_an_already_discarded_candidate_is_not_re_evaluated(self):
        mac = _desktop('mac-conv', ROOM_TEXT)
        pendant = _record('pendant-conv', ROOM_TEXT, discarded=True)

        assert find_duplicate_capture(pendant, [mac]) is None


class TestCaptureRecordProjection:
    def test_projects_persisted_dict_rows_and_models_alike(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource, ConversationStatus
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        model = Conversation(
            id='conv-model',
            created_at=T0,
            started_at=T0,
            finished_at=T0 + timedelta(minutes=5),
            structured=Structured(),
            transcript_segments=[
                TranscriptSegment(
                    id='seg-1', text='Hello, world!', speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0, end=2
                )
            ],
            source=ConversationSource.desktop,
            status=ConversationStatus.processing,
            client_device_id='mac-hash',
            client_platform='macos',
        )
        row = {
            'id': 'conv-row',
            'created_at': T0,
            'started_at': T0.replace(tzinfo=None),
            'finished_at': (T0 + timedelta(minutes=5)).replace(tzinfo=None),
            'status': 'completed',
            'source': 'omi',
            'client_device_id': 'phone-hash',
            'client_platform': 'ios',
            'transcript_segments': [{'text': "Hello world it's me"}],
        }

        from_model = capture_record(model)
        from_row = capture_record(row)

        assert from_model is not None and from_row is not None
        assert from_model.words == ('hello', 'world')
        assert from_model.status == 'processing' and from_model.source == 'desktop'
        assert from_row.words == ('hello', 'world', 'it', 's', 'me')
        assert from_row.started_at.tzinfo is not None, 'naive Firestore datetimes are normalized to UTC'
        assert not same_capture_client(from_model, from_row)

    def test_rows_without_a_wall_window_are_ignored(self):
        assert capture_record({'id': 'x', 'started_at': T0}) is None
        assert capture_record({'id': 'x', 'started_at': T0, 'finished_at': T0 - timedelta(seconds=1)}) is None

    def test_created_at_falls_back_to_started_at_for_ingress_creates(self):
        from models.conversation import CreateConversation

        create = CreateConversation(
            started_at=T0, finished_at=T0 + timedelta(minutes=1), transcript_segments=[], source='desktop'
        )

        record = capture_record(create)

        assert record is not None
        assert record.conversation_id is None
        assert record.created_at == T0


class TestBigramContainment:
    def test_identical_sequences_are_fully_contained(self):
        words = tuple('a b c d e'.split())
        assert bigram_containment(words, words) == pytest.approx(1.0)

    def test_containment_is_relative_to_the_candidate(self):
        short = tuple('a b c'.split())
        long = tuple('x y a b c d e f'.split())
        assert bigram_containment(short, long) == pytest.approx(1.0)
        assert bigram_containment(long, short) == pytest.approx(2 / 7)

    def test_repeated_bigrams_count_only_as_often_as_the_primary_has_them(self):
        candidate = tuple('yes yes yes yes'.split())
        primary = tuple('yes yes no'.split())
        assert bigram_containment(candidate, primary) == pytest.approx(1 / 3)

    def test_too_few_words_have_no_containment(self):
        assert bigram_containment(('one',), ('one', 'two')) == 0.0
        assert bigram_containment(('one', 'two'), ('one',)) == 0.0

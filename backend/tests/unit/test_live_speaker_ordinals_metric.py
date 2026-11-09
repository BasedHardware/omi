"""Live speaker ordinal churn telemetry mirrors the display deferral, once per session.

The tracker must reproduce #23533's qualification exactly enough to be a churn
signal: five seconds of non-overlapping placed speech on an unnamed scoped voice
mint one ordinal, named voices mint none, and scope rotations are counted
separately so churn is readable against provider-epoch and reconnect rotations.
"""

from types import SimpleNamespace

from models.transcript_segment import TranscriptSegment
from routers.listen.transcripts import TranscriptProcessor
from utils.observability.live_speaker_ordinals import (
    MAX_TRACKED_VOICES,
    OMI_LIVE_SPEAKER_ORDINALS_PER_SESSION,
    OMI_LIVE_SPEAKER_SCOPE_ROTATIONS_TOTAL,
    LiveSpeakerOrdinalTracker,
    record_live_speaker_ordinals,
)


def voice(sid, speaker, scope, start, end, *, is_user=False, person_id=None):
    return dict(
        id=sid,
        text='Testing one two',
        speaker_id=speaker,
        speaker_id_scope=scope,
        start=start,
        end=end,
        is_user=is_user,
        person_id=person_id,
    )


def test_deferral_floor_mints_no_ordinal_below_five_placed_seconds():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 4.9))
    assert tracker.close() == (0, 0)


def test_five_seconds_of_one_voice_mints_exactly_one_ordinal():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 2.0))
    tracker.observe(voice('s2', 0, 'scope:0', 3.0, 6.0))
    assert tracker.close() == (1, 0)


def test_overlapping_and_replayed_spans_union_instead_of_double_counting():
    tracker = LiveSpeakerOrdinalTracker()
    # 4s + 4s overlapping in a 1s window is a 7s union: one qualified voice,
    # and a replay of the first span adds nothing.
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 4.0))
    tracker.observe(voice('s1', 0, 'scope:0', 3.0, 7.0))
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 4.0))
    assert tracker.close() == (1, 0)

    # Adjacent bursts that never reach the floor across two voices mint nothing.
    adjacent = LiveSpeakerOrdinalTracker()
    adjacent.observe(voice('a1', 0, 'scope:0', 0.0, 2.5))
    adjacent.observe(voice('a2', 1, 'scope:0', 2.5, 5.0))
    assert adjacent.close() == (0, 0)


def test_same_speaker_in_new_scope_is_a_new_ordinal_and_one_rotation():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 6.0))
    tracker.observe(voice('s2', 1, 'scope:1', 10.0, 16.0))
    tracker.observe(voice('s3', 2, 'scope:2', 20.0, 26.0))
    assert tracker.close() == (3, 2)


def test_named_voices_never_mint_ordinals():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 6.0, is_user=True))
    tracker.observe(voice('s2', 1, 'scope:0', 0.0, 6.0, person_id='person'))
    # A voice named only at close, through the matcher's final map.
    tracker.observe(voice('s3', 2, 'scope:0', 0.0, 6.0))
    tracker.note_named_voices(SimpleNamespace(speaker_to_person={2: ('person', 'Ada')}, _voice_scopes={2: 'scope:0'}))
    assert tracker.close() == (0, 0)


def test_unplaced_or_malformed_spans_add_no_seconds():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', -1.0, -1.0))
    tracker.observe(voice('s2', 0, 'scope:0', 4.0, 4.0))
    tracker.observe(voice('s3', 0, 'scope:0', float('nan'), 6.0))
    tracker.observe(voice('s4', 0, 'scope:0', None, '6.0'))
    assert tracker.close() == (0, 0)


def test_segments_without_usable_speaker_id_are_ignored():
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe({'id': 's1', 'start': 0.0, 'end': 9.0})
    tracker.observe(voice('s2', 'zero', 'scope:0', 0.0, 9.0))
    tracker.observe(voice('s3', True, 'scope:0', 0.0, 9.0))
    assert tracker.close() == (0, 0)


def test_voice_inventory_is_bounded():
    beyond = LiveSpeakerOrdinalTracker()
    for index in range(MAX_TRACKED_VOICES):
        beyond.observe(voice(f's{index}', index, 'scope:0', 0.0, 1.0))
    # The (MAX_TRACKED_VOICES + 1)-th distinct voice is dropped, never a crash.
    beyond.observe(voice('late', MAX_TRACKED_VOICES, 'scope:0', 0.0, 60.0))
    assert beyond.close() == (0, 0)


def test_record_observes_histogram_and_rotation_counter():
    before_observations = OMI_LIVE_SPEAKER_ORDINALS_PER_SESSION._sum.get()
    before_rotations = OMI_LIVE_SPEAKER_SCOPE_ROTATIONS_TOTAL._value.get()
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 6.0))
    tracker.observe(voice('s2', 1, 'scope:1', 8.0, 14.0))
    tracker.observe(voice('s3', 2, 'scope:2', 20.0, 26.0))
    record_live_speaker_ordinals(tracker, SimpleNamespace(speaker_to_person={}, _voice_scopes={}))
    assert OMI_LIVE_SPEAKER_ORDINALS_PER_SESSION._sum.get() == before_observations + 3
    assert OMI_LIVE_SPEAKER_SCOPE_ROTATIONS_TOTAL._value.get() == before_rotations + 2


def test_record_never_raises_and_close_resets_state():
    record_live_speaker_ordinals(None, None)
    record_live_speaker_ordinals(LiveSpeakerOrdinalTracker(), object())
    tracker = LiveSpeakerOrdinalTracker()
    tracker.observe(voice('s1', 0, 'scope:0', 0.0, 6.0))
    assert tracker.close() == (1, 0)
    assert tracker.close() == (0, 0)


async def test_speaker_detection_feeds_the_session_tracker():
    observed = []
    host = SimpleNamespace(
        limits=SimpleNamespace(max_segment_buffer_size=10, max_photo_buffer_size=10),
        translation_language=None,
        language='en',
        speakers=SimpleNamespace(
            observe_segment=lambda speaker_id, scope, segment_id: observed.append((speaker_id, scope, segment_id)),
            person_embeddings={},
            speaker_to_person={},
        ),
        state=SimpleNamespace(speaker_id_enabled=False, current_conversation_id='c1'),
        speaker_ordinal_tracker=LiveSpeakerOrdinalTracker(),
    )
    processor = TranscriptProcessor(host)
    segments = [
        TranscriptSegment(
            id='s1',
            text='Testing one two',
            speaker_id=0,
            speaker_id_scope='scope:0',
            start=0.0,
            end=6.0,
            is_user=False,
            speech_profile_processed=True,
        ),
        TranscriptSegment(
            id='s2',
            text='Testing three four',
            speaker_id=1,
            speaker_id_scope='scope:0',
            start=6.0,
            end=8.0,
            is_user=False,
            speech_profile_processed=True,
        ),
    ]
    await processor._speaker_detection(segments, 0.0)
    assert observed == [(0, 'scope:0', 's1'), (1, 'scope:0', 's2')]
    # One qualified voice plus one still below the deferral floor, one scope.
    assert host.speaker_ordinal_tracker.close() == (1, 0)

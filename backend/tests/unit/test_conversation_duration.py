"""Unit vectors for the shared conversation-duration rule.

`utils.conversations.duration` is the single place that answers "how long was
this conversation". `started_at` is the live-socket streaming-session origin, so
`finished_at - started_at` over-counts by however long the socket had already
been open (#4056); the answer is the transcript span, and the wall window is
only for transcript-free records.

The cross-platform agreement vectors live in
`contracts/parity/conversation_duration.json` and run in
`test_parity_contracts.py`. This module owns the malformed-input handling that
is deliberately outside that fixture (see its Divergence register entry 6).
"""

from datetime import datetime, timedelta, timezone

from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.duration import conversation_duration_seconds, transcript_span_seconds

START = datetime(2026, 9, 7, 23, 32, 33, tzinfo=timezone.utc)


def _segment(text: str, start: float, end: float) -> TranscriptSegment:
    return TranscriptSegment(
        id=f'seg-{start}-{end}',
        text=text,
        speaker='SPEAKER_00',
        speaker_id=0,
        is_user=True,
        start=start,
        end=end,
    )


def _conversation(segments=None, *, started_at=START, finished_at=None) -> Conversation:
    return Conversation(
        id='conv-duration',
        created_at=started_at or START,
        started_at=started_at,
        finished_at=finished_at,
        structured=Structured(),
        transcript_segments=segments or [],
    )


class TestTranscriptSpan:
    def test_span_is_the_maximum_end_not_the_last_segment(self):
        conversation = _conversation(
            [_segment('later half', 8.0, 27.0), _segment('first half', 0.0, 8.0)],
            finished_at=START + timedelta(minutes=42),
        )

        assert conversation_duration_seconds(conversation) == 27.0

    def test_empty_text_segments_do_not_extend_the_span(self):
        conversation = _conversation(
            [_segment('the only speech', 0.0, 8.0), _segment('   ', 0.0, 2565.0)],
            finished_at=START + timedelta(minutes=42),
        )

        assert conversation_duration_seconds(conversation) == 8.0

    def test_reversed_and_non_finite_intervals_are_ignored(self):
        conversation = _conversation(
            [
                _segment('good', 0.0, 8.0),
                _segment('reversed', 3000.0, 12.0),
                _segment('infinite', 0.0, float('inf')),
                _segment('nan', float('nan'), float('nan')),
            ],
            finished_at=START + timedelta(minutes=42),
        )

        assert conversation_duration_seconds(conversation) == 8.0

    def test_a_negative_interval_clamps_to_zero_rather_than_going_backwards(self):
        conversation = _conversation([_segment('before the origin', -9.0, -4.0)])

        assert conversation_duration_seconds(conversation) == 0.0

    def test_a_zero_length_span_is_zero_not_the_wall_window(self):
        """0.0 means "the transcript says zero seconds"; only None falls back."""
        conversation = _conversation([_segment('hm', 0.0, 0.0)], finished_at=START + timedelta(minutes=42))

        assert conversation_duration_seconds(conversation) == 0.0

    def test_dict_segments_are_read_the_same_way_as_models(self):
        assert transcript_span_seconds([{'text': 'hello', 'start': 0, 'end': 8}]) == 8.0

    def test_non_numeric_segment_bounds_are_ignored(self):
        assert transcript_span_seconds([{'text': 'hello', 'start': 'x', 'end': 'y'}]) is None


class TestWallWindowFallback:
    def test_a_transcript_free_record_uses_the_wall_window(self):
        """Photo-only captures carry no transcript; the window is all they have."""
        conversation = _conversation(finished_at=START + timedelta(seconds=45))

        assert conversation_duration_seconds(conversation) == 45.0

    def test_a_reversed_wall_window_clamps_to_zero(self):
        conversation = _conversation(started_at=START, finished_at=START - timedelta(seconds=45))

        assert conversation_duration_seconds(conversation) == 0.0

    def test_missing_timestamps_are_unknowable(self):
        assert conversation_duration_seconds(_conversation(started_at=None)) is None
        assert conversation_duration_seconds(_conversation(finished_at=None)) is None

    def test_segments_that_all_fail_validation_fall_back_and_record_a_fallback(self, monkeypatch):
        """Wall duration is a degraded input here, so ops must see it."""
        import utils.conversations.duration as duration_module

        recorded = []
        monkeypatch.setattr(duration_module, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

        conversation = _conversation(
            [_segment('', 0.0, 8.0)],
            finished_at=START + timedelta(seconds=90),
        )

        assert conversation_duration_seconds(conversation) == 90.0
        assert len(recorded) == 1
        assert recorded[0]['component'] == 'conversation_finalization'
        assert recorded[0]['from_mode'] == 'transcript_span'
        assert recorded[0]['to_mode'] == 'wall_clock'
        assert recorded[0]['outcome'] == 'degraded'

    def test_no_fallback_is_recorded_for_a_record_that_never_had_a_transcript(self, monkeypatch):
        import utils.conversations.duration as duration_module

        recorded = []
        monkeypatch.setattr(duration_module, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

        assert conversation_duration_seconds(_conversation(finished_at=START + timedelta(seconds=45))) == 45.0
        assert recorded == []

    def test_an_unmeasurable_record_with_segments_reports_an_exhausted_fallback(self, monkeypatch):
        import utils.conversations.duration as duration_module

        recorded = []
        monkeypatch.setattr(duration_module, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

        assert conversation_duration_seconds(_conversation([_segment('', 0.0, 8.0)], started_at=None)) is None
        assert recorded[0]['outcome'] == 'exhausted'

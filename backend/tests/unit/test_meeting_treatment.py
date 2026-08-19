from datetime import datetime, timedelta, timezone

from utils.conversations.meeting_treatment import (
    MIN_MEETING_DURATION_SECONDS,
    MIN_TRANSCRIBED_SPEECH_SECONDS,
    deduplicated_transcribed_speech_seconds,
    is_meeting_treatment_eligible,
)

NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


def _meeting(*, duration_seconds: int, segments: list[dict]) -> dict:
    return {
        'source': 'desktop',
        'discarded': False,
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=duration_seconds),
        'external_data': {'conversation_role': 'meeting'},
        'transcript_segments': segments,
    }


def test_call_under_five_minutes_is_ineligible():
    conversation = _meeting(
        duration_seconds=MIN_MEETING_DURATION_SECONDS - 1,
        segments=[{'text': 'continuous discussion', 'start': 0, 'end': MIN_TRANSCRIBED_SPEECH_SECONDS}],
    )

    assert is_meeting_treatment_eligible(conversation) is False


def test_call_over_five_minutes_with_enough_speech_is_eligible():
    conversation = _meeting(
        duration_seconds=MIN_MEETING_DURATION_SECONDS + 60,
        segments=[
            {'text': 'first exchange', 'start': 0, 'end': 35},
            {'text': 'second exchange', 'start': 45, 'end': 70},
        ],
    )

    assert is_meeting_treatment_eligible(conversation) is True


def test_long_mostly_silent_call_is_ineligible():
    conversation = _meeting(
        duration_seconds=20 * 60,
        segments=[
            {
                'text': 'brief accidental transcription',
                'start': 300,
                'end': 300 + MIN_TRANSCRIBED_SPEECH_SECONDS - 1,
            }
        ],
    )

    assert is_meeting_treatment_eligible(conversation) is False


def test_overlapping_duplicate_stream_segments_are_counted_once():
    segments = [
        {'text': 'remote party through microphone', 'start': 0, 'end': 45},
        {'text': 'remote party through system audio', 'start': 0, 'end': 45},
        {'text': 'partially overlapping continuation', 'start': 35, 'end': 60},
    ]

    assert deduplicated_transcribed_speech_seconds(segments) == 60
    assert is_meeting_treatment_eligible(_meeting(duration_seconds=10 * 60, segments=segments)) is True

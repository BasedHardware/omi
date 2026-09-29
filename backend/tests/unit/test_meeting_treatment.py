from datetime import datetime, timedelta, timezone

import pytest

from utils.conversations.meeting_treatment import (
    MIN_MEETING_DURATION_SECONDS,
    MIN_TRANSCRIBED_SPEECH_SECONDS,
    deduplicated_transcribed_speech_seconds,
    is_meeting_treatment_eligible,
    meeting_treatment_verdict,
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
            {'text': 'second exchange', 'start': 335, 'end': 360},
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
        {'text': 'remote party through microphone', 'start': 0, 'end': 35},
        {'text': 'remote party through system audio', 'start': 0, 'end': 35},
        {'text': 'partially overlapping continuation', 'start': 25, 'end': 45},
        {'text': 'closing discussion', 'start': 585, 'end': 600},
    ]

    assert deduplicated_transcribed_speech_seconds(segments) == 60

    # Duration is the transcript span (#19391), so the eligible-meeting fixture
    # needs duplicate streams whose span also clears the five-minute bar.
    meeting_segments = [
        {'text': 'remote party through microphone', 'start': 240, 'end': 270},
        {'text': 'remote party through system audio', 'start': 240, 'end': 270},
        {'text': 'partially overlapping continuation', 'start': 255, 'end': 300},
    ]
    assert deduplicated_transcribed_speech_seconds(meeting_segments) == 60
    assert is_meeting_treatment_eligible(_meeting(duration_seconds=10 * 60, segments=meeting_segments)) is True


@pytest.mark.parametrize(
    ('updates', 'reason', 'eligible'),
    [
        ({}, 'eligible', True),
        # Duration is the transcript span (#19391): a short span, not a short
        # wall window, is what makes a meeting too short.
        ({'transcript_segments': [{'text': 'measured discussion', 'start': 0, 'end': 299}]}, 'too_short', False),
        # Span clears the five-minute bar while the deduplicated speech does not.
        ({'transcript_segments': [{'text': 'brief', 'start': 271, 'end': 300}]}, 'insufficient_speech', False),
        (
            {
                'transcript_segments': [
                    {'text': 'opening', 'start': 0, 'end': 30},
                    {'text': 'closing', 'start': 1690.8, 'end': 1719.8},
                ]
            },
            'insufficient_speech',
            False,
        ),
        (
            {
                'external_data': {
                    'conversation_role': 'meeting',
                    'conversation_finalization_reason': 'max_duration_rotation',
                }
            },
            'rotation',
            False,
        ),
        ({'discarded': True}, 'discarded', False),
        ({'source': 'omi'}, 'not_desktop_meeting', False),
    ],
)
def test_verdict_records_reason_and_measured_inputs_for_every_policy_branch(updates, reason, eligible):
    conversation = _meeting(
        duration_seconds=1720,
        segments=[{'text': 'measured discussion', 'start': 0, 'end': 1720}],
    )
    conversation.update(updates)

    verdict = meeting_treatment_verdict(conversation)

    assert verdict.eligible is eligible
    assert verdict.reason == reason
    expected_duration = max((segment['end'] for segment in conversation['transcript_segments']), default=1720)
    expected_speech = deduplicated_transcribed_speech_seconds(conversation['transcript_segments'])
    assert verdict.duration_s == pytest.approx(expected_duration)
    assert verdict.dedup_speech_s == pytest.approx(expected_speech)


def test_wall_duration_is_used_when_transcript_is_empty():
    conversation = _meeting(duration_seconds=20 * 60, segments=[])

    verdict = meeting_treatment_verdict(conversation)

    assert verdict.duration_s == 20 * 60
    assert verdict.dedup_speech_s == 0

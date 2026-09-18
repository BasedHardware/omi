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


@pytest.mark.parametrize(
    ('updates', 'reason', 'eligible'),
    [
        ({}, 'eligible', True),
        ({'finished_at': NOW + timedelta(seconds=299)}, 'too_short', False),
        ({'transcript_segments': [{'text': 'brief', 'start': 0, 'end': 59}]}, 'insufficient_speech', False),
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
        segments=[{'text': 'measured discussion', 'start': 0, 'end': 1719.8}],
    )
    conversation.update(updates)

    verdict = meeting_treatment_verdict(conversation)

    assert verdict.eligible is eligible
    assert verdict.reason == reason
    assert verdict.duration_s == (299 if reason == 'too_short' else 1720)
    assert verdict.dedup_speech_s == (59 if reason == 'insufficient_speech' else 1719.8)

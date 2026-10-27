"""Bound calendar silence extensions and prefer the stored event's scheduled end."""

from datetime import datetime, timedelta, timezone

import pytest

from models.conversation_continuity import calendar_continuity_identity, continuation_timeout, resumable_continuation
from utils.transcribe_decisions import MAX_CONVERSATION_TIMEOUT_SECONDS


def meeting_row(**context):
    now = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
    return {
        'status': 'in_progress',
        'source': 'omi',
        'client_device_id': 'phone',
        'has_content': True,
        'finished_at': now,
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'event-1',
                'start_time': now,
                **context,
            }
        },
    }


@pytest.mark.parametrize('duration', [10**9, 10**100, 1e300])
def test_oversized_duration_is_capped_at_four_hours(duration):
    row = meeting_row(duration_minutes=duration)
    assert continuation_timeout(row) == MAX_CONVERSATION_TIMEOUT_SECONDS == 14400
    assert resumable_continuation(
        row,
        source='omi',
        device_id='phone',
        now=row['finished_at'] + timedelta(seconds=14399),
        timeout=120,
    )
    assert not resumable_continuation(
        row,
        source='omi',
        device_id='phone',
        now=row['finished_at'] + timedelta(seconds=14400),
        timeout=120,
    )


@pytest.mark.parametrize('duration', [5, 10**9, None])
def test_scheduled_end_wins_over_duration(duration):
    row = meeting_row(duration_minutes=duration, end_time='2026-10-07T11:00:00Z')
    assert continuation_timeout(row) == 3720
    assert calendar_continuity_identity(row) is None
    assert not resumable_continuation(
        row,
        source='omi',
        device_id='phone',
        now=row['finished_at'] + timedelta(seconds=3720),
        timeout=120,
    )


@pytest.mark.parametrize('duration', [True, -1, float('nan'), float('inf')])
def test_invalid_duration_keeps_the_default_boundary(duration):
    assert continuation_timeout(meeting_row(duration_minutes=duration)) == 120


def overrun_row(seconds_after_end):
    """A 10:00-10:30 meeting whose latest speech is relative to its scheduled end."""
    row = meeting_row(end_time='2026-10-07T10:30:00Z')
    row['finished_at'] = datetime(2026, 10, 7, 10, 30, tzinfo=timezone.utc) + timedelta(seconds=seconds_after_end)
    return row


@pytest.mark.parametrize(
    'timeout,seconds_after_end,expected',
    [
        # Well before the end, the window still extends the deadline.
        (120, -1800, 1920),
        (600, -1800, 1920),
        # Speech after the scheduled end keeps the ordinary deadline.
        (120, 60, 120),
        (120, 110, 120),
        (120, 119, 120),
        # A longer user setting is never cut down to the meeting window.
        (600, -60, 600),
        (1800, -600, 1800),
        (MAX_CONVERSATION_TIMEOUT_SECONDS, -1800, MAX_CONVERSATION_TIMEOUT_SECONDS),
    ],
)
def test_meeting_window_never_shortens_the_silence_deadline(timeout, seconds_after_end, expected):
    assert continuation_timeout(overrun_row(seconds_after_end), timeout) == expected


def test_reconnect_after_the_scheduled_end_keeps_the_ordinary_deadline():
    row = overrun_row(110)
    assert resumable_continuation(
        row,
        source='omi',
        device_id='phone',
        now=row['finished_at'] + timedelta(seconds=119),
        timeout=120,
    )
    assert not resumable_continuation(
        row,
        source='omi',
        device_id='phone',
        now=row['finished_at'] + timedelta(seconds=120),
        timeout=120,
    )

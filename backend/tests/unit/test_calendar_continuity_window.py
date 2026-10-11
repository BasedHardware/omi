"""Bound calendar silence extensions and prefer the stored event's scheduled end."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.conversation_continuity import calendar_continuity_identity, continuation_timeout, resumable_continuation
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

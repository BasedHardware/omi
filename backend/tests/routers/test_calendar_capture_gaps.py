"""GET /v1/calendar/capture-gaps — booked meetings with no recorded conversation (SCA-381).

The pure filtering rules live in ``select_capture_gaps`` and are covered by
``tests/unit/test_calendar_linking_overlap_selection.py``. These tests exercise
the route handler itself: window validation, the Firestore/Firestore-adjacent
reads it makes (with their bounds), and that a disconnected calendar surfaces
the same 400 the event picker uses. No network: the Google fetch and the
conversation read are patched at module scope.

``routers.google_calendar`` imports cleanly with the test env vars set (same
pattern as ``test_calendar_onboarding.py``).
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFgX7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import routers.google_calendar as gc

WINDOW_START = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 8, 18, 23, 0, tzinfo=timezone.utc)


def _event(
    start: datetime, end: datetime, *, event_id: str, status: str = 'confirmed', self_response: str = 'accepted'
) -> dict:
    return {
        'id': event_id,
        'summary': f'Event {event_id}',
        'status': status,
        'start': {'dateTime': start.isoformat()},
        'end': {'dateTime': end.isoformat()},
        'attendees': [{'self': True, 'responseStatus': self_response, 'email': 'me@example.com'}],
    }


def _conversation(start: datetime, end: datetime, *, discarded: bool = False) -> dict:
    return {'id': f'conv-{start.isoformat()}', 'started_at': start, 'finished_at': end, 'discarded': discarded}


def _run_gaps(events, conversations):
    with (
        patch.object(gc, '_get_google_calendar_token', MagicMock(return_value=('token', {'connected': True}))),
        patch.object(gc, 'get_google_calendar_events', AsyncMock(return_value=events)) as fetch,
        patch.object(
            gc.conversations_db,
            'get_conversations',
            MagicMock(return_value=list(conversations)),
        ) as conversations_read,
    ):
        rows = asyncio.run(gc.get_calendar_capture_gaps(start=WINDOW_START, end=WINDOW_END, uid='uid-1'))
    return rows, fetch, conversations_read


def test_uncovered_event_is_returned_with_not_captured_coverage():
    events = [
        _event(WINDOW_START + timedelta(hours=1), WINDOW_START + timedelta(hours=1, minutes=30), event_id='evt-open'),
    ]

    rows, _, _ = _run_gaps(events, [])

    assert len(rows) == 1
    row = rows[0].model_dump()
    assert row['event_id'] == 'evt-open'
    assert row['title'] == 'Event evt-open'
    assert row['start_time'] == WINDOW_START + timedelta(hours=1)
    assert row['end_time'] == WINDOW_START + timedelta(hours=1, minutes=30)
    assert row['status'] == 'confirmed'
    assert row['coverage'] == 'not_captured'


def test_event_covered_by_a_kept_conversation_is_not_a_gap_and_never_mints_one():
    covered = _event(
        WINDOW_START + timedelta(hours=1), WINDOW_START + timedelta(hours=1, minutes=30), event_id='evt-covered'
    )

    rows, _, _ = _run_gaps(
        [covered],
        [_conversation(WINDOW_START + timedelta(hours=1, minutes=10), WINDOW_START + timedelta(hours=1, minutes=12))],
    )

    assert rows == []


def test_discarded_conversation_does_not_cover_an_event():
    event = _event(
        WINDOW_START + timedelta(hours=1), WINDOW_START + timedelta(hours=1, minutes=30), event_id='evt-after-scrap'
    )

    rows, _, _ = _run_gaps(
        [event],
        [
            _conversation(
                WINDOW_START + timedelta(hours=1, minutes=10),
                WINDOW_START + timedelta(hours=1, minutes=12),
                discarded=True,
            )
        ],
    )

    assert [row.event_id for row in rows] == ['evt-after-scrap']


def test_the_conversation_read_is_bounded_and_unindexed():
    """include_discarded=True keeps the read a single-field range (no composite index);
    the window is padded one day so an edge event's earlier conversation still counts."""
    events = [
        _event(WINDOW_START + timedelta(hours=1), WINDOW_START + timedelta(hours=1, minutes=30), event_id='evt-open'),
    ]

    _, _, conversations_read = _run_gaps(events, [])

    assert conversations_read.call_count == 1
    kwargs = conversations_read.call_args.kwargs
    assert kwargs['include_discarded'] is True
    assert kwargs['date_field'] == 'started_at'
    assert kwargs['start_date'] == WINDOW_START - gc.CAPTURE_GAPS_CONVERSATION_PAD
    assert kwargs['end_date'] == WINDOW_END
    assert kwargs['limit'] == gc.CAPTURE_GAPS_MAX_CONVERSATIONS


def test_inverted_window_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(gc.get_calendar_capture_gaps(start=WINDOW_END, end=WINDOW_START, uid='uid-1'))

    assert exc_info.value.status_code == 400


def test_oversized_window_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gc.get_calendar_capture_gaps(
                start=WINDOW_START,
                end=WINDOW_START + timedelta(days=32),
                uid='uid-1',
            )
        )

    assert exc_info.value.status_code == 400


def test_disconnected_calendar_is_a_400_before_any_conversation_read():
    with (
        patch.object(
            gc,
            '_get_google_calendar_token',
            MagicMock(side_effect=HTTPException(status_code=400, detail='Google Calendar not connected')),
        ),
        patch.object(gc.conversations_db, 'get_conversations', MagicMock()) as conversations_read,
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(gc.get_calendar_capture_gaps(start=WINDOW_START, end=WINDOW_END, uid='uid-1'))

    assert exc_info.value.status_code == 400
    conversations_read.assert_not_called()


def test_naive_datetimes_are_treated_as_utc():
    events = [
        _event(WINDOW_START + timedelta(hours=1), WINDOW_START + timedelta(hours=1, minutes=30), event_id='evt-open'),
    ]

    rows, fetch, _ = _run_gaps(events, [])

    assert len(rows) == 1
    fetch_kwargs = fetch.await_args.kwargs
    assert fetch_kwargs['time_min'].tzinfo is not None
    assert fetch_kwargs['time_max'].tzinfo is not None

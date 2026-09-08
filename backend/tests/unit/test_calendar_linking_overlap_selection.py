"""Pure overlap-selection rules for calendar <-> conversation matching.

``get_overlapping_calendar_event`` is async and provider-backed, but the matching
rules it applies are load-bearing for two production decisions — auto-linking and
the discard override (SCA-381: calendar overlap outranks discard) — plus the
capture-gap surface (accepted events with no overlapping kept conversation). The
rules live in pure functions so they are testable without Google.

``utils.conversations.calendar_linking`` is loaded through the sanctioned
``stub_modules`` + ``load_module_fresh`` seam (see ``backend/docs/test_isolation.md``)
with its provider/db dependencies stubbed; ``utils.conversations.calendar_utils``
and ``models.conversation`` stay real because the pure rules use them.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFgX7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

cl = None

_STUBBED = [
    'database.users',
    'utils.retrieval.tools.calendar_tools',
    'utils.retrieval.tools.google_utils',
    'utils.executors',
    'utils.integration_telemetry',
    'utils.share_links',
]


@pytest.fixture(scope='module', autouse=True)
def _loaded_calendar_linking():
    global cl
    import sys

    fakes: dict[str, ModuleType] = {name: AutoMockModule(name) for name in _STUBBED}
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.conversations.calendar_linking',
            str(BACKEND_DIR / 'utils' / 'conversations' / 'calendar_linking.py'),
        )
        cl = module
        try:
            yield module
        finally:
            cl = None
            sys.modules.pop('utils.conversations.calendar_linking', None)


WINDOW_START = datetime(2026, 8, 18, 19, 30, tzinfo=timezone.utc)


def _event(
    start: datetime,
    end: datetime,
    *,
    event_id: str = 'evt-1',
    status: str = 'confirmed',
    self_response: str = 'accepted',
    title: str = 'Scaling Forever sync',
) -> dict:
    return {
        'id': event_id,
        'summary': title,
        'status': status,
        'start': {'dateTime': start.isoformat()},
        'end': {'dateTime': end.isoformat()},
        'attendees': [
            {'self': True, 'responseStatus': self_response, 'email': 'me@example.com'},
            {'self': False, 'responseStatus': 'declined', 'email': 'someone-else@example.com'},
        ],
        'htmlLink': f'https://calendar.google.com/x/{event_id}',
    }


class TestAttendanceExclusion:
    def test_cancelled_event_is_excluded(self):
        assert cl.event_attendance_excluded(
            _event(WINDOW_START, WINDOW_START + timedelta(minutes=30), status='cancelled')
        )

    def test_self_declined_event_is_excluded(self):
        assert cl.event_attendance_excluded(
            _event(WINDOW_START, WINDOW_START + timedelta(minutes=30), self_response='declined')
        )

    def test_accepted_tentative_and_needs_action_are_not_excluded(self):
        for response in ('accepted', 'tentative', 'needsAction'):
            event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30), self_response=response)
            assert not cl.event_attendance_excluded(event), response

    def test_another_attendee_declining_does_not_exclude_the_event(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))
        # only the non-self attendee declined
        assert not cl.event_attendance_excluded(event)


class TestSelectOverlappingCalendarEvent:
    def test_short_clip_wholly_inside_a_long_event_matches(self):
        """The SCA-381 case: a 25s scrap inside a 30m accepted meeting.

        The conversation covers itself (100% of the conversation overlaps), which
        is the OR arm that must stay (product decision; do not relitigate).
        """
        conversation_start = WINDOW_START + timedelta(minutes=5)
        conversation_end = conversation_start + timedelta(seconds=25)
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))

        assert (
            cl.select_overlapping_calendar_event([event], conversation_start, conversation_end, require_accepted=True)
            is event
        )

    def test_sub_threshold_overlap_is_rejected(self):
        conversation_start = WINDOW_START + timedelta(minutes=5)
        conversation_end = conversation_start + timedelta(seconds=9)
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))

        assert (
            cl.select_overlapping_calendar_event([event], conversation_start, conversation_end, require_accepted=True)
            is None
        )

    def test_partial_overlap_of_both_sides_is_rejected(self):
        """10m shared between a 30m event and a 30m conversation: neither arm reaches 50%."""
        conversation_start = WINDOW_START - timedelta(minutes=20)
        conversation_end = WINDOW_START + timedelta(minutes=10)
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))

        assert (
            cl.select_overlapping_calendar_event([event], conversation_start, conversation_end, require_accepted=True)
            is None
        )

    def test_require_accepted_skips_declined_and_cancelled_events(self):
        conversation_start = WINDOW_START + timedelta(minutes=5)
        conversation_end = conversation_start + timedelta(seconds=25)
        declined = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-declined',
            self_response='declined',
        )
        cancelled = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-cancelled',
            status='cancelled',
        )

        assert (
            cl.select_overlapping_calendar_event(
                [declined, cancelled], conversation_start, conversation_end, require_accepted=True
            )
            is None
        )

    def test_without_require_accepted_linking_keeps_its_current_behavior(self):
        """The auto-link path must not change: declined events still link there."""
        conversation_start = WINDOW_START + timedelta(minutes=5)
        conversation_end = conversation_start + timedelta(seconds=25)
        declined = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-declined',
            self_response='declined',
        )

        assert cl.select_overlapping_calendar_event([declined], conversation_start, conversation_end) is declined

    def test_longest_overlap_wins(self):
        conversation_start = WINDOW_START
        conversation_end = conversation_start + timedelta(minutes=30)
        shorter = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=10),
            event_id='evt-short',
        )
        longer = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=25),
            event_id='evt-long',
        )

        assert (
            cl.select_overlapping_calendar_event(
                [shorter, longer], conversation_start, conversation_end, require_accepted=True
            )
            is longer
        )


class TestSelectCaptureGaps:
    def _conversations(self, *rows: tuple[datetime, datetime, bool]) -> list[dict]:
        return [
            {'id': f'conv-{index}', 'started_at': start, 'finished_at': end, 'discarded': discarded}
            for index, (start, end, discarded) in enumerate(rows)
        ]

    def test_accepted_event_without_overlapping_conversation_is_a_gap(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))

        rows = cl.select_capture_gaps([event], self._conversations())

        assert rows == [
            {
                'event_id': 'evt-1',
                'title': 'Scaling Forever sync',
                'start_time': WINDOW_START,
                'end_time': WINDOW_START + timedelta(minutes=30),
                'status': 'confirmed',
                'coverage': 'not_captured',
            }
        ]

    def test_event_overlapped_by_a_kept_conversation_is_covered(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))
        conversation = (
            WINDOW_START + timedelta(minutes=10),
            WINDOW_START + timedelta(minutes=12),
            False,
        )

        assert cl.select_capture_gaps([event], self._conversations(conversation)) == []

    def test_only_a_discarded_conversation_overlapping_still_leaves_a_gap(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))
        conversation = (
            WINDOW_START + timedelta(minutes=10),
            WINDOW_START + timedelta(minutes=12),
            True,
        )

        rows = cl.select_capture_gaps([event], self._conversations(conversation))
        assert [row['event_id'] for row in rows] == ['evt-1']

    def test_sub_threshold_overlap_does_not_count_as_coverage(self):
        """A 9s blip is not capture — the same 10s floor the linker applies."""
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))
        conversation = (
            WINDOW_START + timedelta(minutes=10),
            WINDOW_START + timedelta(minutes=10, seconds=9),
            False,
        )

        rows = cl.select_capture_gaps([event], self._conversations(conversation))
        assert [row['event_id'] for row in rows] == ['evt-1']

    def test_declined_cancelled_tentative_and_allday_events_are_skipped(self):
        declined = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-declined',
            self_response='declined',
        )
        cancelled = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-cancelled',
            status='cancelled',
        )
        tentative = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            event_id='evt-tentative',
            status='tentative',
        )
        all_day = {
            'id': 'evt-allday',
            'summary': 'Travel day',
            'status': 'confirmed',
            'start': {'date': '2026-08-18'},
            'end': {'date': '2026-08-19'},
        }
        overlong = _event(
            WINDOW_START,
            WINDOW_START + timedelta(hours=9),
            event_id='evt-overlong',
        )

        assert cl.select_capture_gaps([declined, cancelled, tentative, all_day, overlong], []) == []

    def test_rows_never_fabricate_conversations(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))

        rows = cl.select_capture_gaps([event], [])

        assert rows[0]['coverage'] == 'not_captured'
        assert set(rows[0]) == {
            'event_id',
            'title',
            'start_time',
            'end_time',
            'status',
            'coverage',
        }


class TestGetOverlappingCalendarEventWiring:
    def setup_method(self):
        # Import-time names bound from the stub modules; swap per-test and
        # restore afterwards so module-scoped state never leaks across tests.
        self._originals = (
            cl.users_db,
            cl.run_blocking,
            cl.get_google_calendar_events,
        )
        self._original_integration = cl.users_db.get_integration

    def teardown_method(self):
        cl.users_db, cl.run_blocking, cl.get_google_calendar_events = self._originals
        cl.users_db.get_integration = self._original_integration

    def _patched_provider(self, events: list[dict]) -> AsyncMock:
        cl.users_db.get_integration = MagicMock(return_value={'connected': True, 'access_token': 'token'})

        async def _run_blocking(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        cl.run_blocking = _run_blocking
        cl.get_google_calendar_events = AsyncMock(return_value=events)
        return cl.get_google_calendar_events

    def test_accepted_event_returns_a_link_with_require_accepted(self):
        event = _event(WINDOW_START, WINDOW_START + timedelta(minutes=30))
        self._patched_provider([event])

        link = asyncio.run(
            cl.get_overlapping_calendar_event(
                'uid-1',
                WINDOW_START + timedelta(minutes=5),
                WINDOW_START + timedelta(minutes=5, seconds=25),
                require_accepted=True,
            )
        )

        assert link is not None
        assert link.event_id == 'evt-1'

    def test_declined_only_events_return_none_with_require_accepted(self):
        event = _event(
            WINDOW_START,
            WINDOW_START + timedelta(minutes=30),
            self_response='declined',
        )
        fetch = self._patched_provider([event])

        link = asyncio.run(
            cl.get_overlapping_calendar_event(
                'uid-1',
                WINDOW_START + timedelta(minutes=5),
                WINDOW_START + timedelta(minutes=5, seconds=25),
                require_accepted=True,
            )
        )

        assert link is None
        assert fetch.await_count == 1

    def test_disconnected_calendar_returns_none_without_provider_traffic(self):
        fetch = self._patched_provider([])
        cl.users_db.get_integration = MagicMock(return_value=None)

        link = asyncio.run(
            cl.get_overlapping_calendar_event(
                'uid-1',
                WINDOW_START + timedelta(minutes=5),
                WINDOW_START + timedelta(minutes=5, seconds=25),
                require_accepted=True,
            )
        )

        assert link is None
        fetch.assert_not_called()

    def test_provider_failure_fails_open_to_none(self):
        self._patched_provider([])
        cl.get_google_calendar_events = AsyncMock(side_effect=RuntimeError('google down'))

        link = asyncio.run(
            cl.get_overlapping_calendar_event(
                'uid-1',
                WINDOW_START + timedelta(minutes=5),
                WINDOW_START + timedelta(minutes=5, seconds=25),
                require_accepted=True,
            )
        )

        assert link is None

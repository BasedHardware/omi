"""Meeting-identity resolution before summarization.

Regression cover for a real desktop conversation that was tagged
``external_data.conversation_role == "meeting"`` yet reached the summarization
prompt with ``Speaker 0:`` / ``Speaker 1:`` labels: no ``calendar_event``, no
``calendar_meeting_context``, and every segment's ``person_id`` null.

The pre-summarization lookup only consulted ``redis_db.get_conversation_meeting_id``,
a mapping written in exactly one place (desktop conversation creation, when a
stored meeting already overlaps that instant). When it is absent there was no
second chance. These tests pin the time-overlap fallback, the source ordering,
and the requirement that every layer degrade to no context rather than raise.
"""

from datetime import datetime, timedelta, timezone

import pytest

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from utils.conversations.meeting_context import (
    MIN_OVERLAP_PERCENTAGE,
    MIN_OVERLAP_SECONDS,
    context_from_screen_activity,
    resolve_meeting_context,
    select_overlapping_meeting,
    stored_meeting_window,
)

# The real failing conversation's window: 2026-08-18 19:29-19:58 UTC.
CONVERSATION_START = datetime(2026, 8, 18, 19, 29, tzinfo=timezone.utc)
CONVERSATION_END = datetime(2026, 8, 18, 19, 58, tzinfo=timezone.utc)


def _record(
    event_id: str,
    start: datetime,
    end: datetime,
    *,
    title: str = 'Scaling Forever sync',
    with_end_time: bool = True,
    participants: list[dict[str, str]] | None = None,
) -> dict:
    record = {
        'id': f'doc-{event_id}',
        'calendar_event_id': event_id,
        'title': title,
        'start_time': start,
        'duration_minutes': int((end - start).total_seconds() / 60),
        'participants': participants if participants is not None else [{'name': 'Ash'}],
        'calendar_source': 'macos_calendar',
        # Firestore records carry bookkeeping fields the model does not declare.
        'synced_at': start,
    }
    if with_end_time:
        record['end_time'] = end
    return record


def _context(event_id: str, *, names: list[str], source: str) -> CalendarMeetingContext:
    return CalendarMeetingContext(
        calendar_event_id=event_id,
        title=f'{source} title',
        participants=[MeetingParticipant(name=name) for name in names],
        start_time=CONVERSATION_START,
        duration_minutes=30,
        calendar_source=source,
    )


class TestStoredMeetingWindow:
    def test_uses_explicit_end_time(self):
        record = _record('a', CONVERSATION_START, CONVERSATION_END)
        assert stored_meeting_window(record) == (CONVERSATION_START, CONVERSATION_END)

    def test_derives_end_from_duration_when_end_time_absent(self):
        record = _record('a', CONVERSATION_START, CONVERSATION_END, with_end_time=False)
        assert stored_meeting_window(record) == (CONVERSATION_START, CONVERSATION_END)

    def test_naive_start_is_read_as_utc(self):
        record = _record('a', CONVERSATION_START, CONVERSATION_END, with_end_time=False)
        record['start_time'] = CONVERSATION_START.replace(tzinfo=None)
        assert stored_meeting_window(record) == (CONVERSATION_START, CONVERSATION_END)

    @pytest.mark.parametrize(
        'mutate',
        [
            lambda r: r.update(start_time=None),
            lambda r: r.update(start_time='2026-08-18T19:29:00Z'),
            lambda r: r.update(end_time=CONVERSATION_START),  # end <= start
        ],
    )
    def test_unusable_records_return_none(self, mutate):
        record = _record('a', CONVERSATION_START, CONVERSATION_END)
        mutate(record)
        assert stored_meeting_window(record) is None


class TestSelectOverlappingMeeting:
    def test_matches_the_conversation_window_that_actually_failed(self):
        # The invite ran 19:30-20:00; recording started a minute early and stopped early.
        invite = _record(
            'evt-scaling-forever',
            datetime(2026, 8, 18, 19, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
            participants=[{'name': 'David Zhang'}, {'name': 'Ash'}],
        )
        context = select_overlapping_meeting([invite], started_at=CONVERSATION_START, finished_at=CONVERSATION_END)
        assert context is not None
        assert context.calendar_event_id == 'evt-scaling-forever'
        assert [p.name for p in context.participants] == ['David Zhang', 'Ash']

    def test_picks_the_longest_overlap_among_candidates(self):
        near = _record(
            'short',
            CONVERSATION_START - timedelta(minutes=5),
            CONVERSATION_START + timedelta(minutes=4),
        )
        best = _record('long', CONVERSATION_START, CONVERSATION_END)
        assert (
            select_overlapping_meeting(
                [near, best], started_at=CONVERSATION_START, finished_at=CONVERSATION_END
            ).calendar_event_id
            == 'long'
        )

    def test_calendar_event_outranks_longer_screen_derived_overlap(self):
        screen = _record('screen', CONVERSATION_START, CONVERSATION_END)
        screen['calendar_source'] = 'screen_activity'
        calendar = _record(
            'calendar',
            CONVERSATION_START + timedelta(minutes=2),
            CONVERSATION_END - timedelta(minutes=2),
        )
        calendar['calendar_source'] = 'system_calendar'

        selected = select_overlapping_meeting(
            [screen, calendar], started_at=CONVERSATION_START, finished_at=CONVERSATION_END
        )
        assert selected is not None
        assert selected.calendar_event_id == 'calendar'
        assert selected.calendar_source == 'system_calendar'

    def test_an_all_day_block_matches_only_via_the_conversation_coverage_arm(self):
        # An 8h block covers far less than MIN_OVERLAP_PERCENTAGE of itself, so it fails
        # the meeting-coverage arm. A conversation wholly inside it still scores 100%
        # conversation coverage, which the shared rule accepts. Pinning the documented
        # behaviour rather than inventing a stricter one the Google path does not have.
        all_day = _record(
            'all-day',
            datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 18, 21, 0, tzinfo=timezone.utc),
        )
        short_start = datetime(2026, 8, 18, 19, 29, tzinfo=timezone.utc)
        short_end = short_start + timedelta(seconds=30)
        # Conversation is fully inside the block, so conversation-coverage is 100%:
        # the block IS a legitimate match by the shared rule. Assert the documented
        # behaviour rather than inventing a stricter one.
        assert (
            select_overlapping_meeting([all_day], started_at=short_start, finished_at=short_end).calendar_event_id
            == 'all-day'
        )

    def test_rejects_a_meeting_that_barely_grazes_the_window(self):
        grazing = _record(
            'grazing',
            CONVERSATION_START - timedelta(minutes=30),
            CONVERSATION_START + timedelta(seconds=MIN_OVERLAP_SECONDS - 1),
        )
        assert (
            select_overlapping_meeting([grazing], started_at=CONVERSATION_START, finished_at=CONVERSATION_END) is None
        )

    def test_rejects_partial_overlap_below_both_percentage_arms(self):
        # 4 minutes of overlap: 13% of a 30m meeting, 13% of a 29m conversation.
        partial = _record(
            'partial',
            CONVERSATION_START - timedelta(minutes=26),
            CONVERSATION_START + timedelta(minutes=4),
        )
        overlap_fraction = 4 / 30
        assert overlap_fraction < MIN_OVERLAP_PERCENTAGE
        assert (
            select_overlapping_meeting([partial], started_at=CONVERSATION_START, finished_at=CONVERSATION_END) is None
        )

    def test_no_records_and_no_qualifying_records_return_none(self):
        assert select_overlapping_meeting([], started_at=CONVERSATION_START, finished_at=CONVERSATION_END) is None
        disjoint = _record(
            'other-day',
            datetime(2026, 8, 17, 19, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc),
        )
        assert (
            select_overlapping_meeting([disjoint], started_at=CONVERSATION_START, finished_at=CONVERSATION_END) is None
        )

    def test_malformed_record_does_not_hide_a_good_one(self):
        malformed = {'calendar_event_id': 'broken', 'start_time': 'not-a-datetime'}
        good = _record('good', CONVERSATION_START, CONVERSATION_END)
        assert (
            select_overlapping_meeting(
                [malformed, good], started_at=CONVERSATION_START, finished_at=CONVERSATION_END
            ).calendar_event_id
            == 'good'
        )

    def test_degenerate_conversation_window_returns_none(self):
        record = _record('a', CONVERSATION_START, CONVERSATION_END)
        assert select_overlapping_meeting([record], started_at=CONVERSATION_END, finished_at=CONVERSATION_START) is None


class TestResolveMeetingContextOrdering:
    def test_stored_meeting_outranks_every_weaker_source(self):
        context = resolve_meeting_context(
            direct=_context('direct', names=['Direct Person'], source='client'),
            stored=lambda: _context('stored', names=['Ash'], source='macos_calendar'),
            calendar=lambda: _context('google', names=['Google Person'], source='google'),
            screen=lambda: _context('screen', names=['OCR Person'], source='screen_activity'),
        )
        assert context.calendar_event_id == 'stored'
        assert context.calendar_source == 'macos_calendar'
        # Weaker sources still contribute names the winner did not have.
        assert [p.name for p in context.participants] == [
            'Ash',
            'Direct Person',
            'Google Person',
            'OCR Person',
        ]

    def test_direct_wins_when_no_stored_meeting_exists(self):
        context = resolve_meeting_context(
            direct=_context('direct', names=['Direct Person'], source='client'),
            stored=lambda: None,
            calendar=lambda: _context('google', names=['Google Person'], source='google'),
        )
        assert context.calendar_event_id == 'direct'

    def test_google_wins_over_ocr_when_nothing_better_exists(self):
        context = resolve_meeting_context(
            direct=None,
            stored=lambda: None,
            calendar=lambda: _context('google', names=['Google Person'], source='google'),
            screen=lambda: _context('screen', names=['OCR Person'], source='screen_activity'),
        )
        assert context.calendar_event_id == 'google'
        assert [p.name for p in context.participants] == ['Google Person', 'OCR Person']

    def test_on_device_stored_identity_is_below_calendar_and_above_server_ocr(self):
        context = resolve_meeting_context(
            direct=None,
            stored=lambda: _context('device', names=['Device Person'], source='screen_activity'),
            calendar=lambda: _context('google', names=['Calendar Person'], source='google'),
            screen=lambda: _context('server-ocr', names=['Server OCR Person'], source='screen_activity'),
        )

        assert context.calendar_event_id == 'google'
        assert [p.name for p in context.participants] == [
            'Calendar Person',
            'Device Person',
            'Server OCR Person',
        ]

    def test_on_device_stored_identity_outranks_server_ocr_without_calendar(self):
        context = resolve_meeting_context(
            direct=None,
            stored=lambda: _context('device', names=['Device Person'], source='screen_activity'),
            calendar=lambda: None,
            screen=lambda: _context('server-ocr', names=['Server OCR Person'], source='screen_activity'),
        )

        assert context.calendar_event_id == 'device'
        assert [p.name for p in context.participants] == ['Device Person', 'Server OCR Person']

    def test_ocr_is_used_only_as_a_last_resort(self):
        context = resolve_meeting_context(
            direct=None,
            stored=lambda: None,
            calendar=lambda: None,
            screen=lambda: _context('screen', names=['OCR Person'], source='screen_activity'),
        )
        assert context.calendar_source == 'screen_activity'

    def test_a_disabled_layer_is_never_called(self):
        calls: list[str] = []

        def _tracked(name):
            def supplier():
                calls.append(name)
                return None

            return supplier

        resolve_meeting_context(direct=None, stored=_tracked('stored'), calendar=None, screen=None)
        assert calls == ['stored']


class TestResolveMeetingContextDegradation:
    def test_every_source_absent_yields_no_context(self):
        assert resolve_meeting_context(direct=None) is None
        assert (
            resolve_meeting_context(direct=None, stored=lambda: None, calendar=lambda: None, screen=lambda: None)
            is None
        )

    def test_a_raising_source_is_reported_and_skipped(self):
        errors: list[str] = []

        def _boom():
            raise RuntimeError('firestore unavailable')

        context = resolve_meeting_context(
            direct=None,
            stored=_boom,
            calendar=lambda: _context('google', names=['Google Person'], source='google'),
            on_error=lambda source, exc: errors.append(source),
        )
        assert context.calendar_event_id == 'google'
        assert errors == ['stored']

    def test_all_sources_raising_still_degrades_to_none(self):
        errors: list[str] = []

        def _boom():
            raise RuntimeError('down')

        assert (
            resolve_meeting_context(
                direct=None,
                stored=_boom,
                calendar=_boom,
                screen=_boom,
                on_error=lambda source, exc: errors.append(source),
            )
            is None
        )
        assert errors == ['stored', 'calendar', 'screen']

    def test_a_raising_source_cannot_discard_context_already_found(self):
        def _boom():
            raise RuntimeError('down')

        context = resolve_meeting_context(
            direct=_context('direct', names=['Direct Person'], source='client'),
            stored=_boom,
            calendar=_boom,
            screen=_boom,
        )
        assert context.calendar_event_id == 'direct'


class TestBrowserHostedConferencingDetection:
    def test_google_meet_in_a_chrome_tab_is_recognised(self):
        # The real screenshots for the failing conversation show appName "Google Chrome"
        # and windowTitle "Meet - amc-iajq-asx" — neither matches a conferencing marker,
        # so the OCR layer used to see zero rows for a Google Meet call.
        context = context_from_screen_activity(
            [
                {
                    'appName': 'Google Chrome',
                    'windowTitle': 'Meet - amc-iajq-asx',
                    'ocrText': (
                        'meet.google.com/amc-iajq-asx\n' 'Ash Kalb and Boardy Boardman are in this call\n' 'Mute'
                    ),
                }
            ],
            started_at=CONVERSATION_START,
            finished_at=CONVERSATION_END,
        )
        assert context is not None
        assert [p.name for p in context.participants] == ['Ash Kalb', 'Boardy Boardman']

    def test_an_ordinary_browser_tab_is_not_treated_as_a_meeting(self):
        assert (
            context_from_screen_activity(
                [
                    {
                        'appName': 'Google Chrome',
                        'windowTitle': 'Pull requests - GitHub',
                        'ocrText': 'Some Person\nAnother Person',
                    }
                ],
                started_at=CONVERSATION_START,
                finished_at=CONVERSATION_END,
            )
            is None
        )

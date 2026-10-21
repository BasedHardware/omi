"""GET /v1/calendar/meetings must not 500 the whole list on one malformed record.

The endpoint built `[CalendarMeetingContext(**m) for m in meetings]`, and the model
has required no-default fields (calendar_event_id, title, start_time, duration_minutes),
so a single malformed stored meeting raised a ValidationError and hid every other
meeting the user has. CalendarMeetingContext.from_records skips bad records (reporting
them via on_error) and returns the valid ones.
"""

from datetime import datetime, timezone

from models.calendar_context import CalendarMeetingContext


def _valid(event_id='e1'):
    return {
        'calendar_event_id': event_id,
        'title': 'Standup',
        'start_time': datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        'duration_minutes': 30,
    }


def test_from_records_parses_valid_records():
    out = CalendarMeetingContext.from_records([_valid('a'), _valid('b')])
    assert [m.calendar_event_id for m in out] == ['a', 'b']


def test_from_records_skips_malformed_without_losing_valid():
    records = [
        _valid('good1'),
        {'title': 'missing required fields'},  # no calendar_event_id/start_time/duration_minutes
        {  # bad start_time type
            'calendar_event_id': 'x',
            'title': 't',
            'start_time': 'not-a-date',
            'duration_minutes': 30,
        },
        _valid('good2'),
    ]
    skipped = []
    out = CalendarMeetingContext.from_records(records, on_error=lambda record, exc: skipped.append(record))
    assert [m.calendar_event_id for m in out] == ['good1', 'good2']
    assert len(skipped) == 2


def test_from_records_tolerates_missing_on_error():
    # No on_error callback: malformed records are still skipped, not raised.
    out = CalendarMeetingContext.from_records([{'title': 'bad'}, _valid('ok')])
    assert [m.calendar_event_id for m in out] == ['ok']


def test_from_records_empty():
    assert CalendarMeetingContext.from_records([]) == []


def test_to_storage_dict_round_trips_through_the_reader():
    """The stored external_data shape must parse back to the same context.

    `stores_meeting_context` reads this dict with `CalendarMeetingContext(**raw)`
    and the continuity boundary reads `start_time` / `duration_minutes` off it, so
    a hand-built serializer has to stay complete.
    """
    from models.calendar_context import MeetingParticipant, MeetingParticipantSources

    context = CalendarMeetingContext(
        calendar_event_id='event-1',
        title='Standup',
        participants=[MeetingParticipant(name='Ada', email='ada@example.com')],
        platform='zoom',
        meeting_link='https://example.com/j',
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        duration_minutes=30,
        notes='agenda',
        calendar_source='developer_api',
        participant_sources=MeetingParticipantSources(
            expected_calendar=[MeetingParticipant(name='Ada', email='ada@example.com')],
            observed_screen_listing=None,
        ),
    )

    stored = context.to_storage_dict()

    assert CalendarMeetingContext(**stored) == context
    assert set(stored) == set(CalendarMeetingContext.model_fields)
    assert stored['start_time'] == '2026-01-01T09:00:00+00:00'

"""Tests for resilient timestamp coercion and deterministic sorting in meeting context."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from testing.import_isolation import AutoMockModule, stub_modules


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules(
        {
            'langchain_openai': AutoMockModule('langchain_openai'),
            'langchain_community': AutoMockModule('langchain_community'),
            'utils.memory.memory_service': AutoMockModule('utils.memory.memory_service'),
        }
    ):
        import utils.conversations.meeting_context_pack as pack_module

        yield pack_module


from utils.conversations import meeting_context_pack
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry


def _entry(name=None, email=None, org=None, kind='human', person_id=None):
    return RosterEntry(
        display_name=name,
        email=email,
        organization=org,
        kind=kind,
        source='test',
        person_id=person_id,
    )


def _roster(entries):
    return MeetingRoster(entries=tuple(entries), display_title='Test sync', title_is_window_title=False)


class TestMeetingContextAsUtcCoercion:
    def test_parses_iso_utc_string(self):
        parsed = meeting_context_pack._as_utc('2026-10-18T10:00:00Z')
        assert parsed == datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)

    def test_parses_iso_offset_string(self):
        parsed = meeting_context_pack._as_utc('2026-10-18T12:00:00+02:00')
        assert parsed == datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)

    def test_coerces_naive_datetime_to_utc(self):
        naive = datetime(2026, 10, 18, 10, 0, 0)
        parsed = meeting_context_pack._as_utc(naive)
        assert parsed == datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)

    def test_preserves_aware_utc_datetime(self):
        aware = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)
        parsed = meeting_context_pack._as_utc(aware)
        assert parsed == aware

    def test_invalid_values_return_none(self):
        assert meeting_context_pack._as_utc(None) is None
        assert meeting_context_pack._as_utc('') is None
        assert meeting_context_pack._as_utc('not-a-timestamp') is None
        assert meeting_context_pack._as_utc(12345) is None


class TestLocalDateLabel:
    def test_formats_iso_string_to_local_date(self):
        label = meeting_context_pack._local_date_label('2026-10-18T10:00:00Z', 'UTC')
        assert label == '2026-10-18'

    def test_formats_naive_datetime_to_local_date(self):
        label = meeting_context_pack._local_date_label(datetime(2026, 10, 18, 10, 0, 0), 'UTC')
        assert label == '2026-10-18'

    def test_invalid_value_returns_unknown_date(self):
        assert meeting_context_pack._local_date_label(None, 'UTC') == 'unknown date'
        assert meeting_context_pack._local_date_label('garbage', 'UTC') == 'unknown date'
        assert meeting_context_pack._local_date_label(meeting_context_pack._UTC_MIN, 'UTC') == 'unknown date'


class TestGatherPriorMeetingsTimestampResilience:
    def test_mixed_timestamp_shapes_and_naive_started_at_sort_cleanly(self, monkeypatch):
        start = datetime(2026, 10, 19, 12, 0, 0)  # Naive started_at
        records = [
            {
                'id': 'conv-iso',
                'started_at': '2026-10-18T10:00:00Z',
                'transcript_segments': [{'person_id': 'p-alice'}],
                'structured': {'title': 'ISO string meeting'},
            },
            {
                'id': 'conv-aware',
                'started_at': datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc),
                'transcript_segments': [{'person_id': 'p-alice'}],
                'structured': {'title': 'Aware meeting'},
            },
            {
                'id': 'conv-naive',
                'started_at': datetime(2026, 10, 16, 10, 0, 0),
                'transcript_segments': [{'person_id': 'p-alice'}],
                'structured': {'title': 'Naive meeting'},
            },
            {
                'id': 'conv-missing-ts',
                'started_at': None,
                'created_at': None,
                'transcript_segments': [{'person_id': 'p-alice'}],
                'structured': {'title': 'Missing timestamp meeting'},
            },
        ]

        monkeypatch.setattr(meeting_context_pack.calendar_db, 'list_meetings', lambda *a, **k: [])
        monkeypatch.setattr(
            meeting_context_pack.conversations_db,
            'get_conversations_without_photos',
            lambda *a, **k: records,
        )
        monkeypatch.setattr(meeting_context_pack.action_items_db, 'get_action_items', lambda *a, **k: [])

        roster = _roster([_entry(person_id='p-alice')])
        conversation = SimpleNamespace(started_at=start, id='current-conv')

        notes = meeting_context_pack._gather_prior_meetings('uid', conversation, roster, start, 'UTC')
        # All 4 candidates sorted without TypeError, top 3 retained
        assert len(notes) == 3
        # Should be ordered descending by timestamp
        assert notes[0].title == 'ISO string meeting'
        assert notes[0].started_at == datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)
        assert notes[0].date_label == '2026-10-18'

        assert notes[1].title == 'Aware meeting'
        assert notes[1].started_at == datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc)
        assert notes[1].date_label == '2026-10-17'

        assert notes[2].title == 'Naive meeting'
        assert notes[2].started_at == datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        assert notes[2].date_label == '2026-10-16'

    def test_iso_string_started_at_argument_coerced_properly(self, monkeypatch):
        start_str = '2026-10-19T12:00:00Z'
        calls = {}

        def fake_list_meetings(uid, **kwargs):
            calls['meetings'] = kwargs
            return []

        def fake_conversations(uid, **kwargs):
            calls['conversations'] = kwargs
            return []

        monkeypatch.setattr(meeting_context_pack.calendar_db, 'list_meetings', fake_list_meetings)
        monkeypatch.setattr(
            meeting_context_pack.conversations_db,
            'get_conversations_without_photos',
            fake_conversations,
        )

        roster = _roster([_entry(person_id='p-alice')])
        conversation = SimpleNamespace(started_at=start_str, id='current-conv')

        notes = meeting_context_pack._gather_prior_meetings('uid', conversation, roster, start_str, 'UTC')
        assert notes == ()
        expected_utc = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        assert calls['meetings']['end_date'] == expected_utc
        assert calls['meetings']['start_date'] == expected_utc - timedelta(days=180)

    def test_window_match_with_iso_string_record(self, monkeypatch):
        start_utc = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        meeting_window = (
            datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 15, 11, 0, 0, tzinfo=timezone.utc),
        )

        meeting_record = {
            'calendar_event_id': 'evt-window',
            'start_time': meeting_window[0],
            'end_time': meeting_window[1],
            'participants': [{'name': 'Alice'}],
        }

        # Conversation has no participant matches, but its ISO timestamp falls in the meeting window
        conv_record = {
            'id': 'conv-window-match',
            'started_at': '2026-10-15T10:30:00Z',
            'structured': {'title': 'Window Matched Meeting'},
        }

        monkeypatch.setattr(
            meeting_context_pack.calendar_db,
            'list_meetings',
            lambda *a, **k: [meeting_record],
        )
        monkeypatch.setattr(
            meeting_context_pack.conversations_db,
            'get_conversations_without_photos',
            lambda *a, **k: [conv_record],
        )
        monkeypatch.setattr(meeting_context_pack.action_items_db, 'get_action_items', lambda *a, **k: [])

        roster = _roster([_entry(name='Alice')])
        conversation = SimpleNamespace(started_at=start_utc, id='current-conv')

        notes = meeting_context_pack._gather_prior_meetings('uid', conversation, roster, start_utc, 'UTC')
        assert len(notes) == 1
        assert notes[0].title == 'Window Matched Meeting'
        assert notes[0].started_at == datetime(2026, 10, 15, 10, 30, 0, tzinfo=timezone.utc)


class TestGatherMeetingContextPack:
    def test_gather_meeting_context_pack_accepts_iso_string_started_at(self, monkeypatch):
        records = [
            {
                'id': 'conv-1',
                'started_at': '2026-10-18T10:00:00Z',
                'transcript_segments': [{'person_id': 'p-alice'}],
                'structured': {'title': 'Prior Discussion'},
            }
        ]

        monkeypatch.setattr(meeting_context_pack.calendar_db, 'list_meetings', lambda *a, **k: [])
        monkeypatch.setattr(
            meeting_context_pack.conversations_db,
            'get_conversations_without_photos',
            lambda *a, **k: records,
        )
        monkeypatch.setattr(meeting_context_pack.action_items_db, 'get_action_items', lambda *a, **k: [])
        monkeypatch.setattr(meeting_context_pack, 'load_people_documents', lambda *a, **k: [])
        monkeypatch.setattr(meeting_context_pack, '_gather_goals', lambda *a, **k: ())
        monkeypatch.setattr(meeting_context_pack, '_gather_memories', lambda *a, **k: ())

        roster = _roster([_entry(person_id='p-alice')])
        conversation = SimpleNamespace(started_at='2026-10-19T12:00:00Z', id='current-conv')

        pack = meeting_context_pack.gather_meeting_context_pack(
            'uid',
            conversation,
            roster,
            timezone_name='UTC',
        )
        assert pack is not None
        assert len(pack.prior_meetings) == 1
        assert pack.prior_meetings[0].title == 'Prior Discussion'
        assert pack.prior_meetings[0].started_at == datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)

"""Unit tests for calendar meetings UTC normalization, duration validation, and query filter ordering."""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import database.calendar_meetings as calendar_db
import routers.calendar_meetings as calendar_router


def test_store_calendar_meeting_normalizes_mixed_naive_and_offset_times_to_utc(monkeypatch):
    captured = {}

    monkeypatch.setattr(calendar_db, 'get_meeting_id_by_calendar_event', lambda uid, eid, src: None)

    def fake_create_meeting(uid, data):
        captured.update(data)
        return 'meeting-doc-1'

    monkeypatch.setattr(calendar_db, 'create_meeting', fake_create_meeting)

    plus_two = timezone(timedelta(hours=2))
    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='evt-1',
        calendar_source='google_calendar',
        title='Sync Call',
        start_time=datetime(2026, 9, 24, 14, 0, 0, tzinfo=plus_two),  # 12:00 UTC
        end_time=datetime(2026, 9, 24, 12, 45, 0),  # naive -> 12:45 UTC
    )
    res = calendar_router.store_calendar_meeting(req, uid='uid-1')
    assert res.meeting_id == 'meeting-doc-1'
    assert captured['start_time'] == datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert captured['end_time'] == datetime(2026, 9, 24, 12, 45, 0, tzinfo=timezone.utc)
    assert captured['duration_minutes'] == 45


def test_store_calendar_meeting_rejects_end_time_not_after_start_time():
    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='evt-2',
        calendar_source='macos_calendar',
        title='Invalid Window',
        start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(HTTPException) as exc_info:
        calendar_router.store_calendar_meeting(req, uid='uid-1')
    assert exc_info.value.status_code == 422


def test_list_meetings_applies_where_filters_in_utc_before_limit(monkeypatch):
    calls = []

    class FakeQuery:
        def where(self, field, op, value):
            calls.append(('where', field, op, value))
            return self

        def order_by(self, field, direction=None):
            calls.append(('order_by', field))
            return self

        def limit(self, count):
            calls.append(('limit', count))
            return self

        def stream(self):
            doc = MagicMock()
            doc.id = 'm-1'
            doc.to_dict.return_value = {'title': 'Standup'}
            return [doc]

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())

    naive_start = datetime(2026, 9, 24, 9, 0, 0)
    naive_end = datetime(2026, 9, 24, 18, 0, 0)
    items = calendar_db.list_meetings('uid-1', start_date=naive_start, end_date=naive_end, limit=10)
    assert len(items) == 1
    assert calls[0] == ('where', 'start_time', '>=', datetime(2026, 9, 24, 9, 0, 0, tzinfo=timezone.utc))
    assert calls[1] == ('where', 'start_time', '<=', datetime(2026, 9, 24, 18, 0, 0, tzinfo=timezone.utc))
    assert calls[2] == ('order_by', 'start_time')
    assert calls[3] == ('limit', 10)


@pytest.mark.parametrize(
    'meeting_data',
    [
        {},
        {'calendar_source': 'google_calendar'},
        {'calendar_source': 'google_calendar', 'calendar_event_id': '  '},
        {'calendar_source': '', 'calendar_event_id': 'evt-1'},
    ],
)
def test_create_meeting_rejects_missing_or_blank_natural_key_before_firestore(monkeypatch, meeting_data):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('invalid meeting data must be rejected before Firestore access'),
    )

    with pytest.raises((TypeError, ValueError)):
        calendar_db.create_meeting('uid-1', meeting_data)


def test_create_meeting_rejects_blank_uid_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('invalid uid must be rejected before Firestore access'),
    )

    with pytest.raises(ValueError, match='uid'):
        calendar_db.create_meeting('  ', {'calendar_source': 'google_calendar', 'calendar_event_id': 'evt-1'})


def test_create_meeting_rejects_non_dictionary_payload_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('a non-dictionary payload must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='dictionary'):
        calendar_db.create_meeting('uid-1', None)


def test_create_meeting_uses_original_opaque_identifiers(monkeypatch):
    observed = {}
    transaction = object()
    monkeypatch.setattr(
        calendar_db,
        'calendar_meeting_doc_id',
        lambda uid, source, event_id: observed.update(uid=uid, source=source, event_id=event_id) or 'meeting-1',
    )
    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: MagicMock())
    monkeypatch.setattr(calendar_db, 'db', MagicMock(transaction=lambda: transaction))
    monkeypatch.setattr(
        calendar_db,
        '_upsert_meeting_transaction',
        lambda actual_transaction, doc_ref, data, now: observed.update(
            transaction=actual_transaction,
            data=data,
            now=now,
        ),
    )
    payload = {'calendar_source': 'source-id ', 'calendar_event_id': ' event-id'}

    assert calendar_db.create_meeting('uid-1', payload) == 'meeting-1'
    assert observed['source'] == 'source-id '
    assert observed['event_id'] == ' event-id'
    assert observed['transaction'] is transaction
    assert observed['data'] is payload
    assert observed['now'].tzinfo is timezone.utc


def test_update_meeting_does_not_mutate_caller_payload(monkeypatch):
    document = MagicMock()
    collection = MagicMock()
    collection.document.return_value = document
    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: collection)
    meeting_data = {'title': 'Planning'}

    calendar_db.update_meeting('uid-1', 'meeting-1', meeting_data)

    assert meeting_data == {'title': 'Planning'}
    payload = document.update.call_args.args[0]
    assert payload['title'] == 'Planning'
    assert payload['synced_at'].tzinfo is timezone.utc


def test_update_meeting_rejects_non_dictionary_payload_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('a non-dictionary payload must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='dictionary'):
        calendar_db.update_meeting('uid-1', 'meeting-1', None)


def test_update_meeting_skips_empty_payload_without_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('empty updates must not touch Firestore'),
    )

    calendar_db.update_meeting('uid-1', 'meeting-1', {})


@pytest.mark.parametrize('limit', [101, 10_000])
def test_list_meetings_caps_direct_call_limit(monkeypatch, caplog, limit):
    caplog.set_level(logging.DEBUG, logger=calendar_db.__name__)
    calls = []

    class FakeQuery:
        def order_by(self, field, direction=None):
            return self

        def limit(self, count):
            calls.append(count)
            return self

        def stream(self):
            return []

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())

    assert calendar_db.list_meetings('uid-1', limit=limit) == []
    assert calls == [100]
    assert f'Capping calendar meeting list limit from {limit} to 100' in caplog.text


@pytest.mark.parametrize('limit', [0, -1])
def test_list_meetings_returns_empty_without_firestore_for_non_positive_limit(monkeypatch, limit):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('a non-positive limit must not query Firestore'),
    )

    assert calendar_db.list_meetings('uid-1', limit=limit) == []


@pytest.mark.parametrize('limit', [True, 1.5, '10'])
def test_list_meetings_rejects_non_integer_limits(monkeypatch, limit):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('an invalid limit must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='limit'):
        calendar_db.list_meetings('uid-1', limit=limit)


def test_list_meetings_rejects_invalid_date_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('an invalid date must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='datetime'):
        calendar_db.list_meetings('uid-1', start_date='2026-09-27')


@pytest.mark.parametrize('field', ['calendar_event_id', 'calendar_source'])
def test_store_request_rejects_blank_calendar_identifiers(field):
    payload = {
        'calendar_event_id': 'evt-1',
        'calendar_source': 'google_calendar',
        'title': 'Planning',
        'start_time': datetime(2026, 9, 27, 10, tzinfo=timezone.utc),
        'end_time': datetime(2026, 9, 27, 11, tzinfo=timezone.utc),
    }
    payload[field] = '  '

    with pytest.raises(ValidationError):
        calendar_router.StoreMeetingRequest(**payload)


def test_get_calendar_meeting_rejects_blank_id_before_database(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        'get_meeting',
        lambda uid, meeting_id: pytest.fail('a blank route ID must not reach the database'),
    )

    with pytest.raises(HTTPException) as exc_info:
        calendar_router.get_calendar_meeting('  ', uid='uid-1')

    assert exc_info.value.status_code == 422


def test_calendar_routes_reject_invalid_identifiers_as_http_422(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        'get_meeting',
        lambda uid, meeting_id: pytest.fail('invalid route identifiers must not reach the database'),
    )
    monkeypatch.setattr(
        calendar_db,
        'get_meeting_id_by_calendar_event',
        lambda uid, event_id, source: pytest.fail('invalid body identifiers must not reach the database'),
    )
    app = FastAPI()
    app.include_router(calendar_router.router)
    app.dependency_overrides[calendar_router.auth.get_current_user_uid] = lambda: 'uid-1'

    with TestClient(app) as client:
        blank_path_id = client.get('/v1/calendar/meetings/%20%20')
        blank_event_id = client.post(
            '/v1/calendar/meetings',
            json={
                'calendar_event_id': '  ',
                'calendar_source': 'google_calendar',
                'title': 'Planning',
                'start_time': '2026-09-27T10:00:00Z',
                'end_time': '2026-09-27T11:00:00Z',
            },
        )

    assert blank_path_id.status_code == 422
    assert blank_event_id.status_code == 422


def test_get_meeting_returns_none_when_document_is_missing(monkeypatch):
    document = MagicMock()
    document.get.return_value.exists = False
    collection = MagicMock()
    collection.document.return_value = document
    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: collection)

    assert calendar_db.get_meeting('uid-1', 'meeting-1') is None


def test_get_meeting_adds_document_id_to_existing_record(monkeypatch):
    snapshot = MagicMock()
    snapshot.id = 'meeting-1'
    snapshot.exists = True
    snapshot.to_dict.return_value = {'title': 'Planning'}
    document = MagicMock()
    document.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = document
    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: collection)

    assert calendar_db.get_meeting('uid-1', 'meeting-1') == {'id': 'meeting-1', 'title': 'Planning'}


def test_get_meeting_id_by_calendar_event_returns_first_document_id(monkeypatch):
    calls = []
    document = MagicMock(id='meeting-1')

    class FakeQuery:
        def where(self, field, op, value):
            calls.append(('where', field, op, value))
            return self

        def limit(self, count):
            calls.append(('limit', count))
            return self

        def stream(self):
            return [document]

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())

    assert calendar_db.get_meeting_id_by_calendar_event('uid-1', 'evt-1', 'google_calendar') == 'meeting-1'
    assert calls == [
        ('where', 'calendar_event_id', '==', 'evt-1'),
        ('where', 'calendar_source', '==', 'google_calendar'),
        ('limit', 1),
    ]


def test_get_meeting_id_by_calendar_event_returns_none_without_matches(monkeypatch):
    class FakeQuery:
        def where(self, field, op, value):
            return self

        def limit(self, count):
            return self

        def stream(self):
            return []

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())

    assert calendar_db.get_meeting_id_by_calendar_event('uid-1', 'evt-1', 'google_calendar') is None


@pytest.mark.parametrize(
    'operation',
    [
        lambda uid: calendar_db.get_meeting(uid, 'meeting-1'),
        lambda uid: calendar_db.get_meeting_id_by_calendar_event(uid, 'evt-1', 'google_calendar'),
        lambda uid: calendar_db.delete_meeting(uid, 'meeting-1'),
    ],
)
def test_database_operations_reject_blank_uid_before_firestore(monkeypatch, operation):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('an invalid uid must be rejected before Firestore access'),
    )

    with pytest.raises(ValueError, match='uid'):
        operation('  ')


@pytest.mark.parametrize(
    'operation',
    [
        lambda: calendar_db.get_meeting('uid-1', '  '),
        lambda: calendar_db.update_meeting('uid-1', '  ', {'title': 'Planning'}),
        lambda: calendar_db.delete_meeting('uid-1', '  '),
    ],
)
def test_database_operations_reject_blank_meeting_id_before_firestore(monkeypatch, operation):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('an invalid meeting ID must be rejected before Firestore access'),
    )

    with pytest.raises(ValueError, match='meeting_id'):
        operation()


@pytest.mark.parametrize(
    'event_id,source',
    [('  ', 'google_calendar'), ('evt-1', '  ')],
)
def test_calendar_event_lookup_rejects_blank_identifiers_before_firestore(monkeypatch, event_id, source):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('blank calendar identifiers must be rejected before Firestore access'),
    )

    with pytest.raises(ValueError):
        calendar_db.get_meeting_id_by_calendar_event('uid-1', event_id, source)


def test_delete_meeting_deletes_the_selected_document(monkeypatch):
    collection = MagicMock()
    document = collection.document.return_value
    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: collection)

    calendar_db.delete_meeting('uid-1', 'meeting-1')

    collection.document.assert_called_once_with('meeting-1')
    document.delete.assert_called_once_with()


def test_delete_old_meetings_rejects_invalid_date_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('an invalid date must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='datetime'):
        calendar_db.delete_old_meetings('uid-1', '2026-09-27')


def test_delete_old_meetings_commits_full_batches_and_final_remainder(monkeypatch):
    references = [object() for _ in range(501)]
    committed_batch_sizes = []

    class FakeQuery:
        def where(self, field, op, value):
            return self

        def stream(self):
            return [MagicMock(reference=reference) for reference in references]

    class FakeBatch:
        def __init__(self):
            self.references = []

        def delete(self, reference):
            self.references.append(reference)

        def commit(self):
            committed_batch_sizes.append(len(self.references))

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())
    monkeypatch.setattr(calendar_db, 'db', MagicMock(batch=FakeBatch))

    deleted_count = calendar_db.delete_old_meetings('uid-1', datetime(2026, 9, 27, tzinfo=timezone.utc))

    assert deleted_count == 501
    assert committed_batch_sizes == [500, 1]


def test_get_meetings_in_time_range_normalizes_bounds_and_orders(monkeypatch):
    calls = []

    class FakeQuery:
        def where(self, field, op, value):
            calls.append(('where', field, op, value))
            return self

        def order_by(self, field, direction=None):
            calls.append(('order_by', field, direction))
            return self

        def limit(self, count):
            calls.append(('limit', count))
            return self

        def stream(self):
            return []

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())
    plus_two = timezone(timedelta(hours=2))

    assert (
        calendar_db.get_meetings_in_time_range(
            'uid-1',
            datetime(2026, 9, 27, 12, tzinfo=plus_two),
            datetime(2026, 9, 27, 14, tzinfo=plus_two),
        )
        == []
    )
    assert calls[0] == ('where', 'start_time', '<', datetime(2026, 9, 27, 12, tzinfo=timezone.utc))
    assert calls[1] == ('where', 'end_time', '>', datetime(2026, 9, 27, 10, tzinfo=timezone.utc))
    assert calls[2][0:2] == ('order_by', 'start_time')
    assert calls[3] == ('limit', 10)


def test_get_meetings_in_time_range_rejects_invalid_bounds_before_firestore(monkeypatch):
    monkeypatch.setattr(
        calendar_db,
        '_get_meetings_collection',
        lambda uid: pytest.fail('invalid time bounds must be rejected before Firestore access'),
    )

    with pytest.raises(TypeError, match='datetime'):
        calendar_db.get_meetings_in_time_range('uid-1', 'start', datetime.now(timezone.utc))

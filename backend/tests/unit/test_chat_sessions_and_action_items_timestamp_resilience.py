from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.chat as chat_db
import database.conversations as conversations_db
from database.capture_groups import _aware, _primary_rank, _record
from database.conversation_revisions import ensure_timezone_aware


def test_ensure_timezone_aware_handles_strings_naive_and_none():
    aware_utc = ensure_timezone_aware("2026-10-18T14:30:00Z")
    assert aware_utc == datetime(2026, 10, 18, 14, 30, tzinfo=timezone.utc)
    assert aware_utc.tzinfo == timezone.utc

    aware_offset = ensure_timezone_aware("2026-10-18T16:30:00+02:00")
    assert aware_offset == datetime(2026, 10, 18, 14, 30, tzinfo=timezone.utc)
    assert aware_offset.tzinfo == timezone.utc

    naive_dt = datetime(2026, 10, 18, 10, 0)
    aware_from_naive = ensure_timezone_aware(naive_dt)
    assert aware_from_naive == datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
    assert aware_from_naive.tzinfo == timezone.utc

    none_dt = ensure_timezone_aware(None)
    assert isinstance(none_dt, datetime)
    assert none_dt.tzinfo == timezone.utc

    invalid_dt = ensure_timezone_aware(123456)
    assert isinstance(invalid_dt, datetime)
    assert invalid_dt.tzinfo == timezone.utc


def test_get_chat_sessions_sorting_with_missing_naive_and_string_updated_at():
    class MockDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return dict(self._data)

    firestore_docs = [
        MockDoc('db-sess-1', {'plugin_id': None, 'updated_at': datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)})
    ]

    extra_visible = [
        {'id': 'extra-str', 'plugin_id': None, 'updated_at': '2026-10-18T14:00:00Z'},
        {'id': 'extra-naive', 'plugin_id': None, 'updated_at': datetime(2026, 10, 18, 10, 0)},
        {'id': 'extra-missing', 'plugin_id': None},  # missing updated_at
    ]

    mock_col = MagicMock()
    mock_query = MagicMock()
    mock_col.order_by.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = firestore_docs

    with (
        patch.object(chat_db, 'db', new=MagicMock()) as patched_db,
        patch.object(chat_db, 'visible_sessions', return_value=extra_visible),
    ):
        patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
        sessions = chat_db.get_chat_sessions('test-uid', limit=10, offset=0)

    session_ids = [s['id'] for s in sessions]
    # Ordering descending:
    # 1. extra-str: 14:00
    # 2. db-sess-1: 12:00
    # 3. extra-naive: 10:00
    # 4. extra-missing: min datetime
    assert session_ids == ['extra-str', 'db-sess-1', 'extra-naive', 'extra-missing']


def test_get_action_items_with_missing_created_at_and_string_timestamps():
    class MockDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return dict(self._data)

    docs = [
        MockDoc(
            'conv-with-str',
            {
                'id': 'conv-with-str',
                'status': 'completed',
                'created_at': '2026-10-18T14:00:00Z',
                'structured': {
                    'title': 'Meeting with String Date',
                    'action_items': [
                        {
                            'description': 'Follow up on contracts',
                            'completed': False,
                            'created_at': '2026-10-18T14:05:00Z',
                        }
                    ],
                },
            },
        ),
        MockDoc(
            'conv-missing-created',
            {
                'id': 'conv-missing-created',
                'status': 'completed',
                # missing created_at
                'structured': {
                    'title': 'Meeting with Missing Date',
                    'action_items': [
                        {
                            'description': 'Sync with team',
                            'completed': False,
                        }
                    ],
                },
            },
        ),
        MockDoc(
            'conv-with-naive',
            {
                'id': 'conv-with-naive',
                'status': 'completed',
                'created_at': datetime(2026, 10, 18, 12, 0),
                'structured': {
                    'title': 'Meeting with Naive Date',
                    'action_items': [
                        {
                            'description': 'Review slides',
                            'completed': False,
                        }
                    ],
                },
            },
        ),
    ]

    mock_col = MagicMock()
    mock_query = MagicMock()
    mock_col.where.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.stream.return_value = docs

    with patch.object(conversations_db, 'db', new=MagicMock()) as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
        items = conversations_db.get_action_items('test-uid')

    assert len(items) == 3
    # Sorted by -conversation_created_at:
    # 1. conv-with-str (14:00)
    # 2. conv-with-naive (12:00)
    # 3. conv-missing-created (min datetime)
    assert items[0]['conversation_id'] == 'conv-with-str'
    assert items[0]['description'] == 'Follow up on contracts'
    assert items[0]['created_at'] == datetime(2026, 10, 18, 14, 5, tzinfo=timezone.utc)

    assert items[1]['conversation_id'] == 'conv-with-naive'
    assert items[1]['description'] == 'Review slides'

    assert items[2]['conversation_id'] == 'conv-missing-created'
    assert items[2]['description'] == 'Sync with team'


def test_capture_groups_aware_and_record_resilience():
    dt_str = _aware('2026-10-18T10:00:00Z')
    assert dt_str == datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)

    dt_naive = _aware(datetime(2026, 10, 18, 10, 0))
    assert dt_naive == datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)

    dt_none = _aware(None)
    assert dt_none is None

    # Test _primary_rank with missing id
    rank = _primary_rank({'started_at': dt_str, 'finished_at': datetime(2026, 10, 18, 10, 30, tzinfo=timezone.utc)})
    assert rank == (-1800.0, '')

    # Test _record with missing id and string timestamps
    members = [
        {'id': 'm1', 'started_at': _aware('2026-10-18T10:00:00Z'), 'finished_at': _aware('2026-10-18T10:30:00Z')},
        {'started_at': _aware('2026-10-18T09:00:00Z')},  # missing id and finished_at
    ]
    rec = _record('group-1', members, 1)
    assert rec['id'] == 'group-1'
    assert rec['primary_id'] == 'm1'
    assert len(rec['members']) == 2

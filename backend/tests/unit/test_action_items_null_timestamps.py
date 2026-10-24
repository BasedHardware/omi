from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.action_items as action_items_db


def _mock_user_action_items_collection():
    doc_ref = MagicMock()
    doc_ref.id = 'item-1'
    collection_ref = MagicMock()
    collection_ref.document.return_value = doc_ref
    control_doc = MagicMock()
    control_doc.exists = False
    collection_ref.document.return_value.get.return_value = control_doc
    user_ref = MagicMock()
    user_ref.collection.return_value = collection_ref
    users_collection = MagicMock()
    users_collection.document.return_value = user_ref
    return users_collection, doc_ref


def test_create_action_item_replaces_explicit_none_timestamps():
    users_collection, doc_ref = _mock_user_action_items_collection()
    tx_mock = MagicMock()
    payload = {
        'description': 'Send follow-up notes',
        'completed': True,
        'created_at': None,
        'updated_at': None,
        'completed_at': None,
    }
    with (
        patch.object(action_items_db, 'db', new=MagicMock()) as mock_db,
        patch.object(action_items_db.firestore, 'transactional', side_effect=lambda fn: fn),
    ):
        mock_db.collection.return_value = users_collection
        mock_db.transaction.return_value = tx_mock
        item_id = action_items_db.create_action_item('user-123', payload)

    assert item_id == 'item-1'
    written = tx_mock.set.call_args[0][1]
    assert isinstance(written['created_at'], datetime)
    assert isinstance(written['updated_at'], datetime)
    assert isinstance(written['completed_at'], datetime)


def test_create_action_items_batch_replaces_explicit_none_timestamps():
    users_collection, doc_ref = _mock_user_action_items_collection()
    tx_mock = MagicMock()
    items = [
        {
            'description': 'Review PR',
            'completed': True,
            'created_at': None,
            'updated_at': None,
            'completed_at': None,
        }
    ]
    with (
        patch.object(action_items_db, 'db', new=MagicMock()) as mock_db,
        patch.object(action_items_db.firestore, 'transactional', side_effect=lambda fn: fn),
    ):
        mock_db.collection.return_value = users_collection
        mock_db.transaction.return_value = tx_mock
        created_ids = action_items_db.create_action_items_batch('user-123', items)

    assert created_ids == ['item-1']
    written = tx_mock.set.call_args[0][1]
    assert isinstance(written['created_at'], datetime)
    assert isinstance(written['updated_at'], datetime)
    assert isinstance(written['completed_at'], datetime)


def test_action_item_list_sort_key_handles_none_created_at():
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    items = [
        {'id': 'null-created', 'completed': False, 'due_at': None, 'created_at': None},
        {'id': 'valid-created', 'completed': False, 'due_at': None, 'created_at': now},
    ]
    sorted_items = sorted(items, key=action_items_db._action_item_list_sort_key)
    assert [item['id'] for item in sorted_items] == ['valid-created', 'null-created']


def test_action_item_list_sort_key_handles_naive_and_string_due_at():
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    items = [
        {'id': 'string-due', 'completed': False, 'due_at': '2026-10-25T14:00:00Z', 'created_at': now},
        {'id': 'naive-due', 'completed': False, 'due_at': datetime(2026, 10, 24, 14, 0), 'created_at': now},
        {
            'id': 'aware-due',
            'completed': False,
            'due_at': datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc),
            'created_at': now,
        },
    ]
    sorted_items = sorted(items, key=action_items_db._action_item_list_sort_key)
    assert [item['id'] for item in sorted_items] == ['naive-due', 'string-due', 'aware-due']


def test_action_item_list_sort_key_handles_string_created_at():
    items = [
        {'id': 'string-created', 'completed': False, 'due_at': None, 'created_at': '2026-10-25T14:00:00Z'},
        {
            'id': 'dt-created',
            'completed': False,
            'due_at': None,
            'created_at': datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc),
        },
    ]
    sorted_items = sorted(items, key=action_items_db._action_item_list_sort_key)
    assert [item['id'] for item in sorted_items] == ['string-created', 'dt-created']


def test_get_pending_apple_reminders_sync_sorts_naive_and_string_updated_at():
    class MockDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return dict(self._data)

    docs = [
        MockDoc('item-naive', {'updated_at': datetime(2026, 10, 10, 12, 0), 'completed': False}),
        MockDoc('item-str-newer', {'updated_at': '2026-10-12T12:00:00Z', 'completed': False}),
        MockDoc(
            'item-aware-oldest',
            {'updated_at': datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc), 'completed': False},
        ),
        MockDoc('item-none', {'updated_at': None, 'completed': False}),
    ]

    synced_query = MagicMock()
    synced_query.stream.return_value = docs

    pending_query = MagicMock()
    pending_query.stream.return_value = []

    mock_q = MagicMock()
    mock_q.where.return_value = mock_q
    mock_q.limit.side_effect = lambda limit_val: synced_query if limit_val == 100 else pending_query

    items_ref = MagicMock()
    items_ref.where.return_value = mock_q

    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = items_ref

    with patch.object(action_items_db, 'db', new=client):
        result = action_items_db.get_pending_apple_reminders_sync('user-123')

    synced_ids = [item['id'] for item in result['synced_items']]
    assert synced_ids == ['item-str-newer', 'item-naive', 'item-aware-oldest', 'item-none']


def test_get_scores_subtracts_deleted_items_with_naive_and_string_timestamps():
    class MockDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return dict(self._data)

    deleted_docs = [
        # ISO string due_at (today) and created_at (this week), completed=True
        MockDoc(
            'del-str',
            {
                'deleted': True,
                'completed': True,
                'due_at': '2026-10-15T12:00:00Z',
                'created_at': '2026-10-12T12:00:00Z',
            },
        ),
        # naive due_at (today) and created_at (this week), completed=False
        MockDoc(
            'del-naive',
            {
                'deleted': True,
                'completed': False,
                'due_at': datetime(2026, 10, 15, 8, 0),
                'created_at': datetime(2026, 10, 11, 8, 0),
            },
        ),
        # None timestamps, completed=False
        MockDoc(
            'del-none',
            {
                'deleted': True,
                'completed': False,
                'due_at': None,
                'created_at': None,
            },
        ),
    ]

    mock_count_obj = MagicMock()
    mock_count_obj.value = 10

    mock_query = MagicMock()
    mock_query.count.return_value.get.return_value = [[mock_count_obj]]
    mock_query.where.return_value = mock_query
    mock_query.order_by.return_value = mock_query

    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = mock_query

    with patch.object(action_items_db, '_iter_query_pages', return_value=deleted_docs):
        scores = action_items_db.get_scores('user-123', date='2026-10-15', firestore_client=client)

    # Initial totals were 10 for all queries.
    # del-str (completed=True, due today, created this week):
    #   daily_total: 10 - 1 = 9, daily_completed: 10 - 1 = 9
    #   weekly_total: 10 - 1 = 9, weekly_completed: 10 - 1 = 9
    #   overall_total: 10 - 1 = 9, overall_completed: 10 - 1 = 9
    # del-naive (completed=False, due today, created this week):
    #   daily_total: 9 - 1 = 8, daily_completed: 9
    #   weekly_total: 9 - 1 = 8, weekly_completed: 9
    #   overall_total: 9 - 1 = 8, overall_completed: 9
    # del-none (completed=False, due None, created None):
    #   daily_total: 8, daily_completed: 9 (clamped to daily_total by min/max in get_scores)
    #   weekly_total: 8, weekly_completed: 9
    #   overall_total: 8 - 1 = 7, overall_completed: 9 -> clamped
    assert scores['daily']['total_tasks'] == 8
    assert scores['daily']['completed_tasks'] == 9
    assert scores['weekly']['total_tasks'] == 8
    assert scores['weekly']['completed_tasks'] == 9
    assert scores['overall']['total_tasks'] == 7
    assert scores['overall']['completed_tasks'] == 9

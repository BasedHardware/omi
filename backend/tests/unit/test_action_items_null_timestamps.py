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


def test_action_item_list_sort_key_coerces_iso_string_and_naive_datetimes():
    now_utc = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    items = [
        {
            'id': 'string-due',
            'completed': False,
            'due_at': '2026-10-25T14:00:00Z',
            'created_at': '2026-10-18T10:00:00Z',
        },
        {
            'id': 'naive-due',
            'completed': False,
            'due_at': datetime(2026, 10, 24, 14, 0),
            'created_at': now_utc,
        },
        {
            'id': 'aware-due',
            'completed': False,
            'due_at': datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc),
            'created_at': now_utc,
        },
    ]
    # Sorting mixed string and naive datetimes must not raise TypeError or AttributeError
    sorted_items = sorted(items, key=action_items_db._action_item_list_sort_key)
    assert [item['id'] for item in sorted_items] == ['naive-due', 'string-due', 'aware-due']


def test_coerce_item_datetime_apple_reminders_and_scores():
    # Apple Reminders sorting with ISO string and naive datetimes
    dt_min = datetime.min.replace(tzinfo=timezone.utc)
    synced = [
        {'id': 'item-str', 'updated_at': '2026-10-18T10:00:00Z'},
        {'id': 'item-naive', 'updated_at': datetime(2026, 10, 19, 10, 0)},
        {'id': 'item-none', 'updated_at': None},
    ]
    synced.sort(
        key=lambda x: action_items_db._coerce_item_datetime(x.get('updated_at'), dt_min),
        reverse=True,
    )
    assert [item['id'] for item in synced] == ['item-naive', 'item-str', 'item-none']

    # Scores deleted-items window check with ISO strings and naive datetimes
    tz = timezone.utc
    day_start = datetime(2026, 10, 19, 0, 0, tzinfo=tz)
    day_end = datetime(2026, 10, 20, 0, 0, tzinfo=tz)
    week_start = datetime(2026, 10, 13, 0, 0, tzinfo=tz)

    deleted = [
        {'due_at': '2026-10-19T12:00:00Z', 'created_at': datetime(2026, 10, 15, 12, 0)},
        {'due_at': datetime(2026, 10, 19, 14, 0), 'created_at': '2026-10-14T08:00:00Z'},
        {'due_at': None, 'created_at': None},
    ]

    due_in_day = 0
    created_in_week = 0
    for data in deleted:
        due = action_items_db._coerce_item_datetime(data.get('due_at'), None)
        if due is not None and day_start <= due < day_end:
            due_in_day += 1
        created = action_items_db._coerce_item_datetime(data.get('created_at'), None)
        if created is not None and week_start <= created < day_end:
            created_in_week += 1

    assert due_in_day == 2
    assert created_in_week == 2

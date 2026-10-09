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

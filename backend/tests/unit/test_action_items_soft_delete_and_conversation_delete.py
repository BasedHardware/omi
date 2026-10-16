from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import database.action_items as action_items_db
import routers.action_items as action_items_router
from routers.action_items import (
    AcceptSharedTasksRequest,
    ShareTasksRequest,
    accept_shared_action_items,
    delete_conversation_action_items,
    get_shared_action_items,
    search_action_items,
    share_action_items,
)

UID = 'user-action-items-test'
CONV_ID = 'conv-action-items-test'
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def test_delete_conversation_action_items_returns_404_when_conversation_missing(monkeypatch):
    monkeypatch.setattr(action_items_router.conversations_db, 'get_conversation', lambda uid, cid: None)

    with pytest.raises(HTTPException) as exc_info:
        delete_conversation_action_items(CONV_ID, uid=UID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Conversation not found'


def test_delete_conversation_action_items_returns_402_when_conversation_locked(monkeypatch):
    monkeypatch.setattr(
        action_items_router.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid, 'is_locked': True}
    )
    delete_for_conv = MagicMock()
    monkeypatch.setattr(action_items_router.action_items_db, 'delete_action_items_for_conversation', delete_for_conv)

    with pytest.raises(HTTPException) as exc_info:
        delete_conversation_action_items(CONV_ID, uid=UID)

    assert exc_info.value.status_code == 402
    delete_for_conv.assert_not_called()


def test_delete_conversation_action_items_returns_402_when_any_task_locked(monkeypatch):
    monkeypatch.setattr(
        action_items_router.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid, 'is_locked': False}
    )
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_items_by_conversation',
        lambda uid, cid: [
            {'id': 'task-1', 'is_locked': False},
            {'id': 'task-2', 'is_locked': True},
        ],
    )
    delete_for_conv = MagicMock()
    monkeypatch.setattr(action_items_router.action_items_db, 'delete_action_items_for_conversation', delete_for_conv)

    with pytest.raises(HTTPException) as exc_info:
        delete_conversation_action_items(CONV_ID, uid=UID)

    assert exc_info.value.status_code == 402
    delete_for_conv.assert_not_called()


def test_delete_conversation_action_items_cancels_reminders_even_when_vector_delete_fails(monkeypatch):
    monkeypatch.setattr(
        action_items_router.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid, 'is_locked': False}
    )
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_items_by_conversation',
        lambda uid, cid: [{'id': 'task-1', 'is_locked': False}, {'id': 'task-2', 'is_locked': False}],
    )
    monkeypatch.setattr(action_items_router.action_items_db, 'delete_action_items_for_conversation', lambda uid, cid: 2)
    monkeypatch.setattr(
        action_items_router,
        'delete_action_item_vectors_batch',
        MagicMock(side_effect=RuntimeError('Pinecone unavailable')),
    )
    batch_cancel = MagicMock()
    monkeypatch.setattr(action_items_router, 'send_action_items_batch_deletion_message', batch_cancel)

    result = delete_conversation_action_items(CONV_ID, uid=UID)

    assert result == {'status': 'Ok', 'deleted_count': 2}
    batch_cancel.assert_called_once_with(user_id=UID, action_item_ids=['task-1', 'task-2'])


def test_search_action_items_filters_soft_deleted_and_locked_rows(monkeypatch):
    monkeypatch.setattr(
        action_items_router, 'search_action_items_by_vector', lambda uid, query, limit=10: ['t-live', 't-del', 't-lock']
    )
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_items_by_ids',
        lambda uid, ids: [
            {'id': 't-live', 'description': 'Live task', 'completed': False, 'deleted': False, 'is_locked': False},
            {'id': 't-del', 'description': 'Deleted task', 'completed': False, 'deleted': True, 'is_locked': False},
            {'id': 't-lock', 'description': 'Locked task', 'completed': False, 'deleted': False, 'is_locked': True},
        ],
    )

    result = search_action_items(query='task', limit=10, uid=UID)

    assert [item.id for item in result['action_items']] == ['t-live']


def test_share_and_accept_endpoints_exclude_soft_deleted_tasks(monkeypatch):
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_item',
        lambda uid, tid: {'id': tid, 'description': 'Soft deleted', 'deleted': True, 'is_locked': False},
    )

    with pytest.raises(HTTPException) as share_exc:
        share_action_items(ShareTasksRequest(task_ids=['t-del']), uid=UID)
    assert share_exc.value.status_code == 404

    monkeypatch.setattr(
        action_items_router.redis_db,
        'get_task_share',
        lambda token: {'uid': 'sender-uid', 'display_name': 'Alice', 'task_ids': ['t-del', 't-live']},
    )
    items = {
        't-del': {'id': 't-del', 'description': 'Deleted task', 'deleted': True, 'is_locked': False},
        't-live': {'id': 't-live', 'description': 'Live task', 'deleted': False, 'is_locked': False},
    }
    monkeypatch.setattr(action_items_router.action_items_db, 'get_action_item', lambda uid, tid: items.get(tid))

    preview = get_shared_action_items('tok-1')
    assert preview == {
        'sender_name': 'Alice',
        'tasks': [{'description': 'Live task', 'due_at': None}],
        'count': 1,
    }

    # If all shared tasks were soft-deleted after sharing, accept returns 404 without claiming token.
    monkeypatch.setattr(
        action_items_router.action_items_db,
        'get_action_item',
        lambda uid, tid: {'id': tid, 'description': 'Deleted task', 'deleted': True, 'is_locked': False},
    )
    try_accept = MagicMock(return_value=True)
    monkeypatch.setattr(action_items_router.redis_db, 'try_accept_task_share', try_accept)

    with pytest.raises(HTTPException) as accept_exc:
        accept_shared_action_items(AcceptSharedTasksRequest(token='tok-1'), uid='recipient-uid')
    assert accept_exc.value.status_code == 404
    try_accept.assert_not_called()


def test_get_pending_apple_reminders_sync_skips_soft_deleted_rows_and_retire_clears_sync_requested(monkeypatch):
    pending_docs = [
        SimpleNamespace(
            id='p-live',
            to_dict=lambda: {'description': 'Export me', 'sync_requested': True, 'exported': False, 'deleted': False},
        ),
        SimpleNamespace(
            id='p-deleted',
            to_dict=lambda: {'description': 'Retired', 'sync_requested': True, 'exported': False, 'deleted': True},
        ),
    ]
    synced_docs = [
        SimpleNamespace(
            id='s-live',
            to_dict=lambda: {
                'description': 'Synced live',
                'exported': True,
                'export_platform': 'apple_reminders',
                'updated_at': NOW,
                'deleted': False,
            },
        ),
        SimpleNamespace(
            id='s-deleted',
            to_dict=lambda: {
                'description': 'Synced retired',
                'exported': True,
                'export_platform': 'apple_reminders',
                'updated_at': NOW,
                'deleted': True,
            },
        ),
    ]

    pending_query = MagicMock()
    pending_query.limit.return_value.stream.return_value = iter(pending_docs)
    synced_query = MagicMock()
    synced_query.where.return_value.limit.return_value.stream.return_value = iter(synced_docs)

    items_ref = MagicMock()
    items_ref.where.side_effect = [pending_query, synced_query]

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value = items_ref
    monkeypatch.setattr(action_items_db, 'db', fake_db)

    result = action_items_db.get_pending_apple_reminders_sync(UID)

    assert [item['id'] for item in result['pending_export']] == ['p-live']
    assert [item['id'] for item in result['synced_items']] == ['s-live']

    # Verify retire_action_items_for_conversation clears sync_requested on retired rows.
    removed_doc = SimpleNamespace(id='t-retired', reference=MagicMock())
    retire_query = MagicMock()
    retire_query.stream.return_value = [removed_doc]
    items_ref.where.side_effect = None
    items_ref.where.return_value = retire_query
    batch = MagicMock()
    fake_db.batch.return_value = batch
    monkeypatch.setattr(action_items_db, '_purge_proactivity_source', lambda *a, **k: None)
    monkeypatch.setattr(action_items_db, 'bump_action_items_list_version', lambda *a, **k: None)

    count = action_items_db.retire_action_items_for_conversation(UID, CONV_ID, active_ids=[])
    assert count == 1
    patch_data = batch.update.call_args.args[1]
    assert patch_data['deleted'] is True
    assert patch_data['sync_requested'] is False

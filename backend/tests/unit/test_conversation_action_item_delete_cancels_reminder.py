import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

from models.conversation import DeleteActionItemRequest
from routers import conversations as conversations_router

UID = 'uid-conversation-task-delete'
DUE = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)


class _Item:
    def __init__(self, description):
        self.description = description

    def model_dump(self):
        return {'description': self.description}


def _delete_task(monkeypatch, tasks, description='Send the budget'):
    cancelled = []
    deleted = []
    vectors = []
    conversation = SimpleNamespace(structured=SimpleNamespace(action_items=[_Item(description)]))
    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', lambda uid, cid: conversation)
    monkeypatch.setattr(conversations_router, 'deserialize_conversation', lambda convo: convo)
    monkeypatch.setattr(
        conversations_router.conversations_db, 'update_conversation_action_items', lambda uid, cid, items: None
    )
    monkeypatch.setattr(
        conversations_router.action_items_db, 'get_action_items_by_conversation', lambda uid, cid: list(tasks)
    )
    monkeypatch.setattr(
        conversations_router.action_items_db, 'delete_action_item', lambda uid, item_id: deleted.append(item_id)
    )
    monkeypatch.setattr(conversations_router, 'delete_action_item_vector', lambda uid, item_id: vectors.append(item_id))
    notifications = ModuleType('utils.notifications')
    notifications.sync_action_item_reminder = lambda **kwargs: cancelled.append(kwargs)
    monkeypatch.setitem(sys.modules, 'utils.notifications', notifications)

    conversations_router.delete_action_item(
        DeleteActionItemRequest(description=description, completed=False), 'conv-1', uid=UID
    )
    return deleted, cancelled, vectors


def test_deleting_a_conversation_task_cancels_its_reminder(monkeypatch):
    deleted, cancelled, vectors = _delete_task(
        monkeypatch, [{'id': 'task-1', 'description': 'Send the budget', 'due_at': DUE, 'completed': False}]
    )

    assert deleted == ['task-1']
    assert vectors == ['task-1']
    assert cancelled == [
        {'user_id': UID, 'action_item_id': 'task-1', 'description': '', 'completed': True, 'due_at': None}
    ]


def test_tasks_without_an_armed_reminder_send_nothing(monkeypatch):
    deleted, cancelled, vectors = _delete_task(
        monkeypatch,
        [
            {'id': 'no-due', 'description': 'Send the budget', 'due_at': None, 'completed': False},
            {'id': 'done', 'description': 'Send the budget', 'due_at': DUE, 'completed': True},
            {'id': 'other', 'description': 'Book the venue', 'due_at': DUE, 'completed': False},
        ],
    )

    assert deleted == ['no-due', 'done']
    assert vectors == ['no-due', 'done']
    assert cancelled == []

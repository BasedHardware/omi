import sys
from datetime import datetime, timezone
from types import ModuleType

from fastapi import BackgroundTasks

from routers import conversations as conversations_router

UID = 'uid-delete-reminders'
DUE = datetime(2026, 9, 20, 15, tzinfo=timezone.utc)


def _delete_with_tasks(monkeypatch, tasks, vector_batch_fn=None):
    cancelled = []
    vectors = []
    monkeypatch.setattr(conversations_router, 'MemoryService', lambda db_client=None: object())
    monkeypatch.setattr(conversations_router, 'retraction_can_be_skipped', lambda *a, **k: True)
    monkeypatch.setattr(conversations_router, 'delete_conversation_screen_frames', lambda *a, **k: None)
    monkeypatch.setattr(conversations_router, 'delete_conversation_and_frame_evidence', lambda *a, **k: None)
    monkeypatch.setattr(conversations_router, 'delete_vector', lambda *a, **k: None)
    monkeypatch.setattr(conversations_router, 'delete_transcript_chunk_vectors', lambda *a, **k: None)
    monkeypatch.setattr(
        conversations_router,
        'delete_action_item_vectors_batch',
        vector_batch_fn or (lambda uid, ids: vectors.append((uid, list(ids)))),
        raising=False,
    )
    monkeypatch.setattr(
        conversations_router.action_items_db, 'get_action_items_by_conversation', lambda uid, cid: list(tasks)
    )
    monkeypatch.setattr(
        conversations_router.action_items_db, 'delete_action_items_for_conversation', lambda uid, cid: len(tasks)
    )
    notifications = ModuleType('utils.notifications')
    notifications.sync_action_item_reminder = lambda **kwargs: cancelled.append(kwargs)
    monkeypatch.setitem(sys.modules, 'utils.notifications', notifications)
    conversations_router.delete_conversation('conv-1', BackgroundTasks(), cascade=True, uid=UID)
    return cancelled, vectors


def test_cascade_delete_cancels_reminders_of_deleted_open_tasks(monkeypatch):
    cancelled, _vectors = _delete_with_tasks(
        monkeypatch,
        [
            {'id': 'due-open', 'due_at': DUE, 'completed': False},
            {'id': 'due-done', 'due_at': DUE, 'completed': True},
            {'id': 'no-due', 'due_at': None, 'completed': False},
        ],
    )
    assert cancelled == [
        {'user_id': UID, 'action_item_id': 'due-open', 'description': '', 'completed': True, 'due_at': None}
    ]


def test_cascade_delete_without_tasks_sends_nothing(monkeypatch):
    cancelled, vectors = _delete_with_tasks(monkeypatch, [])
    assert cancelled == []
    assert vectors == []


def test_cascade_delete_drops_the_removed_tasks_search_vectors(monkeypatch):
    """A deleted task's vector must not survive as a ghost.

    find_similar_action_items feeds the extraction prompt so the LLM can suppress
    duplicate tasks; a deleted task's orphaned vector makes a real new task look
    like a duplicate and it is silently never created.
    """
    _cancelled, vectors = _delete_with_tasks(
        monkeypatch,
        [
            {'id': 'due-open', 'due_at': DUE, 'completed': False},
            {'id': 'no-due', 'due_at': None, 'completed': False},
        ],
    )
    assert vectors == [(UID, ['due-open', 'no-due'])]


def test_cascade_delete_cancels_reminders_even_if_vector_delete_raises(monkeypatch):
    """A Pinecone failure when dropping task vectors must not prevent reminder cancellation."""

    def _exploding_delete_vectors(uid, ids):
        raise RuntimeError("Pinecone unavailable")

    cancelled, _vectors = _delete_with_tasks(
        monkeypatch,
        [
            {'id': 'due-open', 'due_at': DUE, 'completed': False},
        ],
        vector_batch_fn=_exploding_delete_vectors,
    )
    assert cancelled == [
        {'user_id': UID, 'action_item_id': 'due-open', 'description': '', 'completed': True, 'due_at': None}
    ]

"""Unit tests ensuring chat_first block validation rejects soft-deleted conversation & task tombstones.

Contract:
- A soft-deleted conversation (`deleted: True`) or task (`deleted: True`) must be treated as unavailable.
- POST /v1/chat-first/blocks/validate must reject blocks referencing tombstones with `entity_unavailable`.
- Active conversations and tasks must continue to validate and produce accepted receipts without regression.
"""

from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.task_intelligence import TaskWorkflowControl
import routers.chat_first as chat_first_router
from tests.unit.universal_memory_test_helpers import configure_universal_memory


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_first_router.router)
    app.dependency_overrides[chat_first_router.auth.get_current_user_uid] = lambda: 'user-1'
    return TestClient(app)


def _enable_chat_first(monkeypatch, *, generation: int = 7) -> None:
    configure_universal_memory(monkeypatch, 'user-1')
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(
            workflow_mode='read', account_generation=generation, chat_first_ui_enabled=True
        ),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )


def _request(*, generation: int = 7, blocks: list[dict]) -> dict:
    return {
        'source_surface': 'main_chat',
        'control_generation': generation,
        'owner_fence': 'user-1',
        'run_id': 'run-1',
        'attempt_id': 'attempt-1',
        'blocks': blocks,
    }


def test_validate_blocks_rejects_soft_deleted_task_card(monkeypatch):
    """TaskCardSpec referencing a soft-deleted task returns entity_unavailable."""
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'deleted': True, 'is_locked': False},
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(blocks=[{'type': 'taskCard', 'task_id': 'deleted-task-1'}]),
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}


def test_validate_blocks_rejects_soft_deleted_capture_link(monkeypatch):
    """CaptureLinkSpec referencing a soft-deleted conversation returns entity_unavailable."""
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.conversations_db,
        'get_conversation',
        lambda uid, cid, **kwargs: {
            'id': cid,
            'source': 'omi',
            'deleted': True,
            'discarded': False,
            'is_locked': False,
        },
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {
                    'type': 'captureLink',
                    'conversation_id': 'deleted-capture-1',
                    'summary': 'Deleted conversation summary',
                }
            ]
        ),
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}


def test_validate_blocks_rejects_soft_deleted_conversation_link(monkeypatch):
    """ConversationLinkSpec referencing a soft-deleted conversation returns entity_unavailable."""
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.conversations_db,
        'get_conversation',
        lambda uid, cid, **kwargs: {
            'id': cid,
            'source': 'desktop',
            'external_data': {'conversation_role': 'meeting'},
            'status': 'completed',
            'deleted': True,
            'discarded': False,
            'is_locked': False,
        },
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {
                    'type': 'conversationLink',
                    'conversation_id': 'deleted-conv-1',
                    'summary': 'Deleted meeting summary',
                }
            ]
        ),
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}


def test_validate_blocks_rejects_question_card_with_soft_deleted_subject(monkeypatch):
    """QuestionCardSpec referencing a soft-deleted task or capture subject returns entity_unavailable."""
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'deleted': True, 'is_locked': False},
    )
    monkeypatch.setattr(
        chat_first_router.conversations_db,
        'get_conversation',
        lambda uid, cid, **kwargs: {
            'id': cid,
            'source': 'omi',
            'deleted': True,
            'discarded': False,
            'is_locked': False,
        },
    )

    # 1. Subject task is deleted
    res_task = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {
                    'type': 'questionCard',
                    'question_id': 'q-1',
                    'text': 'Follow up on deleted task?',
                    'subject': {'kind': 'task', 'id': 'del-task'},
                    'options': [{'option_id': 'opt-1', 'label': 'Yes', 'prepared_answer': 'yes'}],
                }
            ]
        ),
    )
    assert res_task.status_code == 200
    assert res_task.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}

    # 2. Subject capture is deleted
    res_capture = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {
                    'type': 'questionCard',
                    'question_id': 'q-2',
                    'text': 'Follow up on deleted capture?',
                    'subject': {'kind': 'capture', 'id': 'del-capture'},
                    'options': [{'option_id': 'opt-2', 'label': 'Yes', 'prepared_answer': 'yes'}],
                }
            ]
        ),
    )
    assert res_capture.status_code == 200
    assert res_capture.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}


def test_validate_blocks_accepts_active_entities(monkeypatch):
    """Active tasks, captures, and conversations validate successfully with accepted status."""
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'deleted': False, 'is_locked': False},
    )
    monkeypatch.setattr(
        chat_first_router.conversations_db,
        'get_conversation',
        lambda uid, cid, **kwargs: {
            'id': cid,
            'source': 'omi',
            'deleted': False,
            'discarded': False,
            'is_locked': False,
        },
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {'type': 'taskCard', 'task_id': 'active-task-1'},
                {
                    'type': 'captureLink',
                    'conversation_id': 'active-capture-1',
                    'summary': 'Active capture summary',
                },
            ]
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data['accepted'] is True
    assert data['code'] == 'accepted'
    assert len(data['blocks']) == 2

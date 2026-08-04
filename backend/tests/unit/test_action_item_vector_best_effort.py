"""Action-item vector indexing must never fail the write it follows.

Prod incident (2026-07-29 20:47-20:51Z, `backend`/`backend-sync`): every
embeddings call returned ``openai.NotFoundError: 404 Invalid URL (POST
/v1/embeddings)``. ``PATCH /v1/action-items/{id}`` returned HTTP 500 *after*
``action_items_db.update_action_item`` had already committed the Firestore write
— the user saw "failed" on a task edit that had actually landed (and retries
re-applied it). The create / batch / accept-share paths had the same shape.

Index maintenance is best-effort by design (like ``find_similar_action_items``):
losing the vector only drops the task out of semantic search until it is next
indexed, which is strictly better than reporting a committed write as failed.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import vector_db
from routers import action_items as action_items_router
from utils.other import endpoints as auth


class _EmbeddingsOutage:
    """Stands in for `clients.embeddings` while the embeddings provider is 404ing."""

    def embed_query(self, text):
        raise RuntimeError('404 Invalid URL (POST /v1/embeddings)')

    def embed_documents(self, texts):
        raise RuntimeError('404 Invalid URL (POST /v1/embeddings)')


@pytest.fixture
def embeddings_down(monkeypatch):
    monkeypatch.setattr(vector_db, 'index', MagicMock(), raising=False)
    monkeypatch.setattr(vector_db, 'embeddings', _EmbeddingsOutage(), raising=False)


def test_upsert_action_item_vector_degrades_to_none(embeddings_down):
    assert vector_db.upsert_action_item_vector('uid-1', 'task-1', 'Ship the fix') is None


def test_upsert_action_item_vectors_batch_degrades_to_zero(embeddings_down):
    items = [
        {'action_item_id': 'task-1', 'description': 'Ship the fix'},
        {'action_item_id': 'task-2', 'description': 'Write the test'},
    ]
    assert vector_db.upsert_action_item_vectors_batch('uid-1', items) == 0


@pytest.fixture
def committed_description_edit(monkeypatch):
    """Firestore accepts the edit; only the vector index is broken."""
    existing = {'id': 'task-1', 'description': 'Old text', 'completed': False}
    updated = {'id': 'task-1', 'description': 'New text', 'completed': False}

    monkeypatch.setattr(action_items_router, '_get_valid_action_item', lambda *args, **kwargs: existing)
    monkeypatch.setattr(action_items_router.task_links, 'validate_task_links', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        action_items_router.action_items_db, 'update_action_item', lambda *args, **kwargs: True, raising=False
    )
    monkeypatch.setattr(
        action_items_router.action_items_db, 'get_action_item', lambda *args, **kwargs: updated, raising=False
    )
    monkeypatch.setattr(action_items_router, 'sync_action_item_reminder', lambda *args, **kwargs: None, raising=False)


def test_patch_action_item_succeeds_while_embeddings_are_down(embeddings_down, committed_description_edit):
    """The handler must return the updated task, not raise, when indexing it fails."""
    response = action_items_router.update_action_item(
        'task-1',
        action_items_router.ActionItemUpdateRequest(description='New text'),
        uid='uid-1',
    )

    assert response.description == 'New text'


def test_patch_action_item_http_200_while_embeddings_are_down(embeddings_down, committed_description_edit):
    """The same edit over HTTP: the client saw 500 during the incident even though the
    write had committed, so assert the real status code the app returns."""
    app = FastAPI()
    app.include_router(action_items_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-1'

    response = TestClient(app).patch('/v1/action-items/task-1', json={'description': 'New text'})

    assert response.status_code == 200
    assert response.json()['description'] == 'New text'

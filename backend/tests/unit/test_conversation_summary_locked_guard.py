"""Unit tests ensuring PATCH /v1/conversations/{conversation_id}/summary enforces

access validation (_get_valid_conversation_by_id) against paywalled (is_locked)
and soft-deleted conversations.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as conversations_db
from routers import conversations as routes

UID = "test-user-summary-guard"
CONV_LOCKED = "conv-locked-123"
CONV_DELETED = "conv-deleted-456"
CONV_VALID = "conv-valid-789"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as test_client:
        yield test_client


def _setup_mock_db(monkeypatch):
    mock_conversations = {
        CONV_LOCKED: {
            "id": CONV_LOCKED,
            "is_locked": True,
            "deleted": False,
            "structured": {"overview": "Original locked overview"},
        },
        CONV_DELETED: {
            "id": CONV_DELETED,
            "is_locked": False,
            "deleted": True,
            "structured": {"overview": "Original deleted overview"},
        },
        CONV_VALID: {
            "id": CONV_VALID,
            "is_locked": False,
            "deleted": False,
            "structured": {"overview": "Original valid overview"},
        },
    }

    def mock_get_conversation(uid, conversation_id, **kwargs):
        return mock_conversations.get(conversation_id)

    updated_calls = []

    def mock_update_conversation_summary(uid, conversation_id, app_id, content):
        if conversation_id not in mock_conversations:
            return "not_found"
        updated_calls.append((conversation_id, app_id, content))
        return "ok"

    monkeypatch.setattr(conversations_db, "get_conversation", mock_get_conversation)
    monkeypatch.setattr(conversations_db, "update_conversation_summary", mock_update_conversation_summary)
    return updated_calls


def test_patch_conversation_summary_rejects_locked_conversation_with_402(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_LOCKED}/summary",
        json={"content": "Attempted edit on locked conversation"},
    )

    assert response.status_code == 402
    assert response.json()["detail"] == "A paid plan is required to access this conversation."
    assert updated_calls == []


def test_patch_conversation_summary_rejects_soft_deleted_conversation_with_404(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_DELETED}/summary",
        json={"content": "Attempted edit on deleted conversation"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
    assert updated_calls == []


def test_patch_conversation_summary_rejects_nonexistent_conversation_with_404(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        "/v1/conversations/nonexistent-id/summary",
        json={"content": "Attempted edit on nonexistent conversation"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
    assert updated_calls == []


def test_patch_conversation_summary_allows_valid_conversation(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_VALID}/summary",
        json={"content": "Updated valid summary content"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "Ok"}
    assert len(updated_calls) == 1
    assert updated_calls[0] == (CONV_VALID, None, "Updated valid summary content")

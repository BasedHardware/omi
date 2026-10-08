"""Unit tests ensuring PATCH /v1/conversations/{conversation_id}/segments/text enforces

access validation (_get_valid_conversation_by_id) against soft-deleted and paywalled conversations.
"""

from __future__ import annotations

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversations as conversations_db
from routers import conversations as routes
from utils.conversations import transcript_chunks

UID = "test-user-segment-text-guard"
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
            "transcript_segments": [{"id": "seg-1", "text": "Original locked segment"}],
        },
        CONV_DELETED: {
            "id": CONV_DELETED,
            "is_locked": False,
            "deleted": True,
            "transcript_segments": [{"id": "seg-2", "text": "Original deleted segment"}],
        },
        CONV_VALID: {
            "id": CONV_VALID,
            "is_locked": False,
            "deleted": False,
            "transcript_segments": [{"id": "seg-3", "text": "Original valid segment"}],
        },
    }

    def mock_get_conversation(uid, conversation_id, **kwargs):
        return mock_conversations.get(conversation_id)

    updated_calls = []
    monkeypatch.setattr(transcript_chunks, "refresh_transcript_chunks_after_edit", lambda *_args: None)

    def mock_update_conversation_segment_text(uid, conversation_id, segment_id, text):
        if conversation_id not in mock_conversations:
            return "not_found"
        conv = mock_conversations[conversation_id]
        segments = conv.get("transcript_segments", [])
        if not any(s.get("id") == segment_id for s in segments):
            return "segment_not_found"
        updated_calls.append((conversation_id, segment_id, text))
        return "ok"

    monkeypatch.setattr(conversations_db, "get_conversation", mock_get_conversation)
    monkeypatch.setattr(conversations_db, "update_conversation_segment_text", mock_update_conversation_segment_text)
    return updated_calls


def test_patch_conversation_segment_text_rejects_soft_deleted_conversation_with_404(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_DELETED}/segments/text",
        json={"segment_id": "seg-2", "text": "Attempted edit on deleted conversation"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
    assert updated_calls == []


def test_patch_conversation_segment_text_rejects_locked_conversation_with_402(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_LOCKED}/segments/text",
        json={"segment_id": "seg-1", "text": "Attempted edit on locked conversation"},
    )

    assert response.status_code == 402
    assert response.json()["detail"] == "A paid plan is required to access this conversation."
    assert updated_calls == []


def test_patch_conversation_segment_text_rejects_nonexistent_conversation_with_404(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        "/v1/conversations/nonexistent-id/segments/text",
        json={"segment_id": "seg-1", "text": "Attempted edit on nonexistent conversation"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
    assert updated_calls == []


def test_patch_conversation_segment_text_allows_valid_conversation(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_VALID}/segments/text",
        json={"segment_id": "seg-3", "text": "Updated text"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "Ok"}
    assert updated_calls == [(CONV_VALID, "seg-3", "Updated text")]


def test_patch_conversation_segment_text_rejects_nonexistent_segment_with_404(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)

    response = client.patch(
        f"/v1/conversations/{CONV_VALID}/segments/text",
        json={"segment_id": "nonexistent-seg", "text": "Updated text"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Segment not found"
    assert updated_calls == []


def test_successful_edit_refreshes_search_after_the_mutation(monkeypatch, client):
    updated_calls = _setup_mock_db(monkeypatch)
    refreshes = []

    def refresh(uid, conversation_id):
        assert updated_calls == [(CONV_VALID, "seg-3", "Updated text")]
        refreshes.append((uid, conversation_id))

    monkeypatch.setattr(transcript_chunks, "refresh_transcript_chunks_after_edit", refresh)
    response = client.patch(
        f"/v1/conversations/{CONV_VALID}/segments/text",
        json={"segment_id": "seg-3", "text": "Updated text"},
    )
    assert response.status_code == 200
    assert refreshes == [(UID, CONV_VALID)]

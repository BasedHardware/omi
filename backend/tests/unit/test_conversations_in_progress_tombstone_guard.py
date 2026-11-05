"""Unit tests for in-progress conversation tombstone rejection guard in POST /v1/conversations."""

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from routers import conversations as conversations_router
import database.conversations as conversations_db


def test_process_in_progress_conversation_rejects_none(monkeypatch: pytest.MonkeyPatch):
    """When retrieve_in_progress_conversation returns None, the endpoint must raise 404."""
    monkeypatch.setattr(conversations_router, "retrieve_in_progress_conversation", lambda uid: None)

    with pytest.raises(HTTPException) as exc_info:
        conversations_router.process_in_progress_conversation(request=None, uid="test-uid")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Conversation in progress not found"


def test_process_in_progress_conversation_rejects_soft_deleted_tombstone(monkeypatch: pytest.MonkeyPatch):
    """Defense-in-depth: If a soft-deleted tombstone reaches the router, it must raise 404."""
    tombstone = {
        "id": "conv-tombstone-123",
        "status": "in_progress",
        "deleted": True,
    }
    monkeypatch.setattr(conversations_router, "retrieve_in_progress_conversation", lambda uid: tombstone)

    with pytest.raises(HTTPException) as exc_info:
        conversations_router.process_in_progress_conversation(request=None, uid="test-uid")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Conversation in progress not found"

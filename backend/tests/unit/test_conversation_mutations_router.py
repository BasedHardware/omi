from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.conversation_mutations import (
    ConversationMutationConflictError,
    ConversationMutationLockedError,
    ConversationMutationNotFoundError,
    ConversationMutationReceiptUnavailableError,
)
from routers import conversation_mutations as router_module


def _client(monkeypatch, uid: str = "user-123") -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: uid
    return TestClient(app)


def _valid_request_payload() -> dict:
    return {
        "client_mutation_id": "mut_12345",
        "base_revision": datetime.now(timezone.utc).isoformat(),
        "operation": {
            "type": "set_title",
            "title": "Updated Strategy Discussion",
        },
    }


def _dummy_response_dict() -> dict:
    return {
        "status": "ok",
        "client_mutation_id": "mut_12345",
        "conversation_id": "conv_abc123",
        "conversation": {
            "revision": datetime.now(timezone.utc).isoformat(),
            "title": "Updated Strategy Discussion",
            "starred": False,
            "folder_id": None,
            "visibility": "private",
        },
    }


def test_apply_mutation_applied_success(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    def mock_apply(uid, conversation_id, *, client_mutation_id, base_revision, operation):
        assert uid == "user-123"
        assert conversation_id == "conv_abc123"
        assert client_mutation_id == "mut_12345"
        assert operation["type"] == "set_title"
        return _dummy_response_dict(), False

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["conversation_id"] == "conv_abc123"
    assert data["conversation"]["title"] == "Updated Strategy Discussion"
    assert any(event == "conversation_sync_mutation" and kwargs.get("outcome") == "applied" for event, kwargs in events)


def test_apply_mutation_replayed_success(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    def mock_apply(uid, conversation_id, *, client_mutation_id, base_revision, operation):
        return _dummy_response_dict(), True

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 200
    assert any(
        event == "conversation_sync_mutation" and kwargs.get("outcome") == "replayed" for event, kwargs in events
    )


@pytest.mark.parametrize("invalid_id", ["", "   ", "%20"])
def test_apply_mutation_rejects_empty_or_whitespace_conversation_id(monkeypatch, invalid_id):
    client = _client(monkeypatch)
    response = client.post(f"/v1/conversations/{invalid_id}/mutations", json=_valid_request_payload())
    # Should either match route and return 400 'Valid conversation_id is required' or 404 for empty path
    if response.status_code == 400:
        assert response.json()["detail"] == "Valid conversation_id is required"
    else:
        assert response.status_code in (404, 405)


def test_apply_mutation_not_found(monkeypatch):
    def mock_apply(*args, **kwargs):
        raise ConversationMutationNotFoundError("Conversation does not exist")

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_missing/mutations", json=_valid_request_payload())
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_apply_mutation_plan_locked(monkeypatch):
    def mock_apply(*args, **kwargs):
        raise ConversationMutationLockedError("Locked conversation")

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_locked/mutations", json=_valid_request_payload())
    assert response.status_code == 402
    assert response.json()["detail"] == "A paid plan is required to access this conversation."


def test_apply_mutation_conflict(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    conflict_data = {
        "status": "conflict",
        "code": "base_revision_mismatch",
        "client_mutation_id": "mut_12345",
        "conversation_id": "conv_abc123",
        "conversation": {
            "revision": datetime.now(timezone.utc).isoformat(),
            "title": "Remote Title",
            "starred": True,
            "folder_id": None,
            "visibility": "private",
        },
    }

    def mock_apply(*args, **kwargs):
        raise ConversationMutationConflictError(conflict_data)

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 409
    data = response.json()
    assert data["status"] == "conflict"
    assert data["code"] == "base_revision_mismatch"
    assert any(
        event == "conversation_sync_mutation" and kwargs.get("outcome") == "conflict" for event, kwargs in events
    )


def test_apply_mutation_receipt_unavailable(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    def mock_apply(*args, **kwargs):
        raise ConversationMutationReceiptUnavailableError("Receipt read failed")

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 503
    assert response.json()["detail"] == "Conversation mutation acknowledgement unavailable"
    assert any(event == "conversation_sync_mutation" and kwargs.get("outcome") == "error" for event, kwargs in events)


def test_apply_mutation_value_error_returns_400(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    def mock_apply(*args, **kwargs):
        raise ValueError("unsupported conversation mutation: custom_op")

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 400
    assert "unsupported conversation mutation" in response.json()["detail"]
    assert any(event == "conversation_sync_mutation" and kwargs.get("outcome") == "error" for event, kwargs in events)


def test_apply_mutation_unexpected_internal_error_masks_details(monkeypatch):
    events = []
    monkeypatch.setattr(router_module, "record_product_event", lambda event, **kwargs: events.append((event, kwargs)))

    def mock_apply(*args, **kwargs):
        raise RuntimeError("Fatal firestore internal connection error with token sk-998877665544332211")

    monkeypatch.setattr(router_module.mutations_db, "apply_conversation_sync_mutation", mock_apply)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv_abc123/mutations", json=_valid_request_payload())

    assert response.status_code == 500
    # Crucial: raw internal error message and sensitive tokens are NOT exposed in HTTP response
    assert response.json()["detail"] == "Unable to process conversation mutation"
    assert "sk-998877665544332211" not in response.text
    assert any(event == "conversation_sync_mutation" and kwargs.get("outcome") == "error" for event, kwargs in events)


def test_apply_mutation_payload_validation_rejects_malformed_fields(monkeypatch):
    client = _client(monkeypatch)
    # Extra unexpected fields forbidden by model_config = {'extra': 'forbid'}
    bad_payload = _valid_request_payload()
    bad_payload["unexpected_injected_field"] = "malicious"

    response = client.post("/v1/conversations/conv_abc123/mutations", json=bad_payload)
    assert response.status_code == 422

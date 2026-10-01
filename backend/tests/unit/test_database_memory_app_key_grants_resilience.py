"""Unit tests verifying defensive guards and resilience in memory_app_key_grants."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import GoogleAPICallError, NotFound

from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_DOC_ID,
    APP_KEY_MEMORY_GRANT_SUBPATH,
    APP_KEY_MEMORY_GRANTS_COLLECTION,
    MAX_SCOPES_PER_GRANT,
    app_key_memory_grants_document_path,
    build_app_key_scope_grant_contract_state,
    read_app_key_memory_grants_state,
    remove_developer_api_key_memory_grant,
    seed_developer_api_key_memory_grant,
    seed_mcp_api_key_memory_grant,
    _validate_non_empty_string,
)


class _MockDoc:
    def __init__(self, data=None, exists=True, get_exc=None, update_exc=None):
        self.data = data or {}
        self.exists = exists
        self.get_exc = get_exc
        self.update_exc = update_exc
        self.sets = []
        self.updates = []

    def get(self):
        if self.get_exc:
            raise self.get_exc
        return self

    def to_dict(self):
        return self.data

    def set(self, payload, merge=False):
        self.sets.append((payload, merge))

    def update(self, payload):
        if self.update_exc:
            raise self.update_exc
        self.updates.append(payload)


class _MockClient:
    def __init__(self, docs=None):
        self.docs = docs or {}

    def collection(self, path):
        return self

    def document(self, path):
        if path not in self.docs:
            self.docs[path] = _MockDoc(exists=False)
        return self.docs[path]


def test_validate_non_empty_string():
    """Verify _validate_non_empty_string rejects invalid types, whitespace, and path slashes."""
    with pytest.raises(ValueError, match="test_id must be a non-empty string without whitespace"):
        _validate_non_empty_string("", "test_id")
    with pytest.raises(ValueError, match="test_id must be a non-empty string without whitespace"):
        _validate_non_empty_string("   ", "test_id")
    with pytest.raises(ValueError, match="test_id must be a non-empty string without whitespace"):
        _validate_non_empty_string(None, "test_id")
    with pytest.raises(ValueError, match="test_id cannot contain path delimiters"):
        _validate_non_empty_string("id/with/slash", "test_id")

    assert _validate_non_empty_string("  valid-id  ", "test_id") == "valid-id"


def test_app_key_memory_grants_document_path():
    """Verify document path construction and validation."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        app_key_memory_grants_document_path("")

    path = app_key_memory_grants_document_path("user-456")
    assert path == f"users/user-456/{APP_KEY_MEMORY_GRANT_SUBPATH}"


def test_read_app_key_memory_grants_state_validates_inputs():
    """Verify read_app_key_memory_grants_state rejects empty uid or None db_client."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        read_app_key_memory_grants_state("", mock_client)

    with pytest.raises(ValueError, match="db_client is required"):
        read_app_key_memory_grants_state("user-1", None)


def test_read_app_key_memory_grants_state_handles_not_found():
    """Verify NotFound exception returns missing state result."""
    doc = _MockDoc(get_exc=NotFound("Document not found"))
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value = doc

    result = read_app_key_memory_grants_state("user-1", mock_client)
    assert result.present is False
    assert result.malformed is False
    assert result.reason == "missing_app_key_memory_grants_state"


def test_read_app_key_memory_grants_state_reraises_google_api_call_error():
    """Verify GoogleAPICallError is not swallowed."""
    doc = _MockDoc(get_exc=GoogleAPICallError("Internal error"))
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value = doc

    with pytest.raises(GoogleAPICallError, match="Internal error"):
        read_app_key_memory_grants_state("user-1", mock_client)


def test_build_app_key_scope_grant_contract_state_validations():
    """Verify identifier and scope validations on contract builder."""
    with pytest.raises(ValueError, match="consumer must be a non-empty string"):
        build_app_key_scope_grant_contract_state(
            consumer="", app_id="app-1", key_id="key-1", scopes=["memories.read"]
        )

    with pytest.raises(ValueError, match="scopes must be a list of non-empty strings"):
        build_app_key_scope_grant_contract_state(
            consumer="c", app_id="app-1", key_id="key-1", scopes="not-a-list"  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="scopes must be a list of non-empty strings"):
        build_app_key_scope_grant_contract_state(
            consumer="c", app_id="app-1", key_id="key-1", scopes=["memories.read", "  "]
        )

    oversized_scopes = [f"scope_{i}" for i in range(MAX_SCOPES_PER_GRANT + 1)]
    with pytest.raises(ValueError, match="scopes list exceeds maximum allowed length"):
        build_app_key_scope_grant_contract_state(
            consumer="c", app_id="app-1", key_id="key-1", scopes=oversized_scopes
        )


def test_seed_developer_api_key_memory_grant_validates_and_writes(monkeypatch):
    """Verify seed_developer_api_key_memory_grant validates inputs and performs merge write."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        seed_developer_api_key_memory_grant("", "key-1", db_client=mock_client)

    with pytest.raises(ValueError, match="key_id must be a non-empty string"):
        seed_developer_api_key_memory_grant("user-1", "", db_client=mock_client)

    import database._client as db_client_module
    monkeypatch.setattr(db_client_module, "db", None)
    with pytest.raises(ValueError, match="db_client is required"):
        seed_developer_api_key_memory_grant("user-1", "key-1", db_client=None)

    path = seed_developer_api_key_memory_grant(
        "user-1",
        "key-1",
        default_read=True,
        write=True,
        db_client=mock_client,
    )
    assert path == f"users/user-1/{APP_KEY_MEMORY_GRANT_SUBPATH}"
    doc = mock_client.docs[path]
    assert len(doc.sets) == 1
    contract, merge = doc.sets[0]
    assert merge is True
    assert "developer_api" in contract["grants"]
    key_entry = contract["grants"]["developer_api"]["apps"]["developer_api"]["keys"]["key-1"]
    assert key_entry["default_read"] is True
    assert key_entry["write"] is True
    assert key_entry["scopes"] == ["memories.read", "memories.write"]


def test_seed_mcp_api_key_memory_grant_validates_and_writes():
    """Verify seed_mcp_api_key_memory_grant validates inputs and sets MCP consumer."""
    mock_client = _MockClient()
    path = seed_mcp_api_key_memory_grant(
        "user-2",
        "key-2",
        default_read=True,
        write=False,
        db_client=mock_client,
    )
    doc = mock_client.docs[path]
    contract, merge = doc.sets[0]
    assert merge is True
    key_entry = contract["grants"]["mcp"]["apps"]["mcp-api"]["keys"]["key-2"]
    assert key_entry["default_read"] is True
    assert key_entry["write"] is False
    assert key_entry["scopes"] == ["memories.read"]


def test_remove_developer_api_key_memory_grant_validates_and_removes(monkeypatch):
    """Verify remove_developer_api_key_memory_grant handles missing and existing documents."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        remove_developer_api_key_memory_grant("", "key-1", db_client=mock_client)

    import database._client as db_client_module
    monkeypatch.setattr(db_client_module, "db", None)
    with pytest.raises(ValueError, match="db_client is required"):
        remove_developer_api_key_memory_grant("user-1", "key-1", db_client=None)

    # Missing doc does not raise
    path = f"users/user-1/{APP_KEY_MEMORY_GRANT_SUBPATH}"
    mock_client.docs[path] = _MockDoc(exists=False)
    remove_developer_api_key_memory_grant("user-1", "key-1", db_client=mock_client)
    assert len(mock_client.docs[path].updates) == 0


    # NotFound on get does not raise
    mock_client.docs[path] = _MockDoc(get_exc=NotFound("missing"))
    remove_developer_api_key_memory_grant("user-1", "key-1", db_client=mock_client)

    # Existing doc issues update
    existing_doc = _MockDoc(data={"grants": {}}, exists=True)
    mock_client.docs[path] = existing_doc
    remove_developer_api_key_memory_grant("user-1", "key-1", db_client=mock_client)
    assert len(existing_doc.updates) == 1

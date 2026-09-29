"""Hermetic unit tests for backend/database/dev_api_key.py resilience, validation, and DI."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import database.dev_api_key as dev_api_key_db
import database.redis_db as redis_db
from database.api_key_metadata import (
    ApiKeyAuthLookupResult,
    ApiKeyCacheReadMode,
    ApiKeyCacheReadResult,
    ApiKeyRevocationUnavailableError,
    ApiKeyValidationError,
)
from models.dev_api_key import DevApiKey
from utils.scopes import READ_ONLY_SCOPES


def test_clean_user_id_validates_and_normalizes():
    # Valid IDs
    assert dev_api_key_db._clean_user_id("user-123") == "user-123"
    assert dev_api_key_db._clean_user_id("  user-abc  ") == "user-abc"
    assert dev_api_key_db._clean_user_id("0x1234567890abcdef") == "0x1234567890abcdef"

    # Invalid / pathological IDs
    assert dev_api_key_db._clean_user_id("") == ""
    assert dev_api_key_db._clean_user_id("   ") == ""
    assert dev_api_key_db._clean_user_id(None) == ""
    assert dev_api_key_db._clean_user_id(12345) == ""  # type: ignore
    assert dev_api_key_db._clean_user_id("users/admin") == ""
    assert dev_api_key_db._clean_user_id("users\\admin") == ""
    assert dev_api_key_db._clean_user_id("../traversal") == ""
    assert dev_api_key_db._clean_user_id("a" * 129) == ""


def test_clean_key_name_validates_and_normalizes():
    # Valid names
    assert dev_api_key_db._clean_key_name("Production Key") == "Production Key"
    assert dev_api_key_db._clean_key_name("  Test Key 1  ") == "Test Key 1"

    # Missing / non-string / empty
    with pytest.raises(ApiKeyValidationError, match="must be a non-empty string"):
        dev_api_key_db._clean_key_name("")
    with pytest.raises(ApiKeyValidationError, match="must be a non-empty string"):
        dev_api_key_db._clean_key_name("    ")
    with pytest.raises(ApiKeyValidationError, match="must be a non-empty string"):
        dev_api_key_db._clean_key_name(None)  # type: ignore

    # Too long (> 128 chars)
    with pytest.raises(ApiKeyValidationError, match="cannot exceed 128 characters"):
        dev_api_key_db._clean_key_name("k" * 129)

    # Contains raw API key pattern
    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        dev_api_key_db._clean_key_name("omi_dev_0123456789abcdef0123456789abcdef")


def test_create_dev_key_rejects_invalid_inputs():
    with pytest.raises(ApiKeyValidationError, match="Valid user ID is required"):
        dev_api_key_db.create_dev_key("", "Valid Name")

    with pytest.raises(ApiKeyValidationError, match="Valid user ID is required"):
        dev_api_key_db.create_dev_key("   ", "Valid Name")

    with pytest.raises(ApiKeyValidationError, match="Valid user ID is required"):
        dev_api_key_db.create_dev_key("user/malicious", "Valid Name")

    with pytest.raises(ApiKeyValidationError, match="must be a non-empty string"):
        dev_api_key_db.create_dev_key("user-1", "")

    with pytest.raises(ApiKeyValidationError, match="cannot exceed 128 characters"):
        dev_api_key_db.create_dev_key("user-1", "x" * 130)


def test_create_dev_key_with_firestore_di_and_default_scopes():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc

    raw_key, api_key = dev_api_key_db.create_dev_key(
        user_id="  user-prod-1  ",
        name="  Mobile App Key  ",
        scopes=None,
        firestore_client=mock_client,
    )

    assert raw_key.startswith("omi_dev_")
    assert len(raw_key) == 8 + 32  # omi_dev_ prefix + 32 hex chars
    assert api_key.name == "Mobile App Key"
    assert api_key.scopes == READ_ONLY_SCOPES  # Default read-only scopes

    mock_client.collection.assert_called_once_with("dev_api_keys")
    mock_doc.set.assert_called_once()
    stored_doc = mock_doc.set.call_args[0][0]
    assert stored_doc["user_id"] == "user-prod-1"
    assert stored_doc["name"] == "Mobile App Key"
    assert stored_doc["app_id"] == "developer_api"
    assert stored_doc["scopes"] == READ_ONLY_SCOPES


def test_create_dev_key_seeds_memory_grants_when_requested():
    mock_client = MagicMock()
    with patch("database.dev_api_key.seed_developer_api_key_memory_grant") as mock_seed:
        raw_key, api_key = dev_api_key_db.create_dev_key(
            user_id="user-1",
            name="Writer Key",
            scopes=["memories:read", "memories:write"],
            firestore_client=mock_client,
        )
        assert mock_seed.called
        call_kwargs = mock_seed.call_args[1]
        assert call_kwargs["default_read"] is True
        assert call_kwargs["write"] is True
        assert call_kwargs["db_client"] is mock_client


def test_get_dev_keys_for_user_with_invalid_uid_returns_empty():
    for bad_uid in ["", "   ", "user/admin", "../bad", None]:
        keys, repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info(bad_uid)  # type: ignore
        assert keys == []
        assert repairs == frozenset()

        keys_simple = dev_api_key_db.get_dev_keys_for_user(bad_uid)  # type: ignore
        assert keys_simple == []


def test_get_dev_keys_for_user_fail_open_on_firestore_error():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query
    mock_query.stream.side_effect = Exception("Firestore 503 Service Unavailable")

    keys, repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1", firestore_client=mock_client)
    assert keys == []
    assert repairs == frozenset()

    keys_simple = dev_api_key_db.get_dev_keys_for_user("user-1", firestore_client=mock_client)
    assert keys_simple == []


def test_get_dev_keys_for_user_successful_retrieval_and_ordering():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query

    t1 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

    doc1 = MagicMock()
    doc1.id = "key-older"
    doc1.to_dict.return_value = {
        "id": "key-older",
        "name": "Key Older",
        "key_prefix": "omi_dev_1111...aaaa",
        "created_at": t1,
        "app_id": "developer_api",
        "scopes": ["memories:read"],
    }

    doc2 = MagicMock()
    doc2.id = "key-newer"
    doc2.to_dict.return_value = {
        "id": "key-newer",
        "name": "Key Newer",
        "key_prefix": "omi_dev_2222...bbbb",
        "created_at": t2,
        "app_id": "developer_api",
        "scopes": ["memories:read", "memories:write"],
    }

    mock_query.stream.return_value = [doc1, doc2]

    keys, repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1", firestore_client=mock_client)
    assert len(keys) == 2
    assert keys[0].id == "key-newer"  # Newer first
    assert keys[1].id == "key-older"
    assert repairs == frozenset()


def test_delete_dev_key_idempotent_on_invalid_inputs():
    mock_client = MagicMock()
    # Invalid user_id or key_id should return safely without touching DB
    dev_api_key_db.delete_dev_key("", "key-1", firestore_client=mock_client)
    dev_api_key_db.delete_dev_key("   ", "key-1", firestore_client=mock_client)
    dev_api_key_db.delete_dev_key("user/bad", "key-1", firestore_client=mock_client)
    dev_api_key_db.delete_dev_key("user-1", "", firestore_client=mock_client)
    dev_api_key_db.delete_dev_key("user-1", "key/bad", firestore_client=mock_client)
    assert not mock_client.collection.called


def test_delete_dev_key_wraps_firestore_retrieval_error():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc_ref = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc_ref
    mock_doc_ref.get.side_effect = Exception("Deadline exceeded")

    with pytest.raises(ApiKeyRevocationUnavailableError, match="Developer API key retrieval failed"):
        dev_api_key_db.delete_dev_key("user-1", "key-1", firestore_client=mock_client)


def test_delete_dev_key_wraps_firestore_deletion_error():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    valid_hash = "a" * 64
    mock_snapshot.to_dict.return_value = {
        "user_id": "user-1",
        "hashed_key": valid_hash,
    }
    mock_doc_ref.get.return_value = mock_snapshot
    mock_doc_ref.delete.side_effect = Exception("Write permission denied")
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc_ref

    with patch("database.redis_db.delete_cached_dev_api_key_strict", return_value=True):
        with pytest.raises(ApiKeyRevocationUnavailableError, match="Developer API key deletion failed"):
            dev_api_key_db.delete_dev_key("user-1", "key-1", firestore_client=mock_client)


def test_delete_dev_key_successful_flow_with_di():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    valid_hash = "f" * 64
    mock_snapshot.to_dict.return_value = {
        "user_id": "user-1",
        "hashed_key": valid_hash,
    }
    mock_doc_ref.get.return_value = mock_snapshot
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc_ref

    with patch("database.redis_db.delete_cached_dev_api_key_strict", return_value=True) as mock_redis_del:
        with patch("database.dev_api_key.remove_developer_api_key_memory_grant") as mock_remove_grant:
            dev_api_key_db.delete_dev_key("  user-1  ", "  key-1  ", firestore_client=mock_client)

            mock_redis_del.assert_called_once_with(valid_hash)
            mock_doc_ref.delete.assert_called_once()
            mock_remove_grant.assert_called_once_with("user-1", "key-1", db_client=mock_client)


def test_delete_dev_key_ignores_unmatched_user():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {
        "user_id": "other-user",
        "hashed_key": "f" * 64,
    }
    mock_doc_ref.get.return_value = mock_snapshot
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc_ref

    with patch("database.redis_db.delete_cached_dev_api_key_strict") as mock_redis_del:
        dev_api_key_db.delete_dev_key("user-1", "key-1", firestore_client=mock_client)
        mock_redis_del.assert_not_called()
        mock_doc_ref.delete.assert_not_called()


def test_get_api_key_auth_result_rejects_invalid_token_pattern():
    # Never touches Redis or Firestore
    for bad_token in [
        "",
        "short",
        "omi_dev_invalid_hex_characters_here!!!",
        "omi_mcp_0123456789abcdef0123456789abcdef",
    ]:
        result = dev_api_key_db.get_api_key_auth_result(bad_token)
        assert result.context is None


def test_get_api_key_auth_result_fail_closed_on_firestore_error():
    raw_key = "omi_dev_0123456789abcdef0123456789abcdef"
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.side_effect = Exception("Firestore network timeout")

    with patch("database.redis_db.read_cached_dev_api_key_data") as mock_cache:
        mock_cache.return_value = ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS, data=None)
        result = dev_api_key_db.get_api_key_auth_result(raw_key, firestore_client=mock_client)
        assert result.context is None


def test_get_api_key_auth_result_survives_last_used_update_failure():
    raw_key = "omi_dev_0123456789abcdef0123456789abcdef"
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()
    mock_doc = MagicMock()
    mock_ref = MagicMock()
    mock_ref.update.side_effect = Exception("Transient write error")
    mock_doc.id = "key-123"
    mock_doc.reference = mock_ref
    mock_doc.to_dict.return_value = {
        "id": "key-123",
        "user_id": "user-prod",
        "app_id": "developer_api",
        "scopes": ["memories:read"],
    }
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = [mock_doc]
    mock_client.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query

    with patch("database.redis_db.read_cached_dev_api_key_data") as mock_cache:
        mock_cache.return_value = ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS, data=None)
        with patch("database.redis_db.cache_dev_api_key", return_value=True):
            result = dev_api_key_db.get_api_key_auth_result(raw_key, firestore_client=mock_client)
            assert result.context is not None
            assert result.context["user_id"] == "user-prod"
            assert result.context["key_id"] == "key-123"


def test_get_user_id_and_scopes_helpers_with_di():
    mock_client = MagicMock()
    raw_key = "omi_dev_0123456789abcdef0123456789abcdef"
    with patch("database.dev_api_key.get_api_key_auth_result") as mock_auth:
        mock_auth.return_value = ApiKeyAuthLookupResult(
            context={"user_id": "user-42", "scopes": ["memories:read"], "key_id": "k1", "app_id": "developer_api"}
        )
        uid = dev_api_key_db.get_user_id_by_api_key(raw_key, firestore_client=mock_client)
        assert uid == "user-42"
        mock_auth.assert_called_once_with(raw_key, firestore_client=mock_client)

        scopes_dict = dev_api_key_db.get_user_and_scopes_by_api_key(raw_key, firestore_client=mock_client)
        assert scopes_dict == {
            "user_id": "user-42",
            "scopes": ["memories:read"],
            "key_id": "k1",
            "app_id": "developer_api",
        }

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from database.api_key_metadata import (
    _EPOCH_UTC,
    ApiKeyMetadataRepair,
    _coerce_utc_datetime,
    contains_raw_api_key,
    is_valid_api_key_hash,
    project_api_key_metadata,
    normalize_api_key_scopes,
    api_key_scopes_need_repair,
    normalize_api_key_app_id,
    valid_api_key_app_id,
    api_key_auth_user_id,
)


def test_coerce_utc_datetime_aware_and_naive():
    naive = datetime(2026, 10, 16, 12, 0, 0)
    assert _coerce_utc_datetime(naive) == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)

    plus_three = timezone(timedelta(hours=3))
    aware = datetime(2026, 10, 16, 15, 0, 0, tzinfo=plus_three)
    assert _coerce_utc_datetime(aware) == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_coerce_utc_datetime_iso_strings():
    assert _coerce_utc_datetime("2026-10-16T12:00:00Z") == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert _coerce_utc_datetime("  2026-10-16T15:00:00+03:00  ") == datetime(
        2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc
    )


def test_coerce_utc_datetime_callable_to_datetime():
    mock_obj = MagicMock()
    mock_obj.to_datetime.return_value = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert _coerce_utc_datetime(mock_obj) == datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)


def test_coerce_utc_datetime_invalid():
    assert _coerce_utc_datetime(None) is None
    assert _coerce_utc_datetime("not-a-date") is None
    assert _coerce_utc_datetime(12345) is None


def test_contains_raw_api_key():
    assert contains_raw_api_key("key is omi_mcp_" + "a" * 32) is True
    assert contains_raw_api_key("key is omi_dev_" + "0" * 32) is True
    assert contains_raw_api_key("regular_token_abc") is False
    assert contains_raw_api_key(None) is False
    assert contains_raw_api_key(123) is False


def test_is_valid_api_key_hash():
    valid_hash = "a" * 64
    assert is_valid_api_key_hash(valid_hash) is True
    assert is_valid_api_key_hash("A" * 64) is False  # Uppercase not allowed
    assert is_valid_api_key_hash("a" * 63) is False
    assert is_valid_api_key_hash("g" * 64) is False
    assert is_valid_api_key_hash(None) is False


def test_project_api_key_metadata_clean():
    res = project_api_key_metadata(
        document_id="doc_123",
        raw={
            "name": "My MCP Key",
            "key_prefix": "omi_mcp_1234...5678",
            "created_at": "2026-10-16T12:00:00Z",
            "last_used_at": "2026-10-16T13:00:00Z",
        },
        snapshot_create_time="2026-10-16T12:00:00Z",
        key_kind="mcp",
    )
    assert res.metadata["id"] == "doc_123"
    assert res.metadata["name"] == "My MCP Key"
    assert res.metadata["key_prefix"] == "omi_mcp_1234...5678"
    assert res.metadata["created_at"] == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert res.metadata["last_used_at"] == datetime(2026, 10, 16, 13, 0, 0, tzinfo=timezone.utc)
    assert res.repairs == frozenset()


def test_project_api_key_metadata_whitespace_doc_id():
    res = project_api_key_metadata(
        document_id="  doc_padded  ",
        raw={"name": "Dev Key", "key_prefix": "omi_dev_aaaa...bbbb"},
        snapshot_create_time=None,
        key_kind="dev",
    )
    assert res.metadata["id"] == "doc_padded"


def test_project_api_key_metadata_invalid_id_raises():
    with pytest.raises(ValueError, match="Firestore API key document must have an ID"):
        project_api_key_metadata(
            document_id="",
            raw={},
            snapshot_create_time=None,
            key_kind="mcp",
        )
    with pytest.raises(ValueError, match="Firestore API key document must have an ID"):
        project_api_key_metadata(
            document_id="   ",
            raw={},
            snapshot_create_time=None,
            key_kind="mcp",
        )
    with pytest.raises(ValueError, match="Firestore API key document must have an ID"):
        project_api_key_metadata(
            document_id=None,
            raw={},
            snapshot_create_time=None,
            key_kind="mcp",
        )


def test_project_api_key_metadata_unsupported_kind():
    with pytest.raises(ValueError, match="Unsupported API key kind"):
        project_api_key_metadata(
            document_id="doc_1",
            raw={},
            snapshot_create_time=None,
            key_kind="unknown",
        )


def test_project_api_key_metadata_repairs_name_and_prefix():
    # Raw token leaked in name and missing prefix
    raw_token = "omi_mcp_" + "f" * 32
    res = project_api_key_metadata(
        document_id="doc_123",
        raw={
            "name": f"Leaked {raw_token}",
            "key_prefix": "invalid_prefix",
        },
        snapshot_create_time=None,
        key_kind="mcp",
    )
    assert res.metadata["name"] == "Legacy MCP API key"
    assert res.metadata["key_prefix"] == "omi_mcp_legacy"
    assert ApiKeyMetadataRepair.NAME in res.repairs
    assert ApiKeyMetadataRepair.KEY_PREFIX in res.repairs
    assert ApiKeyMetadataRepair.CREATED_AT in res.repairs
    assert res.metadata["created_at"] == _EPOCH_UTC


def test_normalize_api_key_scopes():
    allowed = ["read:memories", "write:memories", "read:tasks"]
    res = normalize_api_key_scopes(
        ["read:memories", "  write:memories  ", "unknown:scope", 123],
        allowed_scopes=allowed,
    )
    assert res == ["read:memories", "write:memories"]

    # Required scopes enforcement
    res_req = normalize_api_key_scopes(
        None,
        allowed_scopes=allowed,
        required_scopes=["read:tasks"],
    )
    assert res_req == ["read:tasks"]


def test_api_key_scopes_need_repair():
    allowed = ["read:memories", "write:memories"]
    assert api_key_scopes_need_repair(None, None, allowed_scopes=allowed, missing_is_valid=True) is False
    assert api_key_scopes_need_repair(None, None, allowed_scopes=allowed, missing_is_valid=False) is True
    assert api_key_scopes_need_repair("not-a-list", [], allowed_scopes=allowed, missing_is_valid=True) is True
    assert api_key_scopes_need_repair(["unknown"], [], allowed_scopes=allowed, missing_is_valid=True) is True
    assert (
        api_key_scopes_need_repair(["read:memories"], ["read:memories"], allowed_scopes=allowed, missing_is_valid=True)
        is False
    )


def test_normalize_and_valid_api_key_app_id():
    assert normalize_api_key_app_id("valid-app_1", default="default-app") == "valid-app_1"
    assert normalize_api_key_app_id("  invalid whitespace  ", default="default-app") == "default-app"
    assert normalize_api_key_app_id("omi_mcp_" + "a" * 32, default="default-app") == "default-app"

    assert valid_api_key_app_id("valid-app-123") == "valid-app-123"
    assert valid_api_key_app_id("") is None
    assert valid_api_key_app_id("   ") is None
    assert valid_api_key_app_id(None) is None


def test_api_key_auth_user_id():
    assert api_key_auth_user_id({"user_id": "user_123"}) == "user_123"
    assert api_key_auth_user_id({"user_id": "  user_padded  "}) is None
    assert api_key_auth_user_id({"user_id": "omi_mcp_" + "a" * 32}) is None
    assert api_key_auth_user_id({"user_id": ""}) is None
    assert api_key_auth_user_id({}) is None
    assert api_key_auth_user_id("not-a-dict") is None

from unittest.mock import MagicMock, patch
import pytest

from database.api_key_metadata import ApiKeyValidationError
from database.mcp_api_key import (
    _clean_key_name,
    _clean_user_id,
    create_mcp_key,
    delete_mcp_key,
    get_api_key_auth_result,
    get_mcp_keys_for_user,
    get_mcp_keys_for_user_with_repair_info,
)


def test_clean_user_id_valid():
    assert _clean_user_id("user_12345") == "user_12345"
    assert _clean_user_id("  user_abc  ") == "user_abc"


@pytest.mark.parametrize("invalid_uid", ["", "   ", None, 12345, [], {}])
def test_clean_user_id_empty_or_invalid_type(invalid_uid):
    with pytest.raises(ApiKeyValidationError, match="user_id"):
        _clean_user_id(invalid_uid)


@pytest.mark.parametrize(
    "traversal_uid",
    [
        "../etc/passwd",
        "users/../../root",
        "user/123",
        "user\\123",
        "..",
        "a" * 129,
    ],
)
def test_clean_user_id_path_traversal_and_bounds(traversal_uid):
    with pytest.raises(ApiKeyValidationError, match="invalid characters or exceeds maximum length"):
        _clean_user_id(traversal_uid)


def test_clean_key_name_valid():
    assert _clean_key_name("Production Key") == "Production Key"
    assert _clean_key_name("   Dev   Key   ") == "Dev Key"


@pytest.mark.parametrize("invalid_name", ["", "    ", None, 999])
def test_clean_key_name_empty_or_invalid_type(invalid_name):
    with pytest.raises(ApiKeyValidationError, match="API key name"):
        _clean_key_name(invalid_name)


def test_clean_key_name_bounds():
    too_long = "x" * 256
    with pytest.raises(ApiKeyValidationError, match="must not exceed 255 characters"):
        _clean_key_name(too_long)


def test_clean_key_name_rejects_raw_token():
    raw_token = "omi_mcp_1234567890abcdef1234567890abcdef"
    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        _clean_key_name(f"My key: {raw_token}")


def test_create_mcp_key_sanitizes_and_persists():
    mock_db = MagicMock()
    mock_doc = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc

    with patch("database.mcp_api_key._db", return_value=mock_db), patch(
        "database.mcp_api_key._seed_mcp_memory_grant"
    ) as mock_seed:
        raw_key, api_key_data = create_mcp_key(
            user_id="  uid_valid_42  ",
            name="   Claude   Agent Key   ",
        )

        assert raw_key.startswith("omi_mcp_")
        assert api_key_data.name == "Claude Agent Key"
        mock_doc.set.assert_called_once()
        saved_doc = mock_doc.set.call_args[0][0]
        assert saved_doc["user_id"] == "uid_valid_42"
        assert saved_doc["name"] == "Claude Agent Key"
        mock_seed.assert_called_once()
        assert mock_seed.call_args[0][0] == "uid_valid_42"


@pytest.mark.parametrize("invalid_uid", ["", "   ", None, "../admin", "bad/uid", "x" * 130])
def test_get_mcp_keys_for_user_invalid_uid_fast_return(invalid_uid):
    with patch("database.mcp_api_key._db") as mock_db:
        keys, repairs = get_mcp_keys_for_user_with_repair_info(invalid_uid)
        assert keys == []
        assert repairs == frozenset()
        mock_db.assert_not_called()

        keys_simple = get_mcp_keys_for_user(invalid_uid)
        assert keys_simple == []


@pytest.mark.parametrize(
    "invalid_input",
    [
        ("", "key_1"),
        ("uid_1", ""),
        ("   ", "key_1"),
        ("uid_1", "   "),
        (None, "key_1"),
        ("uid_1", None),
        ("../admin", "key_1"),
        ("uid_1", "../etc"),
        ("uid/1", "key_1"),
        ("uid_1", "key/1"),
    ],
)
def test_delete_mcp_key_invalid_inputs_noop(invalid_input):
    uid, key_id = invalid_input
    with patch("database.mcp_api_key._db") as mock_db:
        delete_mcp_key(uid, key_id)
        mock_db.assert_not_called()


@pytest.mark.parametrize("invalid_api_key", [None, 12345, [], {}, "invalid_prefix", "omi_dev_123"])
def test_get_api_key_auth_result_non_string_or_prefix(invalid_api_key):
    result = get_api_key_auth_result(invalid_api_key)
    assert result.context is None

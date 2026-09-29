from unittest.mock import MagicMock, patch
import pytest

from database.api_key_metadata import ApiKeyValidationError
from database.dev_api_key import (
    _clean_key_name,
    _clean_user_id,
    create_dev_key,
    delete_dev_key,
    get_dev_keys_for_user,
    get_dev_keys_for_user_with_repair_info,
)


def test_clean_user_id_valid():
    assert _clean_user_id("user_dev_123") == "user_dev_123"
    assert _clean_user_id("  user_dev_456  ") == "user_dev_456"


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
        "d" * 129,
    ],
)
def test_clean_user_id_path_traversal_and_bounds(traversal_uid):
    with pytest.raises(ApiKeyValidationError, match="invalid characters or exceeds maximum length"):
        _clean_user_id(traversal_uid)


def test_clean_key_name_valid():
    assert _clean_key_name("Dev CLI Key") == "Dev CLI Key"
    assert _clean_key_name("   Dev   CLI   Key   ") == "Dev CLI Key"


@pytest.mark.parametrize("invalid_name", ["", "    ", None, 123])
def test_clean_key_name_empty_or_invalid_type(invalid_name):
    with pytest.raises(ApiKeyValidationError, match="API key name"):
        _clean_key_name(invalid_name)


def test_clean_key_name_bounds():
    too_long = "k" * 256
    with pytest.raises(ApiKeyValidationError, match="must not exceed 255 characters"):
        _clean_key_name(too_long)


def test_clean_key_name_rejects_raw_token():
    raw_token = "omi_dev_1234567890abcdef1234567890abcdef"
    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        _clean_key_name(f"Leaked: {raw_token}")


def test_create_dev_key_sanitizes_and_persists():
    mock_db = MagicMock()
    mock_doc = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc

    with patch("database.dev_api_key._db", return_value=mock_db), patch(
        "database.dev_api_key.seed_developer_api_key_memory_grant"
    ) as mock_seed:
        raw_key, api_key_data = create_dev_key(
            user_id="  uid_dev_valid_88  ",
            name="   Dev   Automation Key   ",
            scopes=["memories:read"],
        )

        assert raw_key.startswith("omi_dev_")
        assert api_key_data.name == "Dev Automation Key"
        mock_doc.set.assert_called_once()
        saved_doc = mock_doc.set.call_args[0][0]
        assert saved_doc["user_id"] == "uid_dev_valid_88"
        assert saved_doc["name"] == "Dev Automation Key"
        mock_seed.assert_called_once()
        assert mock_seed.call_args[0][0] == "uid_dev_valid_88"


@pytest.mark.parametrize("invalid_uid", ["", "   ", None, "../admin", "bad/uid", "d" * 130])
def test_get_dev_keys_for_user_invalid_uid_fast_return(invalid_uid):
    with patch("database.dev_api_key._db") as mock_db:
        keys, repairs = get_dev_keys_for_user_with_repair_info(invalid_uid)
        assert keys == []
        assert repairs == frozenset()
        mock_db.assert_not_called()

        keys_simple = get_dev_keys_for_user(invalid_uid)
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
def test_delete_dev_key_invalid_inputs_noop(invalid_input):
    uid, key_id = invalid_input
    with patch("database.dev_api_key._db") as mock_db:
        delete_dev_key(uid, key_id)
        mock_db.assert_not_called()

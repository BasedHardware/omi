import pytest
from unittest.mock import MagicMock

from database.notifications import save_token, get_all_tokens


def test_clean_id_in_notifications():
    with pytest.raises(ValueError, match="uid cannot be empty"):
        save_token("", {"fcm_token": "tok123"})

    with pytest.raises(ValueError, match="uid contains prohibited path-traversal"):
        save_token("../bad_uid", {"fcm_token": "tok123"})

    with pytest.raises(ValueError, match="device_key contains prohibited path-traversal"):
        save_token("valid_uid", {"device_key": "../bad_key", "fcm_token": "tok123"})

    with pytest.raises(ValueError, match="uid cannot be empty"):
        get_all_tokens("")


def test_get_all_tokens_success_and_fallback():
    mock_client = MagicMock()
    mock_user_ref = MagicMock()
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {"fcm_token": "legacy_token_123"}
    mock_user_ref.get.return_value = mock_user_doc

    mock_token_doc = MagicMock()
    mock_token_doc.to_dict.return_value = {"token": "subcoll_token_456"}
    mock_user_ref.collection.return_value.stream.return_value = [mock_token_doc]

    mock_client.collection.return_value.document.return_value = mock_user_ref

    tokens = get_all_tokens("user_123", firestore_client=mock_client)
    assert "subcoll_token_456" in tokens
    assert "legacy_token_123" in tokens

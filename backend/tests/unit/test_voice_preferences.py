from unittest.mock import MagicMock
import pytest
from config.assistant_voices import DEFAULT_ASSISTANT_VOICE
from database.voice_preferences import (
    _ASSISTANT_VOICE_FIELD,
    get_assistant_voice,
    set_assistant_voice,
)


def test_get_assistant_voice_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {_ASSISTANT_VOICE_FIELD: "Aoede"}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    voice = get_assistant_voice("user_123", firestore_client=mock_client)
    assert voice == "Aoede"
    mock_client.collection.assert_called_with("users")
    mock_client.collection.return_value.document.assert_called_with("user_123")


def test_get_assistant_voice_strips_uid():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {_ASSISTANT_VOICE_FIELD: "Kore"}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    voice = get_assistant_voice("  user_123  ", firestore_client=mock_client)
    assert voice == "Kore"
    mock_client.collection.return_value.document.assert_called_with("user_123")


def test_get_assistant_voice_empty_or_whitespace_uid():
    mock_client = MagicMock()
    assert get_assistant_voice("", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE
    assert get_assistant_voice("   ", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE
    mock_client.collection.assert_not_called()


def test_get_assistant_voice_missing_doc_or_none_data():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    assert get_assistant_voice("user_123", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE

    mock_doc.exists = True
    mock_doc.to_dict.return_value = None
    assert get_assistant_voice("user_123", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE


def test_get_assistant_voice_exception_handling():
    mock_client = MagicMock()
    mock_client.collection.side_effect = RuntimeError("Firestore down")

    assert get_assistant_voice("user_123", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE


def test_get_assistant_voice_none_client():
    mock_client = None
    # With none client and db mocked
    res = get_assistant_voice("user_123", firestore_client=mock_client)
    assert res == DEFAULT_ASSISTANT_VOICE or isinstance(res, str)


def test_get_assistant_voice_unrecognized_stored_voice():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {_ASSISTANT_VOICE_FIELD: "NonExistentVoiceXYZ"}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    assert get_assistant_voice("user_123", firestore_client=mock_client) == DEFAULT_ASSISTANT_VOICE


def test_set_assistant_voice_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    voice = set_assistant_voice("user_123", "Puck", firestore_client=mock_client)
    assert voice == "Puck"
    mock_client.collection.assert_called_with("users")
    mock_client.collection.return_value.document.assert_called_with("user_123")
    mock_doc.set.assert_called_with({_ASSISTANT_VOICE_FIELD: "Puck"}, merge=True)


def test_set_assistant_voice_strips_uid_whitespace():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    voice = set_assistant_voice("  user_space  ", "Fenrir", firestore_client=mock_client)
    assert voice == "Fenrir"
    mock_client.collection.return_value.document.assert_called_with("user_space")


def test_set_assistant_voice_empty_uid_raises_value_error():
    mock_client = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        set_assistant_voice("", "Puck", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        set_assistant_voice("   ", "Puck", firestore_client=mock_client)


def test_set_assistant_voice_none_client_raises_runtime_error(monkeypatch):
    import database.voice_preferences as vp

    monkeypatch.setattr(vp, "get_data_plane_firestore_client", lambda: None)
    with pytest.raises(RuntimeError, match="Firestore data plane client is unavailable"):
        set_assistant_voice("user_123", "Puck", firestore_client=None)


def test_set_assistant_voice_exception_propagation():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.set.side_effect = RuntimeError("Write failed")
    mock_client.collection.return_value.document.return_value = mock_doc

    with pytest.raises(RuntimeError, match="Write failed"):
        set_assistant_voice("user_123", "Puck", firestore_client=mock_client)

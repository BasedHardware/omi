from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from database.voice_profiles import (
    SETTINGS_DEFAULTS,
    _clean_uid,
    _state_ref,
    add_owner_voice_confirmation,
    get_tag_prompt_state,
    get_voice_profile_context,
    get_voice_profile_settings,
    mark_tag_prompts_empty,
    record_tag_prompt_answered,
    record_tag_prompts_dismissed,
    record_tag_prompts_shown,
    set_voice_profile_settings,
)


def test_clean_uid():
    assert _clean_uid("user123") == "user123"
    assert _clean_uid("  user123  ") == "user123"
    assert _clean_uid("") is None
    assert _clean_uid("   ") is None
    assert _clean_uid(None) is None
    assert _clean_uid(123) is None


def test_get_voice_profile_settings_blank_uid():
    settings = get_voice_profile_settings("")
    assert settings == SETTINGS_DEFAULTS
    settings = get_voice_profile_settings("   ")
    assert settings == SETTINGS_DEFAULTS


def test_get_voice_profile_settings_valid():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.to_dict.return_value = {"speaker_tag_prompts_enabled": False}
    mock_client.collection.return_value.document.return_value = mock_doc

    settings = get_voice_profile_settings("user123", firestore_client=mock_client)
    assert settings["speaker_tag_prompts_enabled"] is False
    assert settings["save_other_voice_profiles"] is True
    mock_client.collection.assert_called_with("users")
    mock_client.collection().document.assert_called_with("user123")


def test_get_voice_profile_context_blank_uid():
    settings, has_embedding = get_voice_profile_context("")
    assert settings == SETTINGS_DEFAULTS
    assert has_embedding is False


def test_set_voice_profile_settings_validation():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        set_voice_profile_settings("", {"speaker_tag_prompts_enabled": True})

    with pytest.raises(ValueError, match="updates must be a dictionary"):
        set_voice_profile_settings("user123", "not a dict")  # type: ignore

    with pytest.raises(ValueError, match="Unknown voice profile setting"):
        set_voice_profile_settings("user123", {"invalid_key": True})


def test_state_ref_validation():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        _state_ref("")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        _state_ref("   ")

    mock_client = MagicMock()
    mock_user_doc = MagicMock()
    mock_state_coll = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc
    mock_user_doc.collection.return_value = mock_state_coll

    _state_ref("user123", firestore_client=mock_client)
    mock_client.collection.assert_called_with("users")
    mock_client.collection().document.assert_called_with("user123")
    mock_user_doc.collection.assert_called_with("speaker_tag_prompts")
    mock_state_coll.document.assert_called_with("state")


def test_get_tag_prompt_state_blank_uid():
    assert get_tag_prompt_state("") == {}
    assert get_tag_prompt_state("   ") == {}


def test_record_functions_validation():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        record_tag_prompts_shown("", now)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        mark_tag_prompts_empty("", now)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        record_tag_prompts_dismissed("", now)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        record_tag_prompt_answered("", "p1", now)

    with pytest.raises(ValueError, match="prompt_id must be a non-empty string"):
        record_tag_prompt_answered("user123", "", now)


def test_add_owner_voice_confirmation_validation():
    dummy_pool = lambda vecs: [0.0]

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        add_owner_voice_confirmation("", [0.1, 0.2], dummy_pool, conversation_id="c1")

    with pytest.raises(ValueError, match="embedding must be a non-empty sequence of floats"):
        add_owner_voice_confirmation("user1", [], dummy_pool, conversation_id="c1")

    with pytest.raises(ValueError, match="pool must be a callable"):
        add_owner_voice_confirmation("user1", [0.1], None, conversation_id="c1")  # type: ignore

    with pytest.raises(ValueError, match="conversation_id must be a non-empty string"):
        add_owner_voice_confirmation("user1", [0.1], dummy_pool, conversation_id="")

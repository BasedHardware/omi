"""Hermetic unit tests for input validation, boundary guards, and error resilience
in backend/database/voice_profiles.py.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import database.voice_profiles as voice_profiles_db


class _FakeDocSnapshot:
    def __init__(self, doc_id: str, exists: bool = True, data: dict | None = None):
        self.id = doc_id
        self.exists = exists
        self._data = data if data is not None else {}

    def to_dict(self):
        return self._data if self.exists else None


# ---------------------------------------------------------------------------
# get_voice_profile_settings & get_voice_profile_context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_get_voice_profile_settings_invalid_uid_returns_defaults(invalid_uid):
    fake_client = MagicMock()
    res = voice_profiles_db.get_voice_profile_settings(invalid_uid, firestore_client=fake_client)  # type: ignore[arg-type]
    assert res == voice_profiles_db.SETTINGS_DEFAULTS
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_get_voice_profile_context_invalid_uid_returns_defaults(invalid_uid):
    fake_client = MagicMock()
    settings, has_voice = voice_profiles_db.get_voice_profile_context(invalid_uid, firestore_client=fake_client)  # type: ignore[arg-type]
    assert settings == voice_profiles_db.SETTINGS_DEFAULTS
    assert has_voice is False
    fake_client.collection.assert_not_called()


def test_get_voice_profile_settings_normalizes_uid():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref
    doc_ref.get.return_value = _FakeDocSnapshot(
        "user-1", exists=True, data={"speaker_tag_prompts_enabled": False}
    )

    res = voice_profiles_db.get_voice_profile_settings("  user-1  ", firestore_client=fake_client)
    assert res["speaker_tag_prompts_enabled"] is False
    fake_client.collection.return_value.document.assert_called_with("user-1")


# ---------------------------------------------------------------------------
# set_voice_profile_settings validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_set_voice_profile_settings_rejects_invalid_uid(invalid_uid):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles_db.set_voice_profile_settings(
            invalid_uid, {"speaker_tag_prompts_enabled": True}, firestore_client=fake_client  # type: ignore[arg-type]
        )
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_updates", [None, "not-a-dict", 123, []])
def test_set_voice_profile_settings_rejects_non_dict_updates(invalid_updates):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="updates must be a dictionary"):
        voice_profiles_db.set_voice_profile_settings("u-1", invalid_updates, firestore_client=fake_client)  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


def test_set_voice_profile_settings_rejects_unknown_keys():
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="Unknown voice profile setting"):
        voice_profiles_db.set_voice_profile_settings(
            "u-1", {"unknown_key": True}, firestore_client=fake_client
        )
    fake_client.collection.assert_not_called()


def test_set_voice_profile_settings_empty_updates_is_noop():
    fake_client = MagicMock()
    voice_profiles_db.set_voice_profile_settings("u-1", {}, firestore_client=fake_client)
    fake_client.collection.assert_not_called()


def test_set_voice_profile_settings_persists_valid():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref

    voice_profiles_db.set_voice_profile_settings(
        "  user-abc  ", {"save_other_voice_profiles": False}, firestore_client=fake_client
    )

    fake_client.collection.return_value.document.assert_called_with("user-abc")
    doc_ref.set.assert_called_once_with({"save_other_voice_profiles": False}, merge=True)


# ---------------------------------------------------------------------------
# State references & Tag Prompt helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_state_ref_rejects_invalid_uid(invalid_uid):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles_db._state_ref(invalid_uid, fake_client)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_get_tag_prompt_state_invalid_uid_returns_empty(invalid_uid):
    fake_client = MagicMock()
    assert voice_profiles_db.get_tag_prompt_state(invalid_uid, firestore_client=fake_client) == {}  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_record_tag_prompts_shown_invalid_uid_returns_false(invalid_uid):
    fake_client = MagicMock()
    now = datetime.now(timezone.utc)
    assert voice_profiles_db.record_tag_prompts_shown(invalid_uid, now, firestore_client=fake_client) is False  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_mark_tag_prompts_empty_invalid_uid_is_noop(invalid_uid):
    fake_client = MagicMock()
    now = datetime.now(timezone.utc)
    voice_profiles_db.mark_tag_prompts_empty(invalid_uid, now, firestore_client=fake_client)  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_record_tag_prompts_dismissed_invalid_uid_returns_zero(invalid_uid):
    fake_client = MagicMock()
    now = datetime.now(timezone.utc)
    assert voice_profiles_db.record_tag_prompts_dismissed(invalid_uid, now, firestore_client=fake_client) == 0  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_arg", [None, "", "   "])
def test_record_tag_prompt_answered_invalid_coords_is_noop(invalid_arg):
    fake_client = MagicMock()
    now = datetime.now(timezone.utc)
    voice_profiles_db.record_tag_prompt_answered(invalid_arg, "p-1", now, firestore_client=fake_client)  # type: ignore[arg-type]
    voice_profiles_db.record_tag_prompt_answered("u-1", invalid_arg, now, firestore_client=fake_client)  # type: ignore[arg-type]
    fake_client.collection.assert_not_called()


# ---------------------------------------------------------------------------
# add_owner_voice_confirmation validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_add_owner_voice_confirmation_rejects_invalid_uid(invalid_uid):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles_db.add_owner_voice_confirmation(
            invalid_uid, [0.1, 0.2], lambda x: x[0], conversation_id="c-1", firestore_client=fake_client  # type: ignore[arg-type]
        )
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_embedding", [None, [], "not-a-list", 123])
def test_add_owner_voice_confirmation_rejects_invalid_embedding(invalid_embedding):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="embedding must be a non-empty sequence"):
        voice_profiles_db.add_owner_voice_confirmation(
            "u-1", invalid_embedding, lambda x: x[0], conversation_id="c-1", firestore_client=fake_client  # type: ignore[arg-type]
        )
    fake_client.collection.assert_not_called()


def test_add_owner_voice_confirmation_rejects_non_callable_pool():
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="pool must be a callable"):
        voice_profiles_db.add_owner_voice_confirmation(
            "u-1", [0.1, 0.2], "not-a-function", conversation_id="c-1", firestore_client=fake_client  # type: ignore[arg-type]
        )
    fake_client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_conv_id", [None, "", "   "])
def test_add_owner_voice_confirmation_rejects_invalid_conversation_id(invalid_conv_id):
    fake_client = MagicMock()
    with pytest.raises(ValueError, match="conversation_id must be a non-empty string"):
        voice_profiles_db.add_owner_voice_confirmation(
            "u-1", [0.1, 0.2], lambda x: x[0], conversation_id=invalid_conv_id, firestore_client=fake_client  # type: ignore[arg-type]
        )
    fake_client.collection.assert_not_called()

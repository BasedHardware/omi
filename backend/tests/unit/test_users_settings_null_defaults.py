"""Tests for null defaults and resilient writes on user settings in database/users.py.

Covers:
1. get_meeting_note_screenshots_enabled and get_user_private_cloud_sync_enabled default to True
   when explicit None is stored on the Firestore document.
2. get_notification_settings defaults 'enabled' to True and 'frequency' to 0 when stored fields
   are explicitly None or document to_dict() returns None.
3. get_user_speaker_embedding, _get_raw_assistant_settings, get_assistant_settings, and
   _get_ai_user_profile_from_firestore fail soft instead of raising AttributeError when
   an existing document snapshot returns None from .to_dict().
4. set_user_store_recording_permission, set_meeting_note_screenshots_enabled, and
   set_user_private_cloud_sync_enabled use set(..., merge=True) for resilient settings persistence.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _module(name: str, **attrs: object) -> ModuleType:
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@pytest.fixture(scope="module")
def users():
    """Load database.users in an isolated stubbed environment."""
    firestore = _module("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock())
    firestore_v1 = _module("google.cloud.firestore_v1", FieldFilter=MagicMock(), transactional=lambda fn: fn)
    fakes = {
        "google.cloud.firestore": firestore,
        "google.cloud.firestore_v1": firestore_v1,
        "database._client": _module(
            "database._client",
            db=MagicMock(),
            delete_collection_recursive=MagicMock(),
            document_id_from_seed=lambda seed: "id",
            get_firestore_client=MagicMock(),
            get_data_plane_firestore_client=MagicMock(),
            get_customer_firestore_client=MagicMock(),
            data_plane_db=MagicMock(),
        ),
        "database.firestore_cache": _module(
            "database.firestore_cache", CachePolicy=MagicMock(), get_or_fetch=MagicMock(), invalidate=MagicMock()
        ),
        "database.redis_db": _module(
            "database.redis_db",
            try_acquire_client_device_write_lock=MagicMock(return_value=True),
            try_acquire_user_platform_write_lock=MagicMock(return_value=True),
            delete_cached_user_geolocation=MagicMock(),
        ),
        "models.users": _module(
            "models.users",
            Subscription=MagicMock(),
            PlanLimits=MagicMock(),
            PlanType=MagicMock(),
            SubscriptionStatus=MagicMock(),
            LOCATION_CONTEXT_DISCLOSED_PROVIDERS=("Google Maps", "the configured AI chat provider"),
            LOCATION_CONTEXT_PURPOSE="chat_city_context",
            LocationContextConsent=MagicMock(),
            LocationContextConsentStatus=MagicMock(),
        ),
        "utils.subscription": _module("utils.subscription", get_default_basic_subscription=MagicMock()),
        "models.other": _module("models.other", Person=MagicMock()),
    }
    with stub_modules(fakes):
        yield load_module_fresh("database.users", str(BACKEND_DIR / "database" / "users.py"))


def _db_for(to_dict_result, exists: bool = True):
    snapshot = MagicMock()
    snapshot.exists = exists
    snapshot.to_dict.return_value = to_dict_result
    db = MagicMock()
    db.collection.return_value.document.return_value.get.return_value = snapshot
    return db


@pytest.mark.parametrize(
    "fn,field",
    [
        ("get_meeting_note_screenshots_enabled", "meeting_note_screenshots_enabled"),
        ("get_user_private_cloud_sync_enabled", "private_cloud_sync_enabled"),
    ],
)
def test_explicit_none_setting_defaults_to_true(users, fn, field):
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({field: None})):
        assert func("uid") is True


@pytest.mark.parametrize(
    "fn,field",
    [
        ("get_meeting_note_screenshots_enabled", "meeting_note_screenshots_enabled"),
        ("get_user_private_cloud_sync_enabled", "private_cloud_sync_enabled"),
    ],
)
def test_explicit_bool_setting_preserved(users, fn, field):
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({field: False})):
        assert func("uid") is False
    with patch.object(users, "db", _db_for({field: True})):
        assert func("uid") is True


def test_notification_settings_handles_explicit_none(users):
    with patch.object(users, "db", _db_for({"notifications_enabled": None, "notification_frequency": None})):
        result = users.get_notification_settings("uid")
        assert result == {"enabled": True, "frequency": 0}


def test_notification_settings_handles_none_to_dict(users):
    with patch.object(users, "db", _db_for(None, exists=True)):
        result = users.get_notification_settings("uid")
        assert result == {"enabled": True, "frequency": 0}


def test_empty_doc_snapshot_does_not_crash_getters(users):
    mock_db = _db_for(None, exists=True)
    with patch.object(users, "db", mock_db):
        assert users.get_user_speaker_embedding("uid") is None
        assert users._get_ai_user_profile_from_firestore("uid") is None

    with patch("database.users.get_data_plane_firestore_client", return_value=mock_db):
        assert users._get_raw_assistant_settings("uid") == {}
        assert users.get_assistant_settings("uid") == {}


def test_settings_setters_use_merge_write(users):
    mock_ref = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_ref

    with patch.object(users, "db", mock_db):
        users.set_user_store_recording_permission("uid", True)
        mock_ref.set.assert_called_with({"store_recording_permission": True}, merge=True)

        users.set_meeting_note_screenshots_enabled("uid", False)
        mock_ref.set.assert_called_with({"meeting_note_screenshots_enabled": False}, merge=True)

        users.set_user_private_cloud_sync_enabled("uid", True)
        mock_ref.set.assert_called_with({"private_cloud_sync_enabled": True}, merge=True)

"""Unit tests for the speech profile existence check (#5128).

/v3/speech-profile must report has_profile=true for ANY existing profile,
because the listen pipeline (routers/transcribe.py) uses the profile
regardless of age. A 90-day expiry applied only to this endpoint caused
users with older, actively-used profiles to be re-prompted to
"Teach Omi your voice" on every launch.
"""

import inspect
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Mock heavy dependencies at sys.modules level before importing storage
_MISSING = object()
_STUBBED_MODULES = [
    "database",
    "database._client",
    "database.redis_db",
    "database.users",
    "opuslib",
    "utils.cloud_tasks",
    "google.cloud.storage",
    "google.cloud.storage.transfer_manager",
    "google.cloud.exceptions",
    "google.oauth2",
    "google.oauth2.service_account",
]
_previous_modules = {name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULES}

sys.modules["database._client"] = MagicMock()
_mock_database = types.ModuleType("database")
_mock_database.__path__ = []
sys.modules["database"] = _mock_database
_mock_redis_db = MagicMock()
_mock_redis_db.cache_signed_url = MagicMock()
_mock_redis_db.get_cached_signed_url = MagicMock(return_value=None)
sys.modules["database.redis_db"] = _mock_redis_db
_mock_database.redis_db = sys.modules["database.redis_db"]
_mock_database_users = MagicMock()
_mock_database_users.get_data_protection_level = MagicMock(return_value="standard")
sys.modules["database.users"] = _mock_database_users
_mock_database.users = sys.modules["database.users"]
_mock_opuslib = MagicMock()
_mock_opuslib.APPLICATION_VOIP = 2048
sys.modules["opuslib"] = _mock_opuslib
_mock_cloud_tasks = MagicMock()
_mock_cloud_tasks.enqueue_audio_merge_job = MagicMock()
_mock_cloud_tasks.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)
sys.modules["utils.cloud_tasks"] = _mock_cloud_tasks

_mock_gcs_storage = MagicMock()
_mock_gcs_storage.Client.return_value = MagicMock()
sys.modules["google.cloud.storage"] = _mock_gcs_storage
sys.modules["google.cloud.storage.transfer_manager"] = MagicMock()
sys.modules["google.cloud.exceptions"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()

from utils.other import storage as storage_mod

for _name, _previous in _previous_modules.items():
    if _previous is _MISSING:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _previous


class TestGetUserHasSpeechProfile:
    def _bucket_with_blob(self, exists: bool):
        blob = MagicMock()
        blob.exists.return_value = exists
        bucket = MagicMock()
        bucket.blob.return_value = blob
        return bucket, blob

    def test_existing_profile_counts_regardless_of_age(self):
        """An existing profile is reported as present — no age cutoff (#5128)."""
        bucket, blob = self._bucket_with_blob(exists=True)
        with patch.object(storage_mod, "_get_speech_profiles_bucket", return_value=bucket):
            assert storage_mod.get_user_has_speech_profile("uid1") is True
        # No metadata fetch for age checks — the old expiry code called blob.reload()
        blob.reload.assert_not_called()

    def test_missing_profile(self):
        bucket, _ = self._bucket_with_blob(exists=False)
        with patch.object(storage_mod, "_get_speech_profiles_bucket", return_value=bucket):
            assert storage_mod.get_user_has_speech_profile("uid1") is False

    def test_missing_bucket(self):
        with patch.object(storage_mod, "_get_speech_profiles_bucket", return_value=None):
            assert storage_mod.get_user_has_speech_profile("uid1") is False

    def test_no_age_parameter_in_signature(self):
        """Guard against reintroducing an expiry knob on the existence check."""
        params = inspect.signature(storage_mod.get_user_has_speech_profile).parameters
        assert list(params) == ["uid"]

    def test_endpoint_does_not_pass_age_cutoff(self):
        """The /v3/speech-profile router must not filter profiles by age (#5128)."""
        router_src = Path(storage_mod.__file__).parents[2] / "routers" / "speech_profile.py"
        assert "max_age_days" not in router_src.read_text(encoding="utf-8")

"""Unit tests for the speech profile existence check (#5128).

/v3/speech-profile must report has_profile=true for ANY existing profile,
because the listen pipeline (routers/transcribe.py) uses the profile
regardless of age. A 90-day expiry applied only to this endpoint caused
users with older, actively-used profiles to be re-prompted to
"Teach Omi your voice" on every launch.
"""

import inspect
from pathlib import Path
from unittest.mock import patch

from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore


class TestGetUserHasSpeechProfile:
    """get_user_has_speech_profile now checks existence through the neutral object-store port
    (_object_store().exists on _speech_profiles_bucket_name()), not a raw GCS bucket.blob().exists."""

    _BUCKET = "speech-profiles"

    def _store_with(self, exists: bool):
        store = FakeObjectStore()
        if exists:
            store.put(self._BUCKET, "uid1/speech_profile.wav", b"x")
        return store

    def test_existing_profile_counts_regardless_of_age(self):
        """An existing profile is reported as present — no age cutoff (#5128)."""
        store = self._store_with(exists=True)
        with (
            patch.object(storage_mod, "_speech_profiles_bucket_name", return_value=self._BUCKET),
            patch.object(storage_mod, "_object_store", return_value=store),
        ):
            assert storage_mod.get_user_has_speech_profile("uid1") is True

    def test_missing_profile(self):
        store = self._store_with(exists=False)
        with (
            patch.object(storage_mod, "_speech_profiles_bucket_name", return_value=self._BUCKET),
            patch.object(storage_mod, "_object_store", return_value=store),
        ):
            assert storage_mod.get_user_has_speech_profile("uid1") is False

    def test_missing_bucket(self):
        with patch.object(storage_mod, "_speech_profiles_bucket_name", return_value=None):
            assert storage_mod.get_user_has_speech_profile("uid1") is False

    def test_no_age_parameter_in_signature(self):
        """Guard against reintroducing an expiry knob on the existence check."""
        params = inspect.signature(storage_mod.get_user_has_speech_profile).parameters
        assert list(params) == ["uid"]

    def test_endpoint_does_not_pass_age_cutoff(self):
        """The /v3/speech-profile router must not filter profiles by age (#5128)."""
        router_src = Path(storage_mod.__file__).parents[2] / "routers" / "speech_profile.py"
        assert "max_age_days" not in router_src.read_text(encoding="utf-8")

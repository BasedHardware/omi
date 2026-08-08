"""Unit tests for the speech profile existence check (#5128).

/v3/speech-profile must report has_profile=true for ANY existing profile,
because the listen pipeline (routers/transcribe.py) uses the profile
regardless of age. A 90-day expiry applied only to this endpoint caused
users with older, actively-used profiles to be re-prompted to
"Teach Omi your voice" on every launch.
"""

import inspect
from pathlib import Path

from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore


class TestGetUserHasSpeechProfile:
    def _wire(self, monkeypatch, exists: bool) -> FakeObjectStore:
        store = FakeObjectStore()
        if exists:
            store.put("spb", "uid1/speech_profile.wav", b"x")
        monkeypatch.setattr(storage_mod, "_speech_profiles_bucket_name", lambda required=False: "spb")
        monkeypatch.setattr(storage_mod, "_object_store", lambda: store)
        return store

    def test_existing_profile_counts_regardless_of_age(self, monkeypatch):
        """An existing profile is reported as present — no age cutoff (#5128)."""
        store = self._wire(monkeypatch, exists=True)
        meta_reads = []
        monkeypatch.setattr(store, "get_metadata", lambda b, k: (meta_reads.append(k), None)[1])
        assert storage_mod.get_user_has_speech_profile("uid1") is True
        # No metadata fetch for age checks — the old expiry code called blob.reload()
        assert meta_reads == []

    def test_missing_profile(self, monkeypatch):
        self._wire(monkeypatch, exists=False)
        assert storage_mod.get_user_has_speech_profile("uid1") is False

    def test_missing_bucket(self, monkeypatch):
        monkeypatch.setattr(storage_mod, "_speech_profiles_bucket_name", lambda required=False: None)
        touched = []
        monkeypatch.setattr(storage_mod, "_object_store", lambda: touched.append(1))
        assert storage_mod.get_user_has_speech_profile("uid1") is False
        assert touched == []  # unconfigured bucket short-circuits before the store

    def test_no_age_parameter_in_signature(self):
        """Guard against reintroducing an expiry knob on the existence check."""
        params = inspect.signature(storage_mod.get_user_has_speech_profile).parameters
        assert list(params) == ["uid"]

    def test_endpoint_does_not_pass_age_cutoff(self):
        """The /v3/speech-profile router must not filter profiles by age (#5128)."""
        router_src = Path(storage_mod.__file__).parents[2] / "routers" / "speech_profile.py"
        assert "max_age_days" not in router_src.read_text(encoding="utf-8")

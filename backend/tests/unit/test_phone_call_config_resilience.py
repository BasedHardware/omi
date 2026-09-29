"""Unit tests for phone_call_config resilience, error boundaries, input sanitization, and cache behavior."""

from unittest.mock import MagicMock, patch
import pytest

from config.plan_catalog import PlanType
from database import phone_call_config


class TestPhoneCallConfigResilience:
    """Tests for Firestore resilience, cache lifecycle, and policy resolution."""

    def test_clean_iso2_country_valid(self):
        assert phone_call_config._clean_iso2_country("US") == "US"
        assert phone_call_config._clean_iso2_country("us") == "US"
        assert phone_call_config._clean_iso2_country("  gb  ") == "GB"
        assert phone_call_config._clean_iso2_country("de") == "DE"

    def test_clean_iso2_country_invalid(self):
        assert phone_call_config._clean_iso2_country(None) is None
        assert phone_call_config._clean_iso2_country("") is None
        assert phone_call_config._clean_iso2_country("   ") is None
        assert phone_call_config._clean_iso2_country("USA") is None
        assert phone_call_config._clean_iso2_country("12") is None
        assert phone_call_config._clean_iso2_country("U1") is None
        assert phone_call_config._clean_iso2_country(123) is None

    def test_fetch_config_not_found(self):
        fake_doc = MagicMock(exists=False)
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        result = phone_call_config._fetch_config(firestore_client=fake_client)
        assert result == {}
        fake_client.collection.assert_called_with("phone_call_config")
        fake_client.collection.return_value.document.assert_called_with("default")

    def test_fetch_config_found(self):
        data = {
            "free_plan": {"monthly_call_limit": 5, "max_duration_seconds": 300},
            "paid_plan": {"monthly_call_limit": None, "max_duration_seconds": None},
        }
        fake_doc = MagicMock(exists=True)
        fake_doc.to_dict.return_value = data
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        result = phone_call_config._fetch_config(firestore_client=fake_client)
        assert result == data

    def test_fetch_config_handles_storage_exception(self):
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.side_effect = RuntimeError(
            "Firestore transport unavailable"
        )

        # Must not raise; must fallback to empty dict
        result = phone_call_config._fetch_config(firestore_client=fake_client)
        assert result == {}

    def test_get_config_with_explicit_client_bypasses_cache(self):
        fake_client = MagicMock()
        fake_doc = MagicMock(exists=True)
        fake_doc.to_dict.return_value = {"free_plan": {"monthly_call_limit": 10}}
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        with patch.object(phone_call_config, "get_memory_cache") as mock_cache:
            res = phone_call_config._get_config(firestore_client=fake_client)
            assert res == {"free_plan": {"monthly_call_limit": 10}}
            mock_cache.assert_not_called()

    def test_get_config_uses_cache(self):
        fake_cache = MagicMock()
        fake_cache.get_or_fetch.return_value = {"free_plan": {"monthly_call_limit": 2}}

        with patch.object(phone_call_config, "get_memory_cache", return_value=fake_cache):
            res = phone_call_config._get_config()
            assert res == {"free_plan": {"monthly_call_limit": 2}}
            fake_cache.get_or_fetch.assert_called_once()
            args, _ = fake_cache.get_or_fetch.call_args
            assert args[0] == "phone_call_config:default"

    def test_get_config_handles_cache_exception(self):
        fake_cache = MagicMock()
        fake_cache.get_or_fetch.side_effect = RuntimeError("Redis connection broken")

        with (
            patch.object(phone_call_config, "get_memory_cache", return_value=fake_cache),
            patch.object(phone_call_config, "_fetch_config", return_value={"fallback": True}) as mock_fetch,
        ):
            res = phone_call_config._get_config()
            assert res == {"fallback": True}
            mock_fetch.assert_called_once_with(firestore_client=None)

    def test_invalidate_phone_call_config_cache(self):
        fake_cache = MagicMock()
        with patch.object(phone_call_config, "get_memory_cache", return_value=fake_cache):
            phone_call_config.invalidate_phone_call_config_cache()
            fake_cache.delete.assert_called_once_with("phone_call_config:default")

    def test_invalidate_cache_handles_exception(self):
        fake_cache = MagicMock()
        fake_cache.delete.side_effect = RuntimeError("Cache deletion error")
        with patch.object(phone_call_config, "get_memory_cache", return_value=fake_cache):
            # Must not raise
            phone_call_config.invalidate_phone_call_config_cache()

    def test_phone_call_profile_resolution(self):
        # Basic is free
        assert phone_call_config._phone_call_profile_for_plan(PlanType.basic) == "free"
        assert phone_call_config.is_paid_phone_call_plan(PlanType.basic) is False

        # None defaults to free
        assert phone_call_config._phone_call_profile_for_plan(None) == "free"
        assert phone_call_config.is_paid_phone_call_plan(None) is False

        # Whitespace and case-insensitive resolution
        assert phone_call_config._phone_call_profile_for_plan("  BASIC  ") == "free"
        assert phone_call_config._phone_call_profile_for_plan("basic") == "free"

        # Unknown plan falls back safely to free
        assert phone_call_config._phone_call_profile_for_plan("unknown_plan_xyz") == "free"
        assert phone_call_config.is_paid_phone_call_plan("unknown_plan_xyz") is False

    def test_declared_override_sanitizes_values(self):
        defaults = {
            "monthly_call_limit": 0,
            "max_duration_seconds": 180,
            "allowed_countries": [],
        }
        raw_override = {
            "monthly_call_limit": -10,  # negative clamped to 0
            "max_duration_seconds": 600,
            "allowed_countries": ["us", "GB", "invalid", 42, "  ca  "],
            "unexpected_rogue_field": "injected",
        }
        cleaned = phone_call_config._declared_override(raw_override, defaults)
        assert cleaned["monthly_call_limit"] == 0
        assert cleaned["max_duration_seconds"] == 600
        assert cleaned["allowed_countries"] == ["US", "GB", "CA"]
        assert "unexpected_rogue_field" not in cleaned

    def test_declared_override_preserves_none(self):
        defaults = {"monthly_call_limit": 5, "max_duration_seconds": 180, "allowed_countries": []}
        raw_override = {"monthly_call_limit": None, "max_duration_seconds": None}
        cleaned = phone_call_config._declared_override(raw_override, defaults)
        assert cleaned["monthly_call_limit"] is None
        assert cleaned["max_duration_seconds"] is None

    def test_ignored_override_fields(self):
        defaults = {"monthly_call_limit": 0, "max_duration_seconds": 180}
        override = {"monthly_call_limit": 5, "bad_field_b": 1, "bad_field_a": 2}
        ignored = phone_call_config._ignored_override_fields(override, defaults)
        assert ignored == ("bad_field_a", "bad_field_b")

    def test_effective_config_default_catalog_values(self):
        # When Firestore has no overrides, effective config matches catalog defaults
        with patch.object(phone_call_config, "_get_config", return_value={}):
            cfg = phone_call_config.get_free_plan_config()
            assert cfg["phone_calls_profile"] == "free"
            assert "monthly_call_limit" in cfg
            assert cfg["effective_overlay"]["source"] == "catalog"
            assert cfg["effective_overlay"]["declared"] is False

    def test_effective_config_with_firestore_override(self):
        fake_firestore_data = {
            "free_plan": {
                "monthly_call_limit": 15,
                "max_duration_seconds": 450,
                "allowed_countries": ["US"],
            }
        }
        with patch.object(phone_call_config, "_get_config", return_value=fake_firestore_data):
            cfg = phone_call_config.get_free_plan_config()
            assert cfg["monthly_call_limit"] == 15
            assert cfg["max_duration_seconds"] == 450
            assert cfg["allowed_countries"] == ["US"]
            assert cfg["effective_overlay"]["source"] == "firestore"
            assert cfg["effective_overlay"]["declared"] is True

    def test_get_config_for_plan_with_explicit_client(self):
        fake_client = MagicMock()
        fake_doc = MagicMock(exists=True)
        fake_doc.to_dict.return_value = {
            "free_plan": {"monthly_call_limit": 3},
            "paid_plan": {"monthly_call_limit": 100},
        }
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        cfg = phone_call_config.get_config_for_plan(PlanType.basic, firestore_client=fake_client)
        assert cfg["phone_calls_profile"] == "free"
        assert cfg["monthly_call_limit"] == 3

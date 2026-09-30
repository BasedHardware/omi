"""Unit tests for app_review_config input sanitization, error boundaries, and resilience."""

from unittest.mock import MagicMock, patch
import pytest

from database import app_review_config


class TestAppReviewConfigSanitizationAndResilience:
    """Tests for platform cleaning, error fallback boundaries, and subscription UI decision logic."""

    def test_clean_platform_valid(self):
        assert app_review_config._clean_platform("ios") == "ios"
        assert app_review_config._clean_platform("IOS") == "ios"
        assert app_review_config._clean_platform("  macos  ") == "macos"

    def test_clean_platform_empty_or_invalid(self):
        assert app_review_config._clean_platform(None) == ""
        assert app_review_config._clean_platform("") == ""
        assert app_review_config._clean_platform("   ") == ""
        # Path traversal and excessively long strings rejected
        assert app_review_config._clean_platform("../ios") == ""
        assert app_review_config._clean_platform("ios/config") == ""
        assert app_review_config._clean_platform("ios\\config") == ""
        assert app_review_config._clean_platform("a" * 70) == ""

    def test_fetch_review_config_not_found(self):
        fake_doc = MagicMock()
        fake_doc.exists = False
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        result = app_review_config._fetch_review_config("ios", firestore_client=fake_client)
        assert result == {}
        fake_client.collection.assert_called_with("app_review_config")
        fake_client.collection.return_value.document.assert_called_with("ios")

    def test_fetch_review_config_found(self):
        data = {"hidden_versions": ["1.0.531"], "reviewer_uids": ["rev-123"]}
        fake_doc = MagicMock()
        fake_doc.exists = True
        fake_doc.to_dict.return_value = data
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        result = app_review_config._fetch_review_config("ios", firestore_client=fake_client)
        assert result == data

    def test_fetch_review_config_handles_storage_exception(self):
        fake_client = MagicMock()
        fake_client.collection.return_value.document.return_value.get.side_effect = RuntimeError(
            "Firestore network timeout"
        )

        # Must not raise; must return empty dict
        result = app_review_config._fetch_review_config("ios", firestore_client=fake_client)
        assert result == {}

    def test_fetch_review_config_empty_platform_bypasses_storage(self):
        fake_client = MagicMock()
        result = app_review_config._fetch_review_config("", firestore_client=fake_client)
        assert result == {}
        fake_client.collection.assert_not_called()

    def test_get_review_config_with_explicit_client_bypasses_cache(self):
        fake_client = MagicMock()
        fake_doc = MagicMock(exists=True)
        fake_doc.to_dict.return_value = {"hidden_versions": ["2.0.0"]}
        fake_client.collection.return_value.document.return_value.get.return_value = fake_doc

        with patch.object(app_review_config, "get_memory_cache") as mock_cache:
            cfg = app_review_config.get_review_config("ios", firestore_client=fake_client)
            assert cfg == {"hidden_versions": ["2.0.0"]}
            mock_cache.assert_not_called()

    def test_get_review_config_caches_result(self):
        fake_cache = MagicMock()
        fake_cache.get_or_fetch.return_value = {"reviewer_uids": ["u1"]}

        with patch.object(app_review_config, "get_memory_cache", return_value=fake_cache):
            cfg = app_review_config.get_review_config("macos")
            assert cfg == {"reviewer_uids": ["u1"]}
            fake_cache.get_or_fetch.assert_called_once()
            args, _ = fake_cache.get_or_fetch.call_args
            assert args[0] == "app_review_config:macos"

    def test_get_review_config_handles_cache_exception(self):
        fake_cache = MagicMock()
        fake_cache.get_or_fetch.side_effect = RuntimeError("Redis/Memcache unavailable")

        with (
            patch.object(app_review_config, "get_memory_cache", return_value=fake_cache),
            patch.object(app_review_config, "_fetch_review_config", return_value={"fallback": True}) as mock_fetch,
        ):
            cfg = app_review_config.get_review_config("ios")
            assert cfg == {"fallback": True}
            mock_fetch.assert_called_once_with("ios", firestore_client=None)

    def test_invalidate_review_config_cache(self):
        fake_cache = MagicMock()
        with patch.object(app_review_config, "get_memory_cache", return_value=fake_cache):
            # Invalidate single platform
            app_review_config.invalidate_review_config_cache("ios")
            fake_cache.delete.assert_called_with("app_review_config:ios")

            # Invalidate all platforms
            fake_cache.reset_mock()
            app_review_config.invalidate_review_config_cache()
            assert fake_cache.delete.call_count == 2
            fake_cache.delete.assert_any_call("app_review_config:ios")
            fake_cache.delete.assert_any_call("app_review_config:macos")

    def test_should_hide_subscription_ui_unsupported_platform(self):
        # Unsupported platforms should always show subscription UI (hide == False)
        assert app_review_config.should_hide_subscription_ui("user-1", "android", "1.0.0") is False
        assert app_review_config.should_hide_subscription_ui("user-1", "windows", "1.0.0") is False
        assert app_review_config.should_hide_subscription_ui("user-1", None, "1.0.0") is False
        assert app_review_config.should_hide_subscription_ui("user-1", "", "1.0.0") is False

    def test_should_hide_subscription_ui_matches_reviewer_uid(self):
        cfg = {"reviewer_uids": ["reviewer-apple-1", "reviewer-apple-2"], "hidden_versions": []}
        with patch.object(app_review_config, "get_review_config", return_value=cfg):
            assert app_review_config.should_hide_subscription_ui("reviewer-apple-1", "ios", "1.0.0") is True
            assert app_review_config.should_hide_subscription_ui("reviewer-apple-2", "macos", "1.0.0") is True
            assert app_review_config.should_hide_subscription_ui("normal-user", "ios", "1.0.0") is False

    def test_should_hide_subscription_ui_matches_whitespace_and_casing(self):
        cfg = {"reviewer_uids": ["reviewer-apple-1"], "hidden_versions": []}
        with patch.object(app_review_config, "get_review_config", return_value=cfg):
            # Platform with leading/trailing spaces and uppercase
            assert app_review_config.should_hide_subscription_ui("reviewer-apple-1", "  IOS  ", "1.0.0") is True
            assert app_review_config.should_hide_subscription_ui("  reviewer-apple-1  ", "ios", "1.0.0") is True

    def test_should_hide_subscription_ui_matches_hidden_version(self):
        cfg = {"reviewer_uids": [], "hidden_versions": ["1.0.531", "1.0.532+100"]}
        with patch.object(app_review_config, "get_review_config", return_value=cfg):
            # Exact match
            assert app_review_config.should_hide_subscription_ui("u1", "ios", "1.0.531") is True
            # Build number match with base semantic version
            assert app_review_config.should_hide_subscription_ui("u1", "ios", "1.0.531+607") is True
            # Different version
            assert app_review_config.should_hide_subscription_ui("u1", "ios", "1.0.533") is False

    def test_should_hide_subscription_ui_handles_malformed_version_safely(self):
        cfg = {"reviewer_uids": [], "hidden_versions": ["1.0.531", "corrupted.version.string"]}
        with patch.object(app_review_config, "get_review_config", return_value=cfg):
            # When caller passes an invalid/unparseable version string
            with patch.object(app_review_config, "compare_versions", side_effect=ValueError("Invalid version")):
                assert app_review_config.should_hide_subscription_ui("u1", "ios", "invalid..version") is False

    def test_should_hide_subscription_ui_handles_firestore_failure(self):
        with patch.object(app_review_config, "get_review_config", return_value={}):
            assert app_review_config.should_hide_subscription_ui("u1", "ios", "1.0.531") is False

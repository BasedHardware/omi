"""
Unit tests for input validation, whitespace normalization, and error boundaries
in database.app_review_config (#19990).
"""

from unittest.mock import MagicMock, patch
import pytest

from database.app_review_config import (
    _fetch_review_config,
    get_review_config,
    should_hide_subscription_ui,
)


def test_fetch_review_config_handles_non_string_platform():
    assert _fetch_review_config(None) == {}
    assert _fetch_review_config(123) == {}
    assert _fetch_review_config("") == {}
    assert _fetch_review_config("   ") == {}


def test_fetch_review_config_handles_firestore_exception():
    with patch("database.app_review_config.db") as mock_db:
        mock_db.collection.side_effect = Exception("Firestore connection timeout")
        result = _fetch_review_config("ios")
        assert result == {}


def test_get_review_config_handles_invalid_platform():
    assert get_review_config(None) == {}
    assert get_review_config(123) == {}
    assert get_review_config("") == {}


def test_should_hide_subscription_ui_handles_non_string_platform():
    # Non-string platform must return False instead of raising AttributeError
    assert should_hide_subscription_ui("user1", None, "1.0.0") is False
    assert should_hide_subscription_ui("user1", 123, "1.0.0") is False
    assert should_hide_subscription_ui("user1", {}, "1.0.0") is False
    assert should_hide_subscription_ui("user1", "android", "1.0.0") is False


def test_should_hide_subscription_ui_matches_reviewer_uid_with_whitespace():
    mock_config = {
        "reviewer_uids": ["  reviewer_apple_1  ", "reviewer_2"],
        "hidden_versions": [],
    }
    with patch("database.app_review_config.get_review_config", return_value=mock_config):
        # Exact match
        assert should_hide_subscription_ui("reviewer_2", "ios", "1.0.0") is True
        # Match with whitespace in config
        assert should_hide_subscription_ui("reviewer_apple_1", "ios", "1.0.0") is True
        # Match with whitespace in input uid
        assert should_hide_subscription_ui("  reviewer_apple_1  ", "ios", "1.0.0") is True
        # Match with case-insensitive platform
        assert should_hide_subscription_ui("reviewer_apple_1", "  IOS  ", "1.0.0") is True
        # Non-matching user
        assert should_hide_subscription_ui("normal_user", "ios", "1.0.0") is False
        # Non-string uid
        assert should_hide_subscription_ui(None, "ios", "1.0.0") is False


def test_should_hide_subscription_ui_matches_version_with_whitespace_and_handles_malformed():
    mock_config = {
        "reviewer_uids": [],
        "hidden_versions": ["  1.0.531  ", "2.0.0+100"],
    }
    with patch("database.app_review_config.get_review_config", return_value=mock_config):
        # Match version with whitespace
        assert should_hide_subscription_ui("user1", "ios", "1.0.531") is True
        assert should_hide_subscription_ui("user1", "ios", "  1.0.531  ") is True
        assert should_hide_subscription_ui("user1", "ios", "1.0.531+600") is True
        # Non-hidden version
        assert should_hide_subscription_ui("user1", "ios", "1.0.532") is False
        # Non-string app_version
        assert should_hide_subscription_ui("user1", "ios", None) is False


def test_should_hide_subscription_ui_handles_corrupt_version_exception():
    mock_config = {
        "reviewer_uids": [],
        "hidden_versions": ["corrupted_version"],
    }
    with patch("database.app_review_config.get_review_config", return_value=mock_config):
        with patch("database.app_review_config.compare_versions", side_effect=ValueError("Invalid version format")):
            # Should catch exception and not crash
            assert should_hide_subscription_ui("user1", "ios", "1.0.0") is False

"""
Unit tests for input validation, whitespace normalization, and error boundaries
in database.app_review_config (#19990).
"""

from unittest.mock import Mock, patch

import pytest

from database.app_review_config import (
    _SUPPORTED_PLATFORMS,
    _fetch_review_config,
    get_review_config,
    should_hide_subscription_ui,
)

SUPPORTED_REVIEW_PLATFORMS = ("ios", "macos", "android")


def test_review_config_behavior_matrix_covers_every_supported_platform():
    # Adding a platform to production gating must extend the matrix below.
    assert _SUPPORTED_PLATFORMS == set(SUPPORTED_REVIEW_PLATFORMS)


@pytest.mark.parametrize("platform", SUPPORTED_REVIEW_PLATFORMS)
@pytest.mark.parametrize(
    ("config", "uid", "app_version", "expected"),
    [
        pytest.param({"hidden_versions": ["1.0.531+607"]}, "user", "1.0.531+607", True, id="exact-build"),
        pytest.param({"hidden_versions": ["1.0.531"]}, "user", "1.0.531+607", True, id="semantic-version"),
        pytest.param({"reviewer_uids": ["reviewer"]}, "reviewer", "9.9.9+1", True, id="reviewer-uid"),
        pytest.param({}, "user", "1.0.531+607", False, id="missing-document"),
        pytest.param(
            {"hidden_versions": ["1.0.532"], "reviewer_uids": ["another-user"]},
            "user",
            "1.0.531+607",
            False,
            id="no-match",
        ),
    ],
)
def test_supported_platforms_share_subscription_review_config_behavior(
    monkeypatch, platform, config, uid, app_version, expected
):
    monkeypatch.setattr("database.app_review_config.get_review_config", lambda _platform: config)

    assert should_hide_subscription_ui(uid, platform, app_version) is expected


@pytest.mark.parametrize("platform", ["windows", "web", "", "   ", None])
def test_unsupported_or_blank_platform_never_hides_subscription_ui(monkeypatch, platform):
    matching_config = {"hidden_versions": ["1.0.531"], "reviewer_uids": ["reviewer"]}
    monkeypatch.setattr("database.app_review_config.get_review_config", lambda _platform: matching_config)

    assert should_hide_subscription_ui("reviewer", platform, "1.0.531+607") is False


def test_fetch_review_config_handles_non_string_platform():
    assert _fetch_review_config(None) == {}
    assert _fetch_review_config(123) == {}
    assert _fetch_review_config("") == {}
    assert _fetch_review_config("   ") == {}


def test_fetch_review_config_handles_firestore_exception():
    mock_db = Mock()
    mock_db.collection.side_effect = Exception("Firestore connection timeout")
    with patch("database.app_review_config.db", mock_db):
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

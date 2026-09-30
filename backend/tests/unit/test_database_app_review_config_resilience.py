"""Hermetic unit tests for backend/database/app_review_config.py resilience guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from database import app_review_config


class FakeMemoryCache:
    def __init__(self):
        self.store: dict[str, object] = {}

    def get_or_fetch(self, key: str, fetch_fn, ttl: int | None = None):
        if key not in self.store:
            self.store[key] = fetch_fn()
        return self.store[key]

    def clear(self):
        self.store.clear()


@pytest.fixture
def fake_cache(monkeypatch):
    cache = FakeMemoryCache()
    monkeypatch.setattr(app_review_config, "get_memory_cache", lambda: cache)
    return cache


# --- Tests for get_review_config ---

@pytest.mark.parametrize("invalid_platform", [None, "", "   ", 123, [], {}])
def test_get_review_config_rejects_invalid_platform(fake_cache, invalid_platform):
    assert app_review_config.get_review_config(invalid_platform) == {}


def test_get_review_config_fetches_and_caches_clean_platform(fake_cache):
    fake_db = MagicMock()
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {
        "hidden_versions": ["1.0.531"],
        "reviewer_uids": ["rev-123"],
    }
    fake_db.collection.return_value.document.return_value.get.return_value = doc_mock

    with patch.object(app_review_config, "db", fake_db):
        res1 = app_review_config.get_review_config("  iOS  ")
        assert res1 == {"hidden_versions": ["1.0.531"], "reviewer_uids": ["rev-123"]}
        fake_db.collection.return_value.document.assert_called_with("ios")

        # Second call should be served from memory cache
        res2 = app_review_config.get_review_config("ios")
        assert res2 == res1
        assert fake_db.collection.return_value.document.call_count == 1


def test_get_review_config_recovers_gracefully_from_firestore_error(fake_cache):
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.side_effect = RuntimeError("Firestore unavailable")

    with patch.object(app_review_config, "db", fake_db):
        res = app_review_config.get_review_config("macos")
        assert res == {}


# --- Tests for should_hide_subscription_ui ---

@pytest.mark.parametrize("invalid_platform", [None, "", "   ", 123, "android", "windows", "linux"])
def test_should_hide_subscription_ui_returns_false_for_unsupported_or_invalid_platform(fake_cache, invalid_platform):
    assert app_review_config.should_hide_subscription_ui("user-1", invalid_platform, "1.0.0") is False


def test_should_hide_subscription_ui_matches_reviewer_uid(fake_cache):
    config_mock = {
        "reviewer_uids": ["rev-apple-1", "rev-apple-2"],
        "hidden_versions": [],
    }

    with patch.object(app_review_config, "get_review_config", return_value=config_mock):
        # Match with whitespace
        assert app_review_config.should_hide_subscription_ui("  rev-apple-1  ", "ios", "1.0.0") is True
        assert app_review_config.should_hide_subscription_ui("rev-apple-2", "MacOS", "1.0.0") is True
        # Non-matching user
        assert app_review_config.should_hide_subscription_ui("regular-user", "ios", "1.0.0") is False
        # Empty/non-string user
        assert app_review_config.should_hide_subscription_ui("", "ios", "1.0.0") is False
        assert app_review_config.should_hide_subscription_ui(None, "ios", "1.0.0") is False  # type: ignore[arg-type]


def test_should_hide_subscription_ui_matches_hidden_version(fake_cache):
    config_mock = {
        "reviewer_uids": [],
        "hidden_versions": ["1.0.531", "2.0.0"],
    }

    with patch.object(app_review_config, "get_review_config", return_value=config_mock):
        # Semantic match (e.g. build 607 of 1.0.531)
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "1.0.531+607") is True
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "  1.0.531  ") is True
        assert app_review_config.should_hide_subscription_ui("user-1", "macos", "2.0.0") is True
        # Different version
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "1.0.532") is False
        # Empty/non-string version
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "") is False
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", None) is False


def test_should_hide_subscription_ui_handles_corrupt_config_and_versions(fake_cache):
    config_mock = {
        "reviewer_uids": "corrupt-string",
        "hidden_versions": [None, 123, "1.0.0"],
    }

    with patch.object(app_review_config, "get_review_config", return_value=config_mock):
        # Must not crash on non-list reviewer_uids or non-string version items
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "2.0.0") is False
        # Malformed version string does not crash
        assert app_review_config.should_hide_subscription_ui("user-1", "ios", "2.0.0+invalid") is False

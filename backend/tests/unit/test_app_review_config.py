import unittest
from unittest.mock import MagicMock, patch

from database.app_review_config import (
    _SUPPORTED_PLATFORMS,
    get_review_config,
    invalidate_review_config_cache,
    should_hide_subscription_ui,
)
from database.cache_manager import InMemoryCacheManager


class TestAppReviewConfig(unittest.TestCase):
    def setUp(self):
        self._fake_cache = InMemoryCacheManager(max_memory_mb=10)
        self._cache_patch = patch("database.app_review_config.get_memory_cache", return_value=self._fake_cache)
        self._cache_patch.start()
        invalidate_review_config_cache()

    def tearDown(self):
        self._cache_patch.stop()

    def test_supported_platforms_contains_android_ios_macos(self):
        self.assertIn("ios", _SUPPORTED_PLATFORMS)
        self.assertIn("macos", _SUPPORTED_PLATFORMS)
        self.assertIn("android", _SUPPORTED_PLATFORMS)

    def test_unsupported_platform_returns_false(self):
        self.assertFalse(should_hide_subscription_ui("user1", "windows", "1.0.0"))
        self.assertFalse(should_hide_subscription_ui("user1", "", "1.0.0"))
        self.assertFalse(should_hide_subscription_ui("user1", None, "1.0.0"))

    def test_reviewer_uid_matches(self):
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "reviewer_uids": ["apple_reviewer_1", "google_reviewer_android"],
            "hidden_versions": ["2.0.0"],
        }
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        # Android reviewer matches
        self.assertTrue(
            should_hide_subscription_ui("google_reviewer_android", "android", "1.5.0", firestore_client=mock_client)
        )
        # iOS reviewer matches
        self.assertTrue(should_hide_subscription_ui("apple_reviewer_1", "ios", "1.5.0", firestore_client=mock_client))
        # Normal user does not match reviewer
        self.assertFalse(should_hide_subscription_ui("normal_user", "android", "1.5.0", firestore_client=mock_client))

    def test_hidden_version_matches(self):
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "reviewer_uids": [],
            "hidden_versions": ["1.0.531"],
        }
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        # Exact semantic version matches
        self.assertTrue(should_hide_subscription_ui("user1", "android", "1.0.531", firestore_client=mock_client))
        # Build variant of hidden version matches
        self.assertTrue(should_hide_subscription_ui("user1", "android", "1.0.531+607", firestore_client=mock_client))
        # Different version does not match
        self.assertFalse(should_hide_subscription_ui("user1", "android", "1.0.532", firestore_client=mock_client))

    def test_firestore_failure_fails_open_gracefully(self):
        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.get.side_effect = RuntimeError(
            "Firestore unavailable"
        )

        # Must not raise an exception; must return False safely
        self.assertFalse(should_hide_subscription_ui("user1", "android", "1.0.0", firestore_client=mock_client))

    def test_cache_invalidation(self):
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"reviewer_uids": ["u1"]}
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        # Fetch and cache
        cfg1 = get_review_config("android", firestore_client=mock_client)
        self.assertEqual(cfg1.get("reviewer_uids"), ["u1"])

        # Update mock return
        mock_doc.to_dict.return_value = {"reviewer_uids": ["u2"]}
        # Invalidate cache
        invalidate_review_config_cache("android")

        # Refetch gets updated value
        cfg2 = get_review_config("android", firestore_client=mock_client)
        self.assertEqual(cfg2.get("reviewer_uids"), ["u2"])


if __name__ == "__main__":
    unittest.main()

"""Hermetic tests for Twitter chat tools shared-secret authentication guard.

Tests Issue #14451: prevents unauthorized callers from executing actions or reading
data with a victim's Twitter OAuth credentials by requiring TWITTER_TOOLS_SECRET on
all ten /tools/* endpoints.
"""

from __future__ import annotations

import os
import sys
import unittest

APP_DIR = os.path.abspath(os.path.dirname(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import hermetic_stubs

hermetic_stubs.ensure_fastapi()
HTTPException = hermetic_stubs.http_exception()

import twitter_tools_auth as auth

TEST_SECRET = "test-twitter-tools-secret-key-12345"


class TwitterToolsAuthDirectTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("TWITTER_TOOLS_SECRET")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TWITTER_TOOLS_SECRET", None)
        else:
            os.environ["TWITTER_TOOLS_SECRET"] = self._old

    def test_fails_closed_when_unconfigured_or_blank(self):
        os.environ.pop("TWITTER_TOOLS_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(authorization=f"Bearer {TEST_SECRET}")
        self.assertEqual(ctx.exception.status_code, 503)

        os.environ["TWITTER_TOOLS_SECRET"] = "   "
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(authorization=f"Bearer {TEST_SECRET}")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_401_on_missing_credentials(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(authorization=None, twitter_tools_token=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_bearer_token(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(authorization="Bearer wrong-secret-token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_malformed_authorization_header(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        for malformed in ("Basic dXNlcjpwYXNz", "Bearer", "NotBearer token", "Bearer token extra"):
            with self.subTest(header=malformed):
                with self.assertRaises(HTTPException) as ctx:
                    auth.require_twitter_tools_auth(authorization=malformed)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_query_token(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(twitter_tools_token="wrong-query-token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_passes_with_correct_bearer_token(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        # Standard Bearer
        auth.require_twitter_tools_auth(authorization=f"Bearer {TEST_SECRET}")
        # Case-insensitive scheme match
        auth.require_twitter_tools_auth(authorization=f"bearer {TEST_SECRET}")

    def test_passes_with_correct_query_token(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        auth.require_twitter_tools_auth(twitter_tools_token=TEST_SECRET)

    def test_non_ascii_token_returns_401_without_500_type_error(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_twitter_tools_auth(authorization="Bearer \U0001f511\u26a0")
        self.assertEqual(ctx.exception.status_code, 401)


class TwitterToolsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = hermetic_stubs.load_main(APP_DIR)

    def test_all_ten_tools_handlers_accept_auth_dependency(self):
        expected_tools = [
            "tool_post_tweet",
            "tool_get_timeline",
            "tool_get_my_tweets",
            "tool_get_mentions",
            "tool_search_tweets",
            "tool_like_tweet",
            "tool_unlike_tweet",
            "tool_retweet",
            "tool_delete_tweet",
            "tool_get_user_profile",
        ]
        import inspect

        for tool_name in expected_tools:
            handler = getattr(self.main, tool_name, None)
            self.assertIsNotNone(handler, f"Missing tool handler: {tool_name}")
            sig = inspect.signature(handler)
            self.assertIn(
                "_auth",
                sig.parameters,
                f"Handler {tool_name} must declare _auth dependency parameter",
            )
            param = sig.parameters["_auth"]
            self.assertIsNotNone(param.default, f"Handler {tool_name} _auth must have a default Depends")


if __name__ == "__main__":
    unittest.main()

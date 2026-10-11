"""Hermetic tests for the Twitter disconnect HMAC guard."""

import os
import sys
import unittest
from unittest.mock import patch

APP_DIR = os.path.abspath(os.path.dirname(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import hermetic_stubs

# The Hygiene lane runs a bare python3 with no fastapi, so register the stub
# before importing twitter_link_auth -- it does `from fastapi import HTTPException`
# at module scope and would otherwise fail collection there while passing on a
# developer machine that happens to have fastapi installed.
hermetic_stubs.ensure_fastapi()
HTTPException = hermetic_stubs.http_exception()

import twitter_link_auth as auth

TEST_SECRET = "test-twitter-tools-secret"


class TwitterLinkAuthTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("TWITTER_TOOLS_SECRET")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TWITTER_TOOLS_SECRET", None)
        else:
            os.environ["TWITTER_TOOLS_SECRET"] = self._old

    def test_fails_closed_when_unconfigured(self):
        os.environ.pop("TWITTER_TOOLS_SECRET", None)
        self.assertEqual(auth.sign_uid("user-1"), "")
        with self.assertRaises(HTTPException) as ctx:
            auth.require_signed_link("user-1", "")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_401_on_missing_or_wrong_signature(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_signed_link("user-1", "")
        self.assertEqual(ctx.exception.status_code, 401)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_signed_link("user-1", "0" * 64)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_passes_with_correct_signature(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        auth.require_signed_link("user-1", auth.sign_uid("user-1"))

    def test_signature_is_per_uid(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        self.assertEqual(auth.sign_uid("user-1"), auth.sign_uid("user-1"))
        self.assertNotEqual(auth.sign_uid("user-1"), auth.sign_uid("user-2"))

    def test_disconnect_does_not_delete_without_a_valid_signature(self):
        os.environ["TWITTER_TOOLS_SECRET"] = TEST_SECRET
        import asyncio

        twitter_main = hermetic_stubs.load_main(APP_DIR)

        with patch.object(twitter_main, "delete_twitter_tokens") as delete:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(twitter_main.disconnect("victim", ""))
            self.assertEqual(ctx.exception.status_code, 401)
            delete.assert_not_called()

            asyncio.run(twitter_main.disconnect("victim", auth.sign_uid("victim")))
            delete.assert_called_once_with("victim")


if __name__ == "__main__":
    unittest.main()

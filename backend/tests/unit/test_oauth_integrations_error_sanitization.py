"""Hermetic unit tests for error sanitization in OAuth router.

Verifies that Firebase ID token validation failures do not leak token secrets, transport exceptions,
or provider details into HTTP 401 responses.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router

FIREBASE_TRACE = "Failed to establish HTTPSConnectionPool to www.googleapis.com:443"
LEAK_MARKERS = ("HTTPSConnectionPool", "googleapis", "RuntimeError", "Traceback")


class OAuthErrorSanitizationTests(unittest.TestCase):
    def test_oauth_firebase_invalid_id_token_sanitized(self):
        with _loaded_oauth_router() as (oauth, firebase_auth, _apps_db):
            req = MagicMock()
            req.cookies.get.return_value = "valid_csrf"

            def _raise_invalid(*args, **kwargs):
                raise firebase_auth.InvalidIdTokenError(FIREBASE_TRACE)

            firebase_auth.verify_id_token = _raise_invalid

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    oauth.oauth_token(
                        firebase_id_token="bad_token",
                        app_id="app-1",
                        state="opaque",
                        csrf_token="valid_csrf",
                        oauth_csrf_cookie="valid_csrf",
                    )
                )

            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Invalid Firebase ID token.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, str(ctx.exception.detail))

    def test_oauth_firebase_unexpected_error_sanitized(self):
        with _loaded_oauth_router() as (oauth, firebase_auth, _apps_db):
            req = MagicMock()
            req.cookies.get.return_value = "valid_csrf"

            def _raise_runtime(*args, **kwargs):
                raise RuntimeError(FIREBASE_TRACE)

            firebase_auth.verify_id_token = _raise_runtime

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    oauth.oauth_token(
                        firebase_id_token="bad_token",
                        app_id="app-1",
                        state="opaque",
                        csrf_token="valid_csrf",
                        oauth_csrf_cookie="valid_csrf",
                    )
                )

            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Error verifying Firebase ID token.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()

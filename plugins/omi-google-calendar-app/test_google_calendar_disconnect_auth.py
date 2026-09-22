"""Hermetic regression tests for the Google Calendar disconnect HMAC guard.

Covers the `google_calendar_disconnect_auth` dependency: fail-closed 503 when the signing secret is
not configured, 401 on missing/wrong signature, accept on signed uid.
Matches the style of test_shipbob_tools_auth.py (PR #14684).
"""

import os
import sys
import unittest

APP_DIR = os.path.abspath(os.path.dirname(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

SDK_DIR = os.path.abspath(os.path.join(APP_DIR, "..", "omi-plugin-sdk", "src"))
if os.path.exists(SDK_DIR) and SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

from fastapi import HTTPException

import google_calendar_disconnect_auth as auth

TEST_SECRET = "test-google_calendar-disconnect-secret"


class GoogleCalendarDisconnectAuthUnitTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("GOOGLE_CALENDAR_DISCONNECT_SECRET")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("GOOGLE_CALENDAR_DISCONNECT_SECRET", None)
        else:
            os.environ["GOOGLE_CALENDAR_DISCONNECT_SECRET"] = self._old

    def test_fails_closed_when_unconfigured(self):
        os.environ.pop("GOOGLE_CALENDAR_DISCONNECT_SECRET", None)
        self.assertEqual(auth.sign_uid("test-uid"), "")
        with self.assertRaises(HTTPException) as ctx:
            auth.require_disconnect_auth("test-uid", "")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_401_on_missing_or_wrong_signature(self):
        os.environ["GOOGLE_CALENDAR_DISCONNECT_SECRET"] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_disconnect_auth("test-uid", "")
        self.assertEqual(ctx.exception.status_code, 401)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_disconnect_auth("test-uid", "0" * 64)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_passes_with_correct_signature(self):
        os.environ["GOOGLE_CALENDAR_DISCONNECT_SECRET"] = TEST_SECRET
        sig = auth.sign_uid("test-uid")
        try:
            auth.require_disconnect_auth("test-uid", sig)
        except HTTPException:
            self.fail("require_disconnect_auth should not raise with the correct signature")

    def test_sign_uid_consistent_per_uid(self):
        os.environ["GOOGLE_CALENDAR_DISCONNECT_SECRET"] = TEST_SECRET
        self.assertEqual(auth.sign_uid("consistent-uid"), auth.sign_uid("consistent-uid"))

    def test_sign_uid_differentiates_uids(self):
        os.environ["GOOGLE_CALENDAR_DISCONNECT_SECRET"] = TEST_SECRET
        self.assertNotEqual(auth.sign_uid("uid-a"), auth.sign_uid("uid-b"))


if __name__ == "__main__":
    unittest.main()

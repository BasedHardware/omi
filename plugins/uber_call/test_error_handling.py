"""Hermetic error-handling regression suite for uber_call plugin.

Verifies that:
1. Unexpected internal exceptions never leak sensitive file paths, credentials,
   or traceback details into the HTTP response.
2. Non-dict geolocation payloads do not crash `_geo_value` with AttributeError.
3. Boolean coordinates are explicitly rejected rather than coerced into numeric values.
4. Non-string text inputs to location formatting do not raise unhandled AttributeErrors.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException
from main import CallUberRequest, _geo_value, call_uber
from uber_links import _clean_text, _normalize_float, build_location

SECRET_PATH = "/srv/secrets/uber_api_credentials.json"
LEAK_MARKERS = (SECRET_PATH, "RuntimeError", "Traceback", "AttributeError")


class UberErrorHandlingTests(unittest.TestCase):
    def test_unexpected_exception_in_call_uber_returns_generic_500(self):
        req = CallUberRequest(destination="SFO Airport")
        with patch("main.build_uber_deep_links", side_effect=RuntimeError(SECRET_PATH)):
            with self.assertRaises(HTTPException) as ctx:
                call_uber(req)

            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to prepare Uber ride link.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, str(ctx.exception.detail))

    def test_non_dict_geolocation_does_not_crash_geo_value(self):
        non_dict_inputs = ["San Francisco", 12345, [37.77, -122.41], False]
        for val in non_dict_inputs:
            with self.subTest(val=val):
                res = _geo_value(val, "latitude", "lat")
                self.assertIsNone(res)

    def test_boolean_coordinates_rejected(self):
        for bool_val in [True, False]:
            with self.subTest(bool_val=bool_val):
                with self.assertRaises(ValueError) as ctx:
                    _normalize_float(bool_val)
                self.assertIn("bool", str(ctx.exception))

    def test_non_string_clean_text_coerced_safely(self):
        self.assertIsNone(_clean_text(None))
        self.assertEqual(_clean_text(12345), "12345")
        self.assertEqual(_clean_text("  SFO   Airport  "), "SFO Airport")

    def test_valid_call_uber_succeeds(self):
        req = CallUberRequest(destination="SFO Airport", pickup_address="Market St")
        res = call_uber(req)
        self.assertIn("result", res)
        self.assertIn("web_link", res)
        self.assertIn("app_link", res)
        self.assertIn("m.uber.com", res["web_link"])


if __name__ == "__main__":
    unittest.main()

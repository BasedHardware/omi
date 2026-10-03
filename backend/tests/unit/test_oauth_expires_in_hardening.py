"""Hermetic tests for OAuth expires_in hardening in task_integrations_ops."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.task_integrations_ops import (
    MAX_OAUTH_EXPIRES_IN_SECONDS,
    coerce_expires_in,
)


class TestCoerceExpiresIn(unittest.TestCase):
    def test_accepts_positive_int(self):
        self.assertEqual(coerce_expires_in(3600), 3600)
        self.assertEqual(coerce_expires_in(1), 1)

    def test_accepts_numeric_string(self):
        # Providers sometimes return expires_in as a string.
        self.assertEqual(coerce_expires_in("3600"), 3600)
        self.assertEqual(coerce_expires_in(" 3600 "), 3600)

    def test_accepts_integral_float(self):
        self.assertEqual(coerce_expires_in(3600.0), 3600)

    def test_rejects_non_numeric_string(self):
        self.assertIsNone(coerce_expires_in("soon"))
        self.assertIsNone(coerce_expires_in(""))

    def test_rejects_none(self):
        self.assertIsNone(coerce_expires_in(None))

    def test_rejects_wrong_types(self):
        self.assertIsNone(coerce_expires_in({"seconds": 3600}))
        self.assertIsNone(coerce_expires_in([3600]))
        self.assertIsNone(coerce_expires_in(object()))

    def test_rejects_bool(self):
        # bool is an int subclass; True must not become a 1-second expiry.
        self.assertIsNone(coerce_expires_in(True))
        self.assertIsNone(coerce_expires_in(False))

    def test_rejects_non_positive(self):
        self.assertIsNone(coerce_expires_in(0))
        self.assertIsNone(coerce_expires_in(-1))

    def test_rejects_absurd_values(self):
        self.assertIsNone(coerce_expires_in(MAX_OAUTH_EXPIRES_IN_SECONDS + 1))
        self.assertEqual(coerce_expires_in(MAX_OAUTH_EXPIRES_IN_SECONDS), MAX_OAUTH_EXPIRES_IN_SECONDS)

    def test_rejects_nan_and_inf(self):
        self.assertIsNone(coerce_expires_in(float("nan")))
        self.assertIsNone(coerce_expires_in(float("inf")))
        self.assertIsNone(coerce_expires_in(float("-inf")))


class TestRegressionCrashInputs(unittest.TestCase):
    """The exact shapes that raised TypeError before the fix."""

    def test_previously_crashing_inputs_are_now_safe(self):
        from datetime import datetime, timedelta, timezone

        for bad in ["3600", None, {"a": 1}, [], True, float("nan")]:
            with self.subTest(value=bad):
                seconds = coerce_expires_in(bad)
                if seconds is None:
                    continue  # skipped, no crash
                # When a value IS accepted, timedelta must not raise.
                datetime.now(timezone.utc) + timedelta(seconds=seconds)

    def test_string_expiry_would_have_crashed_before(self):
        from datetime import timedelta

        # Documents the original bug: raw string straight into timedelta.
        with self.assertRaises(TypeError):
            timedelta(seconds="3600")
        # The hardened path avoids it entirely.
        self.assertEqual(coerce_expires_in("3600"), 3600)
        from datetime import datetime, timezone
        dt = datetime.now(timezone.utc) + timedelta(seconds=coerce_expires_in("3600"))
        self.assertIsNotNone(dt)


if __name__ == "__main__":
    unittest.main()
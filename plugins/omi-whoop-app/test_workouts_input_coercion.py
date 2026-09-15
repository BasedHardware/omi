"""Regression tests for the Whoop chat tools' input coercion (#13931).

The Omi backend forwards every non-required chat-tool parameter, so a call that
omits `days`/`max_results` reaches the plugin as an explicit JSON `null`. These
tests drive the production handlers through the `requests.get` seam with a fake
transport, so they exercise the real endpoint code and never touch the network.
"""
import asyncio
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from whoop_test_support import DummyRequest, load_main

main = load_main()


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text if payload is None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def _workout_payload():
    return {
        "records": [
            {
                "id": "w1",
                "start": "2026-09-14T07:00:00.000Z",
                "end": "2026-09-14T08:00:00.000Z",
                "sport_name": "running",
                "score": {"strain": 12.5, "average_heart_rate": 142, "max_heart_rate": 171},
            }
        ]
    }


class WorkoutInputCoercionTests(unittest.TestCase):
    """`days`/`max_results` arrive as JSON null and must not reach min()/WHOOP."""

    def setUp(self):
        token_patcher = patch.object(main, "get_valid_access_token", return_value="test-token")
        self.addCleanup(token_patcher.stop)
        token_patcher.start()
        self.calls = []

    def _patch_get(self, response):
        def fake_get(url, headers=None, params=None, timeout=None):
            self.calls.append({"url": url, "headers": headers, "params": params})
            return response

        patcher = patch.object(main.requests, "get", side_effect=fake_get)
        self.addCleanup(patcher.stop)
        patcher.start()
        return patcher

    def _post(self, body):
        return asyncio.run(main.tool_get_workouts(DummyRequest(body)))

    def test_json_null_optionals_fall_back_to_defaults(self):
        """Regression: min(None, 30) raised TypeError and the tool always failed."""
        self._patch_get(FakeResponse(200, _workout_payload()))

        response = self._post({"uid": "u1", "days": None, "max_results": None})

        self.assertIsNone(response.error, response.error)
        self.assertIn("**Workouts (Last 7 Days)**", response.result)

        params = self.calls[0]["params"]
        self.assertEqual(params["limit"], 10)
        start, end = params["start"], params["end"]
        # The requested start date is seven days before the end date.
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        self.assertEqual(end_dt.date() - start_dt.date(), timedelta(days=7))

    def test_missing_and_null_optionals_agree(self):
        self._patch_get(FakeResponse(200, _workout_payload()))
        omitted = self._post({"uid": "u1"})
        nulled = self._post({"uid": "u1", "days": None, "max_results": None})

        self.assertIsNone(omitted.error)
        self.assertIsNone(nulled.error)
        self.assertIn("**Workouts (Last 7 Days)**", omitted.result)
        self.assertIn("**Workouts (Last 7 Days)**", nulled.result)

    def test_numeric_strings_are_coerced(self):
        self._patch_get(FakeResponse(200, _workout_payload()))

        response = self._post({"uid": "u1", "days": "3", "max_results": "25"})

        self.assertIsNone(response.error)
        self.assertIn("**Workouts (Last 3 Days)**", response.result)
        self.assertEqual(self.calls[0]["params"]["limit"], 25)

    def test_non_positive_values_are_clamped_to_one(self):
        for value in (0, -2, "-5"):
            with self.subTest(value=value):
                self.calls = []
                patcher = self._patch_get(FakeResponse(200, _workout_payload()))
                try:
                    response = self._post({"uid": "u1", "days": value, "max_results": value})
                finally:
                    patcher.stop()

                self.assertIsNone(response.error)
                self.assertIn("**Workouts (Last 1 Days)**", response.result)
                params = self.calls[0]["params"]
                self.assertEqual(params["limit"], 1)
                # start == end is an empty window; the clamped window is one day.
                self.assertNotEqual(params["start"][:10], params["end"][:10])

    def test_oversized_values_are_capped(self):
        self._patch_get(FakeResponse(200, _workout_payload()))

        response = self._post({"uid": "u1", "days": 999, "max_results": 999})

        self.assertIsNone(response.error)
        self.assertIn("**Workouts (Last 30 Days)**", response.result)
        self.assertEqual(self.calls[0]["params"]["limit"], 50)

    def test_unparseable_values_fall_back_to_defaults(self):
        for value in ("soon", "", "1.5", True, [], {}):
            with self.subTest(value=value):
                self.calls = []
                patcher = self._patch_get(FakeResponse(200, _workout_payload()))
                try:
                    response = self._post({"uid": "u1", "days": value, "max_results": value})
                finally:
                    patcher.stop()

                self.assertIsNone(response.error, f"{value!r} -> {response.error}")
                self.assertIn("**Workouts (Last 7 Days)**", response.result)
                self.assertEqual(self.calls[0]["params"]["limit"], 10)

    def test_numeric_floats_are_truncated(self):
        self._patch_get(FakeResponse(200, _workout_payload()))

        response = self._post({"uid": "u1", "days": 2.5, "max_results": 2.5})

        self.assertIsNone(response.error)
        self.assertIn("**Workouts (Last 2 Days)**", response.result)
        self.assertEqual(self.calls[0]["params"]["limit"], 2)


class CoerceIntUnitTests(unittest.TestCase):
    """The boundary helper itself, exercised without HTTP."""

    def test_documented_range_is_enforced(self):
        self.assertEqual(main._coerce_int(None, 7, 1, 30), 7)
        self.assertEqual(main._coerce_int(0, 7, 1, 30), 1)
        self.assertEqual(main._coerce_int(-99, 7, 1, 30), 1)
        self.assertEqual(main._coerce_int(31, 7, 1, 30), 30)
        self.assertEqual(main._coerce_int("12", 7, 1, 30), 12)
        self.assertEqual(main._coerce_int(12, 7, 1, 30), 12)
        self.assertEqual(main._coerce_int(2.5, 7, 1, 30), 2)

    def test_unusable_values_use_the_default(self):
        for value in (None, True, False, "abc", "", [], {}, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertEqual(main._coerce_int(value, 10, 1, 50), 10)

    def test_overflowing_floats_fall_back_instead_of_raising(self):
        """A JSON number that overflows int() must not turn into a 500.

        `json.loads("1e309")` produces `inf`, and `int(inf)` raises
        `OverflowError`; the same value can arrive as the string "1e309".
        """
        for value in ("1e309", "1E999", "-1e309", float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertEqual(main._coerce_int(value, 10, 1, 50), 10)

    def test_digit_strings_longer_than_any_float_are_clamped(self):
        """Python ints are unbounded, so a huge digit string is clamped, not dropped."""
        self.assertEqual(main._coerce_int("9" * 4000, 10, 1, 50), 50)


if __name__ == "__main__":
    unittest.main()

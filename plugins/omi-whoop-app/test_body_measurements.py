"""Regression tests for the Whoop body-measurement tool (#13927).

`get_body_measurements` requested `/v1/body_measurement`, which Whoop has never
served, and `whoop_api_request` reported the empty 404 body as the error text --
so every call failed with a blank reason. These tests drive the production
handler through the `requests.get` seam, so no network is involved.
"""
import asyncio
import json
import unittest
from unittest.mock import patch

from whoop_test_support import DummyRequest, load_main

main = load_main()

# The documented Whoop route; the plugin used to request `/v1/body_measurement`.
MEASUREMENT_PATH = "/user/measurement/body"
WHOOP_V1 = "https://api.prod.whoop.com/developer/v1"


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


class BodyMeasurementEndpointTests(unittest.TestCase):
    def setUp(self):
        token_patcher = patch.object(main, "get_valid_access_token", return_value="test-token")
        self.addCleanup(token_patcher.stop)
        token_patcher.start()
        self.calls = []

    def _patch_get(self, routes):
        """routes: url suffix -> FakeResponse, with a 404 default."""

        def fake_get(url, headers=None, params=None, timeout=None):
            self.calls.append({"url": url, "headers": headers})
            for suffix, response in routes.items():
                if url.endswith(suffix):
                    return response
            return FakeResponse(404, None, text="")

        patcher = patch.object(main.requests, "get", side_effect=fake_get)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_requests_the_documented_measurement_route(self):
        """Regression: the tool asked for a route Whoop does not serve (404)."""
        self._patch_get(
            {MEASUREMENT_PATH: FakeResponse(200, {"height_meter": 1.83, "weight_kilogram": 80.0, "max_heart_rate": 191})}
        )

        response = asyncio.run(main.tool_get_body_measurements(DummyRequest({"uid": "u1"})))

        self.assertIsNone(response.error, response.error)
        self.assertIn("**Height:** 183 cm", response.result)
        self.assertIn("**Weight:** 80.0 kg", response.result)
        self.assertIn("**Max Heart Rate:** 191 bpm", response.result)

        requested = [call["url"] for call in self.calls]
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0], f"{WHOOP_V1}{MEASUREMENT_PATH}")
        self.assertEqual(self.calls[0]["headers"]["Authorization"], "Bearer test-token")

    def test_404_is_the_empty_state_not_a_failure(self):
        """A user with no measurements yet gets the friendly empty result.

        WHOOP documents 404 on this user-scoped route as "Requested resource not
        found". Treating it as a failure left the `No body measurements
        available.` branch below reachable only after a 200, i.e. never for the
        users it exists for.
        """
        self._patch_get({})

        response = asyncio.run(main.tool_get_body_measurements(DummyRequest({"uid": "u1"})))

        self.assertIsNone(response.error, response.error)
        self.assertEqual(response.result, "No body measurements available.")

    def test_200_with_no_fields_is_also_the_empty_state(self):
        self._patch_get({MEASUREMENT_PATH: FakeResponse(200, {})})

        response = asyncio.run(main.tool_get_body_measurements(DummyRequest({"uid": "u1"})))

        self.assertIsNone(response.error, response.error)
        self.assertEqual(response.result, "No body measurements available.")

    def test_non_404_failure_still_surfaces_a_status_bearing_reason(self):
        """A real failure must never be reported with a blank reason."""
        self._patch_get({MEASUREMENT_PATH: FakeResponse(500, None, text="")})

        response = asyncio.run(main.tool_get_body_measurements(DummyRequest({"uid": "u1"})))

        error = response.error or ""
        self.assertTrue(error.strip(), "error reason must never be blank")
        self.assertIn("500", error)
        self.assertNotEqual(error.strip(), "Failed to get measurements:")

    def test_upstream_message_is_preserved_when_present(self):
        self._patch_get({MEASUREMENT_PATH: FakeResponse(401, None, text='{"error":"invalid_token"}')})

        response = asyncio.run(main.tool_get_body_measurements(DummyRequest({"uid": "u1"})))

        error = response.error or ""
        self.assertIn("invalid_token", error)


class HttpErrorMessageTests(unittest.TestCase):
    """The shared boundary all seven Whoop tools go through."""

    def test_blank_body_falls_back_to_the_status_code(self):
        self.assertEqual(main._http_error_message(FakeResponse(404, None, text="")), "HTTP 404")
        self.assertEqual(main._http_error_message(FakeResponse(500, None, text="   ")), "HTTP 500")

    def test_body_wins_when_it_carries_information(self):
        self.assertEqual(main._http_error_message(FakeResponse(400, None, text="bad range")), "bad range")

    def test_body_without_json_content_type_is_still_reported(self):
        response = FakeResponse(503, None, text="upstream unavailable")
        self.assertEqual(main._http_error_message(response), "upstream unavailable")


if __name__ == "__main__":
    unittest.main()

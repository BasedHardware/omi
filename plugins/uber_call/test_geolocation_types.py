"""Wrongly typed geolocation values must be rejected as 400, not 500 or a wrong ride link.

The Omi backend forwards ``geolocation`` to this app as free-form JSON
(``dict[str, Any]``), so pydantic does not coerce the values inside it. A
coordinate that arrives as a list or an object reached ``float()``, which
raises TypeError rather than the ValueError ``call_uber`` handles, so the
request failed with an unhandled 500 instead of the documented 400. The same
holds for a non-string address, and a boolean coordinate was silently read as
1.0 / 0.0 and produced a ride link for the wrong pickup point.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uber_links import build_location

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


SECRET_PATH = "/srv/secrets/uber_api_credentials.json"

NON_SCALAR_COORDINATES = [
    [37.7749, -122.4194],
    {"lat": 37.7749},
    (37.7749,),
]


class NonScalarCoordinateTests(unittest.TestCase):
    """build_location raises ValueError -- the contract call_uber maps to 400."""

    def test_non_scalar_latitude_raises_value_error(self):
        for value in NON_SCALAR_COORDINATES:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as ctx:
                    build_location(latitude=value, longitude=-122.4194)
                self.assertIn(type(value).__name__, str(ctx.exception))

    def test_non_scalar_longitude_raises_value_error(self):
        for value in NON_SCALAR_COORDINATES:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_location(latitude=37.7749, longitude=value)

    def test_numeric_strings_and_numbers_still_accepted(self):
        loc = build_location(latitude="37.7749", longitude=-122.4194)
        self.assertAlmostEqual(loc.latitude, 37.7749)
        self.assertAlmostEqual(loc.longitude, -122.4194)

    def test_empty_and_missing_coordinates_still_ignored(self):
        loc = build_location(latitude="", longitude=None, nickname="Home")
        self.assertIsNone(loc.latitude)
        self.assertIsNone(loc.longitude)

    def test_unparseable_string_still_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_location(latitude="nearby", longitude="-122.418028")


class UntypedGeolocationValueTests(unittest.TestCase):
    """build_location raises ValueError, the contract call_uber maps to 400, for mistyped values."""

    def test_boolean_coordinate_raises_value_error(self):
        for value in (True, False):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "bool"):
                    build_location(latitude=value, longitude=-122.4194)
                with self.assertRaisesRegex(ValueError, "bool"):
                    build_location(latitude=37.7749, longitude=value)

    def test_integer_beyond_float_range_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_location(latitude=10**400, longitude=-122.4194)

    def test_unparseable_string_error_does_not_carry_python_internal_text(self):
        with self.assertRaises(ValueError) as ctx:
            build_location(latitude="nearby", longitude=-122.4194)
        self.assertNotIn("could not convert", str(ctx.exception))

    def test_non_string_address_raises_value_error(self):
        for value in (12345, ["a", "b"], {"line": "a"}, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_location(formatted_address=value)

    def test_string_address_is_still_whitespace_normalised(self):
        loc = build_location(formatted_address="  1455   Market St ")
        self.assertEqual(loc.formatted_address, "1455 Market St")


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class NonScalarCoordinateEndpointTests(unittest.TestCase):
    """The same input over HTTP must be a 400, never an unhandled 500."""

    def setUp(self):
        from main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_non_scalar_geolocation_returns_400(self):
        for value in NON_SCALAR_COORDINATES:
            with self.subTest(value=value):
                response = self.client.post(
                    "/api/call_uber",
                    json={
                        "destination": "SFO Airport",
                        "geolocation": {"latitude": value, "longitude": -122.418028},
                    },
                )
                self.assertEqual(response.status_code, 400)

    def test_valid_geolocation_still_builds_links(self):
        response = self.client.post(
            "/api/call_uber",
            json={
                "destination": "SFO Airport",
                "geolocation": {"latitude": 37.7749, "longitude": -122.4194},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("m.uber.com", response.json()["web_link"])


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class UntypedGeolocationEndpointTests(unittest.TestCase):
    """call_uber answers mistyped input with 400/422 and unexpected failures with a generic 500."""

    def setUp(self):
        import main

        self.main = main
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def test_boolean_geolocation_coordinates_return_400(self):
        response = self.client.post(
            "/api/call_uber",
            json={"destination": "SFO Airport", "geolocation": {"latitude": True, "longitude": False}},
        )

        self.assertEqual(response.status_code, 400)

    def test_boolean_request_coordinates_are_rejected(self):
        for field in ("pickup_latitude", "pickup_longitude", "dropoff_latitude", "dropoff_longitude"):
            with self.subTest(field=field):
                response = self.client.post("/api/call_uber", json={"destination": "SFO Airport", field: True})

                self.assertEqual(response.status_code, 422)

    def test_non_string_geolocation_address_returns_400(self):
        for key, value in (("address", 12345), ("formatted_address", ["a", "b"])):
            with self.subTest(key=key):
                response = self.client.post(
                    "/api/call_uber",
                    json={"destination": "SFO Airport", "geolocation": {key: value}},
                )

                self.assertEqual(response.status_code, 400)

    def test_non_dict_geolocation_is_ignored(self):
        # The request model only admits a dict, so build the payload without validation.
        payload = self.main.CallUberRequest.model_construct(destination="SFO Airport", geolocation="San Francisco")

        links = self.main.call_uber(payload)

        self.assertIn("pickup=my_location", links["web_link"])

    def test_unexpected_failure_returns_generic_500(self):
        with patch.object(self.main, "build_uber_deep_links", side_effect=RuntimeError(SECRET_PATH)):
            response = self.client.post("/api/call_uber", json={"destination": "SFO Airport"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Failed to prepare Uber ride link."})

    def test_unexpected_failure_logs_only_the_exception_class_name(self):
        with patch.object(self.main, "build_uber_deep_links", side_effect=RuntimeError(SECRET_PATH)):
            with self.assertLogs(self.main.__name__, level="ERROR") as logs:
                self.client.post("/api/call_uber", json={"destination": "SFO Airport"})

        output = "".join(logs.output)
        self.assertIn("RuntimeError", output)
        self.assertNotIn(SECRET_PATH, output)


if __name__ == "__main__":
    unittest.main()

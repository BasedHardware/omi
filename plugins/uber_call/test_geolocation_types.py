"""Non-scalar geolocation coordinates must be rejected as 400, not 500.

The Omi backend forwards ``geolocation`` to this app as free-form JSON
(``dict[str, Any]``), so pydantic does not coerce the values inside it. A
coordinate that arrives as a list or an object reached ``float()``, which
raises TypeError rather than the ValueError ``call_uber`` handles, so the
request failed with an unhandled 500 instead of the documented 400.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uber_links import build_location

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


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


if __name__ == "__main__":
    unittest.main()

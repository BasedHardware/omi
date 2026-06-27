import sys
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TestClient is not None:
    from main import app


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class CallUberEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_manifest_parameters_are_json_schema_object(self):
        response = self.client.get("/.well-known/omi-tools.json")

        self.assertEqual(response.status_code, 200)
        parameters = response.json()["tools"][0]["parameters"]
        self.assertEqual(parameters["type"], "object")
        self.assertIn("destination", parameters["required"])

    def test_bad_geolocation_returns_400(self):
        response = self.client.post(
            "/api/call_uber",
            json={
                "destination": "SFO Airport",
                "geolocation": {"latitude": "nearby", "longitude": "-122.418028"},
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("could not convert string to float", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()

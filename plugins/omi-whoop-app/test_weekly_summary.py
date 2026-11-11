import sys
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TestClient is not None:
    from main import app


def _page(records, next_token=None):
    body = {"records": records}
    if next_token:
        body["next_token"] = next_token
    return body


def _record(value_path, value):
    """Build a minimal Whoop record with a nested score value at value_path."""
    record = {"score": {}}
    node = record["score"]
    for key in value_path[:-1]:
        node = node.setdefault(key, {})
    node[value_path[-1]] = value
    return record


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class WeeklySummaryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        patcher = patch("main.get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    def _mock_responses(self, by_endpoint):
        """by_endpoint: endpoint -> list of pages (each a dict body) to return in order."""
        calls = {endpoint: iter(pages) for endpoint, pages in by_endpoint.items()}

        def fake_request(uid, method, endpoint, params=None):
            return next(calls[endpoint])

        return fake_request

    def test_follows_continuation_pages_for_all_four_collections(self):
        pages = {
            "/recovery": [
                _page([_record(["recovery_score"], 50)], next_token="r2"),
                _page([_record(["recovery_score"], 70)]),
            ],
            "/cycle": [_page([_record(["strain"], 10.0)])],
            "/activity/sleep": [_page([])],
            "/activity/workout": [
                _page([{} for _ in range(7)], next_token="w2"),
                _page([{} for _ in range(3)]),
            ],
        }
        with patch("main.whoop_api_request", side_effect=self._mock_responses(pages)):
            response = self.client.post("/tools/get_weekly_summary", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        # Regression: before the fix, only the first page was fetched, so this
        # read "Workouts: 7" and averaged recovery over one record instead of two.
        self.assertIn("**Workouts:** 10", result)
        self.assertIn("Avg 60%", result)

    def test_no_continuation_token_stops_after_one_page(self):
        pages = {
            "/recovery": [_page([_record(["recovery_score"], 80)])],
            "/cycle": [_page([])],
            "/activity/sleep": [_page([])],
            "/activity/workout": [_page([{}])],
        }
        with patch("main.whoop_api_request", side_effect=self._mock_responses(pages)):
            response = self.client.post("/tools/get_weekly_summary", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertIn("**Workouts:** 1", result)

    def test_page_failure_reports_unavailable_instead_of_partial_total(self):
        pages = {
            "/recovery": [_page([])],
            "/cycle": [_page([])],
            "/activity/sleep": [_page([])],
            "/activity/workout": [
                _page([{} for _ in range(7)], next_token="w2"),
                {"error": "upstream failure", "status_code": 500},
            ],
        }
        with patch("main.whoop_api_request", side_effect=self._mock_responses(pages)):
            response = self.client.post("/tools/get_weekly_summary", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        # Regression: before the fix, a failed later page was never reachable
        # (only page one was ever fetched) so a partial count could read as final.
        self.assertIn("**Workouts:** Temporarily unavailable", result)
        self.assertNotIn("**Workouts:** 7", result)


if __name__ == "__main__":
    unittest.main()

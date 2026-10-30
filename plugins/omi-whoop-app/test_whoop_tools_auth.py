"""Real HTTP regression coverage for all Whoop tool authentication boundaries."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

import main
from whoop_tools_auth import require_whoop_tools_auth

SECRET = "test-whoop-tools-secret"
PATHS = {
    "/tools/get_recovery",
    "/tools/get_strain",
    "/tools/get_sleep",
    "/tools/get_workouts",
    "/tools/get_weekly_summary",
    "/tools/get_body_measurements",
    "/tools/get_profile",
}


class WhoopToolsAuthTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"WHOOP_TOOLS_SECRET": SECRET})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(main.app)

    def test_every_tool_route_has_guard(self):
        routes = {route.path: route for route in main.app.routes if route.path.startswith("/tools/")}
        self.assertEqual(set(routes), PATHS)
        for route in routes.values():
            self.assertIn(require_whoop_tools_auth, [dep.dependency for dep in route.dependencies])

    def test_rejected_requests_cannot_access_user_data(self):
        cases = [
            (SECRET, {}, {}, 401),
            (SECRET, {"Authorization": "Bearer wrong"}, {}, 401),
            (SECRET, {}, {"whoop_tools_token": "wrong"}, 401),
            (SECRET, {"Authorization": f"Basic {SECRET}"}, {}, 401),
            (SECRET, {"Authorization": "Bearer wrong"}, {"whoop_tools_token": SECRET}, 401),
            (SECRET, {}, {"whoop_tools_token": "☃"}, 401),
            (SECRET, {}, {"whoop_tools_token": "   "}, 401),
            (None, {"Authorization": f"Bearer {SECRET}"}, {}, 503),
            ("   ", {}, {"whoop_tools_token": SECRET}, 503),
        ]
        for secret, headers, params, expected in cases:
            env = {} if secret is None else {"WHOOP_TOOLS_SECRET": secret}
            with patch.dict("os.environ", env, clear=True):
                for path in PATHS:
                    with self.subTest(path=path, status=expected, headers=headers, params=params):
                        with (
                            patch("main.get_valid_access_token") as lookup,
                            patch("main.whoop_api_request") as api,
                        ):
                            response = self.client.post(
                                path, json={"uid": "victim"}, headers=headers, params=params
                            )
                            self.assertEqual(response.status_code, expected)
                            lookup.assert_not_called()
                            api.assert_not_called()

    def test_valid_header_and_query_reach_each_handler(self):
        for path in PATHS:
            for headers, params in [
                ({"Authorization": f"Bearer {SECRET}"}, {}),
                ({}, {"whoop_tools_token": SECRET}),
                ({"Authorization": f"bEaReR {SECRET}"}, {}),
            ]:
                with self.subTest(path=path, headers=headers, params=params):
                    with (
                        patch("main.get_valid_access_token", return_value=None) as lookup,
                        patch("main.whoop_api_request") as api,
                    ):
                        response = self.client.post(
                            path, json={"uid": "test-user"}, headers=headers, params=params
                        )
                        self.assertEqual(response.status_code, 200)
                        lookup.assert_called_once_with("test-user")
                        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()

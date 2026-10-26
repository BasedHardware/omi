import importlib
import json
import os
import re
import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

try:
    from . import iq_auth, main
except (ImportError, ValueError):
    import iq_auth
    import main


class FakeRequest:
    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        authorization: Optional[str] = None,
    ):
        self.headers = headers or {}
        if authorization is not None:
            self.headers["Authorization"] = authorization
        self.query_params = query_params or {}


class AuthHelperTest(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.get("IQ_RATING_SECRET")
        os.environ["IQ_RATING_SECRET"] = "test-secret"

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["IQ_RATING_SECRET"] = self.orig_env
        else:
            os.environ.pop("IQ_RATING_SECRET", None)

    def test_unconfigured_secret_503(self):
        os.environ.pop("IQ_RATING_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth(FakeRequest(), uid="u1")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth(FakeRequest(query_params={"uid": "u1"}), uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        req = FakeRequest(
            authorization="Bearer wrong-token", query_params={"uid": "u1"}
        )
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_ignored(self):
        req = FakeRequest(authorization="Basic test-secret", query_params={"uid": "u1"})
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = FakeRequest(authorization="Bearer test-secret")
        self.assertEqual(iq_auth.require_iq_auth(req, uid="u1"), "u1")

    def test_lowercase_bearer_accepted(self):
        req = FakeRequest(authorization="bearer test-secret")
        self.assertEqual(iq_auth.require_iq_auth(req, uid="u1"), "u1")

    def test_query_token_accepted(self):
        req = FakeRequest(query_params={"uid": "u1", "iq_rating_token": "test-secret"})
        self.assertEqual(iq_auth.require_iq_auth(req, uid="u1"), "u1")

    def test_uid_whitespace_trimmed(self):
        req = FakeRequest(authorization="Bearer test-secret")
        self.assertEqual(iq_auth.require_iq_auth(req, uid="  u1  "), "u1")

    def test_empty_uid_raises_422(self):
        req = FakeRequest(authorization="Bearer test-secret")
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth(req, uid="   ")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_if_uid_none_passes_unauthenticated(self):
        self.assertIsNone(iq_auth.require_iq_auth_if_uid(FakeRequest(), uid=None))
        self.assertIsNone(iq_auth.require_iq_auth_if_uid(FakeRequest(), uid="   "))

    def test_if_uid_present_requires_auth(self):
        with self.assertRaises(HTTPException) as ctx:
            iq_auth.require_iq_auth_if_uid(FakeRequest(), uid="victim")
        self.assertEqual(ctx.exception.status_code, 401)

        req = FakeRequest(query_params={"iq_rating_token": "test-secret"})
        self.assertEqual(iq_auth.require_iq_auth_if_uid(req, uid="victim"), "victim")


class RouteWiringTest(unittest.TestCase):
    """Static check: every uid-keyed iq-rating data route declares the auth dep."""

    def test_routes_use_auth_dependency(self):
        src_path = os.path.join(os.path.dirname(__file__), "main.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()

        for route in (
            "/iq/api",
            "/iq/hide",
            "/iq/unhide",
            "/iq/adjust",
            "/iq/preload",
            "/iq/refresh",
        ):
            idx = src.find(f'"{route}"')
            self.assertGreater(idx, -1, f"Route {route} not found")
            body = src[idx : idx + 400]
            self.assertIn(
                "Depends(require_iq_auth)",
                body,
                f"Route {route} missing auth dependency",
            )

        # /iq page uses the optional-uid variant
        idx = src.find('"/iq", response_class=HTMLResponse')
        self.assertGreater(idx, -1, "/iq page route not found")
        self.assertIn("Depends(require_iq_auth_if_uid)", src[idx : idx + 400])

        # Raw inline JS uid literal must not exist
        self.assertNotIn("'{uid}'", src)

        # JSON data islands must be wired in template and handler
        self.assertIn("uid_data_island", src)
        self.assertIn("token_param_data_island", src)
        self.assertIn("people_data_island", src)
        self.assertIn(
            "JSON.parse(document.getElementById('iq-data-uid').textContent)",
            src,
        )
        self.assertIn(
            "JSON.parse(document.getElementById('iq-data-token-param').textContent)",
            src,
        )
        self.assertIn(
            "JSON.parse(document.getElementById('iq-data-people').textContent)",
            src,
        )

        # Share url must strip iq_rating_token
        self.assertIn("searchParams.delete('iq_rating_token')", src)


class RenderPathTest(unittest.TestCase):
    """Test full render path for /iq page to ensure JSON islands emit and parse correctly."""

    @patch("main.get_people_for_user")
    def test_iq_rating_page_renders_valid_json_islands(self, mock_get_people):
        mock_people = [
            {"id": "p1", "name": "Alice <Engineer>", "iq": 125, "memory_count": 5},
            {"id": "p2", "name": 'Bob "Quote"', "iq": 95, "memory_count": 3},
        ]
        mock_get_people.return_value = mock_people

        req = FakeRequest(query_params={"iq_rating_token": "my-secret-token"})

        # Run iq_rating_page coroutine
        import asyncio

        response = asyncio.run(main.iq_rating_page(req, uid="user_123"))
        self.assertIsInstance(response, HTMLResponse)
        html = response.body.decode("utf-8")

        # 1. Assert islands exist in emitted HTML
        uid_match = re.search(
            r'<script type="application/json" id="iq-data-uid">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(uid_match, "iq-data-uid island not found in HTML")
        uid_val = json.loads(uid_match.group(1))
        self.assertEqual(uid_val, "user_123")

        token_match = re.search(
            r'<script type="application/json" id="iq-data-token-param">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(token_match, "iq-data-token-param island not found")
        token_val = json.loads(token_match.group(1))
        self.assertEqual(token_val, "iq_rating_token=my-secret-token&")

        people_match = re.search(
            r'<script type="application/json" id="iq-data-people">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(people_match, "iq-data-people island not found")

        # 2. Assert no entity corruption (&quot;) and JSON parses directly to a list
        raw_people_content = people_match.group(1)
        self.assertNotIn("&quot;", raw_people_content)

        parsed_people = json.loads(raw_people_content)
        self.assertIsInstance(
            parsed_people, list, "People data must parse to a list, not a string"
        )
        self.assertEqual(len(parsed_people), 2)
        self.assertEqual(parsed_people[0]["name"], "Alice <Engineer>")
        self.assertEqual(parsed_people[1]["name"], 'Bob "Quote"')

        # 3. Assert shareResults removes token
        self.assertIn("searchParams.delete('iq_rating_token')", html)


if __name__ == "__main__":
    unittest.main()

"""Hermetic unit tests for IQ Rating shared-secret auth and route wiring.

No third-party runtime dependencies required.
"""

import html
import importlib.util
import json
import os
import re
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR.parent))
SECRET = "test-secret"


class HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


def _load_auth_module():
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Request = object
    fastapi_stub.Query = lambda *args, **kwargs: None

    class _Status:
        HTTP_401_UNAUTHORIZED = 401
        HTTP_422_UNPROCESSABLE_ENTITY = 422
        HTTP_503_SERVICE_UNAVAILABLE = 503

    fastapi_stub.status = _Status

    spec = importlib.util.spec_from_file_location(
        "iq_auth", APP_DIR / "iq_auth.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastapi": fastapi_stub}):
        spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class FakeRequest:
    def __init__(self, authorization=None, query_params=None):
        self.headers = {}
        if authorization:
            self.headers["Authorization"] = authorization
        self.query_params = query_params or {}


class TestRequireIqAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("IQ_RATING_SECRET")
        os.environ["IQ_RATING_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("IQ_RATING_SECRET", None)
        else:
            os.environ["IQ_RATING_SECRET"] = self._old

    def test_unconfigured_secret_503(self):
        os.environ.pop("IQ_RATING_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth(FakeRequest(), uid="u1")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth(FakeRequest(query_params={"uid": "u1"}), uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        req = FakeRequest(authorization="Bearer nope", query_params={"uid": "u1"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_401(self):
        req = FakeRequest(authorization="Basic test-secret", query_params={"uid": "u1"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = FakeRequest(authorization="Bearer test-secret", query_params={"uid": "u1"})
        self.assertEqual(auth.require_iq_auth(req, uid="u1"), "u1")

    def test_bearer_token_case_insensitive(self):
        req = FakeRequest(authorization="bearer test-secret", query_params={"uid": "u1"})
        self.assertEqual(auth.require_iq_auth(req, uid="u1"), "u1")

    def test_query_token_accepted(self):
        req = FakeRequest(query_params={"uid": "u1", "iq_rating_token": "test-secret"})
        self.assertEqual(auth.require_iq_auth(req, uid="u1"), "u1")

    def test_uid_trimmed(self):
        req = FakeRequest(authorization="Bearer test-secret")
        self.assertEqual(auth.require_iq_auth(req, uid="  u1  "), "u1")

    def test_empty_uid_422(self):
        req = FakeRequest(authorization="Bearer test-secret")
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth(req, uid="   ")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_if_uid_none_passes_unauthenticated(self):
        self.assertIsNone(auth.require_iq_auth_if_uid(FakeRequest(), uid=None))
        self.assertIsNone(auth.require_iq_auth_if_uid(FakeRequest(), uid="   "))

    def test_if_uid_present_requires_auth(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_iq_auth_if_uid(FakeRequest(), uid="victim")
        self.assertEqual(ctx.exception.status_code, 401)
        req = FakeRequest(query_params={"iq_rating_token": "test-secret"})
        self.assertEqual(auth.require_iq_auth_if_uid(req, uid="victim"), "victim")


class TestRenderPath(unittest.TestCase):
    """Behavioral render-path test ensuring data islands are emitted and parse properly."""

    def test_rendered_islands_exist_and_parse_without_entity_corruption(self):
        import iq_rating.main as main_mod

        people = [
            {"id": "p1", "name": "Alice", "iq": 125},
            {"id": "p2", "name": "Bob</script><script>alert(1)</script>", "iq": 85},
        ]
        uid = "user-123"
        token_param = "iq_rating_token=secret&"

        rendered = main_mod.PEOPLE_LIST_CONTENT.format(
            uid_data_island=main_mod._json_data_island("iq-data-uid", uid),
            token_data_island=main_mod._json_data_island("iq-data-token-param", token_param),
            people_data_island=main_mod._json_data_island("iq-data-people", people),
            total_people=len(people),
        )

        # 1. Assert islands exist in the rendered HTML
        self.assertIn('<script type="application/json" id="iq-data-uid">', rendered)
        self.assertIn('<script type="application/json" id="iq-data-token-param">', rendered)
        self.assertIn('<script type="application/json" id="iq-data-people">', rendered)

        # 2. Extract and parse textContent
        uid_match = re.search(r'<script type="application/json" id="iq-data-uid">(.*?)</script>', rendered, re.DOTALL)
        self.assertIsNotNone(uid_match)
        parsed_uid = json.loads(uid_match.group(1))
        self.assertEqual(parsed_uid, uid)

        token_match = re.search(r'<script type="application/json" id="iq-data-token-param">(.*?)</script>', rendered, re.DOTALL)
        self.assertIsNotNone(token_match)
        parsed_token = json.loads(token_match.group(1))
        self.assertEqual(parsed_token, token_param)

        people_match = re.search(r'<script type="application/json" id="iq-data-people">(.*?)</script>', rendered, re.DOTALL)
        self.assertIsNotNone(people_match)
        parsed_people = json.loads(people_match.group(1))
        self.assertIsInstance(parsed_people, list)
        self.assertEqual(len(parsed_people), 2)
        self.assertEqual(parsed_people[0]["name"], "Alice")
        self.assertEqual(parsed_people[1]["iq"], 85)

        # 3. Assert raw text element does not contain HTML quote entities
        self.assertNotIn("&quot;", people_match.group(1))
        # 4. Assert unescaped closing script tag is prevented
        self.assertNotIn("</script>", people_match.group(1))


class RouteWiringTest(unittest.TestCase):
    """Static check: every uid-keyed iq-rating data route declares the auth dep."""

    def test_routes_use_auth_dependency(self):
        src = (APP_DIR / "main.py").read_text(encoding="utf-8")
        for route in ("/iq/api", "/iq/hide", "/iq/unhide", "/iq/adjust", "/iq/preload", "/iq/refresh"):
            idx = src.find(f'"{route}"')
            self.assertGreater(idx, -1, route)
            body = src[idx : idx + 400]
            self.assertIn("Depends(require_iq_auth)", body, route)

        # /iq page uses the optional-uid variant
        idx = src.find('"/iq", response_class=HTMLResponse')
        self.assertIn("Depends(require_iq_auth_if_uid)", src[idx : idx + 400])

        # JS no longer embeds a raw uid literal
        self.assertNotIn("const uid = '{uid}'", src)

        # ShareResults strips token
        self.assertIn("parsed.searchParams.delete('iq_rating_token')", src)


if __name__ == "__main__":
    unittest.main()

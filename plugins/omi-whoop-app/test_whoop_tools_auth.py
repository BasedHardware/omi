"""Tests for the Whoop chat-tools authentication guard (#14453).

Validates the guard contract:
- fails closed (503) when WHOOP_TOOLS_SECRET is unset
- rejects missing credentials (401)
- rejects invalid credentials (401)
- rejects empty Bearer token (401)
- accepts valid credentials via Authorization: Bearer header
- accepts lowercase bearer scheme
- accepts valid credentials via whoop_tools_token query parameter
- handles non-ASCII secrets safely
- pins that all seven /tools/* routes in main.py have require_whoop_tools_auth wired
"""

import ast
import os
import sys
import unittest
from pathlib import Path

import fastapi

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from whoop_tools_auth import require_whoop_tools_auth

SECRET = "test-whoop-secret-key-12345"


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireWhoopToolsAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("WHOOP_TOOLS_SECRET")
        os.environ["WHOOP_TOOLS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("WHOOP_TOOLS_SECRET", None)
        else:
            os.environ["WHOOP_TOOLS_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("WHOOP_TOOLS_SECRET", None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_whoop_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_whoop_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong-secret"})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_whoop_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_bearer_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer "})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_whoop_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertIsNone(require_whoop_tools_auth(req))

    def test_lowercase_bearer_scheme_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"bearer {SECRET}"})
        self.assertIsNone(require_whoop_tools_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"whoop_tools_token": SECRET})
        self.assertIsNone(require_whoop_tools_auth(req))

    def test_non_ascii_secret_does_not_raise(self):
        os.environ["WHOOP_TOOLS_SECRET"] = "whoop-secret-✓-テスト"
        req = _FakeRequest(headers={"Authorization": "Bearer whoop-secret-✓-テスト"})
        self.assertIsNone(require_whoop_tools_auth(req))


class TestToolsRoutesAreWired(unittest.TestCase):
    def test_all_seven_tools_routes_require_auth(self):
        tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
        expected_routes = {
            "tool_get_recovery",
            "tool_get_strain",
            "tool_get_sleep",
            "tool_get_workouts",
            "tool_get_weekly_summary",
            "tool_get_body_measurements",
            "tool_get_profile",
        }
        wired = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in expected_routes:
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                for kw in deco.keywords:
                    if kw.arg != "dependencies" or not isinstance(kw.value, ast.List):
                        continue
                    for elt in kw.value.elts:
                        if (
                            isinstance(elt, ast.Call)
                            and getattr(elt.func, "id", None) == "Depends"
                            and elt.args
                            and getattr(elt.args[0], "id", None) == "require_whoop_tools_auth"
                        ):
                            wired.add(node.name)
        self.assertEqual(wired, expected_routes)


if __name__ == "__main__":
    unittest.main()

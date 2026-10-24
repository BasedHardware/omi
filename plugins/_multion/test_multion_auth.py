"""Tests for the MultiOn mutating-endpoint auth guard.

Covers the guard contract: fail closed (503) when the secret is missing,
reject missing/wrong credentials (401), accept the shared secret through
either ``Authorization: Bearer`` or ``multion_token``, and pin that both
mutating routes are wired to the guard.
"""

import ast
import os
import sys
import unittest
from pathlib import Path

import fastapi

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR.parent))  # plugins/ on path so _multion resolves

from _multion.multion_auth import require_multion_auth  # noqa: E402

SECRET = "test-multion-secret"


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireMultionAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("MULTION_WEBHOOK_SECRET")
        os.environ["MULTION_WEBHOOK_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("MULTION_WEBHOOK_SECRET", None)
        else:
            os.environ["MULTION_WEBHOOK_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("MULTION_WEBHOOK_SECRET", None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_bearer_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer "})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertIsNone(require_multion_auth(req))

    def test_lowercase_bearer_scheme_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"bearer {SECRET}"})
        self.assertIsNone(require_multion_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"multion_token": SECRET})
        self.assertIsNone(require_multion_auth(req))

    def test_non_ascii_secret_does_not_raise(self):
        os.environ["MULTION_WEBHOOK_SECRET"] = "秘密-✓"
        req = _FakeRequest(headers={"Authorization": "Bearer 秘密-✓"})
        self.assertIsNone(require_multion_auth(req))


class TestMutatingRoutesAreWired(unittest.TestCase):
    def test_both_mutating_routes_require_auth(self):
        tree = ast.parse((APP_DIR / "router.py").read_text(encoding="utf-8"))
        wired = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in ("submit_uid", "multion_endpoint"):
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
                            and getattr(elt.args[0], "id", None) == "require_multion_auth"
                        ):
                            wired[node.name] = True
        self.assertEqual(sorted(wired), ["multion_endpoint", "submit_uid"])


if __name__ == "__main__":
    unittest.main()

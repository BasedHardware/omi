"""Hermetic regression tests for the hume-ai tools auth guard.

Before this fix, /save-emotion-memory, /force-send-notification and /audio
trusted a client-supplied uid and wrote an emotion memory into that user's
Omi account (app integration key), pushed a notification to that user, or
attributed the posted audio to that uid's emotion stats — with no caller
authentication. Covers `require_hume_tools_auth`: 503 when unconfigured,
401 on missing/wrong token, bearer + query token accepted.

fastapi is stubbed so the suite runs without third-party packages.

Run: python3 plugins/hume-ai/test_tools_auth.py
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
SECRET = "test-hume-tools-secret"


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load_auth_module():
    fastapi_stub = ModuleType("fastapi")
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Request = object
    spec = importlib.util.spec_from_file_location(
        "hume_tools_auth", APP_DIR / "tools_auth.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastapi": fastapi_stub}):
        spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireHumeToolsAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("HUME_TOOLS_SECRET")
        os.environ["HUME_TOOLS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HUME_TOOLS_SECRET", None)
        else:
            os.environ["HUME_TOOLS_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("HUME_TOOLS_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_fails_closed(self):
        os.environ["HUME_TOOLS_SECRET"] = "   "
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_rejected(self):
        req = _FakeRequest(headers={"Authorization": f"Token {SECRET}"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertIsNone(auth.require_hume_tools_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"hume_tools_token": SECRET})
        self.assertIsNone(auth.require_hume_tools_auth(req))

    def test_bearer_preferred_over_query(self):
        req = _FakeRequest(
            headers={"Authorization": "Bearer wrong"},
            query_params={"hume_tools_token": SECRET},
        )
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_blank_query_token_rejected(self):
        req = _FakeRequest(query_params={"hume_tools_token": "   "})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_hume_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)

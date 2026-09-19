"""
Hermetic regression tests for the Hive chat-tools auth guard (#14455).

Before this fix, all /tools/* routes trusted the uid in the JSON body —
anyone could act with the victim's stored Hive credentials. Covers
require_hive_tools_auth: 503 when unconfigured, 401 on missing/wrong
token, bearer + query token accepted.
"""

import importlib.util
import os
import unittest
from pathlib import Path

import fastapi

APP_DIR = Path(__file__).resolve().parent
SECRET = "test-hive-tools-secret"


def _load_auth_module():
    spec = importlib.util.spec_from_file_location(
        "hive_tools_auth", APP_DIR / "hive_tools_auth.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireHiveToolsAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("HIVE_TOOLS_SECRET")
        os.environ["HIVE_TOOLS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("HIVE_TOOLS_SECRET", None)
        else:
            os.environ["HIVE_TOOLS_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("HIVE_TOOLS_SECRET", None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_hive_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_hive_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_hive_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertIsNone(auth.require_hive_tools_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"hive_tools_token": SECRET})
        self.assertIsNone(auth.require_hive_tools_auth(req))


if __name__ == "__main__":
    unittest.main()

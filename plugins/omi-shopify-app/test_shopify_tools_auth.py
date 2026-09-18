"""Hermetic regression tests for Shopify chat-tool route authentication (#14455).

Tests require_shopify_tools_auth under standard library unittest without external
dependencies or network calls.
"""

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


def _load_auth_module():
    spec = importlib.util.spec_from_file_location(
        "shopify_tools_auth_test_module",
        Path(__file__).with_name("shopify_tools_auth.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    fastapi_mock = types.ModuleType("fastapi")
    fastapi_mock.HTTPException = _FakeHTTPException
    fastapi_mock.Request = object
    with unittest.mock.patch.dict(sys.modules, {"fastapi": fastapi_mock}):
        spec.loader.exec_module(mod)
    return mod


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestShopifyToolsAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = _load_auth_module()

    def test_503_when_secret_unset(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            req = _FakeRequest(headers={"Authorization": "Bearer secret"})
            with self.assertRaises(self.auth.HTTPException) as ctx:
                self.auth.require_shopify_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_401_when_no_token_provided(self):
        with unittest.mock.patch.dict(os.environ, {"SHOPIFY_TOOLS_SECRET": "topsecret"}):
            req = _FakeRequest()
            with self.assertRaises(self.auth.HTTPException) as ctx:
                self.auth.require_shopify_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_401_when_bearer_token_wrong(self):
        with unittest.mock.patch.dict(os.environ, {"SHOPIFY_TOOLS_SECRET": "topsecret"}):
            req = _FakeRequest(headers={"Authorization": "Bearer wrongsecret"})
            with self.assertRaises(self.auth.HTTPException) as ctx:
                self.auth.require_shopify_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_401_when_query_token_wrong(self):
        with unittest.mock.patch.dict(os.environ, {"SHOPIFY_TOOLS_SECRET": "topsecret"}):
            req = _FakeRequest(query_params={"shopify_tools_token": "wrongsecret"})
            with self.assertRaises(self.auth.HTTPException) as ctx:
                self.auth.require_shopify_tools_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_200_when_bearer_token_valid(self):
        with unittest.mock.patch.dict(os.environ, {"SHOPIFY_TOOLS_SECRET": "topsecret"}):
            req = _FakeRequest(headers={"Authorization": "Bearer topsecret"})
            # Should not raise
            self.auth.require_shopify_tools_auth(req)

    def test_200_when_query_token_valid(self):
        with unittest.mock.patch.dict(os.environ, {"SHOPIFY_TOOLS_SECRET": "topsecret"}):
            req = _FakeRequest(query_params={"shopify_tools_token": "topsecret"})
            # Should not raise
            self.auth.require_shopify_tools_auth(req)


if __name__ == "__main__":
    unittest.main()

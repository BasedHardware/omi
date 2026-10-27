"""Hermetic tests for zapier webhook route auth (#14428).

Covers require_zapier_webhook_auth at the trust boundary (503 when
unconfigured, 401 on missing/wrong token, bearer + query token accepted,
422 on blank uid) and that the six data-plane routes declare the
dependency.
"""

import importlib.util
import os
import re
import sys
import types
import unittest
from pathlib import Path

ZAPIER_DIR = Path(__file__).resolve().parent
SECRET = "test-zapier-webhook-secret"


def _load_fastapi_stub():
    try:
        import fastapi
        return
    except ImportError:
        pass
    fa = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    def Depends(dependency=None, **kwargs):
        return dependency

    fa.HTTPException = HTTPException
    fa.Request = Request
    fa.Query = Query
    fa.Depends = Depends
    sys.modules.setdefault("fastapi", fa)


def _load_auth_module():
    _load_fastapi_stub()
    spec = importlib.util.spec_from_file_location(
        "zapier_webhook_auth", ZAPIER_DIR / "webhook_auth.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireZapierWebhookAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("ZAPIER_WEBHOOK_SECRET")
        os.environ["ZAPIER_WEBHOOK_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZAPIER_WEBHOOK_SECRET", None)
        else:
            os.environ["ZAPIER_WEBHOOK_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("ZAPIER_WEBHOOK_SECRET", None)
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(_FakeRequest(), uid="u1")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_is_unconfigured(self):
        os.environ["ZAPIER_WEBHOOK_SECRET"] = "   "
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(_FakeRequest(), uid="u1")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(_FakeRequest(), uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_ascii_token_returns_401_without_500_type_error(self):
        req = _FakeRequest(headers={"Authorization": "Bearer token-with-unicode-🚀"})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_ignored(self):
        req = _FakeRequest(headers={"Authorization": "Basic " + SECRET})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(req, uid="u1")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(auth.require_zapier_webhook_auth(req, uid="u1"), "u1")

    def test_lowercase_bearer_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"bearer {SECRET}"})
        self.assertEqual(auth.require_zapier_webhook_auth(req, uid="u1"), "u1")

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"zapier_webhook_token": SECRET})
        self.assertEqual(auth.require_zapier_webhook_auth(req, uid="u1"), "u1")

    def test_uid_trimmed(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(auth.require_zapier_webhook_auth(req, uid="  u1  "), "u1")

    def test_empty_uid_rejected(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_zapier_webhook_auth(req, uid="   ")
        self.assertEqual(ctx.exception.status_code, 422)


class TestRouteWiring(unittest.TestCase):
    """Static wiring check: the six data-plane routes must declare the auth
    dependency as their uid default. Behavioral coverage is in the tests
    above; this proves the routes declare it."""

    PROTECTED = (
        "subscribe_zapier_trigger",
        "unsubscribe_zapier_trigger",
        "get_trigger_conversation_sample",
        "auth_zapier_me",
        "zapier_conversations",
        "zapier_action_conversations",
    )

    UNPROTECTED = (
        "connect",
        "disconnect",
        "setup_zapier_workflow",
        "is_setup_completed",
    )

    @classmethod
    def setUpClass(cls):
        cls.src = (ZAPIER_DIR / "conversation_created.py").read_text(encoding="utf-8")

    def test_data_plane_routes_require_auth(self):
        for name in self.PROTECTED:
            m = re.search(rf"def {name}\([^)]*\)", self.src)
            self.assertIsNotNone(m, f"Function {name} not found")
            self.assertIn(
                "Depends(require_zapier_webhook_auth)",
                m.group(0),
                f"Function {name} missing auth dependency",
            )

    def test_control_plane_routes_unchanged(self):
        for name in self.UNPROTECTED:
            m = re.search(rf"def {name}\([^)]*\)", self.src)
            self.assertIsNotNone(m, f"Function {name} not found")
            self.assertNotIn("require_zapier_webhook_auth", m.group(0), name)


class TestFastAPIDependencyInjectionIntegration(unittest.TestCase):
    """End-to-end FastAPI dependency injection integration test.

    Verifies TestClient hitting /zapier/me with and without authentication token,
    proving FastAPI's real dependency injection mechanics enforce the guard.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from fastapi import FastAPI, Depends, Request
            from fastapi.testclient import TestClient
        except ImportError:
            raise unittest.SkipTest("fastapi or httpx not installed in test environment")

        app = FastAPI()

        @app.get("/zapier/me")
        async def mock_zapier_me(request: Request, uid: str = Depends(auth.require_zapier_webhook_auth)):
            return {"status": "ok", "uid": uid}

        cls.client = TestClient(app)

    def setUp(self):
        self._old = os.environ.get("ZAPIER_WEBHOOK_SECRET")
        os.environ["ZAPIER_WEBHOOK_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZAPIER_WEBHOOK_SECRET", None)
        else:
            os.environ["ZAPIER_WEBHOOK_SECRET"] = self._old

    def test_zapier_me_fails_closed_when_unconfigured(self):
        os.environ.pop("ZAPIER_WEBHOOK_SECRET", None)
        res = self.client.get("/zapier/me?uid=u123")
        self.assertEqual(res.status_code, 503)

    def test_zapier_me_rejects_missing_credentials(self):
        res = self.client.get("/zapier/me?uid=u123")
        self.assertEqual(res.status_code, 401)

    def test_zapier_me_rejects_invalid_token(self):
        res = self.client.get("/zapier/me?uid=u123", headers={"Authorization": "Bearer wrong-token"})
        self.assertEqual(res.status_code, 401)

    def test_zapier_me_accepts_valid_bearer_token(self):
        res = self.client.get("/zapier/me?uid=u123", headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "uid": "u123"})

    def test_zapier_me_accepts_valid_query_token(self):
        res = self.client.get(f"/zapier/me?uid=u123&zapier_webhook_token={SECRET}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "uid": "u123"})


if __name__ == "__main__":
    unittest.main()

"""Hermetic regression tests for the Composio backend and browser route auth guard.

Covers require_composio_tools_auth:
- 503 when COMPOSIO_TOOLS_SECRET is unconfigured or blank.
- 401 on missing, wrong, or non-bearer server token.
- 200 (auth pass) on valid bearer token or composio_tools_token query param.
- 200 (auth pass) on valid signed session token bound to uid.
- 401 when session token is tampered, expired, or bound to a different uid.

fastapi is stubbed so the suite runs without third-party packages.
"""

import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
SECRET = "test-composio-tools-secret"


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
        "composio_tools_auth", APP_DIR / "src" / "tools_auth.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastapi": fastapi_stub}):
        spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None, path_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.path_params = path_params or {}


class TestRequireComposioToolsAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("COMPOSIO_TOOLS_SECRET")
        os.environ["COMPOSIO_TOOLS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("COMPOSIO_TOOLS_SECRET", None)
        else:
            os.environ["COMPOSIO_TOOLS_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("COMPOSIO_TOOLS_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_fails_closed(self):
        os.environ["COMPOSIO_TOOLS_SECRET"] = "   "
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_rejected(self):
        req = _FakeRequest(headers={"Authorization": f"Token {SECRET}"})
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertIsNone(auth.require_composio_tools_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={"composio_tools_token": SECRET})
        self.assertIsNone(auth.require_composio_tools_auth(req))

    def test_signed_session_header_accepted_with_matching_uid(self):
        uid = "user-abc-123"
        token = auth.create_composio_session_token(uid)
        req = _FakeRequest(
            headers={"X-Composio-Session": token},
            query_params={"uid": uid},
        )
        self.assertEqual(auth.require_composio_tools_auth(req), uid)

    def test_signed_session_param_accepted_with_path_uid(self):
        uid = "user-xyz-456"
        token = auth.create_composio_session_token(uid)
        req = _FakeRequest(
            query_params={"composio_session": token},
            path_params={"uid": uid},
        )
        self.assertEqual(auth.require_composio_tools_auth(req), uid)

    def test_signed_session_rejected_when_uid_mismatched(self):
        attacker_uid = "attacker-evil"
        victim_uid = "victim-user"
        attacker_token = auth.create_composio_session_token(attacker_uid)
        req = _FakeRequest(
            headers={"X-Composio-Session": attacker_token},
            path_params={"uid": victim_uid},
        )
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_signed_session_rejected_when_expired(self):
        uid = "user-old"
        expired_ts = int(time.time()) - 100000  # > 24 hours ago
        expired_token = auth.create_composio_session_token(uid, timestamp=expired_ts)
        req = _FakeRequest(
            headers={"X-Composio-Session": expired_token},
            path_params={"uid": uid},
        )
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_signed_session_rejected_when_tampered(self):
        uid = "user-tamper"
        token = auth.create_composio_session_token(uid)
        tampered_token = token[:-2] + "ff"
        req = _FakeRequest(
            headers={"X-Composio-Session": tampered_token},
            path_params={"uid": uid},
        )
        with self.assertRaises(HTTPException) as ctx:
            auth.require_composio_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)


def _load_notion_module():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import Mock

    fastapi = ModuleType("fastapi")
    fastapi.APIRouter = lambda **kw: SimpleNamespace(get=lambda *a, **k: lambda f: f, post=lambda *a, **k: lambda f: f)
    fastapi.HTTPException = HTTPException
    fastapi.Depends = lambda x: x
    fastapi.Request = object
    fastapi.status = SimpleNamespace(
        HTTP_200_OK=200, HTTP_400_BAD_REQUEST=400, HTTP_401_UNAUTHORIZED=401,
        HTTP_403_FORBIDDEN=403, HTTP_500_INTERNAL_SERVER_ERROR=500, HTTP_503_SERVICE_UNAVAILABLE=503
    )
    fastapi.Form = lambda *a, **k: None
    fastapi.BackgroundTasks = object

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = object
    responses.RedirectResponse = lambda *a, **k: None

    templating = ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda **kw: SimpleNamespace(TemplateResponse=lambda name, ctx: ctx)

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = type("BaseModel", (), {})

    requests = ModuleType("requests")
    requests.exceptions = SimpleNamespace(RequestException=RuntimeError)
    requests.post = Mock(return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": []}))
    requests.get = Mock(return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": []}))

    db = ModuleType("src.db")
    db.store_notion_credentials = Mock()
    db.get_notion_credentials = Mock(return_value={"notion_access_token": "mock-token", "notion_workspace_name": "Test Workspace"})
    db.store_memory = Mock()

    omi_api = ModuleType("src.omi_api")
    omi_api.store_fact = Mock()

    src_pkg = ModuleType("src")
    src_pkg.__path__ = [str(APP_DIR / "src")]

    modules = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.templating": templating,
        "pydantic": pydantic,
        "requests": requests,
        "src": src_pkg,
        "src.db": db,
        "src.omi_api": omi_api,
        "src.tools_auth": auth,
    }

    spec = importlib.util.spec_from_file_location("src.notion", APP_DIR / "src" / "notion.py")
    notion_mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(notion_mod)
    return notion_mod


class TestNotionRouteAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncio
        from types import SimpleNamespace
        cls.asyncio = asyncio
        cls.SimpleNamespace = SimpleNamespace
        cls.notion = _load_notion_module()

    def setUp(self):
        self._old = os.environ.get("COMPOSIO_TOOLS_SECRET")
        os.environ["COMPOSIO_TOOLS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("COMPOSIO_TOOLS_SECRET", None)
        else:
            os.environ["COMPOSIO_TOOLS_SECRET"] = self._old

    def test_search_notion_rejects_mismatched_uid(self):
        req = self.SimpleNamespace(uid="victim", query=None, filter=None, sort=None)
        with self.assertRaises(HTTPException) as ctx:
            self.asyncio.run(self.notion.search_notion(request=req, verified_uid="attacker"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_search_notion_accepts_matching_uid(self):
        req = self.SimpleNamespace(uid="user-1", query=None, filter=None, sort=None)
        res = self.asyncio.run(self.notion.search_notion(request=req, verified_uid="user-1"))
        self.assertEqual(res, {"results": []})

    def test_search_notion_allows_server_shared_secret(self):
        req = self.SimpleNamespace(uid="any-user", query=None, filter=None, sort=None)
        res = self.asyncio.run(self.notion.search_notion(request=req, verified_uid=None))
        self.assertEqual(res, {"results": []})

    def test_get_blocks_rejects_mismatched_uid(self):
        req = self.SimpleNamespace(uid="victim")
        with self.assertRaises(HTTPException) as ctx:
            self.asyncio.run(self.notion.get_blocks("block-1", request=req, verified_uid="attacker"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_extract_memories_rejects_mismatched_uid(self):
        with self.assertRaises(HTTPException) as ctx:
            self.asyncio.run(
                self.notion.extract_memories(
                    uid="victim", block_type="page", block_id="block-1", verified_uid="attacker"
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_import_page_rejects_mismatched_uid(self):
        with self.assertRaises(HTTPException) as ctx:
            self.asyncio.run(self.notion.import_page(request=object(), uid="victim", verified_uid="attacker"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_import_page_propagates_unconfigured_error(self):
        os.environ.pop("COMPOSIO_TOOLS_SECRET", None)
        with self.assertRaises(HTTPException) as ctx:
            self.asyncio.run(self.notion.import_page(request=object(), uid="user-1", verified_uid="user-1"))
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()

"""Hermetic tests for Notion plugin routes and error masking."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent


def load_notion_module():
    fastapi = ModuleType("fastapi")

    class APIRouter:
        def __init__(self, **_kwargs):
            pass

        def post(self, *_args, **_kwargs):
            return lambda handler: handler

        get = post

    fastapi.APIRouter = APIRouter
    fastapi.Depends = lambda value: value

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None, **kwargs):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.HTTPException = HTTPException
    fastapi.Request = type("Request", (), {})
    fastapi.status = SimpleNamespace(
        HTTP_200_OK=200,
        HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401,
        HTTP_500_INTERNAL_SERVER_ERROR=500,
    )
    fastapi.Form = lambda *a, **kw: None

    class BackgroundTasks:
        def add_task(self, *a, **kw):
            pass

    fastapi.BackgroundTasks = BackgroundTasks

    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = type("HTMLResponse", (), {})
    fastapi_responses.RedirectResponse = type("RedirectResponse", (), {})

    fastapi_templating = ModuleType("fastapi.templating")

    class Jinja2Templates:
        def __init__(self, **kw):
            pass

        def TemplateResponse(self, *a, **kw):
            return {}

    fastapi_templating.Jinja2Templates = Jinja2Templates

    pydantic = ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic.BaseModel = BaseModel

    requests = ModuleType("requests")

    class RequestException(Exception):
        pass

    requests.exceptions = SimpleNamespace(RequestException=RequestException)
    requests.post = lambda *a, **kw: None
    requests.get = lambda *a, **kw: None

    src = ModuleType("src")
    src.__path__ = []

    db = ModuleType("src.db")
    db.store_notion_credentials = lambda *a, **kw: None
    db.get_notion_credentials = lambda *a, **kw: {"notion_access_token": "fake_token"}
    db.store_memory = lambda *a, **kw: None

    omi_api = ModuleType("src.omi_api")
    omi_api.store_fact = lambda *a, **kw: True

    tools_auth = ModuleType("src.tools_auth")
    tools_auth.require_composio_tools_auth = lambda req=None: None

    notion_file = APP_DIR / "src" / "notion.py"
    spec = importlib.util.spec_from_file_location("src.notion", notion_file)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "fastapi.templating": fastapi_templating,
            "pydantic": pydantic,
            "requests": requests,
            "requests.exceptions": requests.exceptions,
            "src": src,
            "src.db": db,
            "src.omi_api": omi_api,
            "src.tools_auth": tools_auth,
        },
    ):
        spec.loader.exec_module(module)
    return module


notion = load_notion_module()


class TestNotionRoutes(unittest.TestCase):
    def test_loads_notion_module(self):
        self.assertIsNotNone(notion.router)
        self.assertTrue(callable(notion.format_as_memory))
        self.assertTrue(callable(notion.contains_personal_info))

    def test_format_as_memory_without_name_error(self):
        res = notion.format_as_memory("I like reading books")
        self.assertIn("User likes", res)

    def test_search_notion_masks_exception(self):
        def raise_req_err(*args, **kwargs):
            raise notion.requests.exceptions.RequestException("sensitive connection details")

        req = notion.NotionSearchRequest(uid="test_uid", query="search term")
        with patch.object(notion.requests, "post", side_effect=raise_req_err):
            with self.assertRaises(notion.HTTPException) as ctx:
                asyncio.run(notion.search_notion(req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Error searching Notion workspace")
            self.assertNotIn("sensitive connection details", ctx.exception.detail)

    def test_get_blocks_masks_exception(self):
        def raise_req_err(*args, **kwargs):
            raise notion.requests.exceptions.RequestException("sensitive url path")

        req = notion.NotionBlocksRequest(uid="test_uid")
        with patch.object(notion.requests, "get", side_effect=raise_req_err):
            with self.assertRaises(notion.HTTPException) as ctx:
                asyncio.run(notion.get_blocks("block-123", req))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Error retrieving blocks from Notion")
            self.assertNotIn("sensitive url path", ctx.exception.detail)

    def test_get_page_masks_exception(self):
        def raise_req_err(*args, **kwargs):
            raise notion.requests.exceptions.RequestException("internal token leak")

        with patch.object(notion.requests, "get", side_effect=raise_req_err):
            with self.assertRaises(notion.HTTPException) as ctx:
                asyncio.run(notion.get_page("page-123", "test_uid"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Error retrieving page from Notion")
            self.assertNotIn("internal token leak", ctx.exception.detail)

    def test_extract_memories_masks_exception(self):
        def raise_req_err(*args, **kwargs):
            raise notion.requests.exceptions.RequestException("upstream timeout info")

        with patch.object(notion.requests, "get", side_effect=raise_req_err):
            with self.assertRaises(notion.HTTPException) as ctx:
                asyncio.run(notion.extract_memories(uid="test_uid", block_type="page", block_id="block-123"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Error extracting memories from Notion")
            self.assertNotIn("upstream timeout info", ctx.exception.detail)

    def test_notion_callback_masks_exception(self):
        def raise_req_err(*args, **kwargs):
            raise RuntimeError("internal OAuth handler crash")

        req = notion.Request()
        bg_tasks = notion.BackgroundTasks()
        with patch.object(notion.requests, "post", side_effect=raise_req_err):
            with self.assertRaises(notion.HTTPException) as ctx:
                asyncio.run(notion.notion_callback(req, bg_tasks, code="auth-code", state="test_uid"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Internal error processing Notion authentication callback")
            self.assertNotIn("internal OAuth handler crash", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()

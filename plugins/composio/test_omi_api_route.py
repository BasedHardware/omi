"""Hermetic regression test for the Composio memory integration route."""

import importlib.util
import asyncio
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def load_module():
    fastapi = ModuleType("fastapi")

    class APIRouter:
        def __init__(self, **_kwargs):
            pass

        def post(self, *_args, **_kwargs):
            return lambda handler: handler

        get = post

    fastapi.APIRouter = APIRouter
    fastapi.Depends = lambda value: value
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
    fastapi.Request = type("Request", (), {})
    fastapi.status = SimpleNamespace(HTTP_200_OK=200, HTTP_500_INTERNAL_SERVER_ERROR=500)

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = type("BaseModel", (), {})
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    requests = ModuleType("requests")
    requests.exceptions = SimpleNamespace(RequestException=RuntimeError)
    requests.post = lambda *args, **kwargs: None

    src = ModuleType("src")
    src.__path__ = []
    db = ModuleType("src.db")
    db.get_pending_memories = lambda *_args, **_kwargs: []
    db.update_memory_status = lambda *_args, **_kwargs: None
    db.get_all_memories = lambda *_args, **_kwargs: []

    tools_auth = ModuleType("src.tools_auth")

    def _require_composio_tools_auth(request=None):
        return None

    tools_auth.require_composio_tools_auth = _require_composio_tools_auth

    spec = importlib.util.spec_from_file_location("src.omi_api", Path(__file__).parent / "src" / "omi_api.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "pydantic": pydantic,
            "dotenv": dotenv,
            "requests": requests,
            "src": src,
            "src.db": db,
            "src.tools_auth": tools_auth,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_module()


class OmiApiRouteTests(unittest.TestCase):
    def test_create_fact_posts_to_memories_route(self):
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"
        response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        with patch.object(app.requests, "post", return_value=response) as post:
            self.assertTrue(app.create_fact("user-1", "A memory", "other", "notion"))

        post.assert_called_once()
        url = post.call_args.args[0]
        self.assertEqual(url, "https://api.omi.me/v2/integrations/app-1/user/memories?uid=user-1")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(post.call_args.kwargs["json"], {"text": "A memory", "text_source": "other", "text_source_spec": "notion"})

    def test_create_fact_never_uses_retired_facts_route(self):
        """The integration contract exposes /user/memories, never /user/facts."""
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"
        response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        with patch.object(app.requests, "post", return_value=response) as post:
            self.assertTrue(app.create_fact("user-1", "A memory"))

        url = post.call_args.args[0]
        self.assertIn("/user/memories?", url)
        self.assertNotIn("/user/facts", url)

    def test_create_fact_clamps_custom_source_and_preserves_provenance(self):
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"
        response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        with patch.object(app.requests, "post", return_value=response) as post:
            self.assertTrue(app.create_fact("user-1", "A memory", "notion_page"))

        self.assertEqual(post.call_args.kwargs["json"], {
            "text": "A memory",
            "text_source": "other",
            "text_source_spec": "notion_page",
        })

    def test_create_fact_keeps_existing_provenance_without_duplication(self):
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"
        response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

        with patch.object(app.requests, "post", return_value=response) as post:
            self.assertTrue(app.create_fact("user-1", "A memory", "notion_page", "notion:notion_page"))

        self.assertEqual(post.call_args.kwargs["json"]["text_source"], "other")
        self.assertEqual(post.call_args.kwargs["json"]["text_source_spec"], "notion:notion_page")

    def test_create_fact_rejects_missing_credentials_before_network(self):
        app.APP_ID = None
        app.API_KEY = None

        with patch.object(app.requests, "post") as post:
            with self.assertRaises(ValueError):
                app.create_fact("user-1", "A memory")

        post.assert_not_called()

    def test_process_pending_memories_clamps_custom_source(self):
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"
        response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)
        pending = [{"id": 7, "memory_text": "A Notion memory", "source": "notion_page"}]

        with patch.object(app, "get_pending_memories", return_value=pending), \
             patch.object(app, "update_memory_status") as update_status, \
             patch.object(app.requests, "post", return_value=response) as post:
            result = asyncio.run(app.process_pending_memories("user-1"))

        self.assertEqual(result, {"processed": 1, "results": [{"id": 7, "success": True}]})
        self.assertEqual(post.call_args.kwargs["json"], {
            "text": "A Notion memory",
            "text_source": "other",
            "text_source_spec": "notion:notion_page",
        })
        update_status.assert_called_once_with(7, "completed")

    def test_process_pending_memories_marks_failed_on_request_error(self):
        app.APP_ID = "app-1"
        app.API_KEY = "test-key"

        def raise_request_error():
            raise RuntimeError("422")

        response = SimpleNamespace(status_code=422, raise_for_status=raise_request_error)
        pending = [{"id": 8, "memory_text": "A failed memory", "source": "notion_page"}]

        with patch.object(app, "get_pending_memories", return_value=pending), \
             patch.object(app, "update_memory_status") as update_status, \
             patch.object(app.requests, "post", return_value=response):
            result = asyncio.run(app.process_pending_memories("user-1"))

        self.assertEqual(result, {"processed": 1, "results": [{"id": 8, "success": False}]})
        update_status.assert_called_once_with(8, "failed")


if __name__ == "__main__":
    unittest.main()

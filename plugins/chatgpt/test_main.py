"""
Hermetic test suite for Omi ChatGPT Plugin.
Tests router endpoints, UID redirect encoding, UTC stats timestamps, and error redirection.
Runs with Python standard library only (stubs FastAPI/Jinja2 if absent).
"""

import asyncio
from datetime import datetime
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock

# --- Hermetic stubs for environments without FastAPI / Jinja2 ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyAPIRouter:
        def __init__(self, prefix="", tags=None):
            self.prefix = prefix
            self.tags = tags or []
            self.routes = []

        def get(self, path, response_class=None):
            def decorator(func):
                self.routes.append((path, func))
                return func
            return decorator

    class DummyRequest:
        def __init__(self, scope=None):
            self.scope = scope or {}

    fastapi_mod.APIRouter = DummyAPIRouter
    fastapi_mod.Request = DummyRequest
    sys.modules["fastapi"] = fastapi_mod

if "fastapi.responses" not in sys.modules:
    resp_mod = ModuleType("fastapi.responses")

    class HTMLResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code

    class JSONResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code

    class RedirectResponse:
        def __init__(self, url, status_code=307):
            self.headers = {"location": url}
            self.status_code = status_code

    resp_mod.HTMLResponse = HTMLResponse
    resp_mod.JSONResponse = JSONResponse
    resp_mod.RedirectResponse = RedirectResponse
    sys.modules["fastapi.responses"] = resp_mod

if "fastapi.templating" not in sys.modules:
    templ_mod = ModuleType("fastapi.templating")

    class DummyTemplates:
        def __init__(self, directory=None):
            self.directory = directory

        def TemplateResponse(self, template_name, context):
            return {"template": template_name, "context": context}

    templ_mod.Jinja2Templates = DummyTemplates
    sys.modules["fastapi.templating"] = templ_mod

import main


class TestChatGPTPlugin(unittest.TestCase):

    def test_router_configuration(self):
        self.assertEqual(main.router.prefix, "/chatgpt")
        self.assertIn("chatgpt", main.router.tags)

    def test_redirect_missing_or_blank_uid(self):
        # Empty string
        resp1 = asyncio.run(main.redirect_to_chatgpt(""))
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(resp1.headers["location"], "/chatgpt?error=missing_uid")

        # Whitespace-only string
        resp2 = asyncio.run(main.redirect_to_chatgpt("   "))
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(resp2.headers["location"], "/chatgpt?error=missing_uid")

    def test_redirect_valid_uid(self):
        resp = asyncio.run(main.redirect_to_chatgpt("user_12345"))
        self.assertEqual(resp.status_code, 302)
        expected = "https://chatgpt.com/g/g-67e2772d0af081919a5baddf4a12aacf-omi?prompt=here%20is%20my%20omi%20uid%20user_12345"
        self.assertEqual(resp.headers["location"], expected)

    def test_redirect_url_encoding_special_chars(self):
        resp = asyncio.run(main.redirect_to_chatgpt("user+abc@example.com"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("user%2Babc%40example.com", resp.headers["location"])

    def test_stats_endpoint_returns_utc_timestamp(self):
        fake_req = MagicMock()
        resp = asyncio.run(main.get_stats(fake_req))
        self.assertEqual(resp.content["status"], "success")
        self.assertEqual(resp.content["message"], "Stats endpoint is working")

        # Verify timestamp contains timezone info (+00:00 or Z)
        ts = resp.content["timestamp"]
        self.assertTrue("+00:00" in ts or "Z" in ts or ts.endswith("+00:00"))
        # Parse timestamp to confirm validity
        parsed = datetime.fromisoformat(ts)
        self.assertIsNotNone(parsed.tzinfo)

    def test_chatgpt_page_renders_context(self):
        fake_req = MagicMock()
        resp = asyncio.run(main.chatgpt_page(fake_req, uid="test_uid"))
        # Context should contain uid and title
        if hasattr(resp, "content"):
            content = resp.content
        elif isinstance(resp, dict):
            content = resp.get("context", {})
        else:
            content = {}
        self.assertIn("uid", content)
        self.assertEqual(content["uid"], "test_uid")


if __name__ == "__main__":
    unittest.main()

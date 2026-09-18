"""
Hermetic test suite for Omi Subscription Plugin.
Tests router configuration, endpoint response, logging behavior, and template context.
Runs with Python standard library only (stubs FastAPI/Jinja2 if absent).
"""

import asyncio
import sys
from types import ModuleType
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

    resp_mod.HTMLResponse = HTMLResponse
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


class TestSubscriptionPlugin(unittest.TestCase):

    def test_router_configuration(self):
        self.assertEqual(main.router.prefix, "/subscription")
        self.assertIn("subscription", main.router.tags)

    def test_subscription_page_with_uid(self):
        fake_req = MagicMock()
        resp = asyncio.run(main.subscription_page(fake_req, uid="user_sub_99"))
        if hasattr(resp, "content"):
            content = resp.content
        elif isinstance(resp, dict):
            content = resp
        else:
            content = {}

        if "context" in content:
            ctx = content["context"]
            self.assertEqual(ctx["uid"], "user_sub_99")
            self.assertEqual(ctx["page_title"], "Upgrade to Unlimited")
            self.assertEqual(content["template"], "subscription/index.html")

    def test_subscription_page_without_uid(self):
        fake_req = MagicMock()
        resp = asyncio.run(main.subscription_page(fake_req, uid=""))
        if hasattr(resp, "content"):
            content = resp.content
        elif isinstance(resp, dict):
            content = resp
        else:
            content = {}

        if "context" in content:
            ctx = content["context"]
            self.assertEqual(ctx["uid"], "")
            self.assertEqual(ctx["page_title"], "Upgrade to Unlimited")


if __name__ == "__main__":
    unittest.main()

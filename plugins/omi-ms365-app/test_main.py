"""
Hermetic test suite for the Microsoft 365 (MS365) integration app.

Exercises manifest loading, parameter schemas, endpoint injection,
tool dispatch error flows, and authentication guards without external dependencies.
Runs cleanly under pure standard library Python (including python3 -S).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail

    class Request:
        def __init__(self, json_data=None, query_params=None):
            self._json = json_data or {}
            self.query_params = query_params or {}

        async def json(self):
            return self._json

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = str
    responses.JSONResponse = lambda **kwargs: kwargs.get("content", {})

    itsdangerous = ModuleType("itsdangerous")
    itsdangerous.BadSignature = type("BadSignature", (Exception,), {})
    class URLSafeSerializer:
        def __init__(self, *args, **kwargs):
            pass
        def dumps(self, obj):
            return "mock_signed_state"
        def loads(self, s):
            return {"uid": "mock_uid", "nonce": "123"}
    itsdangerous.URLSafeSerializer = URLSafeSerializer

    config = ModuleType("config")
    class Settings:
        log_level = "INFO"
        session_secret = "test-secret"
        app_base_url = "https://ms365.example.com"
    config.get_settings = lambda: Settings()

    services = ModuleType("services")
    auth = ModuleType("services.auth")
    auth.AuthError = type("AuthError", (Exception,), {})
    auth.build_auth_url = Mock(return_value="https://login.microsoftonline.com")
    auth.exchange_code_for_token = AsyncMock()
    auth.get_access_token = AsyncMock(return_value="fake_access_token")

    profile = ModuleType("services.profile")
    profile.me = AsyncMock(return_value={"displayName": "Test User", "mail": "test@example.com"})

    mail = ModuleType("services.mail")
    mail.list_recent = AsyncMock(return_value=[])
    mail.search = AsyncMock(return_value=[])
    mail.read = AsyncMock(return_value={})
    mail.send = AsyncMock(return_value={"sent": True})

    cal = ModuleType("services.calendar")
    cal.list_upcoming = AsyncMock(return_value=[])
    cal.create_event = AsyncMock(return_value={})
    cal.find_free_slots = AsyncMock(return_value=[])

    teams_svc = ModuleType("services.teams")
    teams_svc.list_recent_chats = AsyncMock(return_value=[])
    teams_svc.send_chat_message = AsyncMock(return_value={})
    teams_svc.list_my_teams = AsyncMock(return_value=[])
    teams_svc.create_online_meeting = AsyncMock(return_value={})

    sp = ModuleType("services.sharepoint")
    sp.list_recent_files = AsyncMock(return_value=[])
    sp.search_files = AsyncMock(return_value=[])
    sp.upload_text_file = AsyncMock(return_value={})
    sp.read_file_text = AsyncMock(return_value="file content")

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "itsdangerous": itsdangerous,
        "config": config,
        "services": services,
        "services.auth": auth,
        "services.profile": profile,
        "services.mail": mail,
        "services.calendar": cal,
        "services.teams": teams_svc,
        "services.sharepoint": sp,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("ms365_main", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, stubs


app_module, stubs = load_app()


class Ms365AppTests(unittest.TestCase):
    def test_manifest_structure_and_parameters(self):
        manifest = app_module._load_manifest()
        self.assertIn("tools", manifest)
        self.assertGreaterEqual(len(manifest["tools"]), 15)

        for tool in manifest["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            self.assertIn("endpoint", tool)
            self.assertTrue(tool["endpoint"].startswith("https://ms365.example.com/tools/"))
            params = tool["parameters"]
            self.assertEqual(params.get("type"), "object")
            self.assertIn("properties", params)

    def test_tool_dispatch_requires_uid(self):
        req = stubs["fastapi"].Request(json_data={})
        with self.assertRaises(stubs["fastapi"].HTTPException) as ctx:
            asyncio.run(app_module.tool_dispatch("get_me", req))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("uid", ctx.exception.detail)

    def test_tool_dispatch_unknown_tool(self):
        req = stubs["fastapi"].Request(json_data={"uid": "user123"})
        with self.assertRaises(stubs["fastapi"].HTTPException) as ctx:
            asyncio.run(app_module.tool_dispatch("nonexistent_tool", req))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Unknown tool", ctx.exception.detail)

    def test_tool_dispatch_success(self):
        req = stubs["fastapi"].Request(json_data={"uid": "user123", "args": {}})
        resp = asyncio.run(app_module.tool_dispatch("get_me", req))
        self.assertEqual(resp.get("displayName"), "Test User")


if __name__ == "__main__":
    unittest.main()

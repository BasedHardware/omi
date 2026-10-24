"""Regression tests pinning that Whoop /tools handlers do not leak raw
exception text in their error responses.

This loads main.py (with hermetic stubs) and drives each tool handler so
that the underlying whoop_api_request raises; the returned ChatToolResponse
error must be a generic message, never the raw exception string.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Response:
    result = None
    error = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi", FastAPI=Framework, Request=Framework, Query=Framework,
        HTTPException=Exception, Depends=lambda dep: dep,
    ),
    "fastapi.responses": module(
        "fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework,
        JSONResponse=Framework,
    ),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_whoop_tokens", "get_whoop_tokens", "update_whoop_tokens",
        "delete_whoop_tokens", "store_oauth_state", "get_uid_from_oauth_state",
        "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
    "whoop_tools_auth": module(
        "whoop_tools_auth", require_whoop_tools_auth=lambda *a, **k: None
    ),
}

spec = importlib.util.spec_from_file_location(
    "whoop_leak_under_test", Path(__file__).with_name("main.py")
)
whoop = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(whoop)


SECRET = "boom-secret-detail-42"


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestWhoopToolErrorLeak(unittest.TestCase):
    # (handler name, request body)
    HANDLERS = [
        ("tool_get_recovery", {"uid": "u"}),
        ("tool_get_strain", {"uid": "u"}),
        ("tool_get_sleep", {"uid": "u"}),
        ("tool_get_workouts", {"uid": "u"}),
        ("tool_get_weekly_summary", {"uid": "u"}),
        ("tool_get_body_measurements", {"uid": "u"}),
        ("tool_get_profile", {"uid": "u"}),
    ]

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_handlers_do_not_leak_raw_exception(self):
        for name, body in self.HANDLERS:
            handler = getattr(whoop, name, None)
            if handler is None:
                continue
            req = mock_request(body)
            with patch.object(whoop, "get_valid_access_token", return_value="tok"), \
                 patch.object(whoop, "whoop_api_request",
                              side_effect=RuntimeError(SECRET)):
                resp = self.loop.run_until_complete(handler(req))
            # An error should be reported...
            self.assertIsNotNone(resp.error, f"{name}: expected an error")
            # ...but it must NOT contain the raw exception detail.
            self.assertNotIn(SECRET, resp.error or "",
                             f"{name} leaks raw exception text")


if __name__ == "__main__":
    unittest.main(verbosity=2)

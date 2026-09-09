"""Hermetic request/handler regressions; framework and persistence are import doubles."""
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

    def mount(self, *args, **kwargs):
        pass


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
    "requests": module("requests", get=Mock(), post=Mock(), put=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, HTTPException=Exception, Request=Framework, Query=Framework),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_shipbob_tokens", "get_shipbob_tokens", "delete_shipbob_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state",
        "update_shipbob_channel", "get_user_settings",
    )}),
}
spec = importlib.util.spec_from_file_location("shipbob_under_test", Path(__file__).with_name("main.py"))
shipbob = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shipbob)


class RequestFailureTests(unittest.TestCase):
    def setUp(self):
        for target, replacement in (
            ("refresh_token_if_needed", Mock(return_value=True)),
            ("get_shipbob_headers", Mock(return_value={"Content-Type": "application/json"})),
            ("log", Mock()),
        ):
            patcher = patch.object(shipbob, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_shared_request_reports_empty_http_errors_for_all_methods(self):
        for method in ("GET", "POST", "PUT", "DELETE"):
            for status in (400, 500):
                with self.subTest(method=method, status=status):
                    response = Mock(status_code=status, text="")
                    with patch.object(shipbob.requests, method.lower(), return_value=response):
                        result = shipbob.make_shipbob_request("test-user", method, "/test")
                    self.assertEqual(result["status_code"], status)
                    self.assertEqual(result["error"], f"ShipBob request failed (HTTP {status})")

    def test_cancellation_uses_actual_helper_and_never_confirms_http_failure(self):
        for status, body in ((400, ""), (500, ""), (500, "upstream failure")):
            with self.subTest(status=status, body=body):
                request = Mock(json=AsyncMock(return_value={"uid": "test-user", "wro_id": 12345}))
                with patch.object(shipbob.requests, "post", return_value=Mock(status_code=status, text=body)) as post:
                    result = asyncio.run(shipbob.tool_cancel_wro(request))
                self.assertIsNone(result.result)
                self.assertEqual(result.error, "Failed to cancel WRO: " + (body or f"ShipBob request failed (HTTP {status})"))
                post.assert_called_once()
                self.assertTrue(post.call_args.args[0].endswith("/2.0/receiving/12345/cancel"))

    def test_successful_cancellation_is_unchanged(self):
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "wro_id": 12345}))
        response = Mock(status_code=200, text='{"id":12345}')
        response.json.return_value = {"id": 12345}
        with patch.object(shipbob.requests, "post", return_value=response):
            result = asyncio.run(shipbob.tool_cancel_wro(request))
        self.assertIsNone(result.error)
        self.assertEqual(result.result, "**WRO #12345 has been cancelled.**")


if __name__ == "__main__":
    unittest.main(verbosity=2)

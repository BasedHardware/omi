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
            for status, body in ((status, body) for status in (400, 500) for body in ("", " ", "\n", " \t\r\n")):
                with self.subTest(method=method, status=status, body=body):
                    response = Mock(status_code=status, text=body)
                    with patch.object(shipbob.requests, method.lower(), return_value=response):
                        result = shipbob.make_shipbob_request("test-user", method, "/test")
                    self.assertEqual(result["status_code"], status)
                    self.assertEqual(result["error"], f"ShipBob request failed (HTTP {status})")

    def test_cancellation_uses_actual_helper_and_never_confirms_http_failure(self):
        for status, body in ((400, ""), (500, ""), (400, " "), (500, "\n"), (500, " \t\r\n"), (500, "upstream failure"), (500, " \nupstream failure\n ")):
            with self.subTest(status=status, body=body):
                request = Mock(json=AsyncMock(return_value={"uid": "test-user", "wro_id": 12345}))
                with patch.object(shipbob.requests, "post", return_value=Mock(status_code=status, text=body)) as post:
                    result = asyncio.run(shipbob.tool_cancel_wro(request))
                self.assertIsNone(result.result)
                self.assertEqual(result.error, "Failed to cancel WRO: " + (body if body.strip() else f"ShipBob request failed (HTTP {status})"))
                post.assert_called_once()
                self.assertTrue(post.call_args.args[0].endswith("/2.0/receiving/12345/cancel"))

    def test_create_and_read_handlers_surface_transport_failures(self):
        cases = (
            (shipbob.tool_create_wro, "POST", {"product_name": "Widget", "quantity": 2, "fulfillment_center_id": 1}, "Failed to create WRO: "),
            (shipbob.tool_get_wros, "GET", {}, "Failed to get WROs: "),
            (shipbob.tool_get_orders, "GET", {}, "Failed to get orders: "),
        )
        for handler, method, payload, prefix in cases:
            for body in ("", " \t\r\n", "forbidden"):
                with self.subTest(handler=handler.__name__, body=body):
                    request = Mock(json=AsyncMock(return_value={"uid": "test-user", **payload}))
                    product = {"name": "Widget", "fulfillable_inventory_items": [{"id": 7}]}
                    with patch.object(shipbob, "search_product_by_name", return_value=product), patch.object(shipbob, "get_shipbob_tokens", return_value=None), patch.object(shipbob.requests, method.lower(), return_value=Mock(status_code=500, text=body)) as transport:
                        result = asyncio.run(handler(request))
                    transport.assert_called_once()
                    self.assertIsNone(result.result)
                    self.assertEqual(result.error, prefix + (body if body.strip() else "ShipBob request failed (HTTP 500)"))

    def test_successful_create_and_empty_reads_are_unchanged(self):
        cases = (
            (shipbob.tool_create_wro, "POST", {"product_name": "Widget", "quantity": 2, "fulfillment_center_id": 1}, {"id": 123, "status": "Awaiting"}, "**WRO Created Successfully!**"),
            (shipbob.tool_get_wros, "GET", {}, [], "No WROs found."),
            (shipbob.tool_get_orders, "GET", {}, [], "No orders found."),
        )
        for handler, method, payload, data, expected in cases:
            with self.subTest(handler=handler.__name__):
                request = Mock(json=AsyncMock(return_value={"uid": "test-user", **payload}))
                response = Mock(status_code=200, text="")
                response.json.return_value = data
                product = {"name": "Widget", "fulfillable_inventory_items": [{"id": 7}]}
                with patch.object(shipbob, "search_product_by_name", return_value=product), patch.object(shipbob, "get_shipbob_tokens", return_value=None), patch.object(shipbob.requests, method.lower(), return_value=response) as transport:
                    result = asyncio.run(handler(request))
                transport.assert_called_once()
                self.assertIsNone(result.error)
                self.assertIn(expected, result.result)

    def test_upstream_cancellation_guards_remain_intact(self):
        for value in (None, {"error": "", "status_code": 500}, {"error": "forbidden", "status_code": 403}):
            with self.subTest(value=value):
                request = Mock(json=AsyncMock(return_value={"uid": "test-user", "wro_id": 12345}))
                with patch.object(shipbob, "make_shipbob_request", return_value=value):
                    result = asyncio.run(shipbob.tool_cancel_wro(request))
                self.assertIsNone(result.result)
                self.assertTrue(result.error)

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

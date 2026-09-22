"""Hermetic regression tests verifying error sanitization in plugins/omi-shipbob-app.
Ensures internal exception details, network errors, and sensitive tokens are not leaked to users.
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
    exception_handler = get
    mount = lambda *args, **kwargs: None


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


class DummyTemplateResponse:
    def __init__(self, name, context):
        self.template = types.SimpleNamespace(name=name)
        self.context = context


class DummyTemplates:
    def __init__(self, *args, **kwargs):
        pass

    def TemplateResponse(self, name, context):
        return DummyTemplateResponse(name, context)


stubs = {
    "requests": module("requests", RequestException=OSError, get=Mock(), post=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi",
        **{
            name: Framework for name in ("Depends", "FastAPI", "HTTPException", "Request", "Query")
        },
    ),
    "fastapi.responses": module(
        "fastapi.responses",
        **{
            name: Framework
            for name in ("HTMLResponse", "RedirectResponse", "JSONResponse")
        },
    ),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=DummyTemplates),
    "fastapi.exceptions": module("fastapi.exceptions", RequestValidationError=Framework),
    "shipbob_tools_auth": module("shipbob_tools_auth", require_shipbob_tools_auth=Mock()),
    "db": module(
        "db",
        **{
            name: Mock()
            for name in (
                "store_shipbob_tokens",
                "get_shipbob_tokens",
                "delete_shipbob_tokens",
                "store_oauth_state",
                "get_oauth_state",
                "delete_oauth_state",
                "update_shipbob_channel",
                "get_user_settings",
            )
        },
    ),
    "models": module(
        "models",
        ChatToolResponse=Response,
        **{
            name: Response
            for name in (
                "GetInventoryRequest",
                "GetProductsRequest",
                "CreateWroRequest",
                "GetWrosRequest",
                "CancelWroRequest",
                "GetOrdersRequest",
                "GetFulfillmentCentersRequest",
                "ShipBobInventoryItem",
                "ShipBobProduct",
                "ShipBobWRO",
                "ShipBobOrder",
                "ShipBobFulfillmentCenter",
            )
        },
    ),
}

spec = importlib.util.spec_from_file_location(
    "shipbob_err_test", Path(__file__).with_name("main.py")
)
shipbob = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shipbob)


def mock_request(body):
    req = Mock()
    req.json = AsyncMock(return_value=body)
    return req


class ShipBobErrorSanitizationTests(unittest.TestCase):
    """Verify that network exceptions and unexpected tool errors return sanitized messages."""

    def test_shipbob_api_request_exception_sanitized(self):
        with patch.object(shipbob, "refresh_token_if_needed", return_value=None):
            with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer secret"}):
                with patch.object(shipbob.requests, "get", side_effect=RuntimeError("connection refused: 10.0.0.1")):
                    res = shipbob.make_shipbob_request("u1", "GET", "/test")
                    self.assertEqual(res, {"error": "API request failed"})
                    self.assertNotIn("10.0.0.1", str(res))

    def test_auth_callback_exception_sanitized(self):
        req = Mock()
        with patch.object(shipbob, "get_oauth_state", return_value="u1:secret"):
            with patch.object(shipbob.requests, "post", side_effect=RuntimeError("db connection failed: postgresql://secret")):
                res = asyncio.run(shipbob.handle_shipbob_callback(req, code="code", state="u1:secret"))
                self.assertEqual(res.template.name, "setup.html")
                self.assertEqual(res.context.get("error"), "Failed to exchange authorization code")
                self.assertNotIn("postgresql", str(res.context))

    def test_tool_get_inventory_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "get_inventory", side_effect=RuntimeError("internal crash in inventory parsing")):
                res = asyncio.run(shipbob.tool_get_inventory(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get inventory")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_products_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "get_products", side_effect=RuntimeError("internal crash in products parsing")):
                res = asyncio.run(shipbob.tool_get_products(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get products")
                self.assertNotIn("internal crash", res.error)

    def test_tool_create_wro_exception_sanitized(self):
        req = mock_request({"uid": "u1", "product_name": "Widget", "quantity": 10})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "get_products", side_effect=RuntimeError("internal crash in WRO creation")):
                res = asyncio.run(shipbob.tool_create_wro(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to create WRO")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_wros_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "make_shipbob_request", side_effect=RuntimeError("internal crash in WRO listing")):
                res = asyncio.run(shipbob.tool_get_wros(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get WROs")
                self.assertNotIn("internal crash", res.error)

    def test_tool_cancel_wro_exception_sanitized(self):
        req = mock_request({"uid": "u1", "wro_id": "123"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "make_shipbob_request", side_effect=RuntimeError("internal crash in WRO cancellation")):
                res = asyncio.run(shipbob.tool_cancel_wro(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to cancel WRO")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_orders_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "make_shipbob_request", side_effect=RuntimeError("internal crash in orders listing")):
                res = asyncio.run(shipbob.tool_get_orders(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get orders")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_fulfillment_centers_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer token"}):
            with patch.object(shipbob, "get_fulfillment_centers", side_effect=RuntimeError("internal crash in FC listing")):
                res = asyncio.run(shipbob.tool_get_fulfillment_centers(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get fulfillment centers")
                self.assertNotIn("internal crash", res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)

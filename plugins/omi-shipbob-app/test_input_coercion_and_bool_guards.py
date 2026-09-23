"""Hermetic regression tests for ShipBob chat tool input coercion and boolean guards.

Tests:
1. _clean_str returns empty string for booleans and None
2. _coerce_int_bounds returns default for booleans rather than clamping 0 to 1
3. tool_create_wro rejects boolean quantity and fulfillment_center_id
4. tool_create_wro and tool_get_inventory reject boolean uid and product_name
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


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


stubs = {
    "requests": module("requests", RequestException=OSError),
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
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
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
            )
        },
    ),
}

spec = importlib.util.spec_from_file_location(
    "shipbob_under_test", Path(__file__).with_name("main.py")
)
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(main)


class DummyRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class ShipBobCoercionAndBoolGuardTests(unittest.TestCase):
    def test_clean_str_booleans_and_none(self):
        self.assertEqual(main._clean_str(False), "")
        self.assertEqual(main._clean_str(True), "")
        self.assertEqual(main._clean_str(None), "")
        self.assertEqual(main._clean_str("  valid_id  "), "valid_id")

    def test_coerce_int_bounds_booleans(self):
        # Must return default 10 instead of clamping 0 to 1
        self.assertEqual(main._coerce_int_bounds(False, default=10, min_val=1, max_val=100), 10)
        self.assertEqual(main._coerce_int_bounds(True, default=10, min_val=1, max_val=100), 10)
        self.assertEqual(main._coerce_int_bounds(None, default=10, min_val=1, max_val=100), 10)

    def test_coerce_int_bounds_values(self):
        self.assertEqual(main._coerce_int_bounds(0, default=10, min_val=1, max_val=100), 1)
        self.assertEqual(main._coerce_int_bounds(25, default=10, min_val=1, max_val=100), 25)
        self.assertEqual(main._coerce_int_bounds(150, default=10, min_val=1, max_val=100), 100)
        self.assertEqual(main._coerce_int_bounds("30", default=10, min_val=1, max_val=100), 30)

    def test_tool_create_wro_boolean_quantity_rejected(self):
        # True must not be accepted as ordering 1 unit
        req_true = DummyRequest({"uid": "user123", "product_name": "Widget", "quantity": True})
        resp_true = asyncio.run(main.tool_create_wro(req_true))
        self.assertEqual(resp_true.error, "Quantity must be a valid positive integer")

        req_false = DummyRequest({"uid": "user123", "product_name": "Widget", "quantity": False})
        resp_false = asyncio.run(main.tool_create_wro(req_false))
        self.assertEqual(resp_false.error, "Quantity must be a valid positive integer")

    def test_tool_create_wro_boolean_fc_id_rejected(self):
        req_fc = DummyRequest({
            "uid": "user123",
            "product_name": "Widget",
            "quantity": 5,
            "fulfillment_center_id": True,
        })
        resp_fc = asyncio.run(main.tool_create_wro(req_fc))
        self.assertEqual(resp_fc.error, "fulfillment_center_id must be a valid integer")

    def test_tool_create_wro_boolean_uid_rejected(self):
        req = DummyRequest({"uid": False, "product_name": "Widget", "quantity": 5})
        resp = asyncio.run(main.tool_create_wro(req))
        self.assertEqual(resp.error, "User ID is required")

    def test_tool_create_wro_boolean_product_name_rejected(self):
        req = DummyRequest({"uid": "user123", "product_name": False, "quantity": 5})
        resp = asyncio.run(main.tool_create_wro(req))
        self.assertEqual(resp.error, "Product name is required")

    def test_tool_get_inventory_boolean_uid_rejected(self):
        req = DummyRequest({"uid": False})
        resp = asyncio.run(main.tool_get_inventory(req))
        self.assertEqual(resp.error, "User ID is required")


if __name__ == "__main__":
    unittest.main()

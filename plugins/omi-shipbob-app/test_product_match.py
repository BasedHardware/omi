"""Hermetic regression: a product name must resolve to exactly one product before a
warehouse receiving order is created, and inventory answers must be about the
product the user named.

search_product_by_name and search_inventory_by_name returned the first item whose
name contained the request or was contained by it. With products "Blue Mug" and
"Blue Mug Set of 4" in ShipBob order, "create a WRO for 40 Blue Mug Set of 4" hit
"Blue Mug" first (its name is contained in the request) and created the receiving
order against the wrong SKU, reporting success. get_inventory answered for the
wrong item the same way.

Framework, HTTP and storage are stand ins; the production handlers run as is.

Run: python3 plugins/omi-shipbob-app/test_product_match.py
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
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
    "requests": module("requests", get=Mock(), post=Mock(), put=Mock(), request=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, HTTPException=Exception, Request=Framework, Query=Framework),
    "fastapi.responses": module(
        "fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework
    ),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "models": module("models", ChatToolResponse=Response),
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
}
spec = importlib.util.spec_from_file_location("shipbob_under_test", Path(__file__).with_name("main.py"))
shipbob = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shipbob)

PRODUCTS = [
    {"id": 1, "name": "Blue Mug", "sku": "MUG-B", "fulfillable_inventory_items": [{"id": 11}]},
    {"id": 2, "name": "Blue Mug Set of 4", "sku": "MUG-B4", "fulfillable_inventory_items": [{"id": 12}]},
    {"id": 3, "name": "Red Mug", "sku": "MUG-R", "fulfillable_inventory_items": [{"id": 13}]},
]
HEADERS = {"Authorization": "Bearer t"}


def request(body):
    return Mock(json=AsyncMock(return_value=body))


class CreateWroResolvesOneProduct(unittest.TestCase):
    def create(self, product_name):
        body = {"uid": "u1", "product_name": product_name, "quantity": 40, "fulfillment_center_id": 7}
        with (
            patch.object(shipbob, "get_shipbob_headers", return_value=HEADERS),
            patch.object(shipbob, "get_products", return_value=PRODUCTS),
            patch.object(shipbob, "make_shipbob_request", return_value={"id": 900, "status": "Awaiting"}) as api,
            patch.object(shipbob, "log"),
        ):
            result = asyncio.run(shipbob.tool_create_wro(request(body)))
        return result, api

    def test_exact_name_wins_over_a_containing_name_that_comes_first(self):
        result, api = self.create("Blue Mug Set of 4")
        api.assert_called_once()
        box_items = api.call_args.kwargs["data"]["boxes"][0]["box_items"]
        self.assertEqual(box_items, [{"inventory_id": 12, "quantity": 40}])
        self.assertIn("Blue Mug Set of 4", result.result)

    def test_ambiguous_name_creates_nothing_and_lists_candidates(self):
        result, api = self.create("mug")
        api.assert_not_called()
        self.assertIsNone(result.result)
        self.assertIn("More than one product matches 'mug'", result.error)
        for sku in ("MUG-B", "MUG-B4", "MUG-R"):
            self.assertIn(sku, result.error)

    def test_single_partial_match_is_used(self):
        result, api = self.create("red")
        api.assert_called_once()
        self.assertEqual(api.call_args.kwargs["data"]["boxes"][0]["box_items"][0]["inventory_id"], 13)

    def test_unknown_name_is_reported(self):
        result, api = self.create("green bowl")
        api.assert_not_called()
        self.assertIn("Could not find product", result.error)


class InventoryAnswersForTheNamedItem(unittest.TestCase):
    def test_ambiguous_inventory_name_is_refused(self):
        inventory = [
            {"id": 11, "name": "Blue Mug", "sku": "MUG-B", "fulfillable_quantity": 5},
            {"id": 12, "name": "Blue Mug Set of 4", "sku": "MUG-B4", "fulfillable_quantity": 9},
        ]
        with (
            patch.object(shipbob, "get_shipbob_headers", return_value=HEADERS),
            patch.object(shipbob, "get_inventory", return_value=inventory),
            patch.object(shipbob, "log"),
        ):
            ambiguous = asyncio.run(shipbob.tool_get_inventory(request({"uid": "u1", "product_name": "blue mug set"})))
            exact = asyncio.run(shipbob.tool_get_inventory(request({"uid": "u1", "product_name": "blue mug"})))
        self.assertIsNone(ambiguous.result)
        self.assertIn("MUG-B4", ambiguous.error)
        self.assertIn("MUG-B,", ambiguous.error)
        self.assertIn("**SKU:** MUG-B\n", exact.result)


if __name__ == "__main__":
    unittest.main()

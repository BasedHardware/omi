"""Hermetic regression for ShipBob name matching (#13997).

search_product_by_name returns the first product whose name contains the
request or is contained by it. With "Blue Mug" and "Blue Mug Set of 4"
listed, "create a WRO for 40 Blue Mug Set of 4" matches "Blue Mug"
first, the receiving order is posted for that inventory id, and the tool
answers "WRO Created Successfully" naming the wrong product.
search_inventory_by_name uses the same rule, so get_inventory for a
named product can report another item's counts.

Required behavior after the fix: exact name first, else a single
partial match; ambiguous names return the candidates with SKU and id
and nothing is posted.

No live ShipBob, FastAPI routing, or Pydantic serialization is tested.
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
            name: Framework for name in ("FastAPI", "HTTPException", "Request", "Query")
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
    "models": module("models", ChatToolResponse=Response),
}
spec = importlib.util.spec_from_file_location(
    "shipbob_under_test", Path(__file__).with_name("main.py")
)
shipbob = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shipbob)


PRODUCTS = [
    {
        "id": 10,
        "name": "Blue Mug",
        "sku": "MUG-1",
        "fulfillable_inventory_items": [{"id": 11}],
    },
    {
        "id": 12,
        "name": "Blue Mug Set of 4",
        "sku": "MUG-4",
        "fulfillable_inventory_items": [{"id": 13}],
    },
]

INVENTORY = [
    {"id": 11, "name": "Blue Mug", "sku": "MUG-1", "fulfillable_quantity": 7},
    {"id": 13, "name": "Blue Mug Set of 4", "sku": "MUG-4", "fulfillable_quantity": 2},
]


class CreateWroDisambiguationTests(unittest.TestCase):
    def setUp(self):
        self.posted = []

    def fake_request(self, uid, method, endpoint, params=None, data=None):
        if method == "POST" and endpoint == "/2.0/receiving":
            self.posted.append(data)
            return {"id": 99, "status": "open"}
        return {"error": f"unexpected {method} {endpoint}"}

    def patches(self):
        return [
            patch.object(
                shipbob,
                "get_shipbob_headers",
                return_value={"Authorization": "Bearer t"},
            ),
            patch.object(shipbob, "get_products", return_value=PRODUCTS),
            patch.object(shipbob, "get_inventory", return_value=INVENTORY),
            patch.object(shipbob, "get_fulfillment_centers", return_value=[{"id": 5}]),
            patch.object(
                shipbob, "make_shipbob_request", side_effect=self.fake_request
            ),
        ]

    def invoke_wro(self, product_name, quantity=40):
        request = Mock(
            json=AsyncMock(
                return_value={
                    "uid": "u1",
                    "product_name": product_name,
                    "quantity": quantity,
                }
            )
        )
        patches = self.patches()
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return asyncio.run(shipbob.tool_create_wro(request))

    def invoke_inventory(self, product_name):
        request = Mock(
            json=AsyncMock(
                return_value={
                    "uid": "u1",
                    "product_name": product_name,
                }
            )
        )
        patches = self.patches()
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return asyncio.run(shipbob.tool_get_inventory(request))

    def wro_inventory_id(self):
        return self.posted[0]["boxes"][0]["box_items"][0]["inventory_id"]

    def test_exact_longer_name_uses_correct_inventory(self):
        result = self.invoke_wro("Blue Mug Set of 4")
        self.assertIsNone(result.error)
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.wro_inventory_id(), 13)

    def test_exact_shorter_name_uses_correct_inventory(self):
        result = self.invoke_wro("Blue Mug")
        self.assertIsNone(result.error)
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.wro_inventory_id(), 11)

    def test_ambiguous_name_posts_nothing_and_lists_candidates(self):
        result = self.invoke_wro("mug")
        self.assertEqual(self.posted, [], "ambiguous 'mug' must not post any WRO")
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("blue mug", text)
        self.assertIn("blue mug set of 4", text)
        self.assertNotIn("wro created successfully", text)

    def test_unknown_product_posts_nothing(self):
        result = self.invoke_wro("Red Plate")
        self.assertEqual(self.posted, [])
        text = ((result.error or "") + "\n" + (result.result or "")).lower()
        self.assertIn("find", text)

    def test_single_partial_match_reports_named_item(self):
        result = self.invoke_inventory("set of 4")
        self.assertIsNone(result.error)
        # "set of 4" is a partial of only "Blue Mug Set of 4".
        self.assertIn("Blue Mug Set of 4", result.result or "")

    def test_partial_matching_two_items_lists_candidates(self):
        # "blue mug set" partially matches both items, so it is ambiguous.
        result = self.invoke_inventory("blue mug set")
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("blue mug", text)
        self.assertIn("blue mug set of 4", text)

    def test_get_inventory_ambiguous_lists_candidates(self):
        result = self.invoke_inventory("mug")
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("blue mug", text)
        self.assertIn("blue mug set of 4", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

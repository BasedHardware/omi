#!/usr/bin/env python3
"""
Unit tests for omi-shipbob-app.
Covers helper guards, input coercion, Pydantic models, and chat tool endpoints.
"""

import sys
import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

# Ensure plugin and sdk directories are on path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

SDK_DIR = os.path.abspath(os.path.join(APP_DIR, "..", "omi-plugin-sdk", "src"))
if os.path.exists(SDK_DIR) and SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

try:
    import omi_plugin_sdk
except ImportError:
    from unittest.mock import MagicMock

    sys.modules["omi_plugin_sdk"] = MagicMock()
    sys.modules["omi_plugin_sdk.models"] = MagicMock()

import models
import main


class DummyRequest:
    """Mock FastAPI Request object with async json() method."""

    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def run_async(coro):
    """Helper to run coroutines synchronously in tests."""
    return asyncio.run(coro)


class TestHelperFunctions(unittest.TestCase):
    """Tests for defensive helper functions."""

    def test_safe_dict(self):
        self.assertEqual(main._safe_dict({"a": 1}), {"a": 1})
        self.assertEqual(main._safe_dict(None), {})
        self.assertEqual(main._safe_dict("not a dict"), {})
        self.assertEqual(main._safe_dict([1, 2, 3]), {})
        self.assertEqual(main._safe_dict(123), {})

    def test_clean_str(self):
        self.assertEqual(main._clean_str("  hello world  "), "hello world")
        self.assertEqual(main._clean_str(None), "")
        self.assertEqual(main._clean_str(123), "123")
        self.assertEqual(main._clean_str(""), "")

    def test_clean_id(self):
        self.assertEqual(main._clean_id("#12345"), "12345")
        self.assertEqual(main._clean_id("  #999  "), "999")
        self.assertEqual(main._clean_id("888"), "888")
        self.assertEqual(main._clean_id(None), "")
        self.assertEqual(main._clean_id("###777"), "777")

    def test_coerce_int_bounds(self):
        # Default fallback
        self.assertEqual(main._coerce_int_bounds(None, default=10), 10)
        self.assertEqual(main._coerce_int_bounds("invalid", default=10), 10)
        self.assertEqual(main._coerce_int_bounds([], default=10), 10)

        # String integer coercion
        self.assertEqual(main._coerce_int_bounds("25"), 25)
        self.assertEqual(main._coerce_int_bounds(25), 25)

        # Bounds clamping
        self.assertEqual(main._coerce_int_bounds(0, min_val=1, max_val=100), 1)
        self.assertEqual(main._coerce_int_bounds(-10, min_val=1, max_val=100), 1)
        self.assertEqual(main._coerce_int_bounds(500, min_val=1, max_val=100), 100)

    def test_safe_body(self):
        # From dictionary directly
        self.assertEqual(run_async(main._safe_body({"key": "value"})), {"key": "value"})

        # From request object with valid json
        req = DummyRequest({"uid": "user1"})
        self.assertEqual(run_async(main._safe_body(req)), {"uid": "user1"})

        # From request throwing error on json()
        err_req = DummyRequest(ValueError("invalid json"))
        self.assertEqual(run_async(main._safe_body(err_req)), {})

        # From non-dict, non-request object
        self.assertEqual(run_async(main._safe_body(None)), {})


class TestDisambiguationAndMatching(unittest.TestCase):
    """Tests for name candidate matching and formatting."""

    def test_match_name_candidates_exact(self):
        items = [
            {"name": "Blue Widget", "id": 1},
            {"name": "Red Widget", "id": 2},
        ]
        exact, partial = main.match_name_candidates(items, "blue widget")
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["id"], 1)
        self.assertEqual(partial, [])

    def test_match_name_candidates_partial(self):
        items = [
            {"name": "Blue Widget Pro", "id": 1},
            {"name": "Red Gadget", "id": 2},
        ]
        exact, partial = main.match_name_candidates(items, "Widget")
        self.assertEqual(exact, [])
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0]["id"], 1)

    def test_match_name_candidates_guards(self):
        # Empty inputs
        self.assertEqual(main.match_name_candidates([], "widget"), ([], []))
        self.assertEqual(main.match_name_candidates(None, "widget"), ([], []))
        self.assertEqual(main.match_name_candidates([{"name": "A"}], ""), ([], []))

        # Non-dict items in list should not cause AttributeError
        items = [None, "non-dict", {"name": "Widget"}]
        exact, partial = main.match_name_candidates(items, "widget")
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["name"], "Widget")

    def test_format_name_candidates(self):
        candidates = [
            {"name": "Item A", "sku": "SKU-A", "id": 101},
            None,  # should be guarded
            {"name": "Item B"},  # missing sku & id
        ]
        res = main.format_name_candidates(candidates, what="product")
        self.assertIn("Multiple products match", res)
        self.assertIn("Item A", res)
        self.assertIn("SKU: SKU-A", res)
        self.assertIn("id: 101", res)
        self.assertIn("Item B", res)
        self.assertIn("SKU: N/A", res)


class TestPydanticModels(unittest.TestCase):
    """Tests for Pydantic request models."""

    def test_get_inventory_request(self):
        req = models.GetInventoryRequest(uid="user123")
        self.assertEqual(req.uid, "user123")
        self.assertEqual(req.limit, 10)
        self.assertIsNone(req.product_name)

        req2 = models.GetInventoryRequest(uid="u2", product_name="Hat", limit=5)
        self.assertEqual(req2.product_name, "Hat")
        self.assertEqual(req2.limit, 5)

    def test_get_products_request(self):
        req = models.GetProductsRequest(uid="u1", search="Shirt")
        self.assertEqual(req.uid, "u1")
        self.assertEqual(req.search, "Shirt")
        self.assertEqual(req.limit, 10)

    def test_create_wro_request(self):
        req = models.CreateWroRequest(uid="u1", product_name="Mug", quantity=50)
        self.assertEqual(req.uid, "u1")
        self.assertEqual(req.product_name, "Mug")
        self.assertEqual(req.quantity, 50)
        self.assertEqual(req.packaging_type, "EverythingInOneBox")
        self.assertEqual(req.package_type, "Package")

    def test_get_wros_request(self):
        req = models.GetWrosRequest(uid="u1", status="Completed")
        self.assertEqual(req.status, "Completed")
        self.assertEqual(req.limit, 10)

    def test_cancel_wro_request(self):
        req = models.CancelWroRequest(uid="u1", wro_id="12345")
        self.assertEqual(req.wro_id, "12345")

    def test_get_orders_request(self):
        req = models.GetOrdersRequest(uid="u1", limit=20)
        self.assertEqual(req.limit, 20)

    def test_get_fulfillment_centers_request(self):
        req = models.GetFulfillmentCentersRequest(uid="u1")
        self.assertEqual(req.uid, "u1")


class TestSelectChannel(unittest.TestCase):
    """Tests for /select-channel endpoint."""

    @patch("main.update_shipbob_channel")
    def test_select_channel_success(self, mock_update):
        req = DummyRequest({"uid": "user1", "channel_id": "1234"})
        res = run_async(main.select_channel(req))
        self.assertEqual(res, {"success": True})
        mock_update.assert_called_once_with("user1", 1234)

    def test_select_channel_missing_uid(self):
        req = DummyRequest({"channel_id": "1234"})
        with self.assertRaises(HTTPException) as ctx:
            run_async(main.select_channel(req))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_select_channel_invalid_channel_id(self):
        req = DummyRequest({"uid": "user1", "channel_id": "notanint"})
        with self.assertRaises(HTTPException) as ctx:
            run_async(main.select_channel(req))
        self.assertEqual(ctx.exception.status_code, 400)


class TestToolGetInventory(unittest.TestCase):
    """Tests for /tools/get_inventory endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_get_inventory(req))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_inventory")
    def test_get_all_inventory_success(self, mock_get_inv, mock_headers):
        mock_get_inv.return_value = [
            {"name": "Product A", "sku": "SKU-A", "fulfillable_quantity": 42},
            {"name": "Product B", "sku": "SKU-B", "total_fulfillable_quantity": 10},
        ]
        req = DummyRequest({"uid": "user1", "limit": "5"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIsNone(res.error)
        self.assertIn("Product A", res.result)
        self.assertIn("42 fulfillable", res.result)
        self.assertIn("Product B", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_inventory", return_value=[])
    def test_get_all_inventory_empty(self, mock_get_inv, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIsNone(res.error)
        self.assertIn("No inventory items found", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_inventory_candidates")
    def test_get_inventory_single_product_hit(self, mock_find, mock_headers):
        mock_find.return_value = [
            {
                "name": "Super Mug",
                "sku": "MUG-1",
                "fulfillable_quantity": 100,
                "onhand_quantity": 120,
                "committed_quantity": 20,
                "awaiting_quantity": 0,
            }
        ]
        req = DummyRequest({"uid": "user1", "product_name": "Super Mug"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIsNone(res.error)
        self.assertIn("Inventory for: Super Mug", res.result)
        self.assertIn("Fulfillable Quantity:** 100", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_inventory_candidates")
    def test_get_inventory_ambiguous_product(self, mock_find, mock_headers):
        mock_find.return_value = [
            {"name": "Mug White", "sku": "MUG-W", "id": 1},
            {"name": "Mug Black", "sku": "MUG-B", "id": 2},
        ]
        req = DummyRequest({"uid": "user1", "product_name": "Mug"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIsNone(res.error)
        self.assertIn("Multiple inventory items match", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_inventory_candidates", return_value=[])
    def test_get_inventory_product_not_found(self, mock_find, mock_headers):
        req = DummyRequest({"uid": "user1", "product_name": "Nonexistent"})
        res = run_async(main.tool_get_inventory(req))
        self.assertIn("Could not find inventory item 'Nonexistent'", res.error)


class TestToolGetProducts(unittest.TestCase):
    """Tests for /tools/get_products endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_get_products(req))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_products(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_products")
    def test_get_products_with_search_and_string_limit(self, mock_get_prod, mock_headers):
        mock_get_prod.return_value = [
            {"name": "Red T-Shirt", "sku": "TSH-RED", "reference_id": "REF1"},
            {"name": "Blue Jeans", "sku": "JNS-BLU"},
            None,  # non-dict item guard
        ]
        req = DummyRequest({"uid": "user1", "search": "shirt", "limit": "5"})
        res = run_async(main.tool_get_products(req))
        self.assertIsNone(res.error)
        self.assertIn("Products (1)", res.result)
        self.assertIn("Red T-Shirt", res.result)
        self.assertIn("[Ref: REF1]", res.result)
        self.assertNotIn("Jeans", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_products", return_value=[])
    def test_get_products_empty(self, mock_get_prod, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_products(req))
        self.assertIsNone(res.error)
        self.assertIn("No products found", res.result)


class TestToolCreateWro(unittest.TestCase):
    """Tests for /tools/create_wro endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_create_wro(req))
        self.assertEqual(res.error, "User ID is required")

    def test_missing_product_name(self):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_create_wro(req))
        self.assertEqual(res.error, "Product name is required")

    def test_invalid_quantity(self):
        # Non-numeric quantity
        req = DummyRequest({"uid": "user1", "product_name": "Hat", "quantity": "five"})
        res = run_async(main.tool_create_wro(req))
        self.assertIn("Quantity must be a valid positive integer", res.error)

        # Zero quantity
        req2 = DummyRequest({"uid": "user1", "product_name": "Hat", "quantity": 0})
        res2 = run_async(main.tool_create_wro(req2))
        self.assertIn("Quantity must be greater than zero", res2.error)

        # Negative quantity
        req3 = DummyRequest({"uid": "user1", "product_name": "Hat", "quantity": -5})
        res3 = run_async(main.tool_create_wro(req3))
        self.assertIn("Quantity must be greater than zero", res3.error)

    def test_invalid_fc_id(self):
        req = DummyRequest(
            {"uid": "user1", "product_name": "Hat", "quantity": 10, "fulfillment_center_id": "invalid_fc"}
        )
        res = run_async(main.tool_create_wro(req))
        self.assertIn("fulfillment_center_id must be a valid integer", res.error)

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1", "product_name": "Hat", "quantity": 10})
        res = run_async(main.tool_create_wro(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_product_candidates")
    def test_ambiguous_product(self, mock_candidates, mock_headers):
        mock_candidates.return_value = [
            {"name": "Hat Red", "sku": "HAT-R", "id": 1},
            {"name": "Hat Blue", "sku": "HAT-B", "id": 2},
        ]
        req = DummyRequest({"uid": "user1", "product_name": "Hat", "quantity": 10})
        res = run_async(main.tool_create_wro(req))
        self.assertIsNone(res.error)
        self.assertIn("Multiple products match", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_product_candidates", return_value=[])
    def test_product_not_found(self, mock_candidates, mock_headers):
        req = DummyRequest({"uid": "user1", "product_name": "Ghost", "quantity": 10})
        res = run_async(main.tool_create_wro(req))
        self.assertIn("Could not find product 'Ghost'", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_product_candidates")
    @patch("main.get_inventory", return_value=[])
    def test_no_inventory_id(self, mock_inv, mock_candidates, mock_headers):
        mock_candidates.return_value = [{"name": "Item", "id": 10}]
        req = DummyRequest({"uid": "user1", "product_name": "Item", "quantity": 10})
        res = run_async(main.tool_create_wro(req))
        self.assertIn("Could not find inventory ID", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_product_candidates")
    @patch("main.get_fulfillment_centers", return_value=[])
    def test_no_fulfillment_centers(self, mock_fcs, mock_candidates, mock_headers):
        mock_candidates.return_value = [{"name": "Item", "fulfillable_inventory_items": [{"id": 999}]}]
        req = DummyRequest({"uid": "user1", "product_name": "Item", "quantity": 10})
        res = run_async(main.tool_create_wro(req))
        self.assertIn("No fulfillment centers available", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.find_product_candidates")
    @patch("main.get_fulfillment_centers")
    @patch("main.make_shipbob_request")
    def test_create_wro_success(self, mock_shipbob, mock_fcs, mock_candidates, mock_headers):
        mock_candidates.return_value = [{"name": "T-Shirt", "fulfillable_inventory_items": [{"id": 555}]}]
        mock_fcs.return_value = [{"id": 42, "name": "Dallas FC"}]
        mock_shipbob.return_value = {
            "id": "WRO-9999",
            "status": "AwaitingArrival",
            "box_labels_uri": "https://shipbob.com/labels/9999.pdf",
        }

        req = DummyRequest(
            {"uid": "user1", "product_name": "T-Shirt", "quantity": "20", "purchase_order_number": "PO-1234"}
        )
        res = run_async(main.tool_create_wro(req))
        self.assertIsNone(res.error)
        self.assertIn("WRO Created Successfully!", res.result)
        self.assertIn("WRO ID:** WRO-9999", res.result)
        self.assertIn("PO Number:** PO-1234", res.result)
        self.assertIn("Box Labels:** https://shipbob.com/labels/9999.pdf", res.result)


class TestToolGetWros(unittest.TestCase):
    """Tests for /tools/get_wros endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_get_wros(req))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_wros(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.make_shipbob_request")
    def test_get_wros_success_with_null_dates(self, mock_req, mock_headers):
        mock_req.return_value = [
            {
                "id": 101,
                "status": "Completed",
                "purchase_order_number": "PO-1",
                "expected_arrival_date": "2026-09-20T10:00:00Z",
            },
            {"id": 102, "status": "AwaitingArrival", "expected_arrival_date": None},  # Null date guard
            None,  # Non-dict guard
        ]
        req = DummyRequest({"uid": "user1", "limit": "10"})
        res = run_async(main.tool_get_wros(req))
        self.assertIsNone(res.error)
        self.assertIn("WRO #101", res.result)
        self.assertIn("2026-09-20", res.result)
        self.assertIn("WRO #102", res.result)
        self.assertIn("Expected: N/A", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.make_shipbob_request", return_value=[])
    def test_get_wros_empty(self, mock_req, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_wros(req))
        self.assertIsNone(res.error)
        self.assertIn("No WROs found", res.result)


class TestToolCancelWro(unittest.TestCase):
    """Tests for /tools/cancel_wro endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_cancel_wro(req))
        self.assertEqual(res.error, "User ID is required")

    def test_missing_wro_id(self):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_cancel_wro(req))
        self.assertEqual(res.error, "WRO ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1", "wro_id": "123"})
        res = run_async(main.tool_cancel_wro(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.make_shipbob_request")
    def test_cancel_wro_strips_hash_and_succeeds(self, mock_req, mock_headers):
        mock_req.return_value = {"success": True}
        req = DummyRequest({"uid": "user1", "wro_id": " #12345 "})
        res = run_async(main.tool_cancel_wro(req))
        self.assertIsNone(res.error)
        self.assertIn("WRO #12345 has been cancelled", res.result)
        mock_req.assert_called_once_with("user1", "POST", "/2.0/receiving/12345/cancel")

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.make_shipbob_request")
    def test_cancel_wro_api_error(self, mock_req, mock_headers):
        mock_req.return_value = {"error": "Cannot cancel completed WRO"}
        req = DummyRequest({"uid": "user1", "wro_id": "12345"})
        res = run_async(main.tool_cancel_wro(req))
        self.assertIn("Cannot cancel completed WRO", res.error)


class FakeResp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


def _headers_ok():
    return {"Authorization": "Bearer t", "Content-Type": "application/json"}


class TestCancelWroRegression13183(unittest.TestCase):
    """Regression tests for cancel_wro error classification (#13183)."""

    def setUp(self):
        from fastapi.testclient import TestClient

        self.client = TestClient(main.app)

    @patch("main.get_shipbob_headers", return_value=_headers_ok())
    @patch("main.refresh_token_if_needed")
    @patch("main.requests.post")
    def test_cancel_empty_body_500_is_error(self, mock_post, _refresh, _headers):
        mock_post.return_value = FakeResp(status_code=500, text="")
        resp = self.client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body.get("error"))
        self.assertNotIn("cancelled", str(body.get("result") or "").lower())

    @patch("main.get_shipbob_headers", return_value=_headers_ok())
    @patch("main.refresh_token_if_needed")
    @patch("main.make_shipbob_request", return_value=None)
    def test_cancel_none_result_is_error(self, mock_req, _refresh, _headers):
        resp = self.client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
        body = resp.json()
        self.assertTrue(body.get("error"))

    @patch("main.get_shipbob_headers", return_value=_headers_ok())
    @patch("main.refresh_token_if_needed")
    @patch("main.make_shipbob_request", return_value={"error": "forbidden", "status_code": 403})
    def test_cancel_nonempty_error_is_surfaced(self, mock_req, _refresh, _headers):
        resp = self.client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
        body = resp.json()
        self.assertIn("forbidden", body.get("error", ""))

    @patch("main.get_shipbob_headers", return_value=_headers_ok())
    @patch("main.refresh_token_if_needed")
    @patch("main.make_shipbob_request", return_value={"id": 123, "status": "cancelled"})
    def test_cancel_success_200_object(self, mock_req, _refresh, _headers):
        resp = self.client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
        body = resp.json()
        self.assertIn(body.get("error"), (None, ""))
        self.assertIn("cancelled", (body.get("result") or "").lower())


class TestToolGetOrders(unittest.TestCase):
    """Tests for /tools/get_orders endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_get_orders(req))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_orders(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_shipbob_tokens", return_value=None)
    @patch("main.make_shipbob_request")
    def test_get_orders_success(self, mock_req, mock_tokens, mock_headers):
        mock_req.return_value = [
            {"id": "ord_1", "order_number": "ORD-1001", "status": "Shipped", "created_date": "2026-09-15T12:00:00Z"},
            {"id": "ord_2", "status": "Processing", "created_date": None},  # Null date guard
            None,  # Non-dict guard
        ]
        req = DummyRequest({"uid": "user1", "limit": "5"})
        res = run_async(main.tool_get_orders(req))
        self.assertIsNone(res.error)
        self.assertIn("Order #ORD-1001", res.result)
        self.assertIn("Shipped", res.result)
        self.assertIn("Order #ord_2", res.result)
        self.assertIn("Processing (N/A)", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_shipbob_tokens", return_value=None)
    @patch("main.make_shipbob_request", return_value=[])
    def test_get_orders_empty(self, mock_req, mock_tokens, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_orders(req))
        self.assertIsNone(res.error)
        self.assertIn("No orders found", res.result)


class TestToolGetFulfillmentCenters(unittest.TestCase):
    """Tests for /tools/get_fulfillment_centers endpoint."""

    def test_missing_uid(self):
        req = DummyRequest({})
        res = run_async(main.tool_get_fulfillment_centers(req))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_shipbob_headers", return_value=None)
    def test_unauthenticated(self, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_fulfillment_centers(req))
        self.assertIn("Please connect your ShipBob account", res.error)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_fulfillment_centers")
    def test_get_fulfillment_centers_success_with_null_address(self, mock_fcs, mock_headers):
        mock_fcs.return_value = [
            {"id": 1, "name": "Chicago FC", "address": {"city": "Chicago", "state": "IL"}},
            {"id": 2, "name": "Dallas FC", "address": None},  # Null address guard against AttributeError
            None,  # Non-dict guard
        ]
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_fulfillment_centers(req))
        self.assertIsNone(res.error)
        self.assertIn("Chicago FC", res.result)
        self.assertIn("Chicago, IL", res.result)
        self.assertIn("Dallas FC", res.result)

    @patch("main.get_shipbob_headers", return_value={"Authorization": "Bearer token"})
    @patch("main.get_fulfillment_centers", return_value=[])
    def test_get_fulfillment_centers_empty(self, mock_fcs, mock_headers):
        req = DummyRequest({"uid": "user1"})
        res = run_async(main.tool_get_fulfillment_centers(req))
        self.assertIsNone(res.error)
        self.assertIn("No fulfillment centers found", res.result)


if __name__ == "__main__":
    unittest.main()

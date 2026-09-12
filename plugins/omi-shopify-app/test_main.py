"""Exercise the full analytics handler with framework/storage/transport doubles.

No live Shopify calls, FastAPI routing or Pydantic serialization are tested.
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
    "fastapi": module("fastapi", **{name: Framework for name in
        ("FastAPI", "HTTPException", "Request", "Query", "Form")}),
    "fastapi.responses": module("fastapi.responses", **{name: Framework for name in
        ("HTMLResponse", "RedirectResponse", "JSONResponse")}),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "db": module("db", **{name: Mock() for name in
        ("store_shopify_tokens", "get_shopify_tokens", "delete_shopify_tokens",
         "store_default_store", "get_default_store", "get_user_settings")}),
    "models": module("models", **{name: Response for name in
        ("ChatToolResponse", "ShopifyOrder", "ShopifyCustomer", "ShopifyLineItem",
         "ShopifyAnalytics", "ShopifyShop")}),
}
spec = importlib.util.spec_from_file_location("shopify_under_test", Path(__file__).with_name("main.py"))
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


def page(start, count):
    return {"orders": [{"id": n, "subtotal_price": "10.00", "total_price": "10.00"}
                       for n in range(start, start + count)]}


class AnalyticsTests(unittest.TestCase):
    def invoke(self, pages):
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "period": "today"}))
        with patch.object(shopify, "get_shopify_tokens", return_value={"connected": True}), \
                patch.object(shopify, "shopify_api_request", side_effect=pages) as api:
            result = asyncio.run(shopify.tool_get_analytics(request))
        self.assertEqual(api.call_count, len(pages))
        return result

    def test_failure_on_any_order_page_is_not_partial_success(self):
        for failed_page in range(1, 5):
            with self.subTest(failed_page=failed_page):
                pages = [page(1 + i * 250, 250) for i in range(failed_page - 1)]
                result = self.invoke(pages + [{"error": "private provider detail"}])
                if failed_page == 1:
                    self.assertEqual(result.error, "Failed to get analytics: private provider detail")
                else:
                    self.assertEqual(result.error, "Failed to get complete analytics. Please try again.")
                    self.assertNotIn("private provider detail", result.error)
                self.assertIsNone(result.result)

    def test_successful_single_and_multiple_pages_keep_totals(self):
        for pages, count in [([page(1, 2)], 2), ([page(1, 250), page(251, 1)], 251),
                             ([page(1, 250), page(251, 0)], 250), ([page(1, 0)], 0)]:
            with self.subTest(count=count):
                result = self.invoke(pages)
                self.assertIsNone(result.error)
                self.assertIn(f"**Total Orders:** {count}", result.result)
                self.assertIn(f"**Total Collected:** ${count * 10:,.2f} USD", result.result)


if __name__ == "__main__":
    unittest.main(verbosity=2)

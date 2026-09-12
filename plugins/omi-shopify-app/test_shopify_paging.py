"""Regression tests for Shopify REST since_id pagination.

These tests drive the production helper through a fake request seam. A store
with more than 250 products or price rules used to be truncated at the first
page; that is the bug that would have been caught here.
"""
import unittest

from shopify_paging import SHOPIFY_MAX_PAGES, SHOPIFY_PAGE_SIZE, fetch_all_pages


def _page(resource_key, start, count):
    return {resource_key: [{"id": i, "title": f"item-{i}"} for i in range(start, start + count)]}


class FetchAllPagesTest(unittest.TestCase):
    def test_single_short_page(self):
        calls = []

        def request_fn(uid, method, endpoint, params=None):
            calls.append(params)
            return _page("products", 1, 3)

        result = fetch_all_pages(request_fn, "u1", "/products.json", "products")
        self.assertEqual(len(result["products"]), 3)
        self.assertEqual(result["page_count"], 1)
        self.assertFalse(result["capped"])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("since_id", calls[0])

    def test_walks_since_id_until_short_page(self):
        calls = []

        def request_fn(uid, method, endpoint, params=None):
            calls.append(dict(params or {}))
            since = (params or {}).get("since_id")
            if since is None:
                return _page("products", 1, SHOPIFY_PAGE_SIZE)
            if since == SHOPIFY_PAGE_SIZE:
                return _page("products", 251, SHOPIFY_PAGE_SIZE)
            if since == 500:
                return _page("products", 501, 10)
            self.fail(f"unexpected since_id {since}")

        result = fetch_all_pages(
            request_fn, "u1", "/products.json", "products", params={"status": "active"}
        )
        self.assertEqual(len(result["products"]), 510)
        self.assertEqual(result["page_count"], 3)
        self.assertFalse(result["capped"])
        self.assertEqual(calls[0]["status"], "active")
        self.assertEqual(calls[1]["since_id"], SHOPIFY_PAGE_SIZE)
        self.assertEqual(calls[2]["since_id"], 500)

    def test_first_page_error_is_returned_unchanged(self):
        def request_fn(uid, method, endpoint, params=None):
            return {"error": "User not authenticated with Shopify"}

        result = fetch_all_pages(request_fn, "u1", "/products.json", "products")
        self.assertEqual(result, {"error": "User not authenticated with Shopify"})

    def test_later_page_error_keeps_collected_records(self):
        def request_fn(uid, method, endpoint, params=None):
            if (params or {}).get("since_id"):
                return {"error": "timeout"}
            return _page("price_rules", 1, SHOPIFY_PAGE_SIZE)

        result = fetch_all_pages(request_fn, "u1", "/price_rules.json", "price_rules")
        self.assertEqual(len(result["price_rules"]), SHOPIFY_PAGE_SIZE)
        self.assertTrue(result["partial"])
        self.assertEqual(result["error"], "timeout")

    def test_cap_on_full_pages(self):
        def request_fn(uid, method, endpoint, params=None):
            since = (params or {}).get("since_id") or 0
            start = since + 1
            return _page("products", start, SHOPIFY_PAGE_SIZE)

        result = fetch_all_pages(
            request_fn, "u1", "/products.json", "products", max_pages=3
        )
        self.assertEqual(len(result["products"]), 3 * SHOPIFY_PAGE_SIZE)
        self.assertEqual(result["page_count"], 3)
        self.assertTrue(result["capped"])

    def test_default_cap_is_ten_pages(self):
        def request_fn(uid, method, endpoint, params=None):
            since = (params or {}).get("since_id") or 0
            return _page("products", since + 1, SHOPIFY_PAGE_SIZE)

        result = fetch_all_pages(request_fn, "u1", "/products.json", "products")
        self.assertEqual(result["page_count"], SHOPIFY_MAX_PAGES)
        self.assertTrue(result["capped"])
        self.assertEqual(len(result["products"]), SHOPIFY_MAX_PAGES * SHOPIFY_PAGE_SIZE)


if __name__ == "__main__":
    unittest.main()

"""Regression: malformed CoinGecko payloads must yield a tool error, not a crash.

The public CoinGecko API can answer with a JSON list where an object was
documented, with null/absent numeric fields, or with a bare string body (edge
cache or an upstream error page). Every parser here assumed dicts and floats,
so such a response raised an unhandled AttributeError/TypeError and the tool
returned a 500 instead of a readable error.

Drives the real FastAPI app with a recorded CoinGecko seam. No network.

Run: python3 plugins/omi-coingecko-crypto-app/test_malformed_payloads.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

ENVELOPE = {"uid": "user-1", "app_id": "app-1", "tool_name": "x"}


def payload_seam(payload):
    async def fetch(endpoint, params=None):
        return payload
    return fetch


class MalformedPayloadsDoNotCrash(unittest.TestCase):
    def setUp(self):
        self.stack = []
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def seam(self, payload):
        patcher = patch.object(main, "_fetch_coingecko", payload_seam(payload))
        patcher.start()
        self.stack.append(patcher)
        self.addCleanup(patcher.stop)

    def post(self, tool, body):
        return self.client.post(f"/tools/{tool}", json={**ENVELOPE, **body})

    def assert_clean_error(self, response):
        self.assertEqual(response.status_code, 200, response.text[:400])
        out = response.json()
        self.assertTrue(out.get("error") or out.get("result"), out)
        return out

    def test_price_endpoint_returning_list_does_not_crash(self):
        self.seam([])
        self.assert_clean_error(self.post("get_crypto_price", {"coin_ids": "bitcoin"}))

    def test_price_coin_entry_not_a_dict_does_not_crash(self):
        self.seam({"bitcoin": "rate limited"})
        self.assert_clean_error(self.post("get_crypto_price", {"coin_ids": "bitcoin"}))

    def test_price_numeric_fields_as_strings_are_coerced(self):
        self.seam({"bitcoin": {"usd": "100.5", "usd_24h_change": "1.25", "usd_market_cap": None, "usd_24h_vol": "3e8"}})
        out = self.assert_clean_error(self.post("get_crypto_price", {"coin_ids": "bitcoin"}))
        self.assertIsNone(out["error"], out)
        self.assertIn("$100.50", out["result"])

    def test_search_coins_not_a_list_does_not_crash(self):
        self.seam({"coins": "nope"})
        self.assert_clean_error(self.post("search_crypto_coins", {"query": "sol"}))

    def test_search_list_with_non_dict_entries_is_filtered(self):
        self.seam({"coins": ["junk", {"id": "solana", "name": "Solana", "symbol": "sol"}]})
        out = self.assert_clean_error(self.post("search_crypto_coins", {"query": "sol"}))
        self.assertIsNone(out["error"], out)
        self.assertIn("Solana", out["result"])

    def test_trending_boxed_items_missing_item_key_do_not_crash(self):
        self.seam({"coins": [{"item": "junk"}, {"item": {"id": "x", "name": "X", "symbol": "x"}}]})
        out = self.assert_clean_error(self.post("get_trending_crypto", {}))
        self.assertIsNone(out["error"], out)
        self.assertIn("X", out["result"])

    def test_trending_price_btc_as_string_does_not_crash(self):
        self.seam({"coins": [{"item": {"id": "x", "name": "X", "symbol": "x", "price_btc": "0.0001"}}]})
        self.assert_clean_error(self.post("get_trending_crypto", {}))

    def test_markets_dict_instead_of_list_does_not_crash(self):
        self.seam({"error": "rate limited"})
        self.assert_clean_error(self.post("get_crypto_market_overview", {}))

    def test_markets_list_with_string_entries_is_filtered(self):
        self.seam(["junk", {"id": "btc", "name": "Bitcoin", "symbol": "btc", "current_price": 1.5, "market_cap_rank": 1}])
        out = self.assert_clean_error(self.post("get_crypto_market_overview", {}))
        self.assertIsNone(out["error"], out)
        self.assertIn("Bitcoin", out["result"])


if __name__ == "__main__":
    unittest.main()

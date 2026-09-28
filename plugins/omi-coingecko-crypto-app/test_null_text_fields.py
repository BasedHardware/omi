"""Regression: a null text field must not lose the whole result list.

`dict.get(key, default)` does not apply its default when the key is present
and null, so `coin.get("symbol", "").upper()` raised AttributeError on an
explicit `"symbol": null`. The handler's broad `except Exception` turned that
into "Unexpected error searching crypto coins: 'NoneType' object has no
attribute 'upper'" — every other coin in the response was discarded and a
Python error string reached the user.

`get_top_cryptocurrencies` already used the safe idiom; search and trending
did not.

Drives the real FastAPI app with a recorded CoinGecko seam. No network.

Run: python3 plugins/omi-coingecko-crypto-app/test_null_text_fields.py
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


class AsTextHelper(unittest.TestCase):
    def test_passes_through_a_string(self):
        self.assertEqual(main._as_text("btc"), "btc")

    def test_null_takes_the_default(self):
        self.assertEqual(main._as_text(None), "")
        self.assertEqual(main._as_text(None, "Unknown"), "Unknown")

    def test_empty_string_takes_the_default(self):
        self.assertEqual(main._as_text("", "Unknown"), "Unknown")

    def test_numbers_render_rather_than_vanish(self):
        self.assertEqual(main._as_text(7), "7")

    def test_structures_and_booleans_take_the_default(self):
        for value in ([1], {"a": 1}, True, False):
            with self.subTest(value=value):
                self.assertEqual(main._as_text(value, "Unknown"), "Unknown")


class SearchWithNullFields(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_null_symbol_does_not_lose_the_result_list(self):
        payload = {
            "coins": [
                {"name": "Bitcoin", "symbol": None, "id": "bitcoin", "market_cap_rank": 1},
                {"name": "Ethereum", "symbol": "eth", "id": "ethereum", "market_cap_rank": 2},
            ]
        }
        with patch.object(main, "_fetch_coingecko", payload_seam(payload)):
            response = self.client.post(
                "/tools/search_crypto_coins", json={**ENVELOPE, "query": "coin"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body.get("error"), body)
        # Both coins survive, and no Python error text reaches the user.
        self.assertIn("Bitcoin", body["result"])
        self.assertIn("ETH", body["result"])
        self.assertNotIn("NoneType", body["result"])

    def test_null_name_and_id_render_as_placeholders(self):
        payload = {"coins": [{"name": None, "symbol": "btc", "id": None}]}
        with patch.object(main, "_fetch_coingecko", payload_seam(payload)):
            response = self.client.post(
                "/tools/search_crypto_coins", json={**ENVELOPE, "query": "coin"}
            )
        body = response.json()
        self.assertIsNone(body.get("error"), body)
        self.assertIn("Unknown", body["result"])
        self.assertNotIn("None", body["result"])


class TrendingWithNullFields(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_null_symbol_does_not_lose_the_trending_list(self):
        payload = {
            "coins": [
                {"item": {"name": "Bitcoin", "symbol": None, "id": "bitcoin"}},
                {"item": {"name": "Solana", "symbol": "sol", "id": "solana"}},
            ]
        }
        with patch.object(main, "_fetch_coingecko", payload_seam(payload)):
            response = self.client.post("/tools/get_trending_crypto", json={**ENVELOPE})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body.get("error"), body)
        self.assertIn("Bitcoin", body["result"])
        self.assertIn("SOL", body["result"])
        self.assertNotIn("NoneType", body["result"])


if __name__ == "__main__":
    unittest.main()

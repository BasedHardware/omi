"""Hermetic regression: optional tool parameters sent as JSON null must take
their defaults instead of failing validation.

The Omi backend builds every non-required manifest parameter as
Optional[...] with default None and, with the pinned langchain-core 1.3.3,
forwards those defaulted fields in the request body. So "what is the
bitcoin price?" reaches this app as {"coin_ids": "bitcoin",
"vs_currency": null}. The request models typed vs_currency, limit and
max_results as plain str/int, pydantic rejected the null, and every
ordinary call answered "invalid tool request: ... Input should be a valid
string/integer".

Drives the real FastAPI app with a recorded CoinGecko seam. No network.

Run: python3 plugins/omi-coingecko-crypto-app/test_null_optionals.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

ENVELOPE = {"uid": "user-1", "app_id": "app-1", "tool_name": "x"}


def fake_coingecko(recorded):
    async def fetch(endpoint, params=None):
        recorded.append((endpoint, dict(params or {})))
        if endpoint == "/simple/price":
            vs = params["vs_currencies"]
            return {
                cid: {vs: 100.0, f"{vs}_24h_change": 1.5, f"{vs}_market_cap": 2e9, f"{vs}_24h_vol": 3e8}
                for cid in params["ids"].split(",")
            }
        if endpoint == "/search":
            return {
                "coins": [
                    {"id": f"coin{i}", "name": f"Coin {i}", "symbol": f"c{i}", "market_cap_rank": i}
                    for i in range(1, 16)
                ]
            }
        if endpoint == "/search/trending":
            return {
                "coins": [
                    {
                        "item": {
                            "id": f"t{i}",
                            "name": f"Trend {i}",
                            "symbol": f"t{i}",
                            "market_cap_rank": i,
                            "data": {"price": 1.0, "price_change_percentage_24h": {"usd": 2.0}},
                        }
                    }
                    for i in range(1, 16)
                ]
            }
        if endpoint == "/coins/markets":
            return [
                {
                    "id": f"m{i}",
                    "name": f"Market {i}",
                    "symbol": f"m{i}",
                    "current_price": 1.0,
                    "market_cap": 1e9,
                    "market_cap_rank": i,
                    "price_change_percentage_24h": 0.5,
                    "total_volume": 1e6,
                }
                for i in range(1, params["per_page"] + 1)
            ]
        raise AssertionError(endpoint)

    return fetch


class NullOptionalParametersTakeDefaults(unittest.TestCase):
    def setUp(self):
        self.calls = []
        patcher = patch.object(main, "_fetch_coingecko", fake_coingecko(self.calls))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def post(self, tool, body):
        response = self.client.post(f"/tools/{tool}", json={**ENVELOPE, **body})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_price_with_null_currency_uses_usd(self):
        out = self.post("get_crypto_price", {"coin_ids": "bitcoin", "vs_currency": None})
        self.assertIsNone(out["error"], out)
        self.assertIn("(USD)", out["result"])
        self.assertEqual(self.calls[-1][1]["vs_currencies"], "usd")

    def test_search_with_null_max_results_uses_five(self):
        out = self.post("search_crypto_coins", {"query": "sol", "max_results": None})
        self.assertIsNone(out["error"], out)
        self.assertEqual(sum(1 for line in out["result"].splitlines() if line[:2].strip().rstrip(".").isdigit()), 5)

    def test_trending_with_null_limit_uses_five(self):
        out = self.post("get_trending_crypto", {"limit": None})
        self.assertIsNone(out["error"], out)
        self.assertEqual(sum(1 for line in out["result"].splitlines() if line[:2].strip().rstrip(".").isdigit()), 5)

    def test_market_overview_with_null_limit_and_currency(self):
        out = self.post("get_crypto_market_overview", {"limit": None, "vs_currency": None})
        self.assertIsNone(out["error"], out)
        self.assertEqual(self.calls[-1][1]["per_page"], 10)
        self.assertEqual(self.calls[-1][1]["vs_currency"], "usd")

    def test_explicit_values_still_apply_and_required_null_still_fails(self):
        out = self.post("get_crypto_price", {"coin_ids": ["ethereum"], "vs_currency": "eur"})
        self.assertIsNone(out["error"], out)
        self.assertEqual(self.calls[-1][1]["vs_currencies"], "eur")
        out = self.post("get_trending_crypto", {"limit": 3})
        self.assertEqual(sum(1 for line in out["result"].splitlines() if line[:2].strip().rstrip(".").isdigit()), 3)
        out = self.post("get_crypto_price", {"coin_ids": None, "vs_currency": None})
        self.assertIsNotNone(out["error"])
        self.assertIn("coin_ids", out["error"])


if __name__ == "__main__":
    unittest.main()

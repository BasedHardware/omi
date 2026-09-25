"""Regression: a non-numeric limit/max_results must answer with a tool error, not a 500.

The Omi backend forwards whatever the model put in the tool call, so an integer
parameter can arrive as a list, an object, or (through JSON's unbounded exponent)
as infinity. ``coerce_limit``/``coerce_max_results`` reached ``int(v)``, which
raises TypeError for a list/object and OverflowError for infinity. pydantic only
converts ValueError and AssertionError raised inside a validator into a request
validation error, so those escaped ``validation_exception_handler`` and returned
an unhandled 500 - even though the same app already answers a non-numeric
*string* ("abc") with the documented ``invalid tool request`` tool error.

Drives the real FastAPI app; the CoinGecko seam is patched out. No network.

Run: python3 -m pytest plugins/omi-coingecko-crypto-app/test_int_param_type_coercion.py -q
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

ENVELOPE = {"uid": "user-1", "app_id": "app-1", "tool_name": "x"}

# Every int parameter the manifest exposes, with the tool that carries it.
INT_PARAMS = (
    ("search_crypto_coins", "max_results", {"query": "sol"}),
    ("get_trending_crypto", "limit", {}),
    ("get_crypto_market_overview", "limit", {}),
)

# Shapes int() cannot consume. Infinity is covered separately: it needs a raw
# body because the test client's JSON encoder refuses to emit it.
NON_NUMERIC = ([], {}, [5], {"value": 5}, [[1]])


def fake_coingecko(calls):
    async def fetch(endpoint, params=None):
        calls.append((endpoint, dict(params or {})))
        if endpoint == "/search":
            return {"coins": [{"id": f"c{i}", "name": f"Coin {i}", "symbol": f"c{i}", "market_cap_rank": i} for i in range(1, 16)]}
        if endpoint == "/search/trending":
            return {"coins": [{"item": {"id": f"t{i}", "name": f"Trend {i}", "symbol": f"t{i}"}} for i in range(1, 16)]}
        if endpoint == "/coins/markets":
            return [
                {"id": f"m{i}", "name": f"Market {i}", "symbol": f"m{i}", "current_price": 1.0, "market_cap": 1e9, "market_cap_rank": i}
                for i in range(1, params["per_page"] + 1)
            ]
        raise AssertionError(endpoint)

    return fetch


class NonNumericIntParametersAreRejectedCleanly(unittest.TestCase):
    def setUp(self):
        self.calls = []
        patcher = patch.object(main, "_fetch_coingecko", fake_coingecko(self.calls))
        patcher.start()
        self.addCleanup(patcher.stop)
        # raise_server_exceptions=False so an unhandled error surfaces as the 500
        # a deployed caller would see instead of exploding inside the test.
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def post(self, tool, body):
        return self.client.post(f"/tools/{tool}", json={**ENVELOPE, **body})

    def post_raw(self, tool, raw_body):
        return self.client.post(f"/tools/{tool}", content=raw_body, headers={"content-type": "application/json"})

    def test_non_numeric_values_return_a_tool_error(self):
        for tool, field, base in INT_PARAMS:
            for value in NON_NUMERIC:
                with self.subTest(tool=tool, field=field, value=value):
                    response = self.post(tool, {**base, field: value})
                    self.assertEqual(response.status_code, 200, response.text[:300])
                    out = response.json()
                    self.assertIsNone(out["result"], out)
                    self.assertIn("invalid tool request", out["error"])
                    self.assertIn(field, out["error"])

    def test_no_upstream_call_is_made_for_a_rejected_request(self):
        self.post("get_crypto_market_overview", {"limit": {"value": 5}})
        self.assertEqual(self.calls, [])

    def test_infinite_limit_returns_a_tool_error(self):
        # JSON has no exponent bound, so "1e400" parses to inf and int(inf)
        # raises OverflowError - the same escape route as the containers above.
        response = self.post_raw(
            "get_trending_crypto",
            '{"uid": "user-1", "app_id": "app-1", "tool_name": "x", "limit": 1e400}',
        )
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertIn("invalid tool request", response.json()["error"])
        self.assertEqual(self.calls, [])

    def test_non_numeric_string_keeps_its_existing_tool_error(self):
        # The contract this fix extends: already correct before, must stay correct.
        response = self.post("get_trending_crypto", {"limit": "abc"})
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertIn("invalid tool request", response.json()["error"])

    def test_numeric_strings_and_floats_still_coerce(self):
        response = self.post("get_crypto_market_overview", {"limit": "7"})
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertIsNone(response.json()["error"], response.text[:300])
        self.assertEqual(self.calls[-1][1]["per_page"], 7)

        response = self.post("get_crypto_market_overview", {"limit": 4.9})
        self.assertIsNone(response.json()["error"], response.text[:300])
        self.assertEqual(self.calls[-1][1]["per_page"], 4)

    def test_null_still_takes_the_default(self):
        # Guards the null-optionals fix these validators exist for.
        response = self.post("get_crypto_market_overview", {"limit": None})
        self.assertIsNone(response.json()["error"], response.text[:300])
        self.assertEqual(self.calls[-1][1]["per_page"], 10)

    def test_out_of_range_numbers_keep_their_bounds_error(self):
        response = self.post("get_trending_crypto", {"limit": 99})
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertIn("invalid tool request", response.json()["error"])


if __name__ == "__main__":
    unittest.main()

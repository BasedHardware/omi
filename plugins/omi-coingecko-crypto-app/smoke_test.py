"""Comprehensive local smoke test for CoinGecko Omi app."""

import asyncio
import httpx
from main import (
    app,
    health,
    omi_tools,
    get_crypto_price,
    search_crypto_coins,
    get_trending_crypto,
    get_crypto_market_overview,
    DEFAULT_USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
)
from models import (
    GetCryptoPriceRequest,
    SearchCryptoCoinsRequest,
    GetTrendingCryptoRequest,
    GetCryptoMarketOverviewRequest,
)


async def run_smoke_tests():
    print("--- 1. Testing Health Endpoint ---")
    h = await health()
    assert h.get("status") == "ok", f"Health check failed: {h}"
    print("[PASS] Health check passed:", h)

    print("\n--- 2. Testing Omi Manifest Endpoint ---")
    manifest = await omi_tools()
    assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
    assert len(manifest.get("tools", [])) == 4, "Expected 4 tools in manifest"
    tool_names = [t["name"] for t in manifest["tools"]]
    print("[PASS] Manifest verified. Registered tools:", tool_names)

    # Initialize httpx client on app state for tool handlers
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app.state.http_client = client

        print("\n--- 3. Testing Price Tool (/tools/get_crypto_price) ---")
        price_req = GetCryptoPriceRequest(coin_ids=["bitcoin", "ethereum"], vs_currency="usd")
        price_res = await get_crypto_price(price_req)
        print("Price Result:\n", price_res.result)
        assert price_res.result is not None, f"Expected result, got error: {price_res.error}"
        assert "Bitcoin" in price_res.result, "Bitcoin missing from price output"

        print("\n--- 4. Testing Search Tool (/tools/search_crypto_coins) ---")
        search_req = SearchCryptoCoinsRequest(query="sol", max_results=3)
        search_res = await search_crypto_coins(search_req)
        print("Search Result:\n", search_res.result)
        assert search_res.result is not None, f"Expected result, got error: {search_res.error}"
        assert "Solana" in search_res.result, "Solana missing from search output"

        print("\n--- 5. Testing Trending Tool (/tools/get_trending_crypto) ---")
        trending_req = GetTrendingCryptoRequest(limit=3)
        trending_res = await get_trending_crypto(trending_req)
        print("Trending Result:\n", trending_res.result)
        assert trending_res.result is not None, f"Expected result, got error: {trending_res.error}"

        print("\n--- 6. Testing Market Overview Tool (/tools/get_crypto_market_overview) ---")
        overview_req = GetCryptoMarketOverviewRequest(limit=5, vs_currency="usd")
        overview_res = await get_crypto_market_overview(overview_req)
        print("Market Overview Result:\n", overview_res.result)
        assert overview_res.result is not None, f"Expected result, got error: {overview_res.error}"
        assert "Top 5 Cryptocurrencies" in overview_res.result

        print("\n--- 7. Testing Error Handling & Missing Coins ---")
        missing_req = GetCryptoPriceRequest(coin_ids=["non-existent-token-xyz-123"], vs_currency="usd")
        missing_res = await get_crypto_price(missing_req)
        print("Non-existent Coin Handling:\n", missing_res.error)
        assert missing_res.error is not None, "Expected error response for non-existent coin ID, but got a result"
        assert "non-existent-token-xyz-123" in missing_res.error, "Error message should mention the invalid coin ID"

        # Verify whitespace-only vs_currency rejection
        try:
            GetCryptoPriceRequest(coin_ids=["bitcoin"], vs_currency="  ")
            assert False, "Should have rejected whitespace-only vs_currency"
        except ValueError:
            pass

    print("\n[SUCCESS] ALL 7 SMOKE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

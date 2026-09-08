"""Standalone integration smoke test for Omi World Time & Solar Ephemeris app."""

import asyncio
import httpx

from main import (
    app,
    calculate_time_difference,
    get_current_time,
    get_solar_times,
    health,
    omi_tools,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from models import (
    CalculateTimeDifferenceRequest,
    GetCurrentTimeRequest,
    GetSolarTimesRequest,
)


async def run_smoke_tests():
    print("==================================================")
    print(" Starting Omi World Time & Solar Ephemeris Smoke Tests ")
    print("==================================================")

    # 1. Health Check
    print("\n[1/6] Testing Health Endpoint...")
    h = await health()
    assert h.get("status") == "ok", f"Health check failed: {h}"
    print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}")

    # 2. Manifest Schema
    print("\n[2/6] Testing Omi Chat Tools Manifest...")
    manifest = await omi_tools()
    assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
    assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
    tools = manifest.get("tools", [])
    assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"
    tool_names = [t["name"] for t in tools]
    print(f"  ✓ Manifest verified. Registered tools: {tool_names}")

    # Initialize client for tool handlers
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app.state.http_client = client

        # 3. Current Time
        print("\n[3/6] Testing /tools/get_current_time (Tokyo)...")
        res_tokyo = await get_current_time(GetCurrentTimeRequest(location="Tokyo"))
        assert res_tokyo.error is None, f"Unexpected error: {res_tokyo.error}"
        assert "Tokyo" in res_tokyo.result, "Expected Tokyo in result"
        assert "UTC+09:00" in res_tokyo.result, "Expected UTC+09:00 in result"
        print("  ✓ Result:\n   ", res_tokyo.result.replace("\n", "\n    "))

        print("\n[3b/6] Testing /tools/get_current_time (London)...")
        res_london = await get_current_time(GetCurrentTimeRequest(location="London"))
        assert res_london.error is None, f"Unexpected error: {res_london.error}"
        print("  ✓ Result:\n   ", res_london.result.replace("\n", "\n    "))

        # 4. Time Difference & Conversion
        print("\n[4/6] Testing /tools/calculate_time_difference (New York -> Tokyo)...")
        diff_req = CalculateTimeDifferenceRequest(
            source_location="New York",
            target_location="Tokyo",
            source_time="14:00",
        )
        res_diff = await calculate_time_difference(diff_req)
        assert res_diff.error is None, f"Unexpected error: {res_diff.error}"
        assert "ahead of" in res_diff.result or "behind" in res_diff.result, "Expected time comparison in result"
        print("  ✓ Result:\n   ", res_diff.result.replace("\n", "\n    "))

        # 5. Solar Ephemeris (Sunrise / Sunset)
        print("\n[5/6] Testing /tools/get_solar_times (Paris)...")
        solar_req = GetSolarTimesRequest(location="Paris", date="2026-09-08")
        res_solar = await get_solar_times(solar_req)
        assert res_solar.error is None, f"Unexpected error: {res_solar.error}"
        assert "Sunrise:" in res_solar.result, "Expected Sunrise in result"
        assert "Sunset:" in res_solar.result, "Expected Sunset in result"
        print("  ✓ Result:\n   ", res_solar.result.replace("\n", "\n    "))

        # 6. Error Handling
        print("\n[6/6] Testing error handling for non-existent location...")
        err_req = GetCurrentTimeRequest(location="AtlantisMythicalUnderwater123")
        res_err = await get_current_time(err_req)
        assert res_err.error is not None, "Expected error response for mythical city"
        print(f"  ✓ Gracefully handled error: {res_err.error}")

    print("\n==================================================")
    print(" ALL 6 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

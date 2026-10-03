"""Standalone integration smoke test for Omi World Time & Solar Ephemeris app.

Tests the full HTTP surface via httpx ASGITransport, verifying routing,
request validation handlers, and ChatToolResponse serialization contracts.
"""

import asyncio
import httpx

from main import app, USER_AGENT, REQUEST_TIMEOUT_SECONDS


async def run_smoke_tests():
    print("==================================================")
    print(" Starting Omi World Time & Solar Ephemeris Smoke Tests ")
    print("==================================================")

    # Initialize lifespan HTTP client for internal upstream calls
    upstream_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=upstream_headers) as upstream_client:
        app.state.http_client = upstream_client

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health Check
            print("\n[1/7] Testing Health Endpoint (GET /health)...")
            res = await client.get("/health")
            assert res.status_code == 200, f"Health check failed with status {res.status_code}"
            h = res.json()
            assert h.get("status") == "ok", f"Health status not ok: {h}"
            assert h.get("service") == "omi-world-time-app", f"Unexpected service name: {h}"
            print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}, Version: {h.get('version')}")

            # 2. Manifest Schema
            print("\n[2/7] Testing Omi Chat Tools Manifest (GET /.well-known/omi-tools.json)...")
            res = await client.get("/.well-known/omi-tools.json")
            assert res.status_code == 200, f"Manifest check failed with status {res.status_code}"
            manifest = res.json()
            assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
            assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
            tools = manifest.get("tools", [])
            assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"
            for tool in tools:
                assert "name" in tool and "endpoint" in tool and "method" in tool, f"Incomplete tool manifest: {tool}"
                assert tool["method"] == "POST", f"Expected method POST, got {tool['method']}"
                assert tool["auth_required"] is False, "auth_required should be False"
            tool_names = [t["name"] for t in tools]
            print(f"  ✓ Manifest verified with endpoints & methods. Registered tools: {tool_names}")

            # 3. Current Time (Tokyo)
            print("\n[3/7] Testing POST /tools/get_current_time (Tokyo)...")
            res = await client.post("/tools/get_current_time", json={"location": "Tokyo"})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error in response: {data}"
            assert "result" in data, "Expected result field in response"
            result_text = data["result"]
            assert "Tokyo" in result_text, "Expected Tokyo in result"
            assert "UTC+09:00" in result_text, "Expected Tokyo UTC+09:00 in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            # 3b. Current Time (London)
            print("\n[4/7] Testing POST /tools/get_current_time (London)...")
            res = await client.post("/tools/get_current_time", json={"location": "London"})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error in response: {data}"
            assert "result" in data, "Expected result field in response"
            result_text = data["result"]
            assert "London" in result_text or "Europe/London" in result_text, "Expected London/Europe/London in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            # 4. Time Difference & Conversion (New York -> Tokyo)
            print("\n[5/7] Testing POST /tools/calculate_time_difference (New York -> Tokyo)...")
            diff_payload = {
                "source_location": "New York",
                "target_location": "Tokyo",
                "source_time": "14:00",
            }
            res = await client.post("/tools/calculate_time_difference", json=diff_payload)
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result field in response"
            result_text = data["result"]
            assert "ahead of" in result_text or "behind" in result_text, "Expected time comparison in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            # 5. Solar Ephemeris (Sunrise / Sunset / Solar Noon / Twilight)
            print("\n[6/7] Testing POST /tools/get_solar_times (Paris)...")
            solar_payload = {"location": "Paris", "date": "2026-09-08"}
            res = await client.post("/tools/get_solar_times", json=solar_payload)
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result field in response"
            result_text = data["result"]
            assert "Sunrise:" in result_text, "Expected Sunrise in result"
            assert "Sunset:" in result_text, "Expected Sunset in result"
            assert "Solar Noon:" in result_text, "Expected Solar Noon in result"
            assert "Day Length:" in result_text, "Expected Day Length in result"
            assert "Dawn (First Light):" in result_text, "Expected Dawn (First Light) in result"
            assert "Dusk (Last Light):" in result_text, "Expected Dusk (Last Light) in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            # 6. Error Handling & Validation Contracts
            print("\n[7/7] Testing Error Handling & Null-Exclusion Contracts...")
            # 6a. Unknown location gracefully returns error (with result omitted)
            res = await client.post("/tools/get_current_time", json={"location": "AtlantisMythicalUnderwater123"})
            assert res.status_code == 200
            err_data = res.json()
            assert "error" in err_data, "Expected error field"
            assert "result" not in err_data, f"Result field must be omitted on error, got: {err_data}"
            print(f"  ✓ Nonexistent location handled: {err_data['error']}")

            # 6b. Invalid 12-hour format rejected
            res = await client.post(
                "/tools/calculate_time_difference",
                json={"source_location": "London", "target_location": "Paris", "source_time": "13:30 PM"},
            )
            assert res.status_code == 200
            err_data = res.json()
            assert "error" in err_data, "Expected error for invalid 12-hour time '13:30 PM'"
            assert "result" not in err_data, "Result must be omitted on error"
            print(f"  ✓ Invalid 12-hour time handled: {err_data['error']}")

    print("\n==================================================")
    print(" ALL 7 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

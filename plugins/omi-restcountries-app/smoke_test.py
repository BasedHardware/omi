"""ASGI integration smoke test for Omi REST Countries & Geographic Intelligence app.

Drives the application over ASGI transport using httpx.AsyncClient, asserting
on real HTTP status codes, routing, serialization, and error contract compliance.
"""

import asyncio
import httpx

from main import app


async def run_smoke_tests():
    print("================================================================")
    print(" Starting Omi REST Countries & Geographic Intelligence Smoke Tests ")
    print("================================================================")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Health Check
        print("\n[1/9] Testing GET /health...")
        resp = await client.get("/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        h = resp.json()
        assert h.get("status") == "ok", f"Health status not ok: {h}"
        print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}, Version: {h.get('version')}")

        # 2. Manifest Schema
        print("\n[2/9] Testing GET /.well-known/omi-tools.json...")
        resp = await client.get("/.well-known/omi-tools.json")
        assert resp.status_code == 200
        manifest = resp.json()
        assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
        assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
        tools = manifest.get("tools", [])
        assert len(tools) == 6, f"Expected 6 tools, got {len(tools)}"
        tool_names = [t["name"] for t in tools]
        print(f"  ✓ Manifest verified. 6 registered tools: {tool_names}")

        # 3. Country Info Lookup (France, Japan, and newly added Russia)
        print("\n[3/9] Testing POST /tools/get_country_info (France & Russia)...")
        resp_fr = await client.post("/tools/get_country_info", json={"country": "France"})
        assert resp_fr.status_code == 200
        data_fr = resp_fr.json()
        assert "error" not in data_fr, f"Unexpected error: {data_fr}"
        assert "result" in data_fr
        assert "Paris" in data_fr["result"]
        assert "EUR" in data_fr["result"]
        print("  ✓ France lookup successful:\n   ", data_fr["result"].splitlines()[0])

        resp_rus = await client.post("/tools/get_country_info", json={"country": "Russia"})
        assert resp_rus.status_code == 200
        data_rus = resp_rus.json()
        assert "error" not in data_rus, f"Russia alias lookup failed: {data_rus}"
        assert "Moscow" in data_rus["result"]
        print("  ✓ Russia alias lookup successful:\n   ", data_rus["result"].splitlines()[0])

        # 4. Search by Capital
        print("\n[4/9] Testing POST /tools/search_by_capital (Canberra)...")
        resp_cap = await client.post("/tools/search_by_capital", json={"capital": "Canberra"})
        assert resp_cap.status_code == 200
        data_cap = resp_cap.json()
        assert "error" not in data_cap
        assert "Australia" in data_cap["result"]
        print("  ✓ Capital lookup result:\n   ", data_cap["result"].splitlines()[0])

        # 5. Border Countries Analysis (Germany & Japan)
        print("\n[5/9] Testing POST /tools/get_border_countries (Germany & Japan)...")
        resp_ger = await client.post("/tools/get_border_countries", json={"country": "Germany"})
        assert resp_ger.status_code == 200
        data_ger = resp_ger.json()
        assert "error" not in data_ger
        assert "9 countries" in data_ger["result"]
        assert "Luxembourg" in data_ger["result"]  # Verifies LUX is resolved
        print("  ✓ Germany borders verified (9 neighboring countries, all resolved).")

        resp_jp = await client.post("/tools/get_border_countries", json={"country": "Japan"})
        assert resp_jp.status_code == 200
        data_jp = resp_jp.json()
        assert "error" not in data_jp
        assert "no land borders" in data_jp["result"]
        print("  ✓ Island nation (Japan) border handling verified.")

        # 6. Currency & Language Discovery
        print("\n[6/9] Testing POST /tools/search_by_currency and /tools/search_by_language...")
        resp_curr = await client.post("/tools/search_by_currency", json={"currency": "EUR"})
        assert resp_curr.status_code == 200
        data_curr = resp_curr.json()
        assert "error" not in data_curr
        assert "France" in data_curr["result"]
        print("  ✓ Currency query (EUR) successful.")

        resp_lang = await client.post("/tools/search_by_language", json={"language": "Spanish"})
        assert resp_lang.status_code == 200
        data_lang = resp_lang.json()
        assert "error" not in data_lang
        assert "Spain" in data_lang["result"]
        print("  ✓ Language query (Spanish) successful.")

        # 7. Country Comparison
        print("\n[7/9] Testing POST /tools/compare_countries (Japan vs Germany)...")
        resp_cmp = await client.post(
            "/tools/compare_countries", json={"country_a": "Japan", "country_b": "Germany"}
        )
        assert resp_cmp.status_code == 200
        data_cmp = resp_cmp.json()
        assert "error" not in data_cmp
        assert "Comparison" in data_cmp["result"]
        print("  ✓ Comparison successful.")

        # 8. Comparison Tie Handling
        print("\n[8/9] Testing POST /tools/compare_countries tie handling...")
        resp_tie = await client.post(
            "/tools/compare_countries", json={"country_a": "France", "country_b": "France"}
        )
        assert resp_tie.status_code == 200
        data_tie = resp_tie.json()
        assert "equal population" in data_tie["result"]
        assert "equal land area" in data_tie["result"]
        print("  ✓ Tie comparison successful (equal values handled cleanly).")

        # 9. Validation Error Contract (omitting 'result' field on error)
        print("\n[9/9] Testing RequestValidationError contract (empty country)...")
        resp_err = await client.post("/tools/get_country_info", json={"country": "   "})
        assert resp_err.status_code == 200
        data_err = resp_err.json()
        assert "error" in data_err
        assert "result" not in data_err, "Validation error response must omit 'result' field"
        print(f"  ✓ Error contract verified: {data_err['error']}")

    print("\n================================================================")
    print(" ALL 9 ASGI SMOKE TESTS COMPLETED SUCCESSFULLY! ")
    print("================================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

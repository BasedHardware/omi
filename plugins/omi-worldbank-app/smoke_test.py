"""Live end-to-end integration smoke test for Omi World Bank App.

Queries live World Bank Open Data APIs to verify real-time data ingestion,
number formatting, alias resolution, and ChatToolResponse contract compliance.
"""

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from test_main import install_dependency_stubs

install_dependency_stubs()

import main
import models


async def run_live_smoke_tests():
    print("=" * 60)
    print("[INFO] Starting World Bank Omi Integration App Live Smoke Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    # 1. Test Manifest
    try:
        manifest = await main.get_manifest()
        assert "tools" in manifest, "Missing 'tools' in manifest"
        assert len(manifest["tools"]) == 4, f"Expected 4 tools, got {len(manifest['tools'])}"
        print(f"✅ [PASS] Tool Manifest: {len(manifest['tools'])} tools registered with zero-auth")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] Tool Manifest: {e}")
        failed += 1

    # 2. Test Country Profile (USA)
    try:
        req = models.CountryProfileRequest(country="United States")
        resp = await main.get_country_profile(req)
        assert resp.error is None, f"Expected error=None, got {resp.error}"
        assert resp.result is not None, "Expected result to be populated"
        assert "United States" in resp.result, "Missing country name in result"
        assert "GDP" in resp.result, "Missing GDP in result"
        print("✅ [PASS] /tools/country-profile (USA): Successfully synthesized profile")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] /tools/country-profile: {e}")
        failed += 1

    # 3. Test Economic Indicator with History (India GDP 3 years)
    try:
        req = models.EconomicIndicatorRequest(country="India", indicator="gdp", years=3)
        resp = await main.get_economic_indicator(req)
        assert resp.error is None, f"Expected error=None, got {resp.error}"
        assert resp.result is not None, "Expected result to be populated"
        assert "India" in resp.result, "Missing country name in result"
        assert "Trillion" in resp.result or "Billion" in resp.result or "$" in resp.result, "Expected currency formatting"
        print("✅ [PASS] /tools/economic-indicator (India GDP 3y): Successfully retrieved trend")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] /tools/economic-indicator: {e}")
        failed += 1

    # 4. Test Economy Comparison (Japan vs Germany)
    try:
        req = models.CompareEconomiesRequest(country_a="Japan", country_b="Germany")
        resp = await main.compare_country_economies(req)
        assert resp.error is None, f"Expected error=None, got {resp.error}"
        assert resp.result is not None, "Expected result to be populated"
        assert "Japan" in resp.result, "Missing Japan in result"
        assert "Germany" in resp.result, "Missing Germany in result"
        print("✅ [PASS] /tools/compare-economies (Japan vs Germany): Side-by-side comparison generated")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] /tools/compare-economies: {e}")
        failed += 1

    # 5. Test Country Discovery / Search (Nordic search query)
    try:
        req = models.SearchCountriesRequest(query="Norway", limit=5)
        resp = await main.search_countries(req)
        assert resp.error is None, f"Expected error=None, got {resp.error}"
        assert resp.result is not None, "Expected result to be populated"
        assert "Norway" in resp.result, "Missing Norway in search result"
        print("✅ [PASS] /tools/search-countries (query='Norway'): Matching countries discovered")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] /tools/search-countries: {e}")
        failed += 1

    # 6. Test Error Handling (Unknown country)
    try:
        req = models.CountryProfileRequest(country="AtlantisKingdomOfMermaids")
        resp = await main.get_country_profile(req)
        assert resp.error is not None, "Expected error for fictitious country"
        assert resp.result is None, "Expected result to be None when error is returned"
        print("✅ [PASS] Error Handling: Graceful rejection with descriptive error message")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] Error Handling: {e}")
        failed += 1

    # 7. Test Health Endpoint
    try:
        health = await main.health_check()
        assert health.get("status") == "healthy", f"Unexpected status: {health}"
        print("✅ [PASS] /health: System status healthy")
        passed += 1
    except Exception as e:
        print(f"❌ [FAIL] /health: {e}")
        failed += 1

    print("=" * 60)
    print(f"📊 Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_live_smoke_tests())
    sys.exit(exit_code)

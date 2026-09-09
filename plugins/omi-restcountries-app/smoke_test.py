"""Live integration smoke test for Omi REST Countries & Geographic Intelligence app."""

import asyncio
import httpx

from main import (
    app,
    compare_countries,
    get_border_countries,
    get_country_info,
    health,
    omi_tools,
    search_by_capital,
    search_by_currency,
    search_by_language,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from models import (
    CompareCountriesRequest,
    GetBorderCountriesRequest,
    GetCountryInfoRequest,
    SearchByCapitalRequest,
    SearchByCurrencyRequest,
    SearchByLanguageRequest,
)


async def run_smoke_tests():
    print("================================================================")
    print(" Starting Omi REST Countries & Geographic Intelligence Smoke Tests ")
    print("================================================================")

    # 1. Health Check
    print("\n[1/8] Testing Health Endpoint...")
    h = await health()
    assert h.get("status") == "ok", f"Health check failed: {h}"
    print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}, Version: {h.get('version')}")

    # 2. Manifest Schema
    print("\n[2/8] Testing Omi Chat Tools Manifest...")
    manifest = await omi_tools()
    assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
    assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
    tools = manifest.get("tools", [])
    assert len(tools) == 6, f"Expected 6 tools, got {len(tools)}"
    tool_names = [t["name"] for t in tools]
    print(f"  ✓ Manifest verified. 6 registered tools: {tool_names}")

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app.state.http_client = client

        # 3. Country Info Lookup
        print("\n[3/8] Testing get_country_info (France & Japan)...")
        res_fr = await get_country_info(GetCountryInfoRequest(country="France"))
        assert res_fr.error is None, f"Unexpected error: {res_fr.error}"
        assert "Paris" in res_fr.result
        assert "EUR" in res_fr.result
        print("  ✓ France lookup successful:\n   ", res_fr.result.splitlines()[0])

        res_jp = await get_country_info(GetCountryInfoRequest(country="JP"))
        assert res_jp.error is None
        assert "Tokyo" in res_jp.result
        print("  ✓ Japan (by CCA2) successful:\n   ", res_jp.result.splitlines()[0])

        # 4. Search by Capital
        print("\n[4/8] Testing search_by_capital (Canberra)...")
        res_cap = await search_by_capital(SearchByCapitalRequest(capital="Canberra"))
        assert res_cap.error is None
        assert "Australia" in res_cap.result
        print("  ✓ Capital lookup result:\n   ", res_cap.result)

        # 5. Border Countries Analysis
        print("\n[5/8] Testing get_border_countries (Germany & Japan)...")
        res_ger_borders = await get_border_countries(GetBorderCountriesRequest(country="Germany"))
        assert res_ger_borders.error is None
        assert "9 countries" in res_ger_borders.result
        print("  ✓ Germany borders verified (9 neighboring countries).")

        res_jp_borders = await get_border_countries(GetBorderCountriesRequest(country="Japan"))
        assert res_jp_borders.error is None
        assert "no land borders" in res_jp_borders.result
        print("  ✓ Island nation (Japan) border handling verified.")

        # 6. Currency & Language Discovery
        print("\n[6/8] Testing search_by_currency (EUR) and search_by_language (Spanish)...")
        res_curr = await search_by_currency(SearchByCurrencyRequest(currency="EUR"))
        assert res_curr.error is None
        assert "France" in res_curr.result
        print(f"  ✓ Currency query successful.")

        res_lang = await search_by_language(SearchByLanguageRequest(language="Spanish"))
        assert res_lang.error is None
        assert "Spain" in res_lang.result
        print(f"  ✓ Language query successful.")

        # 7. Country Comparison
        print("\n[7/8] Testing compare_countries (Japan vs Germany)...")
        res_cmp = await compare_countries(CompareCountriesRequest(country_a="Japan", country_b="Germany"))
        assert res_cmp.error is None
        assert "Population:" in res_cmp.result
        assert "Area:" in res_cmp.result
        print("  ✓ Comparison successful:\n   ", res_cmp.result.splitlines()[0])

        # 8. Error Handling & Non-Existent Protection
        print("\n[8/8] Testing error handling & unknown inputs...")
        res_unknown = await get_country_info(GetCountryInfoRequest(country="MythicalAtlantis"))
        assert res_unknown.result is None
        assert res_unknown.error is not None
        assert "not found" in res_unknown.error
        print(f"  ✓ Graceful error handling verified: {res_unknown.error}")

    print("\n================================================================")
    print(" ALL 8 SMOKE TESTS PASSED CLEANLY! ")
    print("================================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

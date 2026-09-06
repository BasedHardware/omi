"""Live end-to-end integration smoke tests for Omi Nobel Prize App.

Tests actual connectivity and response shapes against the public Nobel Prize API
(https://api.nobelprize.org/2.1).
"""

import os
import sys
import asyncio
import httpx

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from main import (
    BASE_API_URL,
    app,
    get_nobel_laureate_details,
    get_nobel_prize_by_category,
    get_nobel_prizes,
    health_check,
    omi_tools_manifest,
    root,
    search_nobel_laureates,
)
from models import (
    CategoryPrizesRequest,
    LaureateDetailsRequest,
    NobelPrizesRequest,
    SearchLaureatesRequest,
)


async def run_smoke_tests():
    print("=== Starting Omi Nobel Prize App Smoke Tests ===")
    passed = 0
    total = 0

    # 1. Health check
    total += 1
    health = await health_check()
    assert health.get("status") == "ok", f"Unexpected health status: {health}"
    print("[PASS] 1. Health check passed.")
    passed += 1

    # 2. Manifest check
    total += 1
    manifest = await omi_tools_manifest()
    assert len(manifest.get("tools", [])) == 4, "Expected 4 registered tools in manifest."
    print("[PASS] 2. Manifest check passed (4 tools registered).")
    passed += 1

    # 3. Live get_nobel_prizes (Year 2023)
    total += 1
    print("Testing live get_nobel_prizes for 2023...")
    resp = await get_nobel_prizes(NobelPrizesRequest(year=2023, limit=5))
    assert resp.error is None, f"get_nobel_prizes returned error: {resp.error}"
    assert resp.result is not None, "get_nobel_prizes returned empty result."
    assert "2023" in resp.result, "Expected 2023 in result output."
    print(f"[PASS] 3. Live get_nobel_prizes passed. Sample preview:\n   {resp.result[:120]}...\n")
    passed += 1

    # 4. Live get_nobel_prizes with category filter (Peace)
    total += 1
    print("Testing live get_nobel_prizes for Peace...")
    resp = await get_nobel_prizes(NobelPrizesRequest(category="peace", limit=2))
    assert resp.error is None, f"get_nobel_prizes with category returned error: {resp.error}"
    assert "Peace" in resp.result, "Expected Peace in result output."
    print(f"[PASS] 4. Live get_nobel_prizes (category filter) passed.\n")
    passed += 1

    # 5. Live search_nobel_laureates (Einstein)
    total += 1
    print("Testing live search_nobel_laureates ('Einstein')...")
    resp = await search_nobel_laureates(SearchLaureatesRequest(query="Einstein", limit=3))
    assert resp.error is None, f"search_nobel_laureates returned error: {resp.error}"
    assert "Albert Einstein" in resp.result, "Expected Albert Einstein in search result."
    print(f"[PASS] 5. Live search_nobel_laureates passed. Sample preview:\n   {resp.result[:120]}...\n")
    passed += 1

    # 6. Live get_nobel_prize_by_category (Medicine)
    total += 1
    print("Testing live get_nobel_prize_by_category ('medicine')...")
    resp = await get_nobel_prize_by_category(CategoryPrizesRequest(category="medicine", limit=3))
    assert resp.error is None, f"get_nobel_prize_by_category returned error: {resp.error}"
    assert "Physiology or Medicine" in resp.result, "Expected Physiology or Medicine in result."
    print(f"[PASS] 6. Live get_nobel_prize_by_category passed.\n")
    passed += 1

    # 7. Live get_nobel_laureate_details by numeric ID (ID '1' = Wilhelm Röntgen)
    total += 1
    print("Testing live get_nobel_laureate_details by ID ('1')...")
    resp = await get_nobel_laureate_details(LaureateDetailsRequest(identifier="1"))
    assert resp.error is None, f"get_nobel_laureate_details returned error: {resp.error}"
    assert "Röntgen" in resp.result or "Rontgen" in resp.result, "Expected Röntgen in laureate details."
    print(f"[PASS] 7. Live get_nobel_laureate_details by ID passed.\n")
    passed += 1

    # 8. Live get_nobel_laureate_details by Name ("Marie Curie")
    total += 1
    print("Testing live get_nobel_laureate_details by Name ('Marie Curie')...")
    resp = await get_nobel_laureate_details(LaureateDetailsRequest(identifier="Marie Curie"))
    assert resp.error is None, f"get_nobel_laureate_details returned error: {resp.error}"
    assert "Marie Curie" in resp.result, "Expected Marie Curie in details."
    print(f"[PASS] 8. Live get_nobel_laureate_details by Name passed.\n")
    passed += 1

    print(f"=== All {passed}/{total} Live Smoke Tests Passed Successfully! ===")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

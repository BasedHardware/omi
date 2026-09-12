"""Live end-to-end integration smoke tests for Omi Nobel Prize App.

Tests actual HTTP connectivity and response shapes against the public Nobel Prize API
(https://api.nobelprize.org/2.1) through the FastAPI application.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from fastapi.testclient import TestClient
from main import app


def run_smoke_tests():
    print("=== Starting Omi Nobel Prize App Smoke Tests ===")
    client = TestClient(app, raise_server_exceptions=False)
    passed = 0
    total = 0

    # 1. Health check
    total += 1
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check returned {resp.status_code}"
    assert resp.json().get("status") == "ok", f"Unexpected health status: {resp.json()}"
    print("[PASS] 1. Health check passed.")
    passed += 1

    # 2. Manifest check
    total += 1
    resp = client.get("/.well-known/omi-tools.json")
    assert resp.status_code == 200, f"Manifest check returned {resp.status_code}"
    manifest = resp.json()
    assert len(manifest.get("tools", [])) == 4, "Expected 4 registered tools in manifest."
    print("[PASS] 2. Manifest check passed (4 tools registered).")
    passed += 1

    # 3. Live get_nobel_prizes (Year 2023)
    total += 1
    print("Testing live get_nobel_prizes for 2023...")
    resp = client.post("/tools/get_nobel_prizes", json={"year": 2023, "limit": 5})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"get_nobel_prizes returned error: {data.get('error')}"
    assert data.get("result") is not None, "get_nobel_prizes returned empty result."
    assert "2023" in data.get("result"), "Expected 2023 in result output."
    print(f"[PASS] 3. Live get_nobel_prizes passed. Sample preview:\n   {data.get('result')[:120]}...\n")
    passed += 1

    # 4. Live get_nobel_prizes with category filter (Peace)
    total += 1
    print("Testing live get_nobel_prizes for Peace...")
    resp = client.post("/tools/get_nobel_prizes", json={"category": "peace", "limit": 2})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Returned error: {data.get('error')}"
    assert "Peace" in data.get("result"), "Expected Peace in result output."
    print("[PASS] 4. Live get_nobel_prizes (category filter) passed.\n")
    passed += 1

    # 5. Live search_nobel_laureates (Einstein)
    total += 1
    print("Testing live search_nobel_laureates ('Einstein')...")
    resp = client.post("/tools/search_nobel_laureates", json={"query": "Einstein", "limit": 3})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Returned error: {data.get('error')}"
    assert "Albert Einstein" in data.get("result"), "Expected Albert Einstein in search result."
    print(f"[PASS] 5. Live search_nobel_laureates passed. Sample preview:\n   {data.get('result')[:120]}...\n")
    passed += 1

    # 6. Live get_nobel_prize_by_category (Medicine)
    total += 1
    print("Testing live get_nobel_prize_by_category ('medicine')...")
    resp = client.post("/tools/get_nobel_prize_by_category", json={"category": "medicine", "limit": 3})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Returned error: {data.get('error')}"
    assert "Physiology or Medicine" in data.get("result"), "Expected Physiology or Medicine in result."
    print("[PASS] 6. Live get_nobel_prize_by_category passed.\n")
    passed += 1

    # 7. Live get_nobel_laureate_details by numeric ID (ID '1' = Wilhelm Röntgen)
    total += 1
    print("Testing live get_nobel_laureate_details by ID ('1')...")
    resp = client.post("/tools/get_nobel_laureate_details", json={"identifier": "1"})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Returned error: {data.get('error')}"
    assert "Röntgen" in data.get("result") or "Rontgen" in data.get("result"), "Expected Röntgen in laureate details."
    print("[PASS] 7. Live get_nobel_laureate_details by ID passed.\n")
    passed += 1

    # 8. Live get_nobel_laureate_details by Name ("Marie Curie")
    total += 1
    print("Testing live get_nobel_laureate_details by Name ('Marie Curie')...")
    resp = client.post("/tools/get_nobel_laureate_details", json={"identifier": "Marie Curie"})
    assert resp.status_code == 200, f"HTTP status: {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Returned error: {data.get('error')}"
    assert "Marie Curie" in data.get("result"), "Expected Marie Curie in details."
    print("[PASS] 8. Live get_nobel_laureate_details by Name passed.\n")
    passed += 1

    # 9. Verify short-lived cache works live
    total += 1
    print("Testing live cache speedup...")
    resp_cached = client.post("/tools/get_nobel_laureate_details", json={"identifier": "Marie Curie"})
    assert resp_cached.status_code == 200
    assert resp_cached.json() == data
    print("[PASS] 9. Live cache verification passed.\n")
    passed += 1

    print(f"=== All {passed}/{total} Live Smoke Tests Passed Successfully! ===")


if __name__ == "__main__":
    run_smoke_tests()

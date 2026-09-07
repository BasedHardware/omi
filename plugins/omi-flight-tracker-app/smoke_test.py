"""
Live integration smoke test for Omi OpenSky Flight Tracker Integration App.
Executes live queries against real upstream OpenSky Network endpoints to verify
end-to-end telemetry parsing, caching, and voice synthesis.
"""

import re
import sys
import time
from pathlib import Path

# Ensure UTF-8 stdout encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure the app directory is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fastapi.testclient import TestClient
from main import app, cache, rate_limiter


def run_smoke_tests():
    print("=" * 65)
    print("STARTING LIVE OPENSKY AVIATION RADAR SMOKE TESTS")
    print("=" * 65)

    client = TestClient(app)
    cache.clear()
    rate_limiter.history.clear()

    tests_passed = 0
    total_tests = 7

    # Test 1: Local deployment health check
    print("\n[1/7] Testing GET /health (local I/O-free probe)...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Local health check failed with {resp.status_code}"
    health_data = resp.json()
    assert health_data.get("status") == "healthy"
    print(f"  ✓ Status: {health_data.get('status')}")
    tests_passed += 1

    # Test 2: Upstream diagnostic health check
    print("\n[2/7] Testing GET /health/upstream (upstream connectivity probe)...")
    resp = client.get("/health/upstream")
    assert resp.status_code == 200, f"Upstream health check failed with {resp.status_code}"
    upstream_data = resp.json()
    assert upstream_data.get("status") in ("healthy", "degraded")
    print(f"  ✓ Upstream status: {upstream_data.get('status')}")
    print(f"  ✓ Upstream connected: {upstream_data.get('upstream_connected')}")
    tests_passed += 1

    # Test 3: Omi tools manifest
    print("\n[3/7] Testing GET /.well-known/omi-tools.json...")
    resp = client.get("/.well-known/omi-tools.json")
    assert resp.status_code == 200, f"Manifest check failed with {resp.status_code}"
    manifest = resp.json()
    assert manifest.get("auth_required") is False, "auth_required should be False"
    tools = manifest.get("tools", [])
    assert len(tools) == 3, f"Expected 3 tools, found {len(tools)}"
    print(f"  ✓ Registered tools: {[t['name'] for t in tools]}")
    tests_passed += 1

    # Test 4: Overhead flights radar (London Heathrow airspace - high flight density)
    print("\n[4/7] Testing POST /tools/get_flights_overhead (London airspace)...")
    resp = client.post(
        "/tools/get_flights_overhead",
        json={"location": "London", "radius_km": 50.0, "limit": 3}
    )
    assert resp.status_code == 200, f"Overhead tool returned status {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Overhead tool returned error: {data.get('error')}"
    assert data.get("result") is not None, "Expected result field to be present"
    result = data.get("result", "")
    print(f"  ✓ Response received ({len(result)} chars)")
    first_lines = "\n    ".join(result.split("\n")[:6])
    print(f"    {first_lines}")
    tests_passed += 1

    # Extract an active live callsign from the overhead response to test live tracking
    extracted_callsign = None
    callsign_match = re.search(r"Flight\s+([A-Z0-9]{3,8})", result)
    if callsign_match:
        extracted_callsign = callsign_match.group(1).strip()
    target_callsign = extracted_callsign or "DLH400"

    # Test 5: Airspace activity summary (e.g. Frankfurt hub)
    print("\n[5/7] Testing POST /tools/get_airspace_activity (Regional traffic)...")
    resp = client.post(
        "/tools/get_airspace_activity",
        json={"location": "Frankfurt", "limit": 3}
    )
    assert resp.status_code == 200, f"Airspace activity returned status {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Airspace tool returned error: {data.get('error')}"
    assert data.get("result") is not None, "Airspace result must be present"
    activity_result = data.get("result", "")
    print(f"  ✓ Regional traffic report generated:")
    first_lines = "\n    ".join(activity_result.split("\n")[:4])
    print(f"    {first_lines}")
    tests_passed += 1

    # Test 6: Flight tracking with strict assertions
    print(f"\n[6/7] Testing POST /tools/track_flight_by_callsign (target: {target_callsign})...")
    resp = client.post(
        "/tools/track_flight_by_callsign",
        json={"callsign": target_callsign}
    )
    assert resp.status_code == 200, f"Track flight returned status {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Track flight returned error: {data.get('error')}"
    assert data.get("result") is not None, "Track flight result must be present"
    print(f"  ✓ Tracking response generated successfully (result length: {len(data['result'])})")
    tests_passed += 1

    # Test 7: In-memory caching verification
    print("\n[7/7] Testing in-memory LRU cache speedup and presence...")
    cached_keys = list(cache.cache.keys())
    assert any("opensky_states" in k for k in cached_keys), f"Expected cached OpenSky states in {cached_keys}"

    t0 = time.monotonic()
    resp_cached = client.post(
        "/tools/get_flights_overhead",
        json={"location": "London", "radius_km": 50.0, "limit": 3}
    )
    duration = time.monotonic() - t0
    assert resp_cached.status_code == 200
    data_cached = resp_cached.json()
    assert data_cached.get("error") is None, f"Cached request error: {data_cached.get('error')}"
    assert data_cached.get("result") is not None, "Cached result must be present"
    assert duration < 0.2, f"Expected cache hit to complete in <200ms, took {duration * 1000:.2f} ms"
    print(f"  ✓ Verified cache hit served in {duration * 1000:.2f} ms")
    tests_passed += 1

    print("\n" + "=" * 65)
    print(f"[SUCCESS] ALL {tests_passed}/{total_tests} LIVE SMOKE TESTS PASSED CLEANLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_smoke_tests()

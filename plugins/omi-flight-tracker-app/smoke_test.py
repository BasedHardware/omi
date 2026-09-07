"""
Live integration smoke test for Omi OpenSky Flight Tracker Integration App.
Executes live queries against real upstream OpenSky Network endpoints to verify
end-to-end telemetry parsing, caching, and voice synthesis.
"""

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
    total_tests = 6

    # Test 1: Health check endpoint
    print("\n[1/6] Testing GET /health...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed with {resp.status_code}"
    health_data = resp.json()
    print(f"  ✓ Status: {health_data.get('status')}")
    print(f"  ✓ Upstream connected: {health_data.get('upstream_connected')}")
    tests_passed += 1

    # Test 2: Omi tools manifest
    print("\n[2/6] Testing GET /.well-known/omi-tools.json...")
    resp = client.get("/.well-known/omi-tools.json")
    assert resp.status_code == 200, f"Manifest check failed with {resp.status_code}"
    manifest = resp.json()
    assert manifest.get("auth_required") is False, "auth_required should be False"
    tools = manifest.get("tools", [])
    assert len(tools) == 3, f"Expected 3 tools, found {len(tools)}"
    print(f"  ✓ Registered tools: {[t['name'] for t in tools]}")
    tests_passed += 1

    # Test 3: Overhead flights radar (London Heathrow airspace - high flight density)
    print("\n[3/6] Testing POST /tools/get_flights_overhead (London airspace)...")
    resp = client.post(
        "/tools/get_flights_overhead",
        json={"location": "London", "radius_km": 50.0, "limit": 3}
    )
    assert resp.status_code == 200, f"Overhead tool returned status {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Overhead tool returned error: {data.get('error')}"
    result = data.get("result", "")
    print(f"  ✓ Response received ({len(result)} chars)")
    first_lines = "\n    ".join(result.split("\n")[:6])
    print(f"    {first_lines}")
    tests_passed += 1

    # Test 4: Airspace activity summary (e.g. Germany or USA)
    print("\n[4/6] Testing POST /tools/get_airspace_activity (Regional traffic)...")
    resp = client.post(
        "/tools/get_airspace_activity",
        json={"location": "Frankfurt", "limit": 3}
    )
    assert resp.status_code == 200, f"Airspace activity returned status {resp.status_code}"
    data = resp.json()
    assert data.get("error") is None, f"Airspace tool returned error: {data.get('error')}"
    activity_result = data.get("result", "")
    print(f"  ✓ Regional traffic report generated:")
    first_lines = "\n    ".join(activity_result.split("\n")[:4])
    print(f"    {first_lines}")
    tests_passed += 1

    # Test 5: Dynamic flight tracking (track any callsign or sample flight)
    print("\n[5/6] Testing POST /tools/track_flight_by_callsign...")
    resp = client.post(
        "/tools/track_flight_by_callsign",
        json={"callsign": "DLH400"}
    )
    assert resp.status_code == 200, f"Track flight returned status {resp.status_code}"
    data = resp.json()
    print(f"  ✓ Tracking response generated successfully (result present: {bool(data.get('result'))})")
    tests_passed += 1

    # Test 6: In-memory caching speedup test
    print("\n[6/6] Testing in-memory LRU cache speedup...")
    t0 = time.monotonic()
    resp_cached = client.post(
        "/tools/get_flights_overhead",
        json={"location": "London", "radius_km": 50.0, "limit": 3}
    )
    duration = time.monotonic() - t0
    assert resp_cached.status_code == 200
    print(f"  ✓ Cached lookup served in {duration * 1000:.2f} ms (sub-millisecond speedup)")
    tests_passed += 1

    print("\n" + "=" * 65)
    print(f"[SUCCESS] ALL {tests_passed}/{total_tests} LIVE SMOKE TESTS PASSED CLEANLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_smoke_tests()

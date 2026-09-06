"""Live end-to-end smoke test suite for Omi CityBikes Integration App.

Runs live integration tests against the public CityBikes API (api.citybik.es).
Asserts only on the app's fixed response templates and stable network IDs,
preventing false-failures from upstream third-party catalog fluctuations.
"""

import importlib.util
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

# Load models
spec_models = importlib.util.spec_from_file_location("models", os.path.join(_plugin_dir, "models.py"))
models_mod = importlib.util.module_from_spec(spec_models)
sys.modules["models"] = models_mod
spec_models.loader.exec_module(models_mod)

# Load main
spec_main = importlib.util.spec_from_file_location("main", os.path.join(_plugin_dir, "main.py"))
main_mod = importlib.util.module_from_spec(spec_main)
sys.modules["main"] = main_mod
spec_main.loader.exec_module(main_mod)

app = main_mod.app

try:
    from starlette.testclient import TestClient
except ImportError:
    from fastapi.testclient import TestClient


def run_smoke_tests():
    print("=" * 65)
    print("Starting Live Smoke Tests: Omi CityBikes App (api.citybik.es)")
    print("=" * 65)

    client = TestClient(app)

    # 1. Health check
    print("\n[1/8] Testing GET /health...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    assert resp.json().get("status") == "ok"
    print(f"  PASS: {resp.json()}")

    # 2. Omi manifest
    print("\n[2/8] Testing GET /.well-known/omi-tools.json...")
    resp = client.get("/.well-known/omi-tools.json")
    assert resp.status_code == 200, f"Manifest failed: {resp.text}"
    manifest = resp.json()
    assert len(manifest["tools"]) == 4, "Expected 4 tools registered"
    assert manifest.get("schema_version") == "v1"
    print(f"  PASS: {manifest['name']} ({len(manifest['tools'])} tools registered)")

    # 3. Search bike networks (by city name)
    print("\n[3/8] Testing POST /tools/search_bike_networks (query='Paris')...")
    resp = client.post("/tools/search_bike_networks", json={"query": "Paris", "limit": 3})
    assert resp.status_code == 200, f"Search networks failed: {resp.text}"
    data = resp.json()
    assert data["error"] is None, f"Unexpected error: {data['error']}"
    assert "bike network(s) matching 'Paris'" in data["result"]
    assert "- Network ID:" in data["result"]
    print("  PASS: Formatted network listing received:")
    print("  " + "\n  ".join(data["result"].split("\n")[:3]))

    # 4. Search bike networks (by stable network_id)
    print("\n[4/8] Testing POST /tools/search_bike_networks (query='citi-bike-nyc')...")
    resp = client.post("/tools/search_bike_networks", json={"query": "citi-bike-nyc", "limit": 1})
    assert resp.status_code == 200, f"Search networks failed: {resp.text}"
    data = resp.json()
    assert data["error"] is None, f"Unexpected error: {data['error']}"
    assert "citi-bike-nyc" in data["result"]
    assert "- Network ID: `citi-bike-nyc`" in data["result"]
    print("  PASS: Verified stable network ID lookup")

    # 5. Nearby stations with coordinate distance sorting
    print("\n[5/8] Testing POST /tools/get_nearby_bike_stations (citi-bike-nyc coords)...")
    resp = client.post(
        "/tools/get_nearby_bike_stations",
        json={
            "network_id": "citi-bike-nyc",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "limit": 3,
        },
    )
    assert resp.status_code == 200, f"Nearby stations failed: {resp.text}"
    data = resp.json()
    assert data["error"] is None, f"Unexpected error: {data['error']}"
    assert "### 🚲 Bike Stations:" in data["result"]
    assert "bikes available" in data["result"]
    print("  PASS: Stations located with live counts and distance labels:")
    print("  " + "\n  ".join(data["result"].split("\n")[:4]))

    # Dynamically extract the first station name from results for step 6
    station_lines = [l.strip() for l in data["result"].split("\n") if l.strip().startswith("1. **")]
    target_station = station_lines[0].split("**")[1] if station_lines else "Broadway"

    # 6. Station detailed status (dynamically queried)
    print(f"\n[6/8] Testing POST /tools/check_bike_station_status ('{target_station}')...")
    resp = client.post(
        "/tools/check_bike_station_status",
        json={"network_id": "citi-bike-nyc", "station_id_or_name": target_station},
    )
    assert resp.status_code == 200, f"Station status failed: {resp.text}"
    data = resp.json()
    assert data["error"] is None, f"Unexpected error: {data['error']}"
    assert "## 🚲 Station Status:" in data["result"]
    assert "- **Available Bikes**:" in data["result"]
    print("  PASS: Live station availability details confirmed:")
    print("  " + "\n  ".join(data["result"].split("\n")[:4]))

    # 7. City overview (using stable network_id)
    print("\n[7/8] Testing POST /tools/get_city_bike_overview (network='citi-bike-nyc')...")
    resp = client.post("/tools/get_city_bike_overview", json={"city_or_network": "citi-bike-nyc"})
    assert resp.status_code == 200, f"City overview failed: {resp.text}"
    data = resp.json()
    assert data["error"] is None, f"Unexpected error: {data['error']}"
    assert "## 🚲 Micro-Mobility Overview:" in data["result"]
    assert "- **Active Stations**:" in data["result"]
    assert "- **Available Bikes Fleet**:" in data["result"]
    assert "- **Network Availability**:" in data["result"]
    print("  PASS: Citywide fleet statistics verified:")
    print("  " + "\n  ".join(data["result"].split("\n")[:5]))

    # 8. In-memory caching speedup verification
    print("\n[8/8] Testing In-Memory Cache Performance...")
    t0 = time.time()
    resp_cached = client.post("/tools/search_bike_networks", json={"query": "Paris"})
    t_cached = time.time() - t0
    assert resp_cached.status_code == 200
    assert resp_cached.json()["error"] is None
    assert t_cached < 0.5, f"Cache lookup took {t_cached:.4f}s, expected < 0.5s for in-memory hit"
    print(f"  PASS: Cache hit resolved in {t_cached * 1000:.2f}ms (< 500ms bound)")

    print("\n" + "=" * 65)
    print("ALL 8 LIVE SMOKE TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_smoke_tests()

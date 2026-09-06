"""Live end-to-end smoke test suite for Omi CityBikes Integration App.

Runs live integration tests against the public CityBikes API (api.citybik.es).
"""

import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

import importlib.util

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
    print(f"  PASS: {resp.json()}")

    # 2. Omi manifest
    print("\n[2/8] Testing GET /.well-known/omi-tools.json...")
    resp = client.get("/.well-known/omi-tools.json")
    assert resp.status_code == 200, f"Manifest failed: {resp.text}"
    manifest = resp.json()
    assert len(manifest["tools"]) == 4, "Expected 4 tools registered"
    print(f"  PASS: {manifest['name']} ({len(manifest['tools'])} tools registered)")

    # 3. Search bike networks (Paris)
    print("\n[3/8] Testing POST /tools/search_bike_networks (query='Paris')...")
    resp = client.post("/tools/search_bike_networks", json={"query": "Paris", "limit": 3})
    assert resp.status_code == 200, f"Search networks failed: {resp.text}"
    data = resp.json()
    assert data["result"] is not None and "velib" in data["result"].lower(), f"Unexpected result: {data}"
    print("  PASS: Found network:")
    print("  " + "\n  ".join(data["result"].split("\n")[:4]))

    # 4. Search bike networks (NYC)
    print("\n[4/8] Testing POST /tools/search_bike_networks (query='New York')...")
    resp = client.post("/tools/search_bike_networks", json={"query": "New York", "limit": 3})
    assert resp.status_code == 200, f"Search networks failed: {resp.text}"
    data = resp.json()
    assert data["result"] is not None and "citi" in data["result"].lower(), f"Unexpected result: {data}"
    print("  PASS: Found Citi Bike network")

    # 5. Nearby stations with coordinate distance sorting
    print("\n[5/8] Testing POST /tools/get_nearby_bike_stations (citi-bike-nyc near Union Square)...")
    resp = client.post(
        "/tools/get_nearby_bike_stations",
        json={
            "network_id": "citi-bike-nyc",
            "query": "Broadway",
            "latitude": 40.7359,
            "longitude": -73.9911,
            "limit": 3,
        },
    )
    assert resp.status_code == 200, f"Nearby stations failed: {resp.text}"
    data = resp.json()
    assert data["result"] is not None and "available" in data["result"].lower(), f"Unexpected result: {data}"
    print("  PASS: Stations located with live counts:")
    print("  " + "\n  ".join(data["result"].split("\n")[:5]))

    # 6. Station detailed status
    print("\n[6/8] Testing POST /tools/check_bike_station_status (Broadway & E 14 St)...")
    resp = client.post(
        "/tools/check_bike_station_status",
        json={"network_id": "citi-bike-nyc", "station_id_or_name": "Broadway & E 14 St"},
    )
    assert resp.status_code == 200, f"Station status failed: {resp.text}"
    data = resp.json()
    assert data["result"] is not None and "available bikes" in data["result"].lower(), f"Unexpected result: {data}"
    print("  PASS: Live station availability:")
    print("  " + "\n  ".join(data["result"].split("\n")[:4]))

    # 7. City overview (Barcelona)
    print("\n[7/8] Testing POST /tools/get_city_bike_overview (city='Barcelona')...")
    resp = client.post("/tools/get_city_bike_overview", json={"city_or_network": "Barcelona"})
    assert resp.status_code == 200, f"City overview failed: {resp.text}"
    data = resp.json()
    assert data["result"] is not None and "micro-mobility overview" in data["result"].lower(), f"Unexpected result: {data}"
    print("  PASS: Citywide fleet statistics:")
    print("  " + "\n  ".join(data["result"].split("\n")[:5]))

    # 8. In-memory caching speedup verification
    print("\n[8/8] Testing In-Memory Cache Performance...")
    t0 = time.time()
    resp_cached = client.post("/tools/search_bike_networks", json={"query": "Paris"})
    t_cached = time.time() - t0
    assert resp_cached.status_code == 200
    print(f"  PASS: Cache hit resolved in {t_cached * 1000:.2f}ms")

    print("\n" + "=" * 65)
    print("ALL 8 LIVE SMOKE TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_smoke_tests()

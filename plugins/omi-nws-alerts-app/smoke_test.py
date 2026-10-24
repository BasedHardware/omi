"""Live Smoke Test for NWS Severe Weather Alerts Omi App.

Exercises live endpoints against the actual upstream National Weather Service
API (api.weather.gov) to verify real network transport, User-Agent compliance,
GeoJSON parsing, and response formatting.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
import httpx

from main import app


def run_smoke_tests() -> None:
    print("=" * 60)
    print("Starting Live Smoke Tests for NWS Severe Weather Alerts Plugin")
    print("=" * 60)

    with TestClient(app) as client:
        # 1. Health check & Upstream Reachability
        print("\n[1/5] Testing /health endpoint...")
        try:
            resp = client.get("/health")
            print(f"Status Code: {resp.status_code}")
            data = resp.json()
            print(f"Response: {data}")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            assert data.get("status") in {
                "healthy",
                "degraded",
            }, "Unexpected health status"
            print("PASS: /health verified.")
        except Exception as e:
            print(f"FAIL /health: {e}")
            sys.exit(1)

        # 2. Omi Tools Manifest
        print("\n[2/5] Testing /.well-known/omi-tools.json...")
        try:
            resp = client.get("/.well-known/omi-tools.json")
            print(f"Status Code: {resp.status_code}")
            manifest = resp.json()
            tools = manifest.get("tools", [])
            print(f"Manifest schema_version: {manifest.get('schema_version')}")
            print(f"Discovered {len(tools)} tools: {[t['name'] for t in tools]}")
            assert resp.status_code == 200
            assert len(tools) == 3
            tool_names = {t["name"] for t in tools}
            assert "get_active_alerts_by_location" in tool_names
            assert "get_active_alerts_by_state" in tool_names
            assert "get_national_severe_weather_summary" in tool_names
            print("PASS: Tools manifest verified.")
        except Exception as e:
            print(f"FAIL manifest: {e}")
            sys.exit(1)

        # 3. Live Location Alerts (Dallas, TX: 32.7767, -96.7970)
        print("\n[3/5] Testing /tools/get-active-alerts-by-location (Dallas, TX)...")
        try:
            resp = client.post(
                "/tools/get-active-alerts-by-location",
                json={"latitude": 32.7767, "longitude": -96.7970},
            )
            print(f"Status Code: {resp.status_code}")
            data = resp.json()
            result_text = data.get("result", "")
            print(f"Result Snippet (first 150 chars):\n{result_text[:150]}...")
            assert resp.status_code == 200
            assert "result" in data
            assert len(result_text) > 0
            print("PASS: Live location alerts verified.")
        except Exception as e:
            print(f"FAIL location alerts: {e}")
            sys.exit(1)

        # 4. Live State Alerts (Texas - 'TX')
        print("\n[4/5] Testing /tools/get-active-alerts-by-state (TX)...")
        try:
            resp = client.post(
                "/tools/get-active-alerts-by-state",
                json={"state": "Texas", "limit": 3},
            )
            print(f"Status Code: {resp.status_code}")
            data = resp.json()
            result_text = data.get("result", "")
            print(f"Result Snippet (first 150 chars):\n{result_text[:150]}...")
            assert resp.status_code == 200
            assert "result" in data
            assert len(result_text) > 0
            print("PASS: Live state alerts verified.")
        except Exception as e:
            print(f"FAIL state alerts: {e}")
            sys.exit(1)

        # 5. Live National Severe Weather Summary
        print("\n[5/5] Testing /tools/get-national-severe-weather-summary...")
        try:
            resp = client.post(
                "/tools/get-national-severe-weather-summary",
                json={"severity_threshold": "Severe", "limit": 3},
            )
            print(f"Status Code: {resp.status_code}")
            data = resp.json()
            result_text = data.get("result", "")
            print(f"Result Snippet (first 150 chars):\n{result_text[:150]}...")
            assert resp.status_code == 200
            assert "result" in data
            assert "US National Severe Weather Situation Summary" in result_text
            print("PASS: Live national summary verified.")
        except Exception as e:
            print(f"FAIL national summary: {e}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("ALL LIVE SMOKE TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_smoke_tests()

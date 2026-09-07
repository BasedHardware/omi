"""Live end-to-end smoke test for NASA Space & Astronomy Intelligence Omi Integration Plugin.

Verifies live upstream communication with https://api.nasa.gov and https://images-api.nasa.gov.
Assertions rely strictly on structural properties and dynamically returned data
to ensure robustness against live space feeds and discoveries.
"""

import sys
from fastapi.testclient import TestClient
from main import app


def run_smoke_tests() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("🚀 Starting NASA Space & Astronomy Intelligence Smoke Tests...")

    with TestClient(app) as client:
        # 1. Health Probe
        print("\n1. Testing GET /health...")
        resp = client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") in [
            "healthy",
            "degraded",
        ], f"Unexpected status: {data}"
        assert "upstream_nasa_api" in data
        print(
            f"   ✓ Health probe passed: status={data.get('status')}, upstream={data.get('upstream_nasa_api')}"
        )

        # 2. Omi Tools Manifest
        print("\n2. Testing GET /.well-known/omi-tools.json...")
        resp = client.get("/.well-known/omi-tools.json")
        assert resp.status_code == 200
        manifest = resp.json()
        tools = manifest.get("tools", [])
        tool_names = [t.get("name") for t in tools]
        expected_tools = [
            "get_astronomy_picture",
            "get_near_earth_asteroids",
            "search_nasa_media",
        ]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool {expected} in manifest"
        for t in tools:
            assert (
                t.get("auth_required") is False
            ), f"Expected auth_required=False in {t.get('name')}"
            assert "status_message" in t, f"Missing status_message in {t.get('name')}"
        print(
            f"   ✓ Manifest contains all {len(expected_tools)} expected tools with auth_required=False & status_message: {', '.join(tool_names)}"
        )

        # 3. Get Astronomy Picture of the Day (APOD)
        print("\n3. Testing POST /tools/get-astronomy-picture...")
        resp = client.post("/tools/get-astronomy-picture", json={})
        if resp.status_code == 502 and "429" in resp.text:
            print(
                "   ⚠️ Upstream NASA DEMO_KEY rate limit reached (429) - live upstream responded correctly"
            )
        else:
            assert (
                resp.status_code == 200
            ), f"Expected 200, got {resp.status_code}: {resp.text}"
            apod_text = resp.json().get("result", "")
            assert "NASA Astronomy Picture of the Day" in apod_text
            assert "**Title:**" in apod_text
            assert "Media Link" in apod_text
            print(
                "   ✓ APOD retrieved successfully with full title, explanation, and media links"
            )

        # 4. Get Near-Earth Asteroids (NeoWs)
        print("\n4. Testing POST /tools/get-near-earth-asteroids...")
        resp = client.post("/tools/get-near-earth-asteroids", json={"limit": 3})
        if resp.status_code == 502 and "429" in resp.text:
            print(
                "   ⚠️ Upstream NASA DEMO_KEY rate limit reached (429) - live upstream responded correctly"
            )
        else:
            assert (
                resp.status_code == 200
            ), f"Expected 200, got {resp.status_code}: {resp.text}"
            neo_text = resp.json().get("result", "")
            assert "Near-Earth Asteroid Tracking" in neo_text
            assert (
                "Miss Distance:" in neo_text
                or "No near-Earth asteroid encounters" in neo_text
            )
            print(
                "   ✓ Near-Earth asteroid trajectories successfully tracked and calculated"
            )

        # 5. Search NASA Official Media Archive (James Webb)
        print("\n5. Testing POST /tools/search-nasa-media with query 'James Webb'...")
        resp = client.post(
            "/tools/search-nasa-media", json={"query": "James Webb", "limit": 3}
        )
        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        media_text = resp.json().get("result", "")
        assert "NASA Official Media Archive" in media_text
        assert "NASA ID:" in media_text
        print(
            "   ✓ NASA multimedia search returned valid mission assets and preview links"
        )

        # 6. Search with Zero Results
        print("\n6. Testing POST /tools/search-nasa-media with non-existent query...")
        resp = client.post(
            "/tools/search-nasa-media", json={"query": "zzzzzzzzzzzzzzzzzzzzzzzzz"}
        )
        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        empty_text = resp.json().get("result", "")
        assert "No NASA multimedia records found" in empty_text
        print("   ✓ Empty search handled gracefully")

        # 7. Out-of-range APOD Date (handles upstream HTTP 400 with friendly message)
        print(
            "\n7. Testing POST /tools/get-astronomy-picture with out-of-range date (1990-01-01)..."
        )
        resp = client.post("/tools/get-astronomy-picture", json={"date": "1990-01-01"})
        if resp.status_code == 502 and "429" in resp.text:
            print(
                "   ⚠️ Upstream NASA DEMO_KEY rate limit reached (429) - live upstream responded correctly"
            )
        else:
            assert (
                resp.status_code == 200
            ), f"Expected 200, got {resp.status_code}: {resp.text}"
            out_of_range_text = resp.json().get("result", "")
            assert (
                "No NASA Astronomy Picture of the Day found for date '1990-01-01'"
                in out_of_range_text
            )
            print(
                f"   ✓ Out-of-range date handled gracefully: {out_of_range_text.strip()}"
            )

    print("\n🎉 ALL NASA LIVE SMOKE TESTS PASSED CLEANLY!")


if __name__ == "__main__":
    run_smoke_tests()

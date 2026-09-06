"""Live end-to-end smoke test for The Metropolitan Museum of Art Omi Integration Plugin.

Verifies live upstream communication with https://collectionapi.metmuseum.org.
Assertions rely strictly on structural properties and dynamically extracted IDs
to ensure robustness against live museum collection updates.
"""

import re
import sys
from fastapi.testclient import TestClient
from main import app


def run_smoke_tests() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("🚀 Starting Metropolitan Museum of Art Smoke Tests...")

    with TestClient(app) as client:
        # 1. Health Probe
        print("\n1. Testing GET /health...")
        resp = client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") in ["healthy", "degraded"], f"Unexpected status: {data}"
        assert "upstream_met_api" in data
        print(f"   ✓ Health probe passed: status={data.get('status')}, upstream={data.get('upstream_met_api')}")

        # 2. Omi Tools Manifest
        print("\n2. Testing GET /.well-known/omi-tools.json...")
        resp = client.get("/.well-known/omi-tools.json")
        assert resp.status_code == 200
        manifest = resp.json()
        tools = manifest.get("tools", [])
        tool_names = [t.get("name") for t in tools]
        expected_tools = ["search_artworks", "get_artwork_details", "list_departments", "get_department_highlights"]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool {expected} in manifest"
        print(f"   ✓ Manifest contains all {len(expected_tools)} expected tools: {', '.join(tool_names)}")

        # 3. List Curatorial Departments
        print("\n3. Testing POST /tools/list-departments...")
        resp = client.post("/tools/list-departments", json={})
        assert resp.status_code == 200
        dept_text = resp.json().get("response", "")
        assert "Curatorial Departments" in dept_text
        assert "European Paintings" in dept_text or "Asian Art" in dept_text
        print(f"   ✓ Curatorial departments listed successfully ({len(dept_text.splitlines())} lines returned)")

        # 4. Search Artworks (Monet)
        print("\n4. Testing POST /tools/search-artworks with query 'Monet'...")
        resp = client.post("/tools/search-artworks", json={"query": "Monet", "limit": 3, "has_images": True})
        assert resp.status_code == 200
        search_text = resp.json().get("response", "")
        assert "Search Results" in search_text
        assert "Claude Monet" in search_text or "Monet" in search_text
        print("   ✓ Search returned valid artwork results")

        # Extract dynamic Object ID from search response
        id_matches = re.findall(r"Object ID:\*\*\s*`(\d+)`", search_text)
        assert len(id_matches) > 0, f"Could not dynamically extract Object ID from search response: {search_text}"
        dynamic_object_id = int(id_matches[0])
        print(f"   ✓ Dynamically extracted Object ID `{dynamic_object_id}` from live search")

        # 5. Get Artwork Details for Dynamically Extracted Object ID
        print(f"\n5. Testing POST /tools/get-artwork-details for Object ID {dynamic_object_id}...")
        resp = client.post("/tools/get-artwork-details", json={"object_id": dynamic_object_id})
        assert resp.status_code == 200
        detail_text = resp.json().get("response", "")
        assert "**Artist:**" in detail_text
        assert "**Department:**" in detail_text
        assert "**Medium:**" in detail_text
        assert "View on Met Collection" in detail_text
        print("   ✓ Artwork details successfully retrieved with complete metadata card")

        # 6. Get Department Highlights (Department 11 - European Paintings)
        print("\n6. Testing POST /tools/get-department-highlights for Department 11 (European Paintings)...")
        resp = client.post("/tools/get-department-highlights", json={"department_id": 11, "limit": 3})
        assert resp.status_code == 200
        highlights_text = resp.json().get("response", "")
        assert "Highlights from European Paintings" in highlights_text
        assert "Object ID:" in highlights_text
        print("   ✓ Department highlights returned successfully")

        # 7. Search with Zero Results
        print("\n7. Testing POST /tools/search-artworks with non-existent query...")
        resp = client.post("/tools/search-artworks", json={"query": "zzzzzzzzzzzzzzzzzzz", "artist_or_culture": True})
        assert resp.status_code == 200
        empty_text = resp.json().get("response", "")
        assert "No artworks found in The Metropolitan Museum of Art collection" in empty_text
        print("   ✓ Empty search handled gracefully")

    print("\n🎉 ALL LIVE SMOKE TESTS PASSED CLEANLY!")


if __name__ == "__main__":
    run_smoke_tests()

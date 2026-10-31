"""Standalone integration smoke test for Omi Classical Poetry & Verse app.

Tests the full HTTP surface via httpx ASGITransport against live PoetryDB,
verifying routing, manifest schema, response content, and error contracts.
"""

import asyncio
import httpx

from main import REQUEST_TIMEOUT_SECONDS, USER_AGENT, app


async def run_smoke_tests():
    print("==================================================")
    print(" Starting Omi Classical Poetry & Verse Smoke Tests ")
    print("==================================================")

    # Initialize lifespan HTTP client for internal upstream calls
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as upstream_client:
        app.state.http_client = upstream_client

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health Check
            print("\n[1/8] Testing Health Endpoint (GET /health)...")
            res = await client.get("/health")
            assert res.status_code == 200, f"Health check failed with status {res.status_code}"
            h = res.json()
            assert h.get("status") == "ok", f"Health status not ok: {h}"
            assert h.get("service") == "omi-poetry-app", f"Unexpected service name: {h}"
            print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}, Version: {h.get('version')}")

            # 2. Manifest Schema
            print("\n[2/8] Testing Omi Chat Tools Manifest (GET /.well-known/omi-tools.json)...")
            res = await client.get("/.well-known/omi-tools.json")
            assert res.status_code == 200, f"Manifest check failed: {res.status_code}"
            manifest = res.json()
            assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
            assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
            tools = manifest.get("tools", [])
            assert len(tools) == 4, f"Expected 4 tools, got {len(tools)}"
            for tool in tools:
                assert "name" in tool and "endpoint" in tool and "method" in tool, f"Incomplete manifest tool: {tool}"
                assert tool["method"] == "POST", f"Expected method POST, got {tool['method']}"
                assert tool["auth_required"] is False, "auth_required should be False"
            tool_names = [t["name"] for t in tools]
            print(f"  ✓ Manifest verified. Registered tools: {tool_names}")

            # 3. Random Poem (General)
            print("\n[3/8] Testing POST /tools/get_random_poem (General)...")
            res = await client.post("/tools/get_random_poem", json={"max_lines": 20})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result in response"
            print("  ✓ Result preview:\n   ", "\n    ".join(data["result"].splitlines()[:6]))

            # 4. Random Poem by Specific Author (Shakespeare Sonnet)
            print("\n[4/8] Testing POST /tools/get_random_poem (Shakespeare, 15 lines max)...")
            res = await client.post("/tools/get_random_poem", json={"author": "Shakespeare", "max_lines": 15})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "Shakespeare" in data["result"], "Expected Shakespeare in result"
            print("  ✓ Result preview:\n   ", "\n    ".join(data["result"].splitlines()[:6]))

            # 5. Search Poems by Author (Emily Dickinson)
            print("\n[5/8] Testing POST /tools/search_poems_by_author (Emily Dickinson)...")
            res = await client.post("/tools/search_poems_by_author", json={"author": "Emily Dickinson", "max_results": 2})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "Dickinson" in data["result"], "Expected Dickinson in result"
            print("  ✓ Result preview:\n   ", "\n    ".join(data["result"].splitlines()[:6]))

            # 6. Get Poem by Title (Ozymandias)
            print("\n[6/8] Testing POST /tools/get_poem_by_title ('Ozymandias')...")
            res = await client.post("/tools/get_poem_by_title", json={"title": "Ozymandias"})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "Ozymandias" in data["result"], "Expected Ozymandias in result"
            assert "antique land" in data["result"] or "King of Kings" in data["result"], "Expected poem verse text"
            print("  ✓ Result preview:\n   ", "\n    ".join(data["result"].splitlines()[:6]))

            # 7. List Poets (Filter by Shelley)
            print("\n[7/8] Testing POST /tools/list_poets (Filter: 'Shelley')...")
            res = await client.post("/tools/list_poets", json={"query": "Shelley"})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "Shelley" in data["result"], "Expected Shelley in poets list"
            print("  ✓ Result:\n   ", data["result"].replace("\n", "\n    "))

            # 8. Error Handling & Null-Exclusion Contract
            print("\n[8/8] Testing Validation Error Handling & Null-Exclusion...")
            res = await client.post("/tools/search_poems_by_author", json={})
            assert res.status_code == 200
            err_data = res.json()
            assert "error" in err_data, "Expected error for missing author"
            assert "result" not in err_data, f"Result must be excluded on error, got: {err_data}"
            print(f"  ✓ Validation error handled correctly: {err_data['error']}")

    print("\n==================================================")
    print(" ALL 8 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

"""Standalone integration smoke test for Omi Open Trivia & Voice Quiz app.

Tests the full HTTP surface via httpx ASGITransport, verifying routing,
request validation handlers, and ChatToolResponse serialization contracts.
"""

import asyncio
import httpx

from main import REQUEST_TIMEOUT_SECONDS, USER_AGENT, app


async def run_smoke_tests():
    print("==================================================")
    print(" Starting Omi Open Trivia & Quiz App Smoke Tests ")
    print("==================================================")

    # Initialize lifespan HTTP client for internal upstream calls
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as upstream_client:
        app.state.http_client = upstream_client

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health Check
            print("\n[1/7] Testing Health Endpoint (GET /health)...")
            res = await client.get("/health")
            assert res.status_code == 200, f"Health check failed: {res.status_code}"
            h = res.json()
            assert h.get("status") == "ok", f"Health status not ok: {h}"
            assert h.get("service") == "omi-trivia-quiz-app", f"Unexpected service: {h}"
            print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}, Version: {h.get('version')}")

            # 2. Manifest Schema
            print("\n[2/7] Testing Omi Chat Tools Manifest (GET /.well-known/omi-tools.json)...")
            res = await client.get("/.well-known/omi-tools.json")
            assert res.status_code == 200, f"Manifest check failed: {res.status_code}"
            manifest = res.json()
            assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
            assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
            tools = manifest.get("tools", [])
            assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"
            for tool in tools:
                assert "name" in tool and "endpoint" in tool and "method" in tool, f"Incomplete tool manifest: {tool}"
                assert tool["method"] == "POST", f"Expected method POST, got {tool['method']}"
                assert tool["auth_required"] is False, "auth_required should be False"
            tool_names = [t["name"] for t in tools]
            print(f"  ✓ Manifest verified. Registered tools: {tool_names}")

            # 3. Multiple Choice Question (Pinned question_type='multiple')
            print("\n[3/7] Testing POST /tools/get_trivia_question (Science, multiple choice)...")
            payload_science = {
                "category": "Science",
                "difficulty": "medium",
                "question_type": "multiple",
            }
            res = await client.post("/tools/get_trivia_question", json=payload_science)
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result in response"
            result_text = data["result"]
            assert "Question" in result_text, "Expected Question in result"
            assert "Options:" in result_text, "Expected Options in multiple choice result"
            assert "Correct Answer:" in result_text, "Expected Correct Answer in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            print("  Waiting 5s for OpenTDB rate limit...")
            await asyncio.sleep(5.1)

            # 4. History Multiple Choice Question
            print("\n[4/7] Testing POST /tools/get_trivia_question (History)...")
            payload_history = {"category": "History", "question_type": "multiple"}
            res = await client.post("/tools/get_trivia_question", json=payload_history)
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result in response"
            print("  ✓ Result:\n   ", data["result"].replace("\n", "\n    "))

            print("  Waiting 5s for OpenTDB rate limit...")
            await asyncio.sleep(5.1)

            # 5. Quick True/False Challenge
            print("\n[5/7] Testing POST /tools/get_true_false_quiz (True/False)...")
            res = await client.post("/tools/get_true_false_quiz", json={"difficulty": "easy"})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result in response"
            result_text = data["result"]
            assert "True/False" in result_text, "Expected True/False in result"
            print("  ✓ Result:\n   ", result_text.replace("\n", "\n    "))

            # 6. List Categories
            print("\n[6/7] Testing POST /tools/list_trivia_categories...")
            res = await client.post("/tools/list_trivia_categories", json={})
            assert res.status_code == 200, f"Status error: {res.status_code}"
            data = res.json()
            assert "error" not in data, f"Unexpected error: {data}"
            assert "result" in data, "Expected result in response"
            assert "Science" in data["result"], "Expected Science in categories"
            assert "History" in data["result"], "Expected History in categories"
            print(f"  ✓ Listed categories successfully ({len(data['result'].splitlines())} lines)")

            # 7. Error Handling & Null-Exclusion Contract
            print("\n[7/7] Testing Validation Error Handling & Null-Exclusion Contract...")
            res = await client.post("/tools/get_trivia_question", json={"difficulty": "impossible_level"})
            assert res.status_code == 200
            err_data = res.json()
            assert "error" in err_data, "Expected error for invalid difficulty"
            assert "result" not in err_data, f"Result must be excluded on error, got: {err_data}"
            print(f"  ✓ Validation error handled correctly: {err_data['error']}")

    print("\n==================================================")
    print(" ALL 7 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

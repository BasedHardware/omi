"""Standalone integration smoke test for Omi Open Trivia & Voice Quiz app."""

import asyncio
import httpx

from main import (
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    app,
    get_trivia_question,
    get_true_false_quiz,
    health,
    list_trivia_categories,
    omi_tools,
)
from models import (
    GetTriviaQuestionRequest,
    ListCategoriesRequest,
    QuickTrueFalseQuizRequest,
)


async def run_smoke_tests():
    print("==================================================")
    print(" Starting Omi Open Trivia & Quiz App Smoke Tests ")
    print("==================================================")

    # 1. Health Check
    print("\n[1/6] Testing Health Endpoint...")
    h = await health()
    assert h.get("status") == "ok", f"Health check failed: {h}"
    print(f"  ✓ Status: {h.get('status')}, Service: {h.get('service')}")

    # 2. Manifest Schema
    print("\n[2/6] Testing Omi Chat Tools Manifest...")
    manifest = await omi_tools()
    assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
    assert manifest.get("auth", {}).get("type") == "none", "Auth must be none"
    tools = manifest.get("tools", [])
    assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"
    tool_names = [t["name"] for t in tools]
    print(f"  ✓ Manifest verified. Registered tools: {tool_names}")

    # Initialize client for live endpoints
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        app.state.http_client = client

        # 3. Multiple Choice Question
        print("\n[3/6] Testing /tools/get_trivia_question (Science)...")
        res_science = await get_trivia_question(GetTriviaQuestionRequest(category="Science", difficulty="medium"))
        assert res_science.error is None, f"Unexpected error: {res_science.error}"
        assert "Question" in res_science.result, "Expected Question in result"
        assert "Options:" in res_science.result, "Expected Options in result"
        assert "Correct Answer:" in res_science.result, "Expected Correct Answer in result"
        print("  ✓ Result:\n   ", res_science.result.replace("\n", "\n    "))

        print("  Waiting 5s for OpenTDB rate limit...")
        await asyncio.sleep(5.1)

        # 4. History Multiple Choice Question
        print("\n[4/6] Testing /tools/get_trivia_question (History)...")
        res_history = await get_trivia_question(GetTriviaQuestionRequest(category="History"))
        assert res_history.error is None, f"Unexpected error: {res_history.error}"
        print("  ✓ Result:\n   ", res_history.result.replace("\n", "\n    "))

        print("  Waiting 5s for OpenTDB rate limit...")
        await asyncio.sleep(5.1)

        # 5. Quick True/False Challenge
        print("\n[5/6] Testing /tools/get_true_false_quiz (True/False)...")
        res_tf = await get_true_false_quiz(QuickTrueFalseQuizRequest(difficulty="easy"))
        assert res_tf.error is None, f"Unexpected error: {res_tf.error}"
        assert "True/False" in res_tf.result, "Expected True/False in result"
        print("  ✓ Result:\n   ", res_tf.result.replace("\n", "\n    "))

        # 6. List Categories
        print("\n[6/6] Testing /tools/list_trivia_categories...")
        res_cats = await list_trivia_categories(ListCategoriesRequest())
        assert res_cats.error is None, f"Unexpected error: {res_cats.error}"
        assert "Science" in res_cats.result, "Expected Science in categories"
        assert "History" in res_cats.result, "Expected History in categories"
        print(f"  ✓ Listed categories successfully ({len(res_cats.result.splitlines())} lines)")

    print("\n==================================================")
    print(" ALL 6 SMOKE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

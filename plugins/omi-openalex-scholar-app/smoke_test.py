"""Comprehensive local live smoke test for OpenAlex Scholar Omi app."""

import asyncio
import httpx
from main import (
    app,
    health,
    omi_tools,
    search_research_papers,
    get_author_profile,
    get_institution_summary,
    explore_academic_topic,
    DEFAULT_USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
    OPENALEX_BASE_URL,
)
from models import (
    SearchResearchPapersRequest,
    GetAuthorProfileRequest,
    GetInstitutionSummaryRequest,
    ExploreAcademicTopicRequest,
)


async def run_smoke_tests():
    print("--- 1. Testing Health Endpoint ---")
    h = await health()
    assert h.get("status") == "ok", f"Health check failed: {h}"
    assert h.get("app") == "omi-openalex-scholar-app"
    print("[PASS] Health check passed:", h)

    print("\n--- 2. Testing Omi Manifest Endpoint ---")
    manifest = await omi_tools()
    assert manifest.get("schema_version") == "1.0", "Manifest schema version mismatch"
    assert len(manifest.get("tools", [])) == 4, "Expected 4 tools in manifest"
    tool_names = [t["name"] for t in manifest["tools"]]
    assert "explore_academic_topic" in tool_names, "Expected explore_academic_topic in tools"
    print("[PASS] Manifest verified. Registered tools:", tool_names)

    # Initialize client for tool handlers
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(
        base_url=OPENALEX_BASE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers=headers,
        follow_redirects=True,
    ):
        print("\n--- 3. Testing Research Papers Search Tool (/tools/search_research_papers) ---")
        paper_req = SearchResearchPapersRequest(query="attention is all you need", limit=3)
        paper_res = await search_research_papers(paper_req)
        print("Paper Result:\n", paper_res.result)
        assert paper_res.result is not None, f"Expected result, got error: {paper_res.error}"
        assert "Attention Is All You Need" in paper_res.result, "Expected landmark paper in results"
        assert "Citations:" in paper_res.result

        print("\n--- 4. Testing Author Profile Tool (/tools/get_author_profile) ---")
        author_req = GetAuthorProfileRequest(author_name="Yann LeCun")
        author_res = await get_author_profile(author_req)
        print("Author Result:\n", author_res.result)
        assert author_res.result is not None, f"Expected result, got error: {author_res.error}"
        assert "Yann LeCun" in author_res.result
        assert "h-index:" in author_res.result
        assert "Last known institution(s):" in author_res.result

        print("\n--- 5. Testing Institution Summary Tool (/tools/get_institution_summary) ---")
        inst_req = GetInstitutionSummaryRequest(institution_name="Stanford University")
        inst_res = await get_institution_summary(inst_req)
        print("Institution Result:\n", inst_res.result)
        assert inst_res.result is not None, f"Expected result, got error: {inst_res.error}"
        assert "Stanford University" in inst_res.result
        assert "Total Research Publications:" in inst_res.result

        print("\n--- 6. Testing Academic Topic Exploration Tool (/tools/explore_academic_topic) ---")
        topic_req = ExploreAcademicTopicRequest(topic="Quantum Computing")
        topic_res = await explore_academic_topic(topic_req)
        print("Topic Result:\n", topic_res.result)
        assert topic_res.result is not None, f"Expected result, got error: {topic_res.error}"
        assert "Domain Hierarchy:" in topic_res.result
        assert "Total Works:" in topic_res.result

        # Also test backward-compatibility alias with concept field
        concept_req = ExploreAcademicTopicRequest(concept="CRISPR Gene Editing")
        concept_res = await explore_academic_topic(concept_req)
        assert concept_res.result is not None, f"Expected result, got error: {concept_res.error}"
        assert "Research Topic:" in concept_res.result

        print("\n--- 7. Testing Validation and Error Handling ---")
        # Empty search results handling
        missing_paper_req = SearchResearchPapersRequest(query="xyznonexistentquery1234567890abc", limit=3)
        missing_paper_res = await search_research_papers(missing_paper_req)
        print("Missing Query Handling:\n", missing_paper_res.result)
        assert "No academic research papers found" in missing_paper_res.result

        # Missing author handling
        missing_author_req = GetAuthorProfileRequest(author_name="ZzzNonExistentAuthor998877")
        missing_author_res = await get_author_profile(missing_author_req)
        print("Missing Author Handling:\n", missing_author_res.result)
        assert "No researcher profile found" in missing_author_res.result

        # Validation checks
        try:
            SearchResearchPapersRequest(query="   ")
            assert False, "Should have rejected whitespace-only query"
        except ValueError:
            pass

        try:
            GetAuthorProfileRequest(author_name="a")
            assert False, "Should have rejected author name shorter than 2 chars"
        except ValueError:
            pass

        try:
            ExploreAcademicTopicRequest(topic="   ")
            assert False, "Should have rejected whitespace-only topic"
        except ValueError:
            pass

    print("\n[SUCCESS] ALL 7 SMOKE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())

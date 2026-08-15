"""Unit tests for MCP transcript search helpers (#6621)."""

from utils.conversations.mcp_transcript_search import (
    attach_match_snippets_to_conversations,
    build_transcript_match_snippets,
    merge_summary_and_transcript_ids,
    resolve_mcp_conversation_search_ids,
)


def test_snippet_finds_transcript_phrase_summary_would_miss():
    segments = [
        {"id": "s0", "text": "Let's talk about lunch plans", "start": 0.0, "end": 2.0, "speaker_id": 0},
        {
            "id": "s1",
            "text": "The Q3 budget review is next Tuesday at noon",
            "start": 2.5,
            "end": 6.0,
            "speaker_id": 1,
        },
        {"id": "s2", "text": "Sounds good", "start": 6.5, "end": 7.0, "is_user": True},
    ]
    snippets = build_transcript_match_snippets(segments, "budget review")
    assert len(snippets) == 1
    assert "budget review" in snippets[0]["text"].lower()
    assert snippets[0]["segment_id"] == "s1"
    assert snippets[0]["start"] == 2.5
    assert snippets[0]["end"] == 6.0
    assert snippets[0]["start_ms"] == 2500
    assert snippets[0]["end_ms"] == 6000
    # Context neighbor included
    assert "lunch plans" in snippets[0]["text"]


def test_snippet_matches_noncontiguous_multi_term_tokens():
    """All query tokens present but separated must still match (fuzzy multi-term path)."""
    segments = [
        {
            "id": "s1",
            "text": "We need to review the quarterly budget after lunch",
            "start": 1.0,
            "end": 3.0,
        }
    ]
    snippets = build_transcript_match_snippets(segments, "budget review")
    assert len(snippets) == 1
    assert snippets[0]["segment_id"] == "s1"


def test_snippet_rejects_partial_multi_term_tokens():
    segments = [{"id": "s1", "text": "Only the budget looks fine today", "start": 0.0, "end": 1.0}]
    assert build_transcript_match_snippets(segments, "budget review") == []


def test_snippet_empty_when_no_transcript_match():
    segments = [{"id": "s0", "text": "Weather looks fine", "start": 0.0, "end": 1.0}]
    assert build_transcript_match_snippets(segments, "budget review") == []


def test_merge_prefers_transcript_ids_then_summary():
    assert merge_summary_and_transcript_ids(["t1", "t2"], ["s1", "t1", "s2"], limit=3) == ["t1", "t2", "s1"]


def test_resolve_merges_chunk_hits_ahead_of_summary_vectors():
    ids = resolve_mcp_conversation_search_ids(
        "uid",
        "budget",
        limit=5,
        query_vectors=lambda *a, **k: ["summary-only", "shared"],
        search_transcript_chunks=lambda *a, **k: [
            {"conversation_id": "transcript-hit", "chunk_index": 0, "score": 0.9},
            {"conversation_id": "shared", "chunk_index": 1, "score": 0.8},
        ],
    )
    assert ids == ["transcript-hit", "shared", "summary-only"]


def test_resolve_shares_one_query_vector_across_searches():
    captured = {"embed_calls": 0, "summary_vector": None, "chunk_vector": None}
    shared = [0.11, 0.22]

    def _embed(q):
        captured["embed_calls"] += 1
        assert q == "budget"
        return shared

    def _query_vectors(query, uid, starts_at=None, ends_at=None, k=None, query_vector=None):
        captured["summary_vector"] = query_vector
        return ["s1"]

    def _chunks(uid, query, limit=None, starts_at=None, ends_at=None, query_vector=None):
        captured["chunk_vector"] = query_vector
        return []

    ids = resolve_mcp_conversation_search_ids(
        "uid",
        "budget",
        limit=5,
        query_vectors=_query_vectors,
        search_transcript_chunks=_chunks,
        embed_query=_embed,
    )
    assert ids == ["s1"]
    assert captured["embed_calls"] == 1
    assert captured["summary_vector"] is shared
    assert captured["chunk_vector"] is shared


def test_resolve_fail_open_when_chunk_search_raises():
    def _boom(*a, **k):
        raise RuntimeError("pinecone down")

    ids = resolve_mcp_conversation_search_ids(
        "uid",
        "budget",
        limit=5,
        query_vectors=lambda *a, **k: ["only-summary"],
        search_transcript_chunks=_boom,
    )
    assert ids == ["only-summary"]


def test_resolve_ignores_non_list_chunk_results():
    ids = resolve_mcp_conversation_search_ids(
        "uid",
        "budget",
        limit=5,
        query_vectors=lambda *a, **k: ["v1"],
        search_transcript_chunks=lambda *a, **k: "not-a-list",  # type: ignore[arg-type,return-value]
    )
    assert ids == ["v1"]


def test_attach_snippets_to_conversations():
    convs = [
        {
            "id": "c1",
            "transcript_segments": [
                {"id": "s1", "text": "Mention the ACME contract tonight", "start": 1.0, "end": 2.0},
            ],
        }
    ]
    out = attach_match_snippets_to_conversations(convs, "ACME contract")
    assert out[0]["id"] == "c1"
    assert len(out[0]["match_snippets"]) == 1
    assert "ACME contract" in out[0]["match_snippets"][0]["text"]

"""Unit tests for MCP transcript search helpers (#6621)."""

from datetime import datetime, timezone
from unittest.mock import patch

from utils.conversations.mcp_transcript_search import (
    ChatTranscriptSearch,
    attach_match_snippets_to_conversations,
    build_transcript_match_snippets,
    chat_transcript_coverage_note,
    chat_transcript_excerpts,
    merge_chat_conversation_ids,
    merge_summary_and_transcript_ids,
    resolve_mcp_conversation_search_ids,
    search_chat_transcript_chunks,
)


def test_chat_chunk_search_shares_embedding_and_bounds_candidates():
    vector = [0.11, 0.22]
    captured = {}

    def search(uid, query, **kwargs):
        captured.update(uid=uid, query=query, **kwargs)
        return [
            {'conversation_id': 'spoken-only', 'chunk_index': 0},
            {'conversation_id': 'spoken-only', 'chunk_index': 1},
            {'conversation_id': 'other', 'chunk_index': 0},
        ]

    result = search_chat_transcript_chunks(
        'u1',
        'invoice amount',
        limit=5,
        starts_at=10,
        ends_at=20,
        query_vector=vector,
        index_available=True,
        search_transcript_chunks=search,
    )
    assert result.searched is True
    assert result.conversation_ids == ['spoken-only', 'other']
    assert captured['query_vector'] is vector
    assert captured['limit'] == 15
    assert captured['starts_at'] == 10 and captured['ends_at'] == 20


def test_chat_excerpt_is_rebuilt_from_accessible_conversation_only():
    started_at = datetime(2026, 8, 18, tzinfo=timezone.utc)

    def conv(cid, text, **kwargs):
        return {'id': cid, 'started_at': started_at, 'transcript_segments': [{'text': text}], **kwargs}

    search = ChatTranscriptSearch(
        [
            {'conversation_id': 'visible', 'chunk_index': 0},
            {'conversation_id': 'locked', 'chunk_index': 0},
            {'conversation_id': 'discarded', 'chunk_index': 0},
            {'conversation_id': 'missing', 'chunk_index': 0},
            {'conversation_id': 'visible', 'chunk_index': 99},
        ],
        True,
    )
    excerpts = chat_transcript_excerpts(
        [
            conv('visible', 'The renewal is 47 dollars'),
            conv('locked', 'secret', is_locked=True),
            conv('discarded', 'erased', discarded=True),
        ],
        search,
    )
    assert list(excerpts) == ['visible']
    assert '47 dollars' in excerpts['visible']
    assert 'secret' not in str(excerpts) and 'erased' not in str(excerpts)


def test_chat_chunk_search_failure_does_not_claim_transcript_coverage():
    with patch('utils.conversations.mcp_transcript_search.record_fallback') as fallback:
        result = search_chat_transcript_chunks(
            'u1',
            'invoice',
            limit=5,
            starts_at=None,
            ends_at=None,
            query_vector=[1.0],
            index_available=True,
            search_transcript_chunks=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')),
        )
    assert result == ChatTranscriptSearch([], False)
    assert 'cannot establish' in chat_transcript_coverage_note(result.searched)
    fallback.assert_called_once()


def test_chat_merge_preserves_keyword_rank_and_reserves_both_vector_sources():
    assert merge_chat_conversation_ids(
        ['exact-1', 'exact-2', 'exact-3', 'exact-4', 'exact-5'],
        [f'transcript-{index}' for index in range(30)],
        [f'summary-{index}' for index in range(5)],
        limit=5,
    ) == [
        'exact-1',
        'exact-2',
        'exact-3',
        'exact-4',
        'exact-5',
        'transcript-0',
        'transcript-1',
        'summary-0',
        'summary-1',
        'summary-2',
    ]


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


def test_snippet_unicode_multi_term_match():
    segments = [
        {"id": "s0", "text": "Reunión sobre el presupuesto Q3", "start": 1.0, "end": 3.0, "speaker_id": 0},
    ]
    snippets = build_transcript_match_snippets(segments, "presupuesto Q3")
    assert len(snippets) == 1
    assert "presupuesto" in snippets[0]["text"].casefold()


def test_merge_typesense_page_prefers_transcript_on_page_one():
    from utils.conversations.mcp_transcript_search import merge_typesense_page_with_transcript_hits

    assert merge_typesense_page_with_transcript_hits(
        ["ts1", "ts2"],
        ["tr1", "ts1"],
        page=1,
        per_page=3,
    ) == ["tr1", "ts1", "ts2"]


def test_merge_typesense_page_keeps_typesense_order_after_page_one():
    from utils.conversations.mcp_transcript_search import merge_typesense_page_with_transcript_hits

    assert merge_typesense_page_with_transcript_hits(
        ["ts3", "ts4"],
        ["tr1"],
        page=2,
        per_page=10,
    ) == ["ts3", "ts4"]


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


def test_transcript_only_phrase_gets_timed_snippet_for_seek():
    """Typesense title/overview miss spoken words; hydrated segments still yield seek times."""
    out = attach_match_snippets_to_conversations(
        [
            {
                "id": "spoken-only",
                "structured": {"title": "Standup", "overview": "Team sync"},
                "transcript_segments": [
                    {
                        "id": "s1",
                        "text": "Ship the ACME contract by Friday",
                        "start": 42.0,
                        "end": 46.5,
                    },
                ],
            }
        ],
        "ACME contract",
    )
    assert len(out) == 1
    snippet = out[0]["match_snippets"][0]
    assert snippet["start"] == 42.0
    assert snippet["end"] == 46.5
    assert snippet["start_ms"] == 42000

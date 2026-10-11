"""Async fanout/bound tests for POST /v1/conversations/search and the transcript branch."""

import asyncio
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import routers.conversations as conv  # noqa: E402
import database.vector_db as vector_db  # noqa: E402
import utils.conversations.mcp_transcript_search as mcp_transcript_search  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from models.conversation import SearchRequest  # noqa: E402
from utils.conversations.mcp_transcript_search import search_transcript_conversation_ids  # noqa: E402
from utils.conversations.search import ConversationSearchUnavailableError  # noqa: E402


def _conv(cid: str) -> dict:
    return {'id': cid, 'is_locked': False}


def _typesense_result(ids: list, page: int = 1, per_page: int = 10) -> dict:
    return {
        'items': [{'id': i} for i in ids],
        'total_pages': 1,
        'current_page': page,
        'per_page': per_page,
    }


def _install_base_stubs(monkeypatch, *, ids=('c1',), page: int = 1, per_page: int = 10):
    monkeypatch.setattr(conv, 'search_conversations', lambda **kwargs: _typesense_result(list(ids), page, per_page))
    monkeypatch.setattr(
        conv.conversations_db,
        'get_conversations_by_id_without_photos',
        lambda uid, conversation_ids, include_discarded=False: [_conv(i) for i in conversation_ids],
    )
    monkeypatch.setattr(conv, 'redact_conversations_for_list', lambda convs: convs)
    monkeypatch.setattr(conv, 'attach_match_snippets_to_conversations', lambda convs, query: convs)


def test_typesense_and_transcript_branches_run_concurrently(monkeypatch):
    entered = {'typesense': asyncio.Event(), 'transcript': asyncio.Event()}
    release = asyncio.Event()

    first_call = {'done': False}

    async def gated_run_blocking(_executor, fn, *args, **kwargs):
        if not first_call['done']:
            first_call['done'] = True
            entered['typesense'].set()
            await release.wait()
        return fn(*args, **kwargs)

    async def gated_transcript(*_args, **_kwargs):
        entered['transcript'].set()
        await release.wait()
        return ['t1']

    _install_base_stubs(monkeypatch)
    monkeypatch.setattr(conv, 'run_blocking', gated_run_blocking)
    monkeypatch.setattr(conv, 'search_transcript_conversation_ids', gated_transcript)
    monkeypatch.setattr(vector_db, 'index', object())

    async def drive():
        task = asyncio.create_task(conv.search_conversations_endpoint(SearchRequest(query='budget'), uid='u1'))
        await asyncio.wait_for(asyncio.gather(entered['typesense'].wait(), entered['transcript'].wait()), timeout=5)
        release.set()
        return await task

    result = asyncio.run(drive())
    assert [item['id'] for item in result['items']] == ['t1', 'c1']


def test_hung_embedding_fails_open_to_keyword_rows(monkeypatch):
    _install_base_stubs(monkeypatch)
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(mcp_transcript_search, 'TRANSCRIPT_EMBED_TIMEOUT_SECONDS', 0.05)

    async def hung_embed(_query):
        await asyncio.sleep(3600)
        return []

    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(aembed_query=hung_embed))
    monkeypatch.setattr(vector_db, 'search_transcript_chunks', lambda *a, **k: pytest.fail('should time out'))

    result = asyncio.run(conv.search_conversations_endpoint(SearchRequest(query='budget'), uid='u1'))
    assert [item['id'] for item in result['items']] == ['c1']


def test_semantic_branch_skipped_when_index_unconfigured(monkeypatch):
    _install_base_stubs(monkeypatch)
    monkeypatch.setattr(vector_db, 'index', None)
    transcript = AsyncMock(return_value=['t1'])
    monkeypatch.setattr(conv, 'search_transcript_conversation_ids', transcript)

    result = asyncio.run(conv.search_conversations_endpoint(SearchRequest(query='budget'), uid='u1'))
    assert [item['id'] for item in result['items']] == ['c1']
    transcript.assert_not_awaited()


@pytest.mark.parametrize('page,query', [(2, 'budget'), (1, '')])
def test_semantic_branch_skipped_for_later_pages_and_empty_query(monkeypatch, page, query):
    _install_base_stubs(monkeypatch, page=page)
    monkeypatch.setattr(vector_db, 'index', object())
    transcript = AsyncMock(return_value=[])
    monkeypatch.setattr(conv, 'search_transcript_conversation_ids', transcript)

    result = asyncio.run(
        conv.search_conversations_endpoint(SearchRequest(query=query, page=page, start_date='2026-01-01'), uid='u1')
    )
    assert result['current_page'] == page
    transcript.assert_not_awaited()


@pytest.mark.parametrize('per_page,expected_cap', [(100, 200), (250, 250)])
def test_page_one_candidate_cap_bounds_hydration_ids(monkeypatch, per_page, expected_cap):
    captured = {}

    async def fake_transcript(*_args, **kwargs):
        captured['helper_limit'] = kwargs['limit']
        return [f't{i}' for i in range(expected_cap + 50)]

    _install_base_stubs(monkeypatch, per_page=per_page)
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(conv, 'search_transcript_conversation_ids', fake_transcript)

    def capture_hydration(uid, conversation_ids, include_discarded=False):
        captured['hydrated_ids'] = list(conversation_ids)
        return [_conv(i) for i in conversation_ids]

    monkeypatch.setattr(conv.conversations_db, 'get_conversations_by_id_without_photos', capture_hydration)

    asyncio.run(conv.search_conversations_endpoint(SearchRequest(query='q', per_page=per_page), uid='u1'))
    assert captured['helper_limit'] == expected_cap
    assert len(captured['hydrated_ids']) == expected_cap


def test_snippets_only_attached_to_returned_page_rows(monkeypatch):
    captured = {}

    def attach(convs, _query):
        captured['ids'] = [c['id'] for c in convs]
        return convs

    _install_base_stubs(monkeypatch, ids=('c1',), per_page=1)
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(conv, 'search_transcript_conversation_ids', AsyncMock(return_value=['t1', 't2', 't3']))
    monkeypatch.setattr(conv, 'attach_match_snippets_to_conversations', attach)

    result = asyncio.run(conv.search_conversations_endpoint(SearchRequest(query='q', per_page=1), uid='u1'))
    assert len(result['items']) == 1
    assert captured['ids'] == [result['items'][0]['id']]


def test_transcript_helper_embeds_once_and_passes_timeout(monkeypatch):
    captured: dict[str, Any] = {}

    async def embed(query):
        captured['query'] = query
        return [0.1, 0.2]

    def chunks(uid, query, limit=None, starts_at=None, ends_at=None, query_vector=None, timeout_seconds=None):
        captured['vector'] = query_vector
        captured['timeout'] = timeout_seconds
        return [{'conversation_id': 'tr1'}]

    ids = asyncio.run(
        search_transcript_conversation_ids('u1', 'budget', limit=5, search_transcript_chunks=chunks, embed_query=embed)
    )
    assert ids == ['tr1']
    assert captured['query'] == 'budget'
    assert captured['vector'] == [0.1, 0.2]
    assert captured['timeout'] == 5.0


def test_transcript_helper_fails_open_on_embed_timeout(monkeypatch):
    monkeypatch.setattr(mcp_transcript_search, 'TRANSCRIPT_EMBED_TIMEOUT_SECONDS', 0.05)

    async def hung(_query):
        await asyncio.sleep(3600)
        return []

    ids = asyncio.run(
        search_transcript_conversation_ids(
            'u1', 'budget', limit=5, search_transcript_chunks=lambda *a, **k: [], embed_query=hung
        )
    )
    assert ids == []


def test_transcript_helper_fails_open_on_chunk_search_error():
    def boom(*_a, **_k):
        raise RuntimeError('pinecone down')

    async def embed(_q):
        return [0.0]

    ids = asyncio.run(
        search_transcript_conversation_ids('u1', 'budget', limit=5, search_transcript_chunks=boom, embed_query=embed)
    )
    assert ids == []


def test_typesense_unavailable_returns_503(monkeypatch):
    def unavailable(**_kwargs):
        raise ConversationSearchUnavailableError('Typesense search temporarily unavailable')

    _install_base_stubs(monkeypatch)
    monkeypatch.setattr(conv, 'search_conversations', unavailable)
    monkeypatch.setattr(vector_db, 'index', None)

    async def inline_run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(conv, 'run_blocking', inline_run_blocking)

    app = FastAPI()
    app.include_router(conv.router)
    app.dependency_overrides[conv.auth.get_current_user_uid] = lambda: 'u1'
    resp = TestClient(app, raise_server_exceptions=False).post('/v1/conversations/search', json={'query': 'budget'})
    assert resp.status_code == 503


def test_search_transcript_chunks_passes_pinecone_request_timeout(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return {
                'matches': [{'metadata': {'conversation_id': 'c9', 'created_at': 1, 'chunk_index': 0}, 'score': 0.5}]
            }

    def forbidden_embed(_query):
        raise AssertionError('embed_query must not run when query_vector is supplied')

    monkeypatch.setattr(vector_db, 'index', FakeIndex())
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=forbidden_embed))

    rows = vector_db.search_transcript_chunks('u1', 'budget', limit=10, query_vector=[0.1, 0.2], timeout_seconds=5.0)
    assert captured['_request_timeout'] == 5.0
    assert captured['vector'] == [0.1, 0.2]
    assert rows == [{'conversation_id': 'c9', 'created_at': 1, 'chunk_index': 0, 'score': 0.5}]

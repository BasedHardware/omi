"""Durability contracts for X raw-source memory extraction."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.memories import Memory, MemoryCategory
from utils import x_connector
from utils.memory.memory_system import MemorySystem


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.anyio
async def test_sync_retries_pending_raw_posts_when_a_prior_canonical_write_failed(monkeypatch):
    """Raw dedupe cannot hide a source whose prior memory write failed."""
    post = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}
    saved_counts = iter([1, 0])
    extraction_calls = []
    integration_updates = []

    monkeypatch.setattr(x_connector, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(x_connector.users_db, 'get_integration', lambda *args: {'x_user_id': 'x-user'})
    monkeypatch.setattr(
        x_connector.users_db,
        'set_integration',
        lambda _uid, _key, payload: integration_updates.append(payload),
    )
    monkeypatch.setattr(x_connector.x_posts_db, 'get_newest_tweet_id', lambda _uid: None)
    monkeypatch.setattr(x_connector.x_posts_db, 'save_x_posts', lambda _uid, _posts: next(saved_counts))
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'get_pending_memory_extraction_posts',
        lambda _uid, _limit: [post],
    )
    monkeypatch.setattr(x_connector.x_posts_db, 'count_x_posts', lambda _uid: 1)
    monkeypatch.setattr(x_connector, 'upsert_x_post_vectors_batch', lambda *args: None)
    monkeypatch.setattr(x_connector, 'get_valid_access_token', lambda _uid: _async_value('token'))
    monkeypatch.setattr(x_connector, 'fetch_tweets', lambda *args: _async_value([post]))
    monkeypatch.setattr(x_connector, 'fetch_bookmarks', lambda *args: _async_value([]))

    def extract(_uid, posts):
        extraction_calls.append(posts)
        if len(extraction_calls) == 1:
            raise HTTPException(status_code=503, detail='canonical write unavailable')
        return 1

    monkeypatch.setattr(x_connector, '_extract_and_index', extract)

    with pytest.raises(HTTPException, match='canonical write unavailable'):
        await x_connector.sync_x_for_user('uid-1')
    result = await x_connector.sync_x_for_user('uid-1')

    assert extraction_calls == [[post], [post]]
    assert result['new_posts'] == 0
    assert result['memories_created'] == 1
    assert integration_updates[-1]['memory_count'] == 1


def test_pending_x_source_is_acknowledged_only_after_memory_writes_succeed(monkeypatch):
    post = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}
    acknowledgements = []
    memory = Memory(content='User prefers tea', category=MemoryCategory.interesting)

    monkeypatch.setattr(x_connector, 'extract_memories_from_text', lambda *args: [memory])
    monkeypatch.setattr(x_connector, 'resolve_memory_system', lambda *args, **kwargs: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'mark_memory_extraction_completed',
        lambda uid, post_ids: acknowledgements.append((uid, post_ids)),
    )

    class FailingMemoryService:
        def __init__(self, **_kwargs):
            pass

        def write(self, *_args, **_kwargs):
            raise HTTPException(status_code=503, detail='canonical write unavailable')

    monkeypatch.setattr(x_connector, 'MemoryService', FailingMemoryService)

    with pytest.raises(HTTPException, match='canonical write unavailable'):
        x_connector._extract_and_index('uid-1', [post])

    assert acknowledgements == []

    monkeypatch.setattr(x_connector, 'extract_memories_from_text', lambda *args: [])
    assert x_connector._extract_and_index('uid-1', [post]) == 0
    assert acknowledgements == [('uid-1', ['post-1'])]


async def _async_value(value):
    return value

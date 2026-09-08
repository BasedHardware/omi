"""Durability contracts for X raw-source memory extraction."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.memories import Memory, MemoryCategory
from models.memory_contracts import MemoryExtractionError
from utils import x_connector


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
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'mark_memory_extraction_completed',
        lambda uid, post_ids: acknowledgements.append((uid, post_ids)),
    )

    class FailingMemoryService:
        def __init__(self, **_kwargs):
            pass

        def create_external_memory_batch(self, *_args, **_kwargs):
            raise HTTPException(status_code=503, detail='canonical write unavailable')

    monkeypatch.setattr(x_connector, 'MemoryService', FailingMemoryService)

    with pytest.raises(HTTPException, match='canonical write unavailable'):
        x_connector._extract_and_index('uid-1', [post])

    assert acknowledgements == []

    monkeypatch.setattr(x_connector, 'extract_memories_from_text', lambda *args: [])
    assert x_connector._extract_and_index('uid-1', [post]) == 0
    assert acknowledgements == [('uid-1', ['post-1'])]


def test_scheduled_flex_extraction_is_strict_and_fenced_before_acknowledgement(monkeypatch):
    post = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}
    model = object()
    events = []

    def extract(*_args, **kwargs):
        events.append(('extract', kwargs))
        return []

    monkeypatch.setattr(x_connector, 'extract_memories_from_text', extract)
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'mark_memory_extraction_completed',
        lambda _uid, _post_ids: events.append(('ack', None)),
    )

    assert (
        x_connector._extract_and_index(
            'uid-1',
            [post],
            llm=model,
            result_guard=lambda: events.append(('guard', None)),
        )
        == 0
    )
    assert events == [
        ('extract', {'strict': True, 'llm': model}),
        ('guard', None),
        ('ack', None),
    ]


def test_scheduled_x_flex_deferral_remains_pending_without_acknowledgement(monkeypatch):
    from utils.memory.promotion_flex import PromotionFlexDeferred

    post = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}
    acknowledgements = []
    monkeypatch.setattr(
        x_connector,
        'extract_memories_from_text',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PromotionFlexDeferred('capacity')),
    )
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'mark_memory_extraction_completed',
        lambda uid, post_ids: acknowledgements.append((uid, post_ids)),
    )

    with pytest.raises(PromotionFlexDeferred, match='capacity'):
        x_connector._extract_and_index('uid-1', [post], llm=object())

    assert acknowledgements == []


def test_provider_5xx_skips_only_the_failed_chunk_and_leaves_it_pending(monkeypatch):
    """A strict provider 5xx on one chunk cannot starve the batches behind it in the same cycle, and the failed chunk stays pending for the next sync."""
    first_post = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}
    second_post = {'id': 'post-2', 'text': 'Second batch', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}

    calls = []
    acknowledgements = []
    created_batches = []
    recorded = []

    def extract(*_args, **_kwargs):
        chunk_text = _args[1]
        calls.append(chunk_text)
        if 'I prefer tea' in chunk_text:
            raise MemoryExtractionError('external_text_memory_extractor')
        return [Memory(content='Second batch memory', category=MemoryCategory.interesting)]

    class RecordingMemoryService:
        def __init__(self, **_kwargs):
            pass

        def create_external_memory_batch(self, _uid, memory_dbs, **_kwargs):
            created_batches.append(memory_dbs)

    monkeypatch.setattr(x_connector, 'MEMORY_BATCH_CHARS', 10)
    monkeypatch.setattr(x_connector, 'extract_memories_from_text', extract)
    monkeypatch.setattr(x_connector, 'MemoryService', RecordingMemoryService)
    monkeypatch.setattr(x_connector, 'capture_memory_write', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        x_connector.x_posts_db,
        'mark_memory_extraction_completed',
        lambda _uid, post_ids: acknowledgements.append(post_ids),
    )
    monkeypatch.setattr(x_connector, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

    total = x_connector._extract_and_index('uid-1', [first_post, second_post], llm=object())

    assert total == 1
    assert len(calls) == 2, 'a 5xx chunk must not starve the batches behind it in the same cycle'
    assert acknowledgements == [['post-2']], 'the failed chunk stays pending for the next sync'
    assert len(created_batches) == 1 and len(created_batches[0]) == 1
    assert recorded and recorded[0]['reason'] == 'provider_5xx'
    assert recorded[0]['to_mode'] == 'chunk_deferred'
    assert recorded[0]['outcome'] == 'degraded'


async def _async_value(value):
    return value

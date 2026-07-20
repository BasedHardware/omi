"""Behavioral coverage for the live conversation cache used by listen transcripts."""

import pytest

from routers.listen.transcripts import ConversationCache


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class Loader:
    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, conversation_id: str):
        self.calls.append(conversation_id)
        return {
            'id': conversation_id,
            'transcript_segments': [],
            'data_protection_level': 'enhanced' if conversation_id == 'conv-2' else 'standard',
        }


@pytest.mark.anyio
async def test_conversation_cache_reuses_current_generation_and_updates_segments():
    loader = Loader()
    cache = ConversationCache(loader, monotonic=lambda: 10.0)

    first = await cache.get('conv-1')
    second = await cache.get('conv-1')
    cache.update_segments([{'id': 'segment-1'}])

    assert first is second
    assert second['transcript_segments'] == [{'id': 'segment-1'}]
    assert loader.calls == ['conv-1']


@pytest.mark.anyio
async def test_conversation_cache_refreshes_for_new_or_stale_generation():
    loader = Loader()
    now = [0.0]
    cache = ConversationCache(loader, monotonic=lambda: now[0], refresh_seconds=30.0)

    await cache.get('conv-1')
    now[0] = 29.9
    await cache.get('conv-1')
    now[0] = 30.0
    await cache.get('conv-1')
    await cache.get('conv-2')

    assert loader.calls == ['conv-1', 'conv-1', 'conv-2']
    assert cache.protection_level == 'enhanced'


@pytest.mark.anyio
async def test_conversation_cache_force_refresh_and_clear_read_through_again():
    loader = Loader()
    cache = ConversationCache(loader, monotonic=lambda: 1.0)

    await cache.get('conv-1')
    await cache.get('conv-1', force_refresh=True)
    cache.clear()
    await cache.get('conv-1')

    assert loader.calls == ['conv-1', 'conv-1', 'conv-1']

"""Hermetic construction tests for the shared Redis client factories."""

import pytest

import database.redis_db as redis_db


@pytest.mark.asyncio
async def test_async_redis_client_uses_shared_config_and_is_cached(monkeypatch):
    import redis.asyncio as async_redis

    built = []

    class _Recorder:
        def __init__(self, **kwargs):
            built.append(kwargs)

    monkeypatch.setattr(redis_db, '_async_redis_client', None)
    monkeypatch.setattr(async_redis, 'Redis', _Recorder)
    monkeypatch.setenv('REDIS_DB_HOST', 'redis.internal')
    monkeypatch.setenv('REDIS_DB_PORT', '6380')
    monkeypatch.setenv('REDIS_DB_PASSWORD', 'cache-secret')

    first = await redis_db.get_async_redis_client()
    second = await redis_db.get_async_redis_client()

    assert first is second
    assert len(built) == 1
    assert built[0] == {
        'host': 'redis.internal',
        'port': 6380,
        'username': 'default',
        'password': 'cache-secret',
        'health_check_interval': 0,
        'decode_responses': True,
    }

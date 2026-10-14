"""Exercise the actual shared-presence Lua, including stale and overflow states."""

import fakeredis.aioredis
import pytest
from unittest.mock import AsyncMock

from utils.stt import demand_presence


@pytest.fixture
async def presence(monkeypatch):
    client = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(demand_presence, '_client', client)
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_multiple_sockets_unknown_visible_hidden_and_close(presence):
    update = demand_presence.update_presence
    assert await update('user', 'old-build', 'unknown')
    assert await update('user', 'phone', 'hidden')
    assert await update('user', 'old-build', 'visible')
    assert not await update('user', 'old-build', 'hidden')
    assert await update('user', 'desktop', 'visible')
    await update('user', 'desktop', 'close')
    assert not await update('user', 'phone', 'hidden')
    assert not await update('other-user', 'other-phone', 'hidden')


@pytest.mark.asyncio
async def test_stale_or_malformed_member_is_visible(presence):
    key = demand_presence._key('user')
    for value in ('hidden:1', 'unknown:9999999999', 'invalid'):
        await presence.hset(key, 'stale', value)
        assert await demand_presence.update_presence('user', 'phone', 'hidden')
    await demand_presence.update_presence('user', 'stale', 'close')
    assert not await demand_presence.update_presence('user', 'phone', 'hidden')
    assert await presence.ttl(key) > 0


@pytest.mark.asyncio
async def test_overflow_keeps_every_sibling_visible(presence):
    for i in range(32):
        assert not await demand_presence.update_presence('user', str(i), 'hidden')
    assert await demand_presence.update_presence('user', 'overflow-client', 'unknown')
    assert await demand_presence.update_presence('user', '0', 'hidden')
    assert await presence.hlen(demand_presence._key('user')) == 33


@pytest.mark.asyncio
async def test_redis_failure_requires_vendor(monkeypatch):
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(side_effect=OSError)))
    assert await demand_presence.update_presence('user', 'phone', 'hidden')


def test_stage_and_user_keys_are_isolated(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    first = demand_presence._key('private-user')
    assert 'private-user' not in first
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert first != demand_presence._key('private-user')

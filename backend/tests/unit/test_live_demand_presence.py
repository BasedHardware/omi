"""Exercise the actual shared-presence Lua, including stale and overflow states."""

import fakeredis.aioredis
import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from utils.stt import demand_presence
from routers.listen import demand_routing


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
    assert (await update('user', 'old-build', 'unknown')).visible
    assert (await update('user', 'phone', 'hidden')).visible
    assert (await update('user', 'old-build', 'visible')).visible
    assert not (await update('user', 'old-build', 'hidden')).visible
    assert (await update('user', 'desktop', 'visible')).visible
    await update('user', 'desktop', 'close')
    assert not (await update('user', 'phone', 'hidden')).visible
    assert not (await update('other-user', 'other-phone', 'hidden')).visible


@pytest.mark.asyncio
async def test_stale_or_malformed_member_is_visible(presence):
    key = demand_presence._key('user')
    for value in ('hidden:1', 'unknown:9999999999', 'invalid'):
        await presence.hset(key, 'stale', value)
        assert (await demand_presence.update_presence('user', 'phone', 'hidden')).visible
    await demand_presence.update_presence('user', 'stale', 'close')
    assert not (await demand_presence.update_presence('user', 'phone', 'hidden')).visible
    assert await presence.ttl(key) > 0


@pytest.mark.asyncio
async def test_overflow_keeps_every_sibling_visible(presence):
    for i in range(32):
        assert not (await demand_presence.update_presence('user', str(i), 'hidden')).visible
    assert (await demand_presence.update_presence('user', 'overflow-client', 'unknown')).visible
    assert (await demand_presence.update_presence('user', '0', 'hidden')).visible
    assert await presence.hlen(demand_presence._key('user')) == 33


@pytest.mark.asyncio
async def test_redis_failure_requires_vendor(monkeypatch):
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(side_effect=OSError)))
    snapshot = await demand_presence.update_presence('user', 'phone', 'hidden')
    assert snapshot.visible and snapshot.unavailable


def test_stage_and_user_keys_are_isolated(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    first = demand_presence._key('private-user')
    assert 'private-user' not in first
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert first != demand_presence._key('private-user')


@pytest.mark.asyncio
async def test_presence_outage_emits_once_then_rearms_after_recovery(monkeypatch):
    failed = demand_presence.PresenceSnapshot(True, unavailable=True)
    healthy = demand_presence.PresenceSnapshot(False)
    monkeypatch.setattr(demand_routing, 'update_presence', AsyncMock(side_effect=[failed, failed, healthy, failed]))
    fallback = MagicMock()
    monkeypatch.setattr(demand_routing, 'record_fallback', fallback)
    receiver = SimpleNamespace(host=SimpleNamespace(request=SimpleNamespace(uid='user')))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    assert await demand.publish()
    assert await demand.publish()
    assert not await demand.publish()
    assert await demand.publish()
    assert fallback.call_count == 2
    assert fallback.call_args.kwargs['reason'] == 'gate_unavailable'
    assert fallback.call_args.kwargs['from_mode'] == 'demand_presence'


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', [None, 'invalid', False, 2])
async def test_unknown_presence_response_requires_vendor(monkeypatch, reply):
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(return_value=reply)))
    snapshot = await demand_presence.update_presence('user', 'phone', 'hidden')
    assert snapshot.visible and snapshot.unavailable

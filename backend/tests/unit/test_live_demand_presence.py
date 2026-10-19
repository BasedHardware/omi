"""Exercise the actual shared-presence Lua, including stale and overflow states."""

import asyncio
import logging

import fakeredis.aioredis
import pytest
from redis import exceptions as redis_exceptions
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


FAILED = demand_presence.PresenceSnapshot(True, unavailable=True, error='timeout')
HIDDEN = demand_presence.PresenceSnapshot(False)


def _routing(monkeypatch, replies, *, eligible=True, clock=None):
    monkeypatch.setattr(demand_routing, 'update_presence', AsyncMock(side_effect=replies))
    fallback = MagicMock()
    monkeypatch.setattr(demand_routing, 'record_fallback', fallback)
    if clock is not None:
        monkeypatch.setattr(demand_routing.time, 'monotonic', lambda: clock[0])
    receiver = SimpleNamespace(host=SimpleNamespace(request=SimpleNamespace(uid='user')))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=eligible)
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    return demand, fallback


@pytest.mark.asyncio
async def test_presence_outage_emits_once_then_rearms_after_recovery(monkeypatch):
    # No good answer yet: the very first miss cannot be bridged.
    demand, fallback = _routing(monkeypatch, [FAILED, FAILED, HIDDEN, FAILED, FAILED, HIDDEN])
    assert await demand.publish()
    assert await demand.publish()
    assert not await demand.publish()
    assert not await demand.publish()  # single miss after a good answer is bridged
    assert await demand.publish()  # second consecutive miss is a real outage
    assert fallback.call_count == 2
    assert fallback.call_args.kwargs['reason'] == 'gate_unavailable'
    assert fallback.call_args.kwargs['from_mode'] == 'demand_presence'


@pytest.mark.asyncio
async def test_single_missed_heartbeat_keeps_last_known_state_without_event(monkeypatch):
    clock = [100.0]
    demand, fallback = _routing(monkeypatch, [HIDDEN, FAILED, HIDDEN, FAILED, FAILED], clock=clock)
    assert not await demand.publish()
    clock[0] += 1
    assert not await demand.publish()  # bridged
    fallback.assert_not_called()
    clock[0] += 1
    assert not await demand.publish()  # recovery resets the miss counter
    clock[0] += 1
    assert not await demand.publish()  # a new single miss is bridged again
    clock[0] += 1
    assert await demand.publish()  # two in a row: vendor required, event emitted
    assert fallback.call_count == 1


@pytest.mark.asyncio
async def test_bridged_state_expires_with_the_lease(monkeypatch):
    clock = [100.0]
    demand, fallback = _routing(monkeypatch, [HIDDEN, FAILED], clock=clock)
    assert not await demand.publish()
    clock[0] += demand_routing.PRESENCE_LEASE_SECONDS
    assert await demand.publish()
    assert fallback.call_count == 1


@pytest.mark.asyncio
async def test_admission_and_non_admitted_sessions_never_use_a_bridged_miss(monkeypatch):
    demand, fallback = _routing(monkeypatch, [HIDDEN, FAILED])
    assert not await demand.publish()
    assert await demand.publish(tolerate_miss=False)  # admission path stays strict
    assert fallback.call_count == 1

    other, other_fallback = _routing(monkeypatch, [HIDDEN, FAILED], eligible=False)
    assert not await other.publish()
    assert await other.publish()
    assert other_fallback.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('eligible,cohort', [(True, 'admitted'), (False, 'ineligible')])
async def test_gate_fallback_event_carries_demand_cohort(monkeypatch, eligible, cohort):
    demand, fallback = _routing(monkeypatch, [FAILED], eligible=eligible)
    await demand.publish()
    assert fallback.call_args.kwargs['demand_cohort'] == cohort
    host_cohort = SimpleNamespace(cohort='eligible_control')
    demand.receiver.host.demand_telemetry = host_cohort
    assert demand.cohort == 'eligible_control'


def test_record_fallback_labels_gate_detail_with_explicit_cohort(monkeypatch):
    from utils.observability import fallback as fallback_module

    seen = []
    monkeypatch.setattr(fallback_module, 'record_metric', lambda metric, labels, value=1, **kw: seen.append(labels))
    fallback_module.record_fallback(
        component='stt_live_session',
        from_mode='demand_presence',
        to_mode='vendor',
        reason='gate_unavailable',
        outcome='degraded',
        demand_cohort='admitted',
    )
    fallback_module.record_fallback(
        component='stt_live_session',
        from_mode='demand_presence',
        to_mode='vendor',
        reason='gate_unavailable',
        outcome='degraded',
        demand_cohort='not-a-cohort',
    )
    assert [(row['demand_cohort'], row['reason']) for row in seen] == [
        ('admitted', 'gate_unavailable'),
        ('ineligible', 'gate_unavailable'),
    ]


@pytest.mark.asyncio
async def test_non_admitted_session_heartbeats_slowly_instead_of_every_second(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(demand_routing.time, 'monotonic', lambda: now[0])
    state = SimpleNamespace(active=True, stt_terminal_failure=False)

    async def wait(seconds):
        now[0] += seconds
        state.active = now[0] < 60
        return not state.active

    host = SimpleNamespace(request=SimpleNamespace(uid='user'), state=state, wait=wait, stt_model='soniox')
    receiver = SimpleNamespace(host=host, lane_meter=SimpleNamespace(flush=lambda **kw: None))
    update = AsyncMock(return_value=HIDDEN)
    monkeypatch.setattr(demand_routing, 'update_presence', update)
    monkeypatch.setattr(demand_routing, 'record_fallback', MagicMock())
    demand = demand_routing.LiveDemandRouting(receiver, eligible=False)
    await demand.run()
    heartbeats = [c for c in update.await_args_list if c.args[2] != 'close']
    # 60 loop seconds: ~1 per 10s (not 60), still inside the 30s presence lease; one close.
    assert 5 <= len(heartbeats) <= 7
    assert update.await_args_list[-1].args[2] == 'close'
    assert demand_routing.NON_ADMITTED_HEARTBEAT_SECONDS * 2 < demand_routing.PRESENCE_LEASE_SECONDS


@pytest.mark.asyncio
async def test_admitted_session_still_heartbeats_every_loop(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(demand_routing.time, 'monotonic', lambda: now[0])
    state = SimpleNamespace(active=True, stt_terminal_failure=False)

    async def wait(seconds):
        now[0] += seconds
        state.active = now[0] < 10
        return not state.active

    host = SimpleNamespace(request=SimpleNamespace(uid='user'), state=state, wait=wait, stt_model='soniox')
    receiver = SimpleNamespace(host=host, lane_meter=SimpleNamespace(flush=lambda **kw: None))
    update = AsyncMock(return_value=HIDDEN)
    monkeypatch.setattr(demand_routing, 'update_presence', update)
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(return_value=False))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    await demand.run()
    assert len([c for c in update.await_args_list if c.args[2] != 'close']) >= 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'exc,expected',
    [
        (asyncio.TimeoutError(), 'timeout'),
        (redis_exceptions.TimeoutError('host 10.0.0.1 secret'), 'timeout'),
        (redis_exceptions.ConnectionError('password=hunter2'), 'connection'),
        (OSError('boom'), 'connection'),
        (ValueError('Invalid demand presence result'), 'response'),
        (redis_exceptions.ResponseError('OOM command not allowed'), 'redis_error'),
        (RuntimeError('anything else'), 'other'),
    ],
)
async def test_failure_is_logged_with_bounded_class_never_message(monkeypatch, caplog, exc, expected):
    monkeypatch.setattr(demand_presence, '_last_logged', None)
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(side_effect=exc)))
    with caplog.at_level(logging.WARNING, logger=demand_presence.logger.name):
        snapshot = await demand_presence.update_presence('private-user', 'phone', 'hidden')
    assert snapshot.unavailable and snapshot.visible and snapshot.error == expected
    text = '\n'.join(r.getMessage() for r in caplog.records)
    assert f'error_class={expected}' in text
    for leaked in ('hunter2', '10.0.0.1', 'secret', 'private-user', 'boom', 'OOM'):
        assert leaked not in text


@pytest.mark.asyncio
async def test_failure_logging_is_rate_limited(monkeypatch, caplog):
    monkeypatch.setattr(demand_presence, '_last_logged', None)
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(side_effect=OSError)))
    with caplog.at_level(logging.WARNING, logger=demand_presence.logger.name):
        for _ in range(20):
            await demand_presence.update_presence('user', 'phone', 'hidden')
    assert len(caplog.records) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', [None, 'invalid', False, 2])
async def test_unknown_presence_response_requires_vendor(monkeypatch, reply):
    monkeypatch.setattr(demand_presence, '_client', AsyncMock(eval=AsyncMock(return_value=reply)))
    snapshot = await demand_presence.update_presence('user', 'phone', 'hidden')
    assert snapshot.visible and snapshot.unavailable


@pytest.mark.asyncio
async def test_failed_non_admitted_heartbeat_retries_next_loop(monkeypatch):
    clock = [0.0]
    demand, _ = _routing(monkeypatch, [HIDDEN, FAILED, HIDDEN], eligible=False, clock=clock)
    assert demand._presence_due()  # never published
    await demand.publish()
    assert not demand._presence_due()
    clock[0] += demand_routing.NON_ADMITTED_HEARTBEAT_SECONDS
    assert demand._presence_due()
    await demand.publish()  # times out: the slot is not consumed
    clock[0] += 1
    assert demand._presence_due()
    await demand.publish()
    assert not demand._presence_due()


@pytest.mark.asyncio
async def test_first_failed_heartbeat_is_retried_immediately(monkeypatch):
    demand, _ = _routing(monkeypatch, [FAILED], eligible=False)
    await demand.publish()
    assert demand._presence_due()


@pytest.mark.asyncio
async def test_unavailable_found_by_concurrent_publish_forces_vendor_in_same_iteration(monkeypatch):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    state = SimpleNamespace(active=True, stt_terminal_failure=False)
    host = SimpleNamespace(
        request=SimpleNamespace(uid='user'), state=state, wait=AsyncMock(return_value=True), stt_model='parakeet-window'
    )
    receiver = SimpleNamespace(
        host=host, lane_meter=SimpleNamespace(flush=lambda **kw: None), _switch_live_demand=AsyncMock(return_value=True)
    )
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    monkeypatch.setattr(demand, 'publish', AsyncMock(return_value=False))

    async def consumer(uid):
        demand._presence_unavailable = True  # observe() publish lands a second miss meanwhile
        return False

    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', consumer)
    await demand.run()
    receiver._switch_live_demand.assert_awaited_with('vendor')
    assert demand.policy.reason == 'visible'

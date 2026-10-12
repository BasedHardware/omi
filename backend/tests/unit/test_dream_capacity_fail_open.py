"""Missing evidence is advisory; confirmed cooldown and slot occupancy still wait."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from config.vertex_reservations import RESERVATIONS, State
from utils import dream_agent, dream_capacity
from utils.llm.vertex_pt_routing import PT_MODEL_CURRENT
from utils.llm.vertex_reservation_state import ReservationState


@pytest.fixture(autouse=True)
def capacity_scope(monkeypatch):
    dream_capacity._local_state.cache_clear()
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    yield
    dream_capacity._local_state.cache_clear()


def decisions(caplog):
    return [json.loads(record.message) for record in caplog.records if record.message.startswith('{')]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure', ['client', 'refresh', 'key', 'lookup', 'no_client', 'empty', 'unknown', 'inactive', 'conflict']
)
async def test_unavailable_evidence_admits_and_logs_only_safe_fields(monkeypatch, caplog, failure):
    secret = 'invented password and account text'
    client = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(return_value=True), eval=AsyncMock())
    state = ReservationState(client)
    states = {model: State.ACTIVE if model == PT_MODEL_CURRENT else State.INACTIVE for model in RESERVATIONS}
    refresh = AsyncMock(return_value=states)
    monkeypatch.setattr(state, 'refresh', refresh)
    expected = 'probe_failed'
    if failure in {'client', 'key'}:

        def broken():
            raise RuntimeError(secret)

        monkeypatch.setattr(state, failure, broken)
    elif failure == 'refresh':
        refresh.side_effect = ValueError(secret)
    elif failure == 'lookup':
        client.get.side_effect = ConnectionError(secret)
    elif failure == 'no_client':
        monkeypatch.setattr(state, 'client', lambda: None)
        expected = 'no_client'
    elif failure in {'empty', 'unknown'}:
        refresh.return_value = {} if failure == 'empty' else {model: State.UNKNOWN for model in RESERVATIONS}
        expected = 'no_states'
    else:
        refresh.return_value = {
            model: State.INACTIVE if failure == 'inactive' else State.ACTIVE for model in RESERVATIONS
        }
        expected = 'no_active_model'
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    assert await dream_capacity.available_model() == PT_MODEL_CURRENT
    assert decisions(caplog) == [
        {
            'event': 'dream_capacity_decision',
            'decision': 'admit',
            'reason': expected,
            'source': 'evidence',
            'model': PT_MODEL_CURRENT,
        }
    ]
    assert secret not in caplog.text
    slot = await dream_capacity.claim(2)
    assert slot is not None
    await dream_capacity.release(slot)


@pytest.mark.asyncio
async def test_missing_store_does_not_stop_real_or_canary_admission(monkeypatch):
    state = ReservationState()
    monkeypatch.setattr(state, 'client', lambda: None)
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={}))
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    admitted = AsyncMock(return_value={'status': 'complete'})
    monkeypatch.setattr(dream_agent, '_run_admitted_pass', admitted)
    for canary in (False, True):
        assert await dream_agent.run_pass('synthetic', canary=canary) == {'status': 'complete'}
    assert admitted.await_count == 2
    assert not dream_capacity._local().slots


@pytest.mark.asyncio
async def test_existing_probe_lease_does_not_hold_cold_store_admission(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    seconds, _ = await redis.time()
    await redis.set(state.key(), json.dumps({'leases': {model: seconds + 600 for model in RESERVATIONS}}))
    probe = AsyncMock(side_effect=AssertionError('unexpired lease re-probed'))
    monkeypatch.setattr(dream_capacity, '_probe', probe)
    try:
        assert await dream_capacity.available_model() == PT_MODEL_CURRENT
        probe.assert_not_awaited()
        assert not state._probe_tasks
    finally:
        await state.aclose()
        await redis.aclose()


@pytest.mark.asyncio
async def test_probe_exception_is_visible_and_does_not_stop_admission(monkeypatch, caplog):
    state = ReservationState()
    monkeypatch.setattr(state, 'client', lambda: SimpleNamespace(get=AsyncMock(return_value=None)))
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={}))
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    monkeypatch.setattr(dream_capacity, 'get_desktop_gemini_client', lambda: object())
    monkeypatch.setattr(dream_capacity, '_vertex_tokens', lambda: SimpleNamespace(get_access_token=AsyncMock()))
    monkeypatch.setattr(dream_capacity, 'probe_reservation', AsyncMock(side_effect=RuntimeError('invented secret')))
    assert await dream_capacity._probe(PT_MODEL_CURRENT, 'us') == 'inconclusive'
    assert await dream_capacity.available_model() == PT_MODEL_CURRENT
    assert decisions(caplog)[0]['reason'] == 'probe_failed'
    assert 'invented secret' not in caplog.text


@pytest.mark.asyncio
async def test_probe_capacity_observation_is_not_itself_a_waiting_decision(monkeypatch, caplog):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={}))
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    monkeypatch.setattr(dream_capacity, 'get_desktop_gemini_client', lambda: object())
    monkeypatch.setattr(dream_capacity, '_vertex_tokens', lambda: SimpleNamespace(get_access_token=AsyncMock()))
    monkeypatch.setattr(dream_capacity, 'probe_reservation', AsyncMock(return_value='capacity_error'))
    try:
        assert await dream_capacity._probe(PT_MODEL_CURRENT, 'us') == 'capacity_error'
        assert not decisions(caplog)
        assert await dream_capacity.available_model() is None
        assert len(decisions(caplog)) == 1 and decisions(caplog)[0]['reason'] == 'saturated'
    finally:
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('shared', [False, True])
async def test_429_cooldown_blocks_during_outage_and_expires(monkeypatch, caplog, shared):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={}))
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    try:
        if shared:
            await redis.set(state.key() + ':saturated:' + PT_MODEL_CURRENT, '1', ex=120)
        else:
            monkeypatch.setattr(state, 'client', lambda: None)
            await dream_capacity.mark_saturated(PT_MODEL_CURRENT)
        caplog.clear()
        assert await dream_capacity.available_model() is None
        assert len(decisions(caplog)) == 1
        assert decisions(caplog)[0]['reason'] == 'saturated'
        assert decisions(caplog)[0]['decision'] == 'waiting'
        if shared:
            assert 119 <= await redis.ttl(state.key() + ':saturated:' + PT_MODEL_CURRENT) <= 120
            await redis.delete(state.key() + ':saturated:' + PT_MODEL_CURRENT)
        else:
            dream_capacity._local().cooldowns[PT_MODEL_CURRENT] = 0
        assert await dream_capacity.available_model() == PT_MODEL_CURRENT
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_outage_slots_stay_bounded_and_old_release_cannot_erase_replacement(monkeypatch, caplog):
    state = ReservationState()
    monkeypatch.setattr(state, 'client', lambda: None)
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={}))
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    first, second = await dream_capacity.claim(2), await dream_capacity.claim(2)
    assert first and second and first[1] != second[1]
    caplog.clear()
    assert await dream_capacity.claim(2) is None
    waiting = [row for row in decisions(caplog) if row['decision'] == 'waiting']
    assert len(waiting) == 1 and waiting[0]['source'] == 'local_slots'
    local = dream_capacity._local()
    local.slots[0] = first[1], 0  # The ambiguous/cancelled slot's 240s TTL expired.
    replacement = await dream_capacity.claim(2)
    assert replacement and replacement[1] != first[1]
    await dream_capacity.release(first)
    assert local.slots[0][0] == replacement[1]
    await dream_capacity.release(second)
    await dream_capacity.release(replacement)
    assert not local.slots

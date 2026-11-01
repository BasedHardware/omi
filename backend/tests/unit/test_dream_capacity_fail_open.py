"""Dream fails closed on absent evidence, while allowlisted on-demand keeps slots."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from config.vertex_reservations import State
from llm_gateway.gateway.dream_lanes import DREAM_MODEL
from utils import dream_capacity
from utils.llm.vertex_reservation_state import ReservationState

OLD = 'gemini-2.5-flash'


@pytest.fixture(autouse=True)
def capacity_scope(monkeypatch):
    dream_capacity._local_state.cache_clear()
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.delenv('DREAM_ON_DEMAND_ENABLED', raising=False)
    yield
    dream_capacity._local_state.cache_clear()


@pytest.fixture
async def capacity(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={DREAM_MODEL: State.ACTIVE}))
    yield state, redis
    await state.aclose()
    await redis.aclose()


async def evidence(state, redis, successes):
    seconds, micros = await redis.time()
    now = seconds + micros / 1_000_000
    await redis.set(
        state.key(), json.dumps({'evidence': {m: {'success_at': now - age} for m, age in successes.items()}})
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure',
    [
        'client',
        'refresh',
        'refresh_empty',
        'refresh_unknown',
        'key',
        'lookup',
        'no_client',
        'empty',
        'unknown',
        'stale',
        'old_model',
        'conflict',
        'malformed',
    ],
)
async def test_unavailable_evidence_waits_without_secret_logging(monkeypatch, caplog, capacity, failure):
    state, redis = capacity
    secret = 'invented private content'
    await evidence(state, redis, {DREAM_MODEL: 0})
    if failure in {'client', 'key'}:

        def broken():
            raise RuntimeError(secret)

        monkeypatch.setattr(state, failure, broken)
    elif failure == 'refresh':
        state.refresh.side_effect = RuntimeError(secret)
    elif failure in {'refresh_empty', 'refresh_unknown'}:
        state.refresh.return_value = {} if failure == 'refresh_empty' else {DREAM_MODEL: State.UNKNOWN}
    elif failure == 'lookup':
        monkeypatch.setattr(redis, 'get', AsyncMock(side_effect=ConnectionError(secret)))
    elif failure == 'no_client':
        monkeypatch.setattr(state, 'client', lambda: None)
    elif failure in {'empty', 'unknown'}:
        await redis.delete(state.key())
    elif failure == 'stale':
        await evidence(state, redis, {DREAM_MODEL: 901})
    elif failure == 'old_model':
        await evidence(state, redis, {OLD: 0})
    elif failure == 'conflict':
        await evidence(state, redis, {DREAM_MODEL: 0, OLD: 0})
    elif failure == 'malformed':
        await redis.set(state.key(), secret)
    assert await dream_capacity.available_model() is None
    assert await dream_capacity.claim(2) is None
    assert not dream_capacity._local().slots
    assert secret not in caplog.text
    rows = [json.loads(record.message) for record in caplog.records if record.message.startswith('{')]
    assert rows and all(row['decision'] == 'waiting' and row['model'] == DREAM_MODEL for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure,stage,exc',
    [
        ('client', 'client', 'RuntimeError'),
        ('refresh', 'refresh', 'RuntimeError'),
        ('lookup', 'headroom', 'ConnectionError'),
    ],
)
async def test_state_errors_are_labeled_state_error_with_payload_free_warning(
    monkeypatch, caplog, capacity, failure, stage, exc
):
    state, redis = capacity
    secret = 'invented private content'
    await evidence(state, redis, {DREAM_MODEL: 0})
    if failure == 'client':

        def broken():
            raise RuntimeError(secret)

        monkeypatch.setattr(state, 'client', broken)
    elif failure == 'refresh':
        state.refresh.side_effect = RuntimeError(secret)
    else:
        monkeypatch.setattr(redis, 'get', AsyncMock(side_effect=ConnectionError(secret)))
    assert await dream_capacity.available_model() is None
    assert secret not in caplog.text
    rows = [json.loads(record.message) for record in caplog.records if record.message.startswith('{')]
    assert [row['reason'] for row in rows] == ['state_error']
    assert rows[0]['decision'] == 'waiting' and rows[0]['source'] == 'evidence'
    warnings = [record.message for record in caplog.records if 'dream_capacity_state_error' in record.message]
    assert warnings == [f'dream_capacity_state_error model={DREAM_MODEL} stage={stage} exc={exc}']


@pytest.mark.asyncio
async def test_raising_probe_callable_stays_advisory_and_never_labels_the_decision(monkeypatch, caplog):
    # The probe callable runs as a background task inside refresh and its own
    # containment converts failures to 'inconclusive', so a raising probe can
    # never surface as a state_error/probe_failed admission decision.
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    await evidence(state, redis, {DREAM_MODEL: 901})

    async def raising_probe(model, location):
        raise RuntimeError('invented probe secret')

    monkeypatch.setattr(dream_capacity, '_probe', raising_probe)
    try:
        assert await dream_capacity.available_model() is None
        await asyncio.gather(*state._probe_tasks)
        rows = [json.loads(record.message) for record in caplog.records if record.message.startswith('{')]
        assert [row['reason'] for row in rows] == ['no_states']
        assert 'dream_capacity_state_error' not in caplog.text
        assert 'probe_failed' not in caplog.text
        assert 'invented probe secret' not in caplog.text
    finally:
        await state.aclose()
        await redis.aclose()


@pytest.mark.asyncio
async def test_fresh_38_evidence_admits_but_overrides_cannot_fabricate_it(monkeypatch, capacity):
    state, redis = capacity
    monkeypatch.setenv('OMI_VERTEX_PT_MODEL', DREAM_MODEL)
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', json.dumps({DREAM_MODEL: 'active'}))
    assert await dream_capacity.available_model() is None
    await evidence(state, redis, {DREAM_MODEL: 0})
    assert await dream_capacity.available_model() == DREAM_MODEL
    slot = await dream_capacity.claim(2)
    assert slot and not slot[0].startswith('dream-local:')
    await dream_capacity.release(slot)
    assert not dream_capacity._local().slots


@pytest.mark.asyncio
@pytest.mark.parametrize('shared', [True, False])
async def test_recent_429_waits_even_with_fresh_success(monkeypatch, capacity, shared):
    state, redis = capacity
    await evidence(state, redis, {DREAM_MODEL: 0})
    if shared:
        await redis.set(state.key() + ':saturated:' + DREAM_MODEL, '1', ex=120)
    else:
        await dream_capacity.mark_saturated(DREAM_MODEL)
    assert await dream_capacity.available_model() is None
    if shared:
        await redis.delete(state.key() + ':saturated:' + DREAM_MODEL)
    else:
        dream_capacity._local().cooldowns[DREAM_MODEL] = 0
        await redis.delete(state.key() + ':saturated:' + DREAM_MODEL)
    assert await dream_capacity.available_model() == DREAM_MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'utilization,age,admitted',
    [
        (0.69, 0, True),
        (0.7, 0, False),
        (0.9, 0, False),
        (0.1, 901, False),
        (-1, 0, False),
        (True, 0, False),
        ('0.2', 0, False),
    ],
)
async def test_optional_measured_utilization_has_conservative_threshold(capacity, utilization, age, admitted):
    state, redis = capacity
    await evidence(state, redis, {DREAM_MODEL: 0})
    seconds, _ = await redis.time()
    await redis.set(
        state.key() + ':dedicated-utilization:' + DREAM_MODEL,
        json.dumps({'utilization': utilization, 'observed_at': seconds - age}),
    )
    assert (await dream_capacity.available_model() == DREAM_MODEL) is admitted


@pytest.mark.asyncio
async def test_redis_slot_failure_does_not_become_local_reserved_admission(monkeypatch, capacity):
    state, redis = capacity
    await evidence(state, redis, {DREAM_MODEL: 0})
    monkeypatch.setattr(redis, 'set', AsyncMock(side_effect=ConnectionError('synthetic')))
    assert await dream_capacity.claim(2) is None
    assert not dream_capacity._local().slots


@pytest.mark.asyncio
async def test_on_demand_requires_allowlist_and_flag_and_preserves_slot_bound(monkeypatch, capacity):
    state, redis = capacity
    monkeypatch.setattr(state, 'client', lambda: None)
    assert await dream_capacity.available_model(mode='on_demand', owner_allowlisted=True) is None
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    assert await dream_capacity.available_model(mode='on_demand') is None
    assert await dream_capacity.available_model(mode='on_demand', owner_allowlisted='true') is None
    opts = {'mode': 'on_demand', 'owner_allowlisted': True}
    first, second = await dream_capacity.claim(2, **opts), await dream_capacity.claim(2, **opts)
    assert first and second
    assert await dream_capacity.claim(2, **opts) is None
    dream_capacity._local().slots[0] = first[1], 0
    replacement = await dream_capacity.claim(2, **opts)
    assert replacement
    await dream_capacity.release(first)
    assert dream_capacity._local().slots[0][0] == replacement[1]
    await dream_capacity.release(second)
    await dream_capacity.release(replacement)
    assert not dream_capacity._local().slots
    state.refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [PermissionError, ConnectionError, TimeoutError])
async def test_probe_exception_is_advisory_and_does_not_log_content(monkeypatch, caplog, capacity, error):
    state, redis = capacity
    await evidence(state, redis, {DREAM_MODEL: 0})
    post = AsyncMock(side_effect=error('invented secret'))
    monkeypatch.setattr(dream_capacity, 'get_llm_gateway_client', lambda: SimpleNamespace(post=post))
    assert await dream_capacity._probe(DREAM_MODEL, 'us') == 'inconclusive'
    assert await dream_capacity.available_model() == DREAM_MODEL
    assert await redis.get(state.key() + ':dream-probe-failed:' + DREAM_MODEL) is None
    assert 'invented secret' not in caplog.text


@pytest.mark.asyncio
async def test_old_replica_probe_failure_cannot_veto_strict_shared_evidence(capacity):
    state, redis = capacity
    await evidence(state, redis, {DREAM_MODEL: 0})
    await redis.set(state.key() + ':dream-probe-failed:' + DREAM_MODEL, '1', ex=600)
    assert await dream_capacity.available_model() == DREAM_MODEL
    dream_capacity._local_state.cache_clear()  # Another worker reads the same proof.
    assert await dream_capacity.available_model() == DREAM_MODEL
    await evidence(state, redis, {DREAM_MODEL: 901})
    assert await dream_capacity.available_model() is None

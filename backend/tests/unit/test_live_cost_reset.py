"""Operator reset exercises real Redis WATCH/MULTI semantics using fakeredis."""

import json

import fakeredis.aioredis
import pytest

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS
from utils.stt.live_cost_reset import reset_cost_target
from utils.stt.live_gate import GateState, transition


@pytest.fixture(params=DEFAULT_TARGETS, ids=lambda target: target.id)
def runtime(monkeypatch, request):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.delenv('STT_ROUTING_TARGETS_JSON', raising=False)
    monkeypatch.delenv('STT_ROUTING_DISRUPTION_GATE', raising=False)
    return request.param


@pytest.mark.asyncio
async def test_reset_dry_run_atomic_all_scopes_and_reversible_bench(runtime, caplog):
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        keys = [live_stt_state.cost_key(runtime, lang) for lang in ('all', *live_stt_state.ROUTED_LANGUAGES)]
        old = GateState(stage=5, n=20, failures=2, generation=8, strikes=3)
        for key in keys:
            await redis.set(key, json.dumps(old.encode()))
        other = next(target for target in DEFAULT_TARGETS if target.id != runtime.id)
        other_key = live_stt_state.cost_key(other, 'all')
        await redis.set(other_key, 'untouched')
        args = dict(target=runtime.id, environment='offline', reason='sttbench-20261027')
        dry_run = await reset_cost_target(redis, **args)
        assert not dry_run['applied'] and await redis.dbsize() == len(keys) + 1
        assert GateState.decode(json.loads(await redis.get(keys[0]))) == old
        applied = await reset_cost_target(redis, apply=True, **args)
        assert applied['applied'] and len(applied['scopes']) == len(keys)
        assert 'live_stt_cost_operator_reset' in caplog.text
        generation = applied['scopes'][0]['generation']
        assert generation > 9
        for key in keys:
            state = GateState.decode(json.loads(await redis.get(key)))
            assert state == GateState(generation=generation)
            assert 0 < await redis.ttl(key) <= 900
        audit_key = live_stt_state.cost_key(runtime, 'operator-audit:' + applied['audit_id'])
        assert json.loads(await redis.get(audit_key)) == applied
        assert 0 < await redis.ttl(audit_key) <= 30 * 86400
        assert await redis.get(other_key) == 'untouched'
        # A reset does not override the detector for new failures.
        for i in range(8):
            state = transition(state, True, 0, witness=f'{i:016x}')
        assert state.stage == 0
        rollback = await reset_cost_target(redis, stage=0, apply=True, **args)
        state = GateState.decode(json.loads(await redis.get(keys[0])))
        assert state.stage == 0 and state.generation > generation and await redis.ttl(keys[0]) == -1
        assert state.until == pytest.approx(rollback['timestamp'] + 300)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change', [dict(environment='prod'), dict(target='unknown'), dict(stage=25), dict(reason='user text')]
)
async def test_invalid_reset_never_writes(runtime, change):
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        args = dict(target=runtime.id, environment='offline', reason='incident', apply=True)
        with pytest.raises(ValueError):
            await reset_cost_target(redis, **(args | change))
        assert await redis.dbsize() == 0


@pytest.mark.asyncio
async def test_concurrent_vote_retries_whole_reset_and_audits_actual_generation(runtime, monkeypatch):
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        key = live_stt_state.cost_key(runtime, 'en')
        await redis.set(key, json.dumps(GateState(stage=5, generation=3).encode()))
        real_time = redis.time
        calls = 0

        async def interleave_vote():
            nonlocal calls
            calls += 1
            if calls == 1:
                await redis.set(key, json.dumps(GateState(stage=25, generation=4).encode()))
            return await real_time()

        monkeypatch.setattr(redis, 'time', interleave_vote)
        result = await reset_cost_target(redis, target=runtime.id, environment='offline', reason='race', apply=True)
        assert calls == 2
        generation = next(s for s in result['scopes'] if s['language'] == 'en')['generation']
        assert generation > 5
        assert GateState.decode(json.loads(await redis.get(key))) == GateState(generation=generation)
        assert next(s for s in result['scopes'] if s['language'] == 'en')['old_stage'] == 25


@pytest.mark.asyncio
async def test_undecodable_scope_aborts_every_scope(runtime):
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        key = live_stt_state.cost_key(runtime, 'en')
        await redis.set(key, 'invalid')
        with pytest.raises(ValueError):
            await reset_cost_target(redis, target=runtime.id, environment='offline', reason='invalid', apply=True)
        assert await redis.dbsize() == 1 and await redis.get(key) == 'invalid'

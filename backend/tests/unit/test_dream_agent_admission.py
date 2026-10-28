"""Eligibility gates real pass/drain admission before reserved-capacity waits."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
from unittest.mock import AsyncMock, Mock

import fakeredis.aioredis
import pytest

from config.vertex_reservations import State
from database import dream_scheduler, dream_store
from utils import rollout_cohorts
from llm_gateway.gateway.dream_lanes import DREAM_MODEL
from tests.unit.test_dream_harness_runtime import runtime, store, scripted, UID
from utils import dream_agent, dream_capacity, dream_seed, dream_harness_transport
from utils.dream_capacity import claim as claim_capacity, release as release_capacity
from utils.llm.vertex_reservation_state import ReservationState


@pytest.fixture
async def admission(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', '')
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_CONCURRENCY', '1')
    monkeypatch.setattr(dream_scheduler, 'get_firestore_client', lambda: runtime)
    dream_capacity._local_state.cache_clear()
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        state = ReservationState(redis)
        monkeypatch.setattr(dream_capacity, 'reservation_state', state)
        monkeypatch.setattr(state, 'refresh', AsyncMock(return_value={DREAM_MODEL: State.INACTIVE}))
        monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(wraps=claim_capacity))
        monkeypatch.setattr(dream_capacity, 'release', AsyncMock(wraps=release_capacity))
        yield runtime
        await state.aclose()
    dream_capacity._local_state.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('dry_run', [False, True])
async def test_ineligible_pass_skips_capacity_seed_and_lease(admission, monkeypatch, dry_run):
    admission.rows[('dream_due', UID)] = {'due_at': dream_scheduler.EPOCH}
    before = deepcopy(admission.rows)
    load = Mock(wraps=dream_seed.load)
    acquire = Mock(wraps=dream_store.acquire)
    record = Mock(wraps=dream_agent.record_pass)
    monkeypatch.setattr(dream_seed, 'load', load)
    monkeypatch.setattr(dream_store, 'acquire', acquire)
    monkeypatch.setattr(dream_agent, 'record_pass', record)
    assert await dream_capacity.available_model() is None

    report = await dream_agent.run_pass(UID, dry_run=dry_run)

    assert report == {'status': 'not_admitted', 'reason': 'ineligible'}
    dream_capacity.claim.assert_not_awaited()
    load.assert_not_called()
    acquire.assert_not_called()
    record.assert_called_once_with(report)
    if not dry_run:
        before.pop(('dream_due', UID))
    assert admission.rows == before


@pytest.mark.asyncio
async def test_owner_queued_under_all_is_removed_after_allowlist_switch_without_drain_retry(admission, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    assert dream_store.mark_dirty(UID, [('conversations', 'one')])
    assert ('dream_due', UID) in admission.rows
    before = deepcopy(admission.rows)
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')

    # Isolate discovery/query IO; keep the actual drain, pass and row deletion.
    candidates = Mock(side_effect=lambda **kwargs: [UID] if ('dream_due', UID) in admission.rows else [])
    monkeypatch.setattr(dream_scheduler, 'candidates', candidates)
    sleep = AsyncMock(side_effect=AssertionError('ineligible owner retried'))
    monkeypatch.setattr(dream_agent.asyncio, 'sleep', sleep)

    assert await dream_agent.drain() == [{'status': 'not_admitted', 'reason': 'ineligible'}]
    assert await dream_agent.drain() == []
    dream_capacity.claim.assert_not_awaited()
    sleep.assert_not_awaited()
    assert candidates.call_count == 2
    before.pop(('dream_due', UID))
    assert admission.rows == before  # Dirty work and user data survive for future eligibility.
    assert not dream_store.mark_dirty(UID, [('conversations', 'two')])
    assert ('dream_due', UID) not in admission.rows


@pytest.mark.asyncio
async def test_allowlisted_owner_completes_with_real_on_demand_capacity(admission, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    assert await dream_capacity.available_model() is None
    report = await dream_agent.run_pass(UID, turn=scripted([True, True]))
    assert report['status'] == 'complete', report
    assert report['verifier_calls'] == 2
    assert dream_capacity.claim.await_args.kwargs['mode'] == 'on_demand'
    assert dream_capacity.claim.await_args.kwargs['owner_allowlisted'] is True
    dream_capacity.release.assert_awaited_once()
    assert not dream_capacity._local().slots


@pytest.mark.asyncio
async def test_authoritative_store_still_rejects_deleted_allowlisted_owner(admission, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    admission.rows[('users', UID)]['deleted'] = True
    model = AsyncMock(side_effect=AssertionError('deleted owner reached model'))
    assert await dream_agent.run_pass(UID, turn=model) == {'status': 'not_admitted'}
    dream_capacity.claim.assert_awaited_once()
    dream_capacity.release.assert_awaited_once()
    model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('membership', [True, False, 'error'])
async def test_cold_and_expired_cohort_is_loaded_before_dream_capacity(admission, monkeypatch, membership):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=None))
    release = threading.Event()
    reads = []

    def read(uid):
        reads.append(uid)
        assert release.wait(1)
        if membership == 'error':
            raise RuntimeError('synthetic unavailable store')
        return {'prod': {'dream-agent': membership}}

    rollout_cohorts.configure_rollout_runtime()
    cache = rollout_cohorts._TTLReads(read)
    monkeypatch.setattr(rollout_cohorts, '_cache', cache)
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(rollout_cohorts, '_background_submitter', pool.submit)
        for attempt in range(2):
            release.clear()

            async def unblock():
                await asyncio.sleep(0)
                release.set()

            pulse = asyncio.create_task(unblock())
            try:
                report = await dream_agent.run_pass(UID)
            finally:
                release.set()
                await pulse
            expected = (
                {'status': 'waiting', 'reason': 'reserved_capacity'}
                if membership is True
                else (
                    {'status': 'waiting', 'reason': 'eligibility_unavailable'}
                    if membership == 'error'
                    else {'status': 'not_admitted', 'reason': 'ineligible'}
                )
            )
            assert report == expected
            assert reads == [UID] * (attempt + 1)
            cache.entries[UID].expires = 0
    assert dream_capacity.claim.await_count == (2 if membership is True else 0)


@pytest.mark.asyncio
async def test_each_model_turn_refreshes_membership_before_capacity_selection(admission, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    # Stop before the gateway: the assertion concerns the real turn's routing boundary.
    monkeypatch.setattr(dream_harness_transport, 'attempt_room', lambda *args, **kwargs: (10, 128))
    capacity = AsyncMock(return_value=None)
    monkeypatch.setattr(dream_capacity, 'available_model', capacity)
    membership = [True]
    reads = []

    def read(uid):
        reads.append(uid)
        return {'prod': {'dream-agent': membership[0]}}

    rollout_cohorts.configure_rollout_runtime()
    cache = rollout_cohorts._TTLReads(read)
    monkeypatch.setattr(rollout_cohorts, '_cache', cache)
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(rollout_cohorts, '_background_submitter', pool.submit)
        for value, expected in [(True, 'on_demand'), (True, 'on_demand'), (False, 'reserved')]:
            membership[0] = value
            if UID in cache.entries:
                cache.entries[UID].expires = 0
            with pytest.raises(dream_harness_transport.CapacityWait):
                await dream_harness_transport.model_turn(UID, dream_harness_transport.MAIN_LANE, None, [])
            assert capacity.await_args.kwargs == {'mode': expected, 'owner_allowlisted': value}
    assert reads == [UID] * 3

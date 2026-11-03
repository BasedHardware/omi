"""Backend discovery waits for 3.8 reservation evidence before owner admission."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import httpx
import pytest

from config.vertex_reservations import State
from models.agent_tools import VerificationBatch as Plan
from utils import dream_agent, dream_capacity, dream_harness_transport as dream_transport
from utils.dream_metrics import PASSES
from utils.llm.shaped_agent import Budget, Mount
from utils.llm.vertex_reservation_state import ReservationState

OLD, NEW = 'gemini-2.5-flash', 'gemini-3.8-flash'


@pytest.fixture(autouse=True)
def isolated_local_capacity():
    dream_capacity._local_state.cache_clear()
    yield
    dream_capacity._local_state.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(503, 'inconclusive'), (200, 'dedicated_success')])
async def test_legacy_backend_probe_keeps_its_direct_dedicated_path(monkeypatch, status, expected):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == 'us-central1-aiplatform.googleapis.com'
        assert request.url.path.endswith(f'/models/{OLD}:generateContent')
        assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
        assert request.headers['Authorization'] == 'Bearer synthetic-token'
        return httpx.Response(
            status,
            json={
                'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'},
                'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
            },
        )

    token = AsyncMock(return_value='synthetic-token')
    monkeypatch.setattr(dream_capacity, '_vertex_tokens', lambda: SimpleNamespace(get_access_token=token))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(dream_capacity, 'get_desktop_gemini_client', lambda: client)
        assert await dream_capacity._probe(OLD, 'us-central1') == expected
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('override', [{OLD: 'inactive'}, {OLD: 'inactive', NEW: 'inactive'}])
async def test_dream_admission_uses_raw_evidence_despite_desktop_override(monkeypatch, override):
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', json.dumps(override))
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    seconds, micros = await redis.time()
    now = seconds + micros / 1_000_000
    await redis.set(
        state.key(),
        json.dumps(
            {
                'evidence': {NEW: {'success_at': now - 1}},
                'leases': {OLD: now + 600, NEW: now + 600},
            }
        ),
    )
    try:
        # available_model passes apply_overrides=False, including when an
        # operator explicitly overrides the target as well as retired 2.5.
        assert await dream_capacity.available_model() == NEW
        assert not state._probe_tasks
    finally:
        await state.aclose()
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'status,failure,lane,cools',
    [
        (429, None, dream_transport.MAIN_LANE, True),
        (503, 'reserved_capacity_unavailable', dream_transport.MAIN_LANE, True),
        (429, 'provider_429_omi_paid', dream_transport.MAIN_LANE, True),
        (500, None, dream_transport.MAIN_LANE, False),
        (503, 'invalid_config', dream_transport.MAIN_LANE, False),
    ],
)
async def test_gateway_capacity_errors_cool_the_selected_model_only(monkeypatch, caplog, status, failure, lane, cools):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_PROJECT', 'based-hardware')
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    available = AsyncMock(return_value=OLD)
    monkeypatch.setattr(dream_capacity, 'available_model', available)

    async def post(*args, **kwargs):
        # A later admission could see another model; this request must cool OLD.
        available.return_value = NEW
        return httpx.Response(
            status,
            request=httpx.Request('POST', 'https://synthetic.invalid'),
            json={'error': {'failure_class': failure, 'message': 'invented private body'}},
        )

    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: SimpleNamespace(post=post))
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    try:
        with pytest.raises(dream_transport.CapacityWait if cools else RuntimeError) as exc:
            await dream_transport.model_turn('synthetic', lane, Mount(schema=Plan, budget=Budget(tokens=20000)), [])
        assert 'invented private body' not in str(exc.value)
        assert await redis.get(state.key() + ':saturated:' + NEW) is None
        key = state.key() + ':saturated:' + OLD
        if cools:
            assert await redis.get(key) == '1'
            assert 119 <= await redis.ttl(key) <= 120
        else:
            assert await redis.get(key) is None
        assert available.await_count == (1 if lane == dream_transport.MAIN_LANE else 0)
        assert 'invented private body' not in caplog.text
    finally:
        await redis.aclose()


def test_no_model_sweep_is_visible_without_owner_admission(monkeypatch, caplog):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.delenv('DREAM_ON_DEMAND_ENABLED', raising=False)
    monkeypatch.setattr(dream_agent, 'RESERVED_RECHECK_SECONDS', 0)
    available = AsyncMock(return_value=None)
    monkeypatch.setattr(dream_capacity, 'available_model', available)
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: pytest.fail('owner page read'))
    metric = PASSES.labels('waiting', 'none')._value
    before = metric.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        assert asyncio.run(dream_agent.drain()) == [{'status': 'waiting', 'reason': 'reserved_capacity'}]
    assert available.await_count == 1 + dream_agent.RESERVED_RECHECKS
    assert metric.get() == before + 1
    assert 'Dream status=waiting' in caplog.text


def test_sweep_rechecks_after_stale_evidence_before_giving_up(monkeypatch):
    # The first admission check launches the probe; fresh evidence opens the sweep on a recheck.
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.delenv('DREAM_ON_DEMAND_ENABLED', raising=False)
    monkeypatch.setattr(dream_agent, 'RESERVED_RECHECK_SECONDS', 0)
    available = AsyncMock(side_effect=[None, None, NEW])
    monkeypatch.setattr(dream_capacity, 'available_model', available)
    pages = []
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: pages.append(k) or [])
    assert asyncio.run(dream_agent.drain()) == []
    assert available.await_count == 3
    assert len(pages) == 1


def test_sweep_stops_rechecking_when_global_kill_switch_turns_off(monkeypatch):
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent, 'on_demand_enabled', lambda: False)
    available = AsyncMock(return_value=None)
    monkeypatch.setattr(dream_capacity, 'available_model', available)

    async def switch_off(seconds):
        monkeypatch.setattr(dream_agent, 'enabled', lambda: False)

    monkeypatch.setattr(dream_agent.asyncio, 'sleep', switch_off)
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: pytest.fail('owner page read'))
    assert asyncio.run(dream_agent.drain()) == []
    available.assert_awaited_once()


def test_late_pass_gets_only_the_remaining_drain_budget(monkeypatch):
    # A pass admitted late in the sweep must end through its own deadline, not the drain's cancel.
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent, 'concurrency', lambda: 1)
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=NEW))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: ['owner-a'])
    monkeypatch.setattr(dream_agent, 'DRAIN_TIMEOUT_SECONDS', 1000)
    budgets = []

    async def fake_pass(uid, *, timeout_seconds=None, **kwargs):
        budgets.append(timeout_seconds)
        return {'status': 'complete'}

    monkeypatch.setattr(dream_agent, 'run_pass', fake_pass)
    asyncio.run(dream_agent.drain())
    assert len(budgets) == 1
    assert budgets[0] <= 1000 - dream_agent.FINISH_MARGIN_SECONDS
    assert budgets[0] < dream_agent.PASS_TIMEOUT_SECONDS


def test_no_pass_starts_below_the_minimum_remaining_budget(monkeypatch):
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent, 'concurrency', lambda: 2)
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=NEW))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: ['owner-a', 'owner-b'])
    monkeypatch.setattr(
        dream_agent, 'DRAIN_TIMEOUT_SECONDS', dream_agent.MIN_PASS_SECONDS + dream_agent.FINISH_MARGIN_SECONDS - 1
    )
    monkeypatch.setattr(dream_agent, 'run_pass', AsyncMock(side_effect=AssertionError('pass started')))
    assert asyncio.run(dream_agent.drain()) == []


def test_no_model_stops_before_gateway_access(monkeypatch):
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=None))
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: pytest.fail('gateway accessed'))
    sink = {'tokens': 0}
    with pytest.raises(dream_transport.CapacityWait):
        asyncio.run(
            dream_transport.model_turn(
                'synthetic',
                dream_transport.MAIN_LANE,
                Mount(schema=Plan, budget=Budget(tokens=20000)),
                [],
                usage_sink=sink,
            )
        )
    assert sink == {'tokens': 0}


@pytest.mark.asyncio
@pytest.mark.parametrize('credential_failure', [False, True])
async def test_keyless_probe_denial_is_advisory_without_a_provider_fallback(monkeypatch, credential_failure):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    token = (
        AsyncMock(side_effect=PermissionError('synthetic ADC denial'))
        if credential_failure
        else AsyncMock(return_value='synthetic-token')
    )
    monkeypatch.setattr(dream_capacity, '_vertex_tokens', lambda: SimpleNamespace(get_access_token=token))
    saturated = AsyncMock()
    monkeypatch.setattr(dream_capacity, 'mark_saturated', saturated)
    requests = []

    def denied(request):
        requests.append(request)
        assert request.url.path.endswith(f'/models/{OLD}:generateContent')
        assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
        assert not request.url.params
        assert json.loads(request.content)['contents'][0]['parts'] == [{'text': 'Reply OK.'}]
        return httpx.Response(403, json={'error': {'status': 'PERMISSION_DENIED'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(denied)) as client:
        monkeypatch.setattr(dream_capacity, 'get_desktop_gemini_client', lambda: client)
        assert await dream_capacity._probe(OLD, 'us-central1') == 'inconclusive'

    assert len(requests) == (0 if credential_failure else 1)
    saturated.assert_not_awaited()


@pytest.mark.asyncio
async def test_38_saturation_cooldown_is_short_in_both_local_and_shared_state(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    try:
        await dream_capacity.mark_saturated(NEW)
        assert 0 < dream_capacity._local().cooldowns[NEW] - dream_capacity.time.monotonic() <= 10
        assert 0 < await redis.ttl(state.key() + ':saturated:' + NEW) <= 10
        # Gateway observations use the same short TTL, including another process's 429.
        await state.record(NEW, 'dedicated', 429, None)
        assert 0 < await redis.ttl(state.key() + ':saturated:' + NEW) <= 10
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_capacity_wait_uses_bounded_jitter_and_rechecks_shared_evidence(monkeypatch):
    now, pauses = [0], []
    available = AsyncMock(side_effect=[None, None, NEW])
    monkeypatch.setattr(dream_capacity, 'available_model', available)

    async def sleep(seconds):
        pauses.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(dream_capacity.asyncio, 'sleep', sleep)
    assert await dream_capacity.wait_for_capacity(200, 20, clock=lambda: now[0])
    assert len(pauses) == 3
    assert all(lo <= pause <= hi for pause, lo, hi in zip(pauses, [5, 10, 15], [10, 20, 30]))
    assert available.await_count == 3
    pauses.clear()
    available.reset_mock()
    assert not await dream_capacity.wait_for_capacity(now[0] + 21, 20, clock=lambda: now[0])
    assert not pauses and available.await_count == 0


@pytest.mark.asyncio
async def test_capacity_wait_stays_fail_closed_and_is_cancellable(monkeypatch):
    pauses = []
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=None))

    async def sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(dream_capacity.asyncio, 'sleep', sleep)
    assert not await dream_capacity.wait_for_capacity(1000, 20, clock=lambda: 0)
    assert len(pauses) == 6 and all(5 <= pause <= 30 for pause in pauses)

    async def cancelled(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(dream_capacity.asyncio, 'sleep', cancelled)
    with pytest.raises(asyncio.CancelledError):
        await dream_capacity.wait_for_capacity(1000, 20, clock=lambda: 0)

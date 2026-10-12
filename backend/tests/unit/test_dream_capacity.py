"""Backend discovery and cooldown work without gateway reservation storage."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import httpx
import pytest

from config.vertex_reservations import State
from models.dream_agent import Plan
from utils import dream_agent, dream_capacity, dream_transport
from utils.dream_metrics import PASSES
from utils.llm.shaped_agent import Budget, Mount
from utils.llm.vertex_reservation_state import ReservationState
from utils.llm.vertex_pt_routing import PT_MODEL_CURRENT

OLD, NEW = 'gemini-2.5-flash', 'gemini-3.8-flash'


@pytest.fixture(autouse=True)
def isolated_local_capacity():
    dream_capacity._local_state.cache_clear()
    yield
    dream_capacity._local_state.cache_clear()


@pytest.mark.asyncio
async def test_backend_discovery_publishes_shared_evidence_without_gateway(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware')
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_PROJECT', 'based-hardware')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)
    requests = []

    def respond(request):
        requests.append(request)
        if OLD not in request.url.path:
            return httpx.Response(503, json={'error': {}})
        return httpx.Response(
            200,
            json={
                'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'},
                'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
            },
        )

    token = AsyncMock(return_value='synthetic-token')
    monkeypatch.setattr(dream_capacity, '_vertex_tokens', lambda: SimpleNamespace(get_access_token=token))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(dream_capacity, 'get_desktop_gemini_client', lambda: client)
        try:
            # Cold discovery is advisory: the first sweep still admits.
            assert await dream_capacity.available_model() == PT_MODEL_CURRENT
            slot = await dream_capacity.claim(2)
            assert slot is not None
            await dream_capacity.release(slot)
            await asyncio.gather(*state._probe_tasks)
            assert await dream_capacity.available_model() == OLD
            await asyncio.gather(*state._probe_tasks)
            assert await dream_capacity.available_model() == OLD
            doc = json.loads(await redis.get(state.key()))
            assert state.key().startswith('vertex-reservations:v1:based-hardware:')
            assert doc['states'][OLD] == 'active' and doc['evidence'][OLD]['success_at'] > 0
            assert (await ReservationState(redis).refresh())[OLD] == State.ACTIVE
            assert len(requests) == 2  # One globally leased probe per declared model.
            for request in requests:
                assert '/projects/based-hardware/' in request.url.path
                assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
                assert request.headers['Authorization'] == 'Bearer synthetic-token'
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
        (429, None, dream_transport.TRIAGE_LANE, False),
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
        with pytest.raises(dream_transport.CapacityWait if cools else dream_transport.PreTokenFailure) as exc:
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
        decisions = [json.loads(record.message) for record in caplog.records if record.message.startswith('{')]
        assert len(decisions) == int(cools)
        if cools:
            assert decisions[0]['decision'] == 'waiting'
            assert decisions[0]['reason'] == 'saturated' and decisions[0]['source'] == 'gateway_response'
    finally:
        await redis.aclose()


def test_no_model_sweep_is_visible_without_owner_admission(monkeypatch, caplog):
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=None))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: pytest.fail('owner page read'))
    metric = PASSES.labels('waiting', 'none')._value
    before = metric.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        assert asyncio.run(dream_agent.drain()) == [{'status': 'waiting', 'reason': 'reserved_capacity'}]
    assert metric.get() == before + 1
    assert 'Dream pass status=waiting' in caplog.text


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
    assert sink == {'tokens': 0, 'usage_unknown': False}

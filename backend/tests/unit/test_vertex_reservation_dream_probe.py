"""Dream discovery uses its real gateway identity and strict shared PT evidence."""

import asyncio
import json
from unittest.mock import AsyncMock

import fakeredis.aioredis
from fastapi import FastAPI
import httpx
import pytest

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import VertexGeminiProvider
from llm_gateway.routers import dependencies, openai_compatible
from utils import dream_capacity
from utils.llm.vertex_reservation_state import ReservationState
from utils.llm.usage_tracker import set_usage_context, reset_usage_context

MODEL = 'gemini-3.8-flash'
OLD = 'gemini-2.5-flash'


@pytest.fixture
async def gateway_probe(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.invalid')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    dream_capacity._local_state.cache_clear()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = ReservationState(redis)
    gateway_state = ReservationState(redis)
    monkeypatch.setattr(dream_capacity, 'reservation_state', state)

    def no_direct_credentials():
        pytest.fail('Dream probe used backend ADC instead of gateway service auth')

    monkeypatch.setattr(dream_capacity, '_vertex_tokens', no_direct_credentials)
    requests = []
    reply = {'status': 200, 'traffic': 'PROVISIONED_THROUGHPUT'}

    def vertex(request):
        requests.append(request)
        assert str(request.url) == (
            'https://aiplatform.googleapis.com/v1/projects/synthetic-project/locations/us/'
            f'publishers/google/models/{MODEL}:generateContent'
        )
        assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
        assert request.headers['Authorization'] == 'Bearer synthetic-gateway-token'
        if reply['status'] != 200:
            return httpx.Response(reply['status'], json={'error': {'message': 'synthetic denial'}})
        payload = {
            'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 3, 'candidatesTokenCount': 1},
        }
        if reply['traffic'] is not None:
            payload['usageMetadata']['trafficType'] = reply['traffic']
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(vertex)) as vertex_client:
        provider = VertexGeminiProvider(
            http_client=vertex_client, access_token_supplier=AsyncMock(return_value='synthetic-gateway-token')
        )
        provider._reservations = gateway_state
        app = FastAPI()
        app.include_router(openai_compatible.router)

        @app.middleware('http')
        async def synthetic_request(request, call_next):
            assert request.headers.get('X-Omi-User-Uid') is None
            assert request.headers['X-Omi-LLM-Feature'] == 'dream_reservation_probe'
            assert request.headers['Authorization'] == 'Bearer synthetic-service-token'
            payload = await request.json()
            assert payload['model'] == 'omi:auto:dream-verify'
            assert payload['google'] == {'dream_capacity_mode': 'reserved', 'dream_reserved_only': True}
            return await call_next(request)

        app.dependency_overrides[dependencies.get_gateway_config] = load_gateway_config
        app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'gemini': provider})
        monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', lambda *a, **k: None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as gateway_client:
            # The HTTP pool is shared with real Dream calls, without a real network.
            monkeypatch.setattr(dream_capacity, 'get_llm_gateway_client', lambda: gateway_client, raising=False)
            try:
                yield state, redis, requests, reply
            finally:
                await state.aclose()
                await gateway_state.aclose()
                await redis.aclose()
                dream_capacity._local_state.cache_clear()


async def seed(state, redis, age, *, old_lease_seconds=600, target_lease_seconds=0):
    seconds, micros = await redis.time()
    now = seconds + micros / 1_000_000
    await redis.set(
        state.key(),
        json.dumps(
            {
                'evidence': {MODEL: {'success_at': now - age}},
                'leases': {OLD: now + old_lease_seconds, MODEL: now + target_lease_seconds},
            }
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('old_lease_seconds', [600, -1])
async def test_cold_admission_recovers_via_gateway_without_backend_vertex_permission(gateway_probe, old_lease_seconds):
    state, redis, requests, _ = gateway_probe
    await seed(state, redis, 901, old_lease_seconds=old_lease_seconds)
    # Old replicas' advisory failures must not veto fresh gateway proof.
    await redis.set(state.key() + ':dream-probe-failed:' + MODEL, '1', ex=600)
    token = set_usage_context('synthetic-owner', 'synthetic-feature')
    try:
        assert await dream_capacity.available_model() is None
        await asyncio.gather(*state._probe_tasks)
    finally:
        reset_usage_context(token)
    assert await dream_capacity.available_model() == MODEL
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'Reply OK.'}]}]
    assert body['generationConfig']['maxOutputTokens'] == 16
    assert (await ReservationState(redis).refresh())[MODEL].value == 'active'
    slot = await dream_capacity.claim(2)
    assert slot and not slot[0].startswith('dream-local:')
    await dream_capacity.release(slot)


@pytest.mark.asyncio
async def test_stale_admission_bypasses_snapshot_and_claims_only_dream_model(gateway_probe):
    state, redis, requests, _ = gateway_probe
    await seed(state, redis, 901, old_lease_seconds=-1)
    # A read-only refresh in this process must not suppress a subsequent claim.
    await state.refresh()
    before = json.loads(await redis.get(state.key()))['leases'][OLD]
    assert await dream_capacity.available_model() is None
    await asyncio.gather(*state._probe_tasks)
    assert len(requests) == 1
    assert json.loads(await redis.get(state.key()))['leases'][OLD] == before
    assert await dream_capacity.available_model() == MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'env,value',
    [
        ('OMI_VERTEX_RESERVATION_STATES', json.dumps({OLD: 'inactive'})),
        ('OMI_VERTEX_RESERVATION_STATES', json.dumps({MODEL: 'active'})),
        ('OMI_VERTEX_RESERVATION_STATES', json.dumps({MODEL: 'inactive'})),
        ('OMI_VERTEX_PT_MODEL', OLD),
        ('OMI_VERTEX_PT_MODEL', MODEL),
    ],
)
async def test_stale_dream_proof_is_independent_of_desktop_routing_overrides(gateway_probe, monkeypatch, env, value):
    state, redis, requests, _ = gateway_probe
    monkeypatch.setenv(env, value)
    await seed(state, redis, 901, old_lease_seconds=-1)
    assert await dream_capacity.available_model() is None
    await asyncio.gather(*state._probe_tasks)
    assert len(requests) == 1
    assert await dream_capacity.available_model() == MODEL


@pytest.mark.asyncio
async def test_stale_probe_is_leased_across_replicas_and_retries_after_expiry(gateway_probe, monkeypatch):
    state, redis, requests, reply = gateway_probe
    reply['status'] = 403  # No fresh evidence: every admission keeps asking for a probe.
    await seed(state, redis, 901, old_lease_seconds=-1)
    replicas = [state, ReservationState(redis), ReservationState(redis)]
    try:
        await asyncio.gather(
            *(
                replica.refresh(dream_capacity._probe, probe_model=MODEL, fresh_seconds=900, apply_overrides=False)
                for replica in replicas
            )
        )
        await asyncio.gather(*(task for replica in replicas for task in replica._probe_tasks))
        assert len(requests) == 1
        for replica in replicas:
            monkeypatch.setattr(dream_capacity, 'reservation_state', replica)
            assert await dream_capacity.available_model() is None
            await asyncio.gather(*replica._probe_tasks)
        assert len(requests) == 1
        # Advance the lease, without a real-clock sleep or shortening its window.
        doc = json.loads(await redis.get(state.key()))
        doc['leases'][MODEL] = 0
        await redis.set(state.key(), json.dumps(doc))
        assert await dream_capacity.available_model() is None
        await asyncio.gather(*replicas[-1]._probe_tasks)
        assert len(requests) == 2
    finally:
        for replica in replicas[1:]:
            await replica.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('fresh_seconds,age,expected_calls', [(900, 899, 0), (60, 61, 1)])
async def test_admission_probes_only_at_dream_freshness_threshold(
    gateway_probe, monkeypatch, fresh_seconds, age, expected_calls
):
    state, redis, requests, _ = gateway_probe
    monkeypatch.setenv('DREAM_RESERVATION_FRESH_SECONDS', str(fresh_seconds))
    await seed(state, redis, age, old_lease_seconds=-1)
    assert (await dream_capacity.available_model() == MODEL) is (expected_calls == 0)
    await asyncio.gather(*state._probe_tasks)
    assert len(requests) == expected_calls
    assert await dream_capacity.available_model() == MODEL


@pytest.mark.asyncio
async def test_stale_admission_respects_existing_target_lease(gateway_probe):
    state, redis, requests, _ = gateway_probe
    await seed(state, redis, 901, old_lease_seconds=-1, target_lease_seconds=600)
    # Neither another service's target lease nor the expired 2.5 lease is stolen.
    await state.refresh()
    before = json.loads(await redis.get(state.key()))['leases']
    assert await dream_capacity.available_model() is None
    assert not state._probe_tasks
    assert requests == []
    assert json.loads(await redis.get(state.key()))['leases'] == before


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 403, 503])
async def test_noncapacity_gateway_denial_cannot_veto_fresh_shared_evidence(gateway_probe, status):
    state, redis, requests, reply = gateway_probe
    await seed(state, redis, 0)
    reply['status'] = status
    assert await dream_capacity._probe(MODEL, 'us') == 'inconclusive'
    assert await dream_capacity.available_model() == MODEL
    assert await redis.get(state.key() + ':dream-probe-failed:' + MODEL) is None
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_gateway_capacity_denial_still_cools_for_ten_seconds(gateway_probe):
    state, redis, requests, reply = gateway_probe
    await seed(state, redis, 0)
    reply['status'] = 429
    assert await dream_capacity._probe(MODEL, 'us') == 'capacity_error'
    assert await dream_capacity.available_model() is None
    assert 0 < await redis.ttl(state.key() + ':saturated:' + MODEL) <= 10
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('traffic', [None, 'ON_DEMAND'])
async def test_gateway_200_does_not_manufacture_reservation_evidence(gateway_probe, traffic):
    state, redis, requests, reply = gateway_probe
    await seed(state, redis, 901)
    reply['traffic'] = traffic
    assert await dream_capacity.available_model() is None
    await asyncio.gather(*state._probe_tasks)
    assert await dream_capacity.available_model() is None
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['false', '0', 'off'])
async def test_gateway_probe_kill_switch_makes_no_call_and_keeps_fresh_evidence(gateway_probe, monkeypatch, value):
    state, redis, requests, _ = gateway_probe
    monkeypatch.setenv('DREAM_GATEWAY_PROBE_ENABLED', value)
    await seed(state, redis, 0)
    assert await dream_capacity._probe(MODEL, 'us') == 'inconclusive'
    assert await dream_capacity.available_model() == MODEL
    assert requests == []


@pytest.mark.asyncio
async def test_stale_admission_kill_switch_makes_no_call_or_claim(gateway_probe, monkeypatch):
    state, redis, requests, _ = gateway_probe
    monkeypatch.setenv('DREAM_GATEWAY_PROBE_ENABLED', 'false')
    await seed(state, redis, 901, old_lease_seconds=-1)
    await state.refresh()
    before = json.loads(await redis.get(state.key()))['leases']
    assert await dream_capacity.available_model() is None
    assert not state._probe_tasks
    assert requests == []
    assert json.loads(await redis.get(state.key()))['leases'] == before

"""Order migration serves only the active dedicated model; probes use synthetic input."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from config.vertex_reservations import State
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import VertexGeminiProvider
from llm_gateway.gateway.schemas import ProviderRef
from utils.llm import vertex_pt_routing as ptr
from utils.llm.vertex_reservation_probe import probe_reservation
from utils.llm.vertex_reservation_state import ReservationState


@pytest.mark.parametrize('location', ['us', 'us-central1', 'global'])
@pytest.mark.asyncio
async def test_moved_order_routes_every_alias_to_declared_dedicated_endpoint(monkeypatch, location):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, location)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            provider._reservations,
            'refresh',
            AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.INACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE}),
        )
        for anchor in ptr.DESKTOP_TEXT_LANES:
            await provider.create_chat_completion(
                {'messages': [{'role': 'user', 'content': 'synthetic'}]},
                provider_ref=ProviderRef(provider='gemini', model=anchor),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=1000,
            )
    assert len(seen) == len(ptr.DESKTOP_TEXT_LANES)
    for request in seen:
        assert f'/locations/{location}/' in request.url.path
        assert ptr.PT_MODEL_TARGET + ':generateContent' in request.url.path
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        assert json.loads(request.content)['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}


@pytest.mark.parametrize(
    'traffic,expected',
    [('PROVISIONED_THROUGHPUT', 'dedicated_success'), ('ON_DEMAND', 'inconclusive'), (None, 'inconclusive')],
)
@pytest.mark.asyncio
async def test_discovery_is_synthetic_dedicated_and_requires_strict_metadata(monkeypatch, traffic, expected):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')

    def handler(request):
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        assert json.loads(request.content)['contents'] == [{'role': 'user', 'parts': [{'text': 'Reply OK.'}]}]
        return httpx.Response(
            200,
            json={
                'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'trafficType': traffic},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (
            await probe_reservation(client, AsyncMock(return_value='synthetic'), ptr.PT_MODEL_TARGET, 'us') == expected
        )


@pytest.mark.parametrize('status', [200, 201, 429])
@pytest.mark.parametrize('traffic', ['PROVISIONED_THROUGHPUT', 'ON_DEMAND', None])
@pytest.mark.asyncio
async def test_only_strict_completed_dedicated_responses_publish_active_state(monkeypatch, status, traffic):
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('REDIS_DB_HOST', raising=False)
    state = ReservationState()
    await state.record(ptr.PT_MODEL_TARGET, 'dedicated', status, traffic)
    states = await state.refresh()
    assert (states[ptr.PT_MODEL_TARGET] == State.ACTIVE) == (status < 300 and traffic == 'PROVISIONED_THROUGHPUT')

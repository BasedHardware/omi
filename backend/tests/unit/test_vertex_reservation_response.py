"""Exercise completed reservation evidence through both serving transports."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request

from config.vertex_reservations import State
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import VertexGeminiProvider
from llm_gateway.gateway.schemas import ProviderRef
from routers import desktop_proxy as proxy
from utils.llm.vertex_reservation_state import ReservationState

TARGET = 'gemini-3.8-flash'


def complete(traffic='PROVISIONED_THROUGHPUT'):
    return {
        'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
        'usageMetadata': {'trafficType': traffic},
    }


def wire(case, stream):
    payload = complete()
    if case == 'empty':
        return b''
    if case == 'object':
        payload = {}
    elif case == 'metadata_only':
        payload.pop('candidates')
    elif case == 'partial':
        payload['candidates'][0].pop('finishReason')
    elif case == 'missing':
        payload.pop('usageMetadata')
    elif case == 'on_demand':
        payload['usageMetadata']['trafficType'] = 'ON_DEMAND'
    encoded = json.dumps(payload).encode()
    if not stream:
        return encoded
    if case == 'unterminated':
        return b'data: ' + encoded
    if case == 'contradictory':
        return b'data: ' + json.dumps(complete('ON_DEMAND')).encode() + b'\n\ndata: ' + encoded + b'\n\n'
    return b'data: ' + encoded + b'\n\n'


def request():
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {
                'type': 'http.request',
                'body': b'{"contents":[{"parts":[{"text":"synthetic"}]}]}',
                'more_body': False,
            }
        await asyncio.Event().wait()

    return Request({'type': 'http', 'method': 'POST', 'path': '/', 'query_string': b'', 'headers': []}, receive)


@pytest.mark.asyncio
@pytest.mark.parametrize('transport', ['gateway', 'direct'])
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(
    'case',
    ['empty', 'object', 'metadata_only', 'partial', 'missing', 'on_demand', 'valid', 'unterminated', 'contradictory'],
)
async def test_completed_explicit_pt_evidence_matrix(monkeypatch, transport, stream, case):
    if not stream and case in {'unterminated', 'contradictory'}:
        pytest.skip('SSE framing only')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    store = ReservationState()
    monkeypatch.setattr(store, 'transact', AsyncMock(return_value=({}, None)))
    token = AsyncMock(return_value='synthetic-token')
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=wire(case, stream)))
    ) as client:
        if transport == 'gateway':
            provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
            provider._reservations = store
            # Exercise dedicated response processing without supplying positive evidence.
            monkeypatch.setattr(provider, '_attempt_plan', lambda *a, **k: [(TARGET, 'dedicated')])
            kwargs = dict(
                provider_ref=ProviderRef(provider='gemini', model=TARGET),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=10000,
            )
            try:
                if stream:
                    _ = [
                        c
                        async for c in provider.stream_chat_completion(
                            {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                        )
                    ]
                else:
                    await provider.create_chat_completion(
                        {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                    )
            except Exception:
                assert case != 'valid'
        else:

            async def connected(_):
                await asyncio.Event().wait()

            monkeypatch.setattr(proxy, '_wait_for_disconnect', connected)
            monkeypatch.setattr(proxy, 'schedule_managed_attempt', lambda _: False)
            monkeypatch.setattr(proxy, 'reservation_state', store)
            proxy._reservation_snapshot.set({})
            monkeypatch.setattr(proxy, 'get_byok_key', lambda _: None)
            monkeypatch.setattr(proxy, 'llm_stub_enabled', lambda: False)
            monkeypatch.setattr(proxy, '_company_paid_via_gateway', lambda *a: False)
            monkeypatch.setattr(proxy, '_refresh_reservations', AsyncMock(return_value={}))
            monkeypatch.setattr(proxy, '_meter_server_request', AsyncMock(side_effect=lambda uid, path, *a: path))
            route = proxy.UpstreamRoute(
                'https://synthetic.invalid',
                {'X-Vertex-AI-LLM-Request-Type': 'dedicated'},
                {},
                'vertex_ai',
                'application_default_credentials',
                'us',
            )
            monkeypatch.setattr(proxy, '_upstream', AsyncMock(return_value=route))
            monkeypatch.setattr(proxy, 'get_desktop_gemini_client', lambda: client)
            monkeypatch.setattr(proxy, 'get_desktop_gemini_stream_client', lambda: client)
            monkeypatch.setattr(proxy, 'get_desktop_gemini_semaphore', lambda: asyncio.Semaphore(1))
            action = 'streamGenerateContent' if stream else 'generateContent'
            response = await asyncio.wait_for(
                proxy._proxy(request(), f'models/{TARGET}:{action}', stream, 'synthetic'), 2
            )
            if stream:
                _ = [c async for c in response.body_iterator]
        assert (TARGET in store._positive) == (case == 'valid')

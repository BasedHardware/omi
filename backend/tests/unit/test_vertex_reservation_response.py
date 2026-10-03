"""Exercise completed reservation evidence through both serving transports."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from starlette.requests import Request

from config.vertex_reservations import State
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import VertexGeminiProvider
from llm_gateway.gateway.schemas import ProviderRef
from routers import desktop_proxy as proxy
from utils.llm import desktop_gemini_telemetry
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
    elif case == 'invalid_finish':
        payload['candidates'][0]['finishReason'] = ['STOP']
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
    [
        'empty',
        'object',
        'metadata_only',
        'partial',
        'missing',
        'on_demand',
        'valid',
        'unterminated',
        'contradictory',
        'invalid_finish',
    ],
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
            monkeypatch.setattr(desktop_gemini_telemetry, 'schedule_managed_attempt', lambda _: False)
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


@pytest.mark.asyncio
@pytest.mark.parametrize('transport', ['gateway', 'direct'])
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize(
    'case',
    [
        'capacity',
        'generic429',
        'absent',
        '403',
        '500',
        'malformed',
        'empty',
        'on_demand',
        'valid',
        'overflow_off',
        'timeout',
        'connection',
        'unavailable',
        'shared_unavailable',
        'shared_backpressure',
    ],
)
async def test_shared_recovery_policy_matrix_through_both_transports(monkeypatch, transport, stream, active, case):
    from llm_gateway.gateway.provider_types import ProviderFailure
    from utils.llm import vertex_pt_routing as ptr

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.OVERFLOW_ENABLED_ENV, 'false' if case == 'overflow_off' else 'true')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    seen = []
    statuses = {
        'capacity': 429,
        'generic429': 429,
        'absent': 404,
        '403': 403,
        '500': 500,
        'overflow_off': 429,
        'unavailable': 404,
        'shared_unavailable': 429,
        'shared_backpressure': 429,
    }
    messages = {
        'capacity': 'Exceeded the provisioned throughput.',
        'overflow_off': 'Exceeded the provisioned throughput.',
        'generic429': 'Quota exceeded for requests per minute',
        'absent': 'No provisioned throughput order configured',
        'unavailable': 'Publisher Model was not found',
        'shared_unavailable': 'Exceeded the provisioned throughput.',
        'shared_backpressure': 'Exceeded the provisioned throughput.',
    }

    def handler(req):
        seen.append(req)
        if case in {'timeout', 'connection'}:
            raise (httpx.ReadTimeout if case == 'timeout' else httpx.ConnectError)('synthetic failure', request=req)
        if len(seen) == 2 and case in {'shared_unavailable', 'shared_backpressure'}:
            return httpx.Response(
                404 if case == 'shared_unavailable' else 429,
                json={
                    'error': {
                        'message': (
                            'Publisher Model was not found'
                            if case == 'shared_unavailable'
                            else 'Quota exceeded for requests per minute'
                        )
                    }
                },
            )
        if len(seen) == 1 and case in statuses:
            return httpx.Response(statuses[case], json={'error': {'message': messages.get(case, 'synthetic failure')}})
        if len(seen) == 1 and case in {'malformed', 'empty'}:
            return httpx.Response(
                200, content=(b'data: {bad\n\n' if stream else b'{bad') if case == 'malformed' else b''
            )
        payload = complete('ON_DEMAND' if case == 'on_demand' or len(seen) > 1 else 'PROVISIONED_THROUGHPUT')
        return httpx.Response(
            200, content=b'data: ' + json.dumps(payload).encode() + b'\n\n' if stream else json.dumps(payload).encode()
        )

    states = {TARGET: State.ACTIVE} if active else {}
    store = ReservationState()
    note_request = Mock(wraps=store.note_request)
    monkeypatch.setattr(store, 'note_request', note_request)
    monkeypatch.setattr(store, 'refresh', AsyncMock(return_value=states))
    monkeypatch.setattr(store, 'transact', AsyncMock(return_value=(states, None)))
    token = AsyncMock(return_value='synthetic-token')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if transport == 'gateway':
            provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
            provider._reservations = store
            kwargs = dict(
                provider_ref=ProviderRef(provider='gemini', model=TARGET),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=10000,
            )
            try:
                if stream:
                    _ = [
                        chunk
                        async for chunk in provider.stream_chat_completion(
                            {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                        )
                    ]
                else:
                    await provider.create_chat_completion(
                        {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                    )
            except ProviderFailure:
                assert case in statuses or case in {'empty', 'malformed', 'timeout', 'connection'}
        else:

            async def connected(_):
                await asyncio.Event().wait()

            async def refresh():
                proxy._reservation_snapshot.set(states)
                return states

            monkeypatch.setattr(proxy, '_wait_for_disconnect', connected)
            monkeypatch.setattr(desktop_gemini_telemetry, 'schedule_managed_attempt', lambda _: False)
            monkeypatch.setattr(proxy, 'reservation_state', store)
            proxy._reservation_snapshot.set({})
            monkeypatch.setattr(proxy, '_model_unavailable_at', {})
            monkeypatch.setattr(proxy, 'get_byok_key', lambda _: None)
            monkeypatch.setattr(proxy, 'llm_stub_enabled', lambda: False)
            monkeypatch.setattr(proxy, '_company_paid_via_gateway', lambda *a: False)
            monkeypatch.setattr(proxy, '_refresh_reservations', refresh)
            monkeypatch.setattr(proxy, '_meter_server_request', AsyncMock(side_effect=lambda uid, path, *a: path))
            monkeypatch.setattr(proxy._vertex_tokens, 'get_access_token', token)
            monkeypatch.setattr(proxy, 'get_desktop_gemini_client', lambda: client)
            monkeypatch.setattr(proxy, 'get_desktop_gemini_stream_client', lambda: client)
            monkeypatch.setattr(proxy, 'get_desktop_gemini_semaphore', lambda: asyncio.Semaphore(1))
            action = 'streamGenerateContent' if stream else 'generateContent'
            response = await asyncio.wait_for(
                proxy._proxy(request(), f'models/{TARGET}:{action}', stream, 'synthetic'), 2
            )
            if stream:
                _ = [chunk async for chunk in response.body_iterator]
        expected = ['dedicated' if active else 'shared']
        if active and case in {'capacity', 'absent', 'unavailable', 'shared_unavailable', 'shared_backpressure'}:
            expected.append('shared')
        fallback = (case == 'unavailable' and not active) or (case == 'shared_unavailable' and active)
        if fallback:
            expected.append('shared')
        assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == expected
        assert note_request.call_count == len(seen)
        assert [call.args[1] for call in note_request.call_args_list] == expected
        assert all(f'/models/{TARGET}:' in str(r.url) for r in (seen[:-1] if fallback else seen))
        if fallback:
            assert '/models/gemini-3.1-flash-lite:' in str(seen[-1].url)
        assert (TARGET in store._positive) == (active and case == 'valid')

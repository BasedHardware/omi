"""Exercise completed reservation evidence through the gateway Vertex provider."""

import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from config.vertex_reservations import State
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import VertexGeminiProvider, ProviderFailure
from llm_gateway.gateway.schemas import ProviderRef, FailureClass
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


@pytest.mark.asyncio
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
async def test_completed_explicit_pt_evidence_matrix(monkeypatch, stream, case):
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
        assert (TARGET in store._positive) == (case == 'valid')


@pytest.mark.asyncio
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
async def test_shared_recovery_policy_matrix_through_gateway(monkeypatch, stream, active, case):
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
            assert not active or case in statuses or case in {'empty', 'malformed', 'timeout', 'connection'}
        expected = ['dedicated'] if active else []
        assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == expected
        assert note_request.call_count == len(seen)
        assert [call.args[1] for call in note_request.call_args_list] == expected
        assert all(f'/models/{TARGET}:' in str(r.url) for r in seen)
        assert (TARGET in store._positive) == (active and case == 'valid')

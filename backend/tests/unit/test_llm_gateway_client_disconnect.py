"""Client-disconnect classification at the gateway's request-body boundary.

A caller that closes its connection before the JSON body finishes arriving is
an expected peer event. Starlette raises ``ClientDisconnect`` from the body
read; before the shared boundary classified it, the exception escaped every
JSON surface as an unhandled ASGI traceback (llm-gateway prod:
``starlette.requests.ClientDisconnect`` from ``systemone``'s first read) and
left no rejection metric behind. These tests pin the classification, the
bounded 400, and the "no provider work, no route accounting" behavior of each
surface's disconnect arm.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.errors import (
    INVALID_REQUEST_REJECTION_CODES,
    GatewayClientDisconnectedError,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.metrics import _safe_rejection_reason  # pyright: ignore[reportPrivateUsage]
from llm_gateway.routers import anthropic_messages, embeddings, openai_compatible, systemone


def _disconnecting_request(request_id: str, path: str) -> Request:
    async def receive():
        return {'type': 'http.disconnect'}

    request = Request({'type': 'http', 'method': 'POST', 'path': path, 'headers': []}, receive)
    request.state.request_id = request_id
    return request


def _gateway_config():
    return load_gateway_config(prod_mode=True)


def _recorded_rejections(monkeypatch: pytest.MonkeyPatch, module, surface: str) -> list[dict]:
    recorded: list[dict] = []
    monkeypatch.setattr(module, 'observe_request_rejection', lambda **kwargs: recorded.append(kwargs))
    assert surface
    return recorded


async def test_request_json_classifies_client_disconnect():
    request = _disconnecting_request('probe-disconnect', '/v1/systemone')

    with pytest.raises(GatewayClientDisconnectedError) as excinfo:
        await openai_compatible._request_json(request)  # pyright: ignore[reportPrivateUsage]

    assert excinfo.value.code.value == 'invalid_request'
    assert excinfo.value.rejection_reason == 'request_body_disconnected'


def test_request_json_disconnect_reason_is_a_registered_rejection_code():
    assert 'request_body_disconnected' in INVALID_REQUEST_REJECTION_CODES
    assert _safe_rejection_reason('request_body_disconnected') == 'request_body_disconnected'


async def test_request_json_still_classifies_malformed_json_as_request_body_json():
    async def receive():
        return {'type': 'http.request', 'body': b'{', 'more_body': False}

    request = Request({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions', 'headers': []}, receive)

    with pytest.raises(GatewayInvalidRequestError) as excinfo:
        await openai_compatible._request_json(request)  # pyright: ignore[reportPrivateUsage]

    assert excinfo.value.rejection_reason == 'request_body_json'


async def test_request_json_disconnect_wraps_the_transport_exception():
    sentinel = ConnectionResetError('transport close')

    async def receive():
        raise sentinel

    request = Request({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions', 'headers': []}, receive)

    with pytest.raises(GatewayClientDisconnectedError) as excinfo:
        await openai_compatible._request_json(request)  # pyright: ignore[reportPrivateUsage]

    assert excinfo.value.__cause__ is sentinel


async def test_request_json_still_propagates_unknown_receive_failures():
    sentinel = RuntimeError('not a transport failure')

    async def receive():
        raise sentinel

    request = Request({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions', 'headers': []}, receive)

    with pytest.raises(RuntimeError) as excinfo:
        await openai_compatible._request_json(request)  # pyright: ignore[reportPrivateUsage]

    assert excinfo.value is sentinel


async def test_chat_completions_client_disconnect_returns_400_and_records_rejection(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, openai_compatible, 'openai_chat_completions')
    request = _disconnecting_request('chat-disconnect-1', '/v1/chat/completions')

    response = await openai_compatible.create_chat_completion(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        openai_compatible.ProviderRegistry({}),
    )

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'openai_chat_completions'
    assert recorded[0]['error_class'] == 'invalid_request'
    assert isinstance(recorded[0]['error'], GatewayClientDisconnectedError)
    body = json.loads(bytes(response.body))
    assert body['error']['type'] == 'invalid_request_error'
    assert body['error']['code'] == 'invalid_request'


async def test_chat_completions_disconnect_never_resolves_a_route(monkeypatch):
    def _route_must_not_resolve(*_args, **_kwargs):
        raise AssertionError('route resolution ran for a request whose caller had already left')

    monkeypatch.setattr(openai_compatible, 'resolve_chat_completion_route', _route_must_not_resolve)
    request = _disconnecting_request('chat-disconnect-2', '/v1/chat/completions')

    response = await openai_compatible.create_chat_completion(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        openai_compatible.ProviderRegistry({}),
    )

    assert response.status_code == 400


async def test_embeddings_client_disconnect_returns_400_and_records_rejection(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, embeddings, 'openai_embeddings')
    scheduled: list = []
    monkeypatch.setattr(embeddings, 'schedule_attempt_trace', lambda *args, **kwargs: scheduled.append(args))
    request = _disconnecting_request('embed-disconnect-1', '/v1/embeddings')

    response = await embeddings.create_embedding(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        embeddings.ProviderRegistry({}),
    )

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'openai_embeddings'
    assert recorded[0]['error_class'] == 'invalid_request'
    assert scheduled == []


async def test_embeddings_disconnect_never_touches_the_provider_registry(monkeypatch):
    def _provider_must_not_run(*_args, **_kwargs):
        raise AssertionError('embedding provider ran for a request whose caller had already left')

    monkeypatch.setattr(embeddings, 'execute_embedding', _provider_must_not_run)
    request = _disconnecting_request('embed-disconnect-2', '/v1/embeddings')

    response = await embeddings.create_embedding(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        embeddings.ProviderRegistry({}),
    )

    assert response.status_code == 400


async def test_embeddings_malformed_json_keeps_existing_rejection_path(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, embeddings, 'openai_embeddings')

    async def receive():
        return {'type': 'http.request', 'body': b'not json', 'more_body': False}

    request = Request({'type': 'http', 'method': 'POST', 'path': '/v1/embeddings', 'headers': []}, receive)
    request.state.request_id = 'embed-bad-json'

    response = await embeddings.create_embedding(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        embeddings.ProviderRegistry({}),
    )

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['error_class'] == 'invalid_request'
    assert isinstance(recorded[0]['error'], GatewayInvalidRequestError)


async def test_systemone_client_disconnect_returns_400_and_records_rejection(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, systemone, 'openrouter_systemone')
    scheduled: list = []
    monkeypatch.setattr(systemone, 'schedule_attempt_trace', lambda *args, **kwargs: scheduled.append(args))
    request = _disconnecting_request('systemone-disconnect-1', '/v1/systemone')

    response = await systemone.create_systemone(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        systemone.ProviderRegistry({}),
    )

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'openrouter_systemone'
    assert recorded[0]['error_class'] == 'invalid_request'
    assert scheduled == []


async def test_systemone_disconnect_skips_proactivity_admission(monkeypatch):
    def _proactivity_must_not_run(*_args, **_kwargs):
        raise AssertionError('proactivity admission ran for a request whose caller had already left')

    monkeypatch.setattr(systemone, 'context_from_request', _proactivity_must_not_run)
    monkeypatch.setattr(systemone, 'attempt_scope', _proactivity_must_not_run)
    request = _disconnecting_request('systemone-disconnect-2', '/v1/systemone')

    response = await systemone.create_systemone(
        request,
        ServiceCaller(name='backend'),
        _gateway_config(),
        systemone.ProviderRegistry({}),
    )

    assert response.status_code == 400


async def test_image_generation_client_disconnect_returns_400_and_records_rejection(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, openai_compatible, 'openai_images_generations')
    request = _disconnecting_request('image-disconnect-1', '/v1/images/generations')

    response = await openai_compatible.create_image_generation(request, ServiceCaller(name='backend'))

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'openai_images_generations'
    assert recorded[0]['error_class'] == 'invalid_request'


async def test_image_generation_disconnect_never_calls_the_image_provider(monkeypatch):
    def _image_provider_must_not_run():
        raise AssertionError('image provider client built for a request whose caller had already left')

    monkeypatch.setattr(openai_compatible, '_get_image_generation_client', _image_provider_must_not_run)
    request = _disconnecting_request('image-disconnect-2', '/v1/images/generations')

    response = await openai_compatible.create_image_generation(request, ServiceCaller(name='backend'))

    assert response.status_code == 400


async def test_anthropic_client_disconnect_records_rejection_and_raises_400(monkeypatch):
    recorded = _recorded_rejections(monkeypatch, anthropic_messages, 'anthropic_messages')
    request = _disconnecting_request('anthropic-disconnect-1', '/v1/messages')

    with pytest.raises(HTTPException) as excinfo:
        await anthropic_messages.create_anthropic_message(
            request,
            ServiceCaller(name='backend'),
            _gateway_config(),
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == 'request body not received'
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'anthropic_messages'
    assert recorded[0]['error_class'] == 'request_body_disconnected'


async def test_discard_abandoned_body_envelope_is_openai_shaped():
    exc = GatewayClientDisconnectedError(
        'request body not received: client disconnected',
        rejection_reason='request_body_disconnected',
    )

    response = await openai_compatible._discard_abandoned_body(exc)  # pyright: ignore[reportPrivateUsage]

    assert response.status_code == 400
    body = json.loads(bytes(response.body))
    assert body['error']['message'] == 'request body not received: client disconnected'
    assert body['error']['type'] == 'invalid_request_error'
    assert body['error']['code'] == 'invalid_request'

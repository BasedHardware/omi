from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
VERTEX_GATEWAY_PATH = REPO_ROOT / 'scripts' / 'dev-harness' / 'dev_harness' / 'jit_vertex_gateway.py'


def _load_vertex_gateway(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / 'backend'))
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 's' * 32)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')
    spec = importlib.util.spec_from_file_location(
        f'jit_vertex_gateway_contract_{time.monotonic_ns()}', VERTEX_GATEWAY_PATH
    )
    assert spec is not None and spec.loader is not None
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    return gateway


def _vertex_headers(**extra: str) -> dict[str, str]:
    return {
        'authorization': f"Bearer {'s' * 32}",
        'x-omi-service-caller': 'backend',
        **extra,
    }


def test_vertex_broker_rejects_multimodal_and_tool_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    with pytest.raises(HTTPException) as image_error:
        gateway._reject_unsupported_surfaces(
            {
                'messages': [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'image_url',
                                'image_url': {'url': 'data:image/png;base64,x'},
                            }
                        ],
                    }
                ]
            }
        )
    assert getattr(image_error.value, 'status_code', None) == 422

    with pytest.raises(HTTPException) as tool_error:
        gateway._reject_unsupported_surfaces({'messages': [], 'tools': [{'type': 'function'}]})
    assert getattr(tool_error.value, 'status_code', None) == 422


def test_vertex_broker_behaviorally_enforces_auth_byok_tools_and_body_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    client = TestClient(gateway.app)
    endpoint = '/v1/chat/completions'
    payload = {'messages': [{'role': 'user', 'content': 'hello'}]}

    assert client.post(endpoint, json=payload).status_code == 401
    assert (
        client.post(
            endpoint,
            json=payload,
            headers={
                'authorization': f"Bearer {'s' * 32}",
                'x-omi-service-caller': 'frontend',
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            endpoint,
            json=payload,
            headers=_vertex_headers(**{'x-omi-byok-openai': 'forbidden'}),
        ).status_code
        == 400
    )
    assert (
        client.post(
            endpoint,
            json={**payload, 'tools': [{'type': 'function'}]},
            headers=_vertex_headers(),
        ).status_code
        == 422
    )
    oversized = b'{' + (b'x' * gateway.MAX_REQUEST_BYTES) + b'}'
    assert (
        client.post(
            endpoint,
            content=oversized,
            headers={**_vertex_headers(), 'content-type': 'application/json'},
        ).status_code
        == 413
    )


def test_vertex_broker_clamps_output_and_caps_nonstream_response(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    class FakeProvider:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def create_chat_completion(self, request, **_kwargs):
            self.requests.append(dict(request))
            return SimpleNamespace(
                response={
                    'id': 'test',
                    'choices': [{'message': {'role': 'assistant', 'content': 'bounded'}}],
                }
            )

    provider = FakeProvider()
    monkeypatch.setattr(gateway, '_get_provider', lambda: provider)
    client = TestClient(gateway.app)
    response = client.post(
        '/v1/chat/completions',
        json={
            'messages': [{'role': 'user', 'content': 'hello'}],
            'max_tokens': gateway.MAX_OUTPUT_TOKENS * 100,
        },
        headers=_vertex_headers(),
    )
    assert response.status_code == 200
    assert provider.requests[0]['max_tokens'] == gateway.MAX_OUTPUT_TOKENS
    assert gateway._in_flight == 0

    monkeypatch.setattr(gateway, 'MAX_RESPONSE_BYTES', 8)
    response = client.post(
        '/v1/chat/completions',
        json={'messages': [{'role': 'user', 'content': 'hello'}]},
        headers=_vertex_headers(),
    )
    assert response.status_code == 502
    assert gateway._in_flight == 0


def test_vertex_broker_caps_stream_bytes_and_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    monkeypatch.setattr(gateway, 'MAX_RESPONSE_BYTES', 5)

    async def chunks():
        yield b'123'
        yield b'456'

    async def consume() -> None:
        async for _chunk in gateway._bounded_stream(chunks()):
            pass

    with pytest.raises(RuntimeError, match='response budget'):
        asyncio.run(consume())

    gateway._request_starts.clear()
    gateway._in_flight = 0
    gateway._reserve_request_slot()
    gateway._reserve_request_slot()
    with pytest.raises(HTTPException) as saturated:
        gateway._reserve_request_slot()
    assert saturated.value.status_code == 429
    gateway._release_request_slot()
    gateway._release_request_slot()
    assert gateway._in_flight == 0


def test_vertex_broker_readiness_refreshes_development_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    refreshed = 0

    def refresh() -> None:
        nonlocal refreshed
        refreshed += 1

    monkeypatch.setattr(gateway, '_refresh_development_adc', refresh)
    response = TestClient(gateway.app).get('/ready')
    assert response.status_code == 200
    assert refreshed == 1


def test_vertex_broker_adc_requires_dev_detected_and_quota_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    class FakeCredentials:
        def __init__(self, quota_project_id: str | None) -> None:
            self.quota_project_id = quota_project_id
            self.refreshed = False

        def refresh(self, _request) -> None:
            self.refreshed = True

    wrong_quota = FakeCredentials('based-hardware')
    monkeypatch.setattr(
        gateway.google.auth,
        'default',
        lambda **_kwargs: (wrong_quota, 'based-hardware-dev'),
    )
    with pytest.raises(RuntimeError, match='quota project'):
        gateway._refresh_development_adc()
    assert not wrong_quota.refreshed

    dev_quota = FakeCredentials('based-hardware-dev')
    monkeypatch.setattr(
        gateway.google.auth,
        'default',
        lambda **_kwargs: (dev_quota, 'based-hardware-dev'),
    )
    gateway._refresh_development_adc()
    assert dev_quota.refreshed

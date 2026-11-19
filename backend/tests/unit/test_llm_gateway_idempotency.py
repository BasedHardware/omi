from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from llm_gateway.gateway import idempotency
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider
from llm_gateway.main import app
from llm_gateway.routers import dependencies

POST = '/v1/chat/completions'
BODY = {'model': 'omi:auto:conv-structure', 'messages': [{'role': 'user', 'content': 'synthetic prompt'}]}


@pytest.fixture
def gateway(monkeypatch):
    provider = FakeChatCompletionProvider()
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'test-gateway-service-token')
    monkeypatch.delenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', raising=False)
    monkeypatch.setitem(
        app.dependency_overrides, dependencies.get_provider_registry, lambda: ProviderRegistry({'openai': provider})
    )
    headers = {
        'Authorization': 'Bearer test-gateway-service-token',
        'X-Omi-Service-Caller': 'backend',
        'X-Omi-User-Uid': 'test-owner',
        'Idempotency-Key': str(uuid4()),
    }
    with TestClient(app) as client:
        yield client, headers, provider


def test_kill_switch_fails_keyed_calls_closed_and_leaves_legacy_open(gateway, monkeypatch):
    client, headers, provider = gateway
    monkeypatch.setenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', 'off')
    assert client.post(POST, json=BODY, headers=headers).json()['error']['code'] == 'idempotency_disabled'
    assert client.get(f'{POST}/operations/{headers["Idempotency-Key"]}', headers=headers).status_code == 503
    assert provider.calls == []
    headers.pop('Idempotency-Key')
    assert client.post(POST, json=BODY, headers=headers).status_code == 200
    assert len(provider.calls) == 1


def test_keyed_request_bounds_reject_before_storage_or_provider(gateway, monkeypatch):
    client, headers, provider = gateway
    monkeypatch.setattr(idempotency, 'MAX_REQUEST_BYTES', 256)

    def no_storage(*args):
        pytest.fail('invalid request reached storage')

    monkeypatch.setattr(idempotency, '_claim', no_storage)
    assert client.post(POST, json=BODY, headers={**headers, 'Idempotency-Key': 'bad'}).status_code == 400
    assert client.post(POST, json={**BODY, 'stream': True}, headers=headers).status_code == 400
    assert client.post(POST, content=b'x' * 257, headers=headers).status_code == 413
    headers.pop('Idempotency-Key')
    assert client.post(f'{POST}/operations', json=BODY, headers=headers).status_code == 400
    assert provider.calls == []

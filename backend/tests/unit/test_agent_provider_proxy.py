import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import database.users
from routers import agent_provider_proxy


class _Document:
    def __init__(self, document_id, data):
        self.id = document_id
        self._data = data

    def to_dict(self):
        return self._data


class _Response:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"ok":true}'


class _Client:
    calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def post(self, url, *, content, headers):
        self.calls.append((url, content, headers))
        return _Response()


def test_find_agent_uid_requires_one_exact_firestore_match(monkeypatch):
    query = MagicMock()
    query.stream.return_value = [
        _Document("user-1", {"agentVm": {"authToken": "vm-token"}}),
    ]
    firestore_client = MagicMock()
    firestore_client.collection.return_value.where.return_value.limit.return_value = query
    monkeypatch.setattr(agent_provider_proxy, "get_firestore_client", lambda: firestore_client)

    assert agent_provider_proxy._find_agent_uid("vm-token") == "user-1"
    assert agent_provider_proxy._find_agent_uid("other-token") is None
    query.stream.return_value = [
        _Document("user-1", {"agentVm": {"authToken": "vm-token"}}),
        _Document("user-2", {"agentVm": {"authToken": "vm-token"}}),
    ]
    assert agent_provider_proxy._find_agent_uid("vm-token") is None


def test_gateway_headers_fail_closed_without_service_auth(monkeypatch):
    request = SimpleNamespace(headers={})
    monkeypatch.setattr(agent_provider_proxy, "get_llm_gateway_service_token", lambda: None)

    with pytest.raises(HTTPException) as error:
        agent_provider_proxy._gateway_request_headers(request, "user-1")

    assert error.value.status_code == 503


def test_anthropic_proxy_uses_sdk_messages_path():
    route_paths = {
        route.path for route in agent_provider_proxy.router.routes if getattr(route, "methods", None) == {"POST"}
    }

    assert "/v1/agent/anthropic/v1/messages" in route_paths


@pytest.mark.asyncio
async def test_anthropic_proxy_rewrites_model_and_does_not_forward_vm_token(monkeypatch):
    body = json.dumps({"model": "claude-3-5-sonnet", "messages": [], "stream": False}).encode()
    request = SimpleNamespace(
        headers={"anthropic-version": "2023-06-01", "x-api-key": "vm-token"},
    )

    request.stream = lambda: _body_stream(body)
    client = _Client()
    _Client.calls = []

    async def authorize(_request):
        return _authorized_user()

    monkeypatch.setattr(agent_provider_proxy, "_authorize_agent", authorize)
    monkeypatch.setattr(
        agent_provider_proxy,
        "_gateway_request_headers",
        lambda _request, uid: {"Authorization": "Bearer gateway-token", "X-Omi-User-Uid": uid},
    )
    monkeypatch.setattr(agent_provider_proxy, "get_llm_gateway_base_url", lambda: "http://gateway")
    monkeypatch.setattr(agent_provider_proxy.httpx, "AsyncClient", lambda **_kwargs: client)

    response = await agent_provider_proxy.agent_anthropic_messages(request)

    assert response.status_code == 200
    assert json.loads(response.body) == {"ok": True}
    assert client.calls
    url, forwarded_body, headers = client.calls[0]
    assert url == "http://gateway/v1/messages"
    assert json.loads(forwarded_body)["model"] == "omi:auto:chat-agent"
    assert headers == {"Authorization": "Bearer gateway-token", "X-Omi-User-Uid": "user-1"}


@pytest.mark.asyncio
async def test_anthropic_proxy_rejects_oversized_body(monkeypatch):
    request = SimpleNamespace(
        headers={}, stream=lambda: _body_stream(b"x" * (agent_provider_proxy._MAX_BODY_BYTES + 1))
    )

    async def authorize(_request):
        return _authorized_user()

    monkeypatch.setattr(agent_provider_proxy, "_authorize_agent", authorize)

    with pytest.raises(HTTPException) as error:
        await agent_provider_proxy.agent_anthropic_messages(request)

    assert error.value.status_code == 413


def _authorized_user():
    return "user-1"


async def _body_stream(body):
    yield body

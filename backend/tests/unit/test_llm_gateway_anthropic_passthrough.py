from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from llm_gateway.main import app
from llm_gateway.routers import anthropic_messages
from utils.llm.gateway_client import feature_auto_lane_id

CHAT_AGENT_LANE = feature_auto_lane_id('chat_agent')


class _FakeAsyncStreamContext:
    def __init__(self, *, status_code: int, chunks: list[bytes]):
        self.status_code = status_code
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def aread(self) -> bytes:
        return b''.join(self._chunks)

    def aiter_bytes(self):
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _FakeAsyncClient:
    def __init__(self):
        self.post_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self._post_response: httpx.Response | None = None
        self._stream_context: _FakeAsyncStreamContext | None = None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str], **kwargs):
        self.post_calls.append({'url': url, 'json': json, 'headers': headers, **kwargs})
        assert self._post_response is not None
        return self._post_response

    def stream(self, method: str, url: str, *, json: dict[str, Any], headers: dict[str, str], **kwargs):
        self.stream_calls.append({'method': method, 'url': url, 'json': json, 'headers': headers, **kwargs})
        assert self._stream_context is not None
        return self._stream_context


def _auth_headers() -> dict[str, str]:
    return {
        'authorization': 'Bearer shared-secret',
        'x-omi-service-caller': 'backend',
    }


def _agentic_request(**overrides: Any) -> dict[str, Any]:
    body = {
        'model': CHAT_AGENT_LANE,
        'max_tokens': 1024,
        'system': [
            {
                'type': 'text',
                'text': 'You are Omi.',
                'cache_control': {'type': 'ephemeral', 'ttl': '1h'},
            }
        ],
        'messages': [{'role': 'user', 'content': 'hello'}],
        'tools': [{'name': 'get_memories_tool', 'description': 'Get memories', 'input_schema': {'type': 'object'}}],
        'stream': False,
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _reset_anthropic_client(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'anthropic-test-key')
    anthropic_messages._anthropic_http_client = None
    fake = _FakeAsyncClient()
    monkeypatch.setattr(anthropic_messages, '_get_anthropic_http_client', lambda: fake)
    yield fake
    anthropic_messages._anthropic_http_client = None


def test_anthropic_messages_requires_service_auth():
    response = TestClient(app).post('/v1/messages', json=_agentic_request())
    assert response.status_code == 401


def test_anthropic_messages_passthrough_preserves_cache_control(_reset_anthropic_client):
    fake: _FakeAsyncClient = _reset_anthropic_client
    fake._post_response = httpx.Response(
        200,
        json={'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-sonnet-4-6'},
    )

    response = TestClient(app).post('/v1/messages', json=_agentic_request(), headers=_auth_headers())

    assert response.status_code == 200
    assert len(fake.post_calls) == 1
    forwarded = fake.post_calls[0]['json']
    assert forwarded['model'] == 'claude-sonnet-4-6'
    assert forwarded['system'][0]['cache_control'] == {'type': 'ephemeral', 'ttl': '1h'}
    assert forwarded['tools'][0]['name'] == 'get_memories_tool'
    assert fake.post_calls[0]['headers']['x-api-key'] == 'anthropic-test-key'


def test_anthropic_messages_stream_passthrough_preserves_server_tool_sse(_reset_anthropic_client):
    fake: _FakeAsyncClient = _reset_anthropic_client
    sse_chunks = [
        b'event: message_start\n',
        b'data: {"type":"message_start"}\n\n',
        b'event: content_block_start\n',
        b'data: {"type":"content_block_start","content_block":{"type":"server_tool_use","name":"web_search"}}\n\n',
        b'event: content_block_delta\n',
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}\n\n',
        b'event: message_stop\n',
        b'data: {"type":"message_stop"}\n\n',
    ]
    fake._stream_context = _FakeAsyncStreamContext(status_code=200, chunks=sse_chunks)

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.content

    assert len(fake.stream_calls) == 1
    assert fake.stream_calls[0]['json']['stream'] is True
    assert fake.stream_calls[0]['json']['system'][0]['cache_control']['ttl'] == '1h'
    assert b'server_tool_use' in body
    assert b'web_search' in body
    assert b'text_delta' in body


def test_anthropic_messages_uses_byok_key_header_when_present(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    fake._post_response = httpx.Response(
        200, json={'id': 'msg_byok', 'type': 'message', 'role': 'assistant', 'content': []}
    )

    headers = {**_auth_headers(), 'x-omi-byok-anthropic-key': 'user-sk-ant'}
    response = TestClient(app).post('/v1/messages', json=_agentic_request(), headers=headers)

    assert response.status_code == 200
    assert fake.post_calls[0]['headers']['x-api-key'] == 'user-sk-ant'

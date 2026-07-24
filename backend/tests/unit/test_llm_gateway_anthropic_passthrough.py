from __future__ import annotations

import asyncio
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
    def __init__(
        self,
        *,
        status_code: int,
        chunks: list[bytes],
        stream_error: Exception | None = None,
        exit_error: Exception | None = None,
        enter_error: BaseException | None = None,
    ):
        self.status_code = status_code
        self._chunks = chunks
        self._stream_error = stream_error
        self._exit_error = exit_error
        self._enter_error = enter_error

    async def __aenter__(self):
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, *_args):
        if self._exit_error is not None:
            raise self._exit_error
        return None

    async def aread(self) -> bytes:
        return b''.join(self._chunks)

    def aiter_bytes(self):
        async def _gen():
            for chunk in self._chunks:
                yield chunk
            if self._stream_error is not None:
                raise self._stream_error

        return _gen()


class _FakeAsyncClient:
    def __init__(self):
        self.post_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self._post_response: httpx.Response | None = None
        self._stream_context: _FakeAsyncStreamContext | None = None
        self._stream_context_factory = None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str], **kwargs):
        self.post_calls.append({'url': url, 'json': json, 'headers': headers, **kwargs})
        assert self._post_response is not None
        return self._post_response

    def stream(self, method: str, url: str, *, json: dict[str, Any], headers: dict[str, str], **kwargs):
        call = {'method': method, 'url': url, 'json': json, 'headers': headers, **kwargs}
        self.stream_calls.append(call)
        if self._stream_context_factory is not None:
            return self._stream_context_factory(call)
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
        'cache_control': {'type': 'ephemeral', 'ttl': '1h'},
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


def test_anthropic_messages_unknown_lane_records_pre_route_rejection(monkeypatch):
    recorded: list[dict[str, str]] = []
    monkeypatch.setattr(
        anthropic_messages,
        'observe_request_rejection',
        lambda **kwargs: recorded.append(kwargs),
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(model='omi:auto:not-real'),
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'anthropic_messages'
    assert recorded[0]['error_class'] == 'http_404'
    assert recorded[0]['request_id']


def test_anthropic_messages_rejects_openai_compatible_lane():
    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(model='omi:auto:chat-structured'),
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    assert 'not an anthropic messages lane' in response.json()['detail']


def test_anthropic_messages_passthrough_preserves_cache_control(_reset_anthropic_client):
    fake: _FakeAsyncClient = _reset_anthropic_client
    fake._post_response = httpx.Response(
        200,
        json={'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-sonnet-5'},
    )

    response = TestClient(app).post('/v1/messages', json=_agentic_request(), headers=_auth_headers())

    assert response.status_code == 200
    assert len(fake.post_calls) == 1
    forwarded = fake.post_calls[0]['json']
    assert forwarded['model'] == 'claude-sonnet-5'
    assert 'effort' not in forwarded
    assert forwarded['system'][0]['cache_control'] == {'type': 'ephemeral', 'ttl': '1h'}
    assert forwarded['cache_control'] == {'type': 'ephemeral', 'ttl': '1h'}
    assert forwarded['tools'][0]['name'] == 'get_memories_tool'
    assert fake.post_calls[0]['headers']['x-api-key'] == 'anthropic-test-key'


def test_anthropic_messages_records_cache_read_and_write_usage(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    persisted = []

    def capture_persist(context, trace):
        persisted.append((context, trace))

    monkeypatch.setattr(anthropic_messages, 'schedule_attempt_trace', capture_persist)
    fake._post_response = httpx.Response(
        200,
        json={
            'id': 'msg_2',
            'type': 'message',
            'role': 'assistant',
            'content': [],
            'model': 'claude-sonnet-5',
            'usage': {
                'input_tokens': 100,
                'cache_read_input_tokens': 900,
                'cache_creation_input_tokens': 50,
                'output_tokens': 10,
            },
        },
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(),
        headers={**_auth_headers(), 'x-omi-user-uid': 'user-123', 'x-omi-llm-feature': 'chat_agent'},
    )

    assert response.status_code == 200
    assert len(persisted) == 1
    context, trace = persisted[0]
    assert context.user_uid == 'user-123'
    assert context.feature == 'chat_agent'
    assert trace.attempts[0].usage is not None
    assert trace.attempts[0].usage.cached_input_tokens == 900
    assert trace.attempts[0].usage.cache_write_tokens == 50
    assert trace.attempts[0].usage.cache_write_ttl == '1h'
    assert trace.attempts[0].usage.cache_status.value == 'partial_hit'


def test_anthropic_messages_stream_passthrough_preserves_server_tool_sse(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
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
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'success'
    assert recorded[0]['phase'] == 'terminal_marker'
    assert recorded[0]['context'].credential_source == 'omi_managed'


def test_chat_agent_stream_omits_unsupported_effort_option(_reset_anthropic_client):
    """The production chat-agent streaming shape must not trigger Anthropic capability rejection."""
    fake: _FakeAsyncClient = _reset_anthropic_client

    def provider_response(call: dict[str, Any]) -> _FakeAsyncStreamContext:
        if 'effort' in call['json']:
            return _FakeAsyncStreamContext(
                status_code=400,
                chunks=[b'{"error":{"type":"invalid_request_error","message":"effort is not supported"}}'],
            )
        return _FakeAsyncStreamContext(
            status_code=200,
            chunks=[b'event: message_stop\n', b'data: {"type":"message_stop"}\n\n'],
        )

    fake._stream_context_factory = provider_response

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert 'effort' not in fake.stream_calls[0]['json']


def test_anthropic_messages_stream_returns_upstream_error_status(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    fake._stream_context = _FakeAsyncStreamContext(
        status_code=529,
        chunks=[b'{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'],
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 529
    assert response.json()['error']['type'] == 'overloaded_error'
    assert response.headers.get('content-type', '').startswith('application/json')
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'provider_5xx'


def test_anthropic_missing_key_records_streaming_before_output(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 503
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'invalid_config'
    assert recorded[0]['phase'] == 'before_output'
    assert recorded[0]['streaming'] is True


@pytest.mark.asyncio
async def test_anthropic_stream_open_cancellation_records_cancelled(monkeypatch, _reset_anthropic_client):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    fake._stream_context = _FakeAsyncStreamContext(
        status_code=200,
        chunks=[],
        enter_error=asyncio.CancelledError(),
    )
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    metric_context = anthropic_messages._AnthropicMetricContext(
        started_at=anthropic_messages.time_request(),
        lane_id=CHAT_AGENT_LANE,
        route_artifact_id='route.chat_agent.model_config.001',
        provider='anthropic',
        model='claude-sonnet-5',
        credential_source='omi_managed',
        request_id='9dc9d507-51a9-45b4-9f36-689521da3669',
    )

    with pytest.raises(asyncio.CancelledError):
        await anthropic_messages._streaming_anthropic_messages_response(
            _agentic_request(stream=True),
            headers={'x-api-key': 'test'},
            metric_context=metric_context,
        )

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['error_class'] == 'client_cancelled'
    assert recorded[0]['phase'] == 'before_output'
    assert recorded[0]['streaming'] is True


def test_anthropic_messages_uses_byok_key_header_when_present(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    fake._post_response = httpx.Response(
        200, json={'id': 'msg_byok', 'type': 'message', 'role': 'assistant', 'content': []}
    )

    headers = {**_auth_headers(), 'x-omi-byok-anthropic-key': 'user-sk-ant'}
    response = TestClient(app).post('/v1/messages', json=_agentic_request(), headers=headers)

    assert response.status_code == 200
    assert fake.post_calls[0]['headers']['x-api-key'] == 'user-sk-ant'
    assert recorded[0]['outcome'] == 'success'
    assert recorded[0]['context'].credential_source == 'service_forwarded_byok'


def test_anthropic_stream_eof_without_message_stop_is_not_success(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    fake._stream_context = _FakeAsyncStreamContext(
        status_code=200,
        chunks=[b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n'],
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'eof_before_terminal_marker'


def test_anthropic_stream_error_event_is_terminal_error(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    fake._stream_context = _FakeAsyncStreamContext(
        status_code=200,
        chunks=[b'event: error\ndata: {"type":"error"}\n\n'],
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'provider_error_event'


def test_anthropic_stream_midstream_transport_failure_is_distinct(_reset_anthropic_client, monkeypatch):
    fake: _FakeAsyncClient = _reset_anthropic_client
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    fake._stream_context = _FakeAsyncStreamContext(
        status_code=200,
        chunks=[b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n'],
        stream_error=httpx.ReadError('stream reset'),
    )

    response = TestClient(app).post(
        '/v1/messages',
        json=_agentic_request(stream=True),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert b'event: error' in response.content
    assert len(recorded) == 1
    assert recorded[0]['error_class'] == 'transport_midstream'


@pytest.mark.asyncio
async def test_anthropic_stream_cleanup_failure_still_observes_one_terminal(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        anthropic_messages,
        '_observe_message_terminal',
        lambda context, **kwargs: recorded.append({'context': context, **kwargs}),
    )
    stream_context = _FakeAsyncStreamContext(
        status_code=200,
        chunks=[b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n'],
        exit_error=RuntimeError('cleanup failed'),
    )
    metric_context = anthropic_messages._AnthropicMetricContext(
        started_at=anthropic_messages.time_request(),
        lane_id=CHAT_AGENT_LANE,
        route_artifact_id='route.chat_agent.model_config.001',
        provider='anthropic',
        model='claude-sonnet-5',
        credential_source='omi_managed',
        request_id='ef7217b8-9c75-4467-bdf5-bf3c818a37ac',
    )

    with pytest.raises(RuntimeError, match='cleanup failed'):
        _ = [
            chunk
            async for chunk in anthropic_messages._iter_open_anthropic_stream(
                stream_context,
                stream_context,
                metric_context=metric_context,
            )
        ]

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'eof_before_terminal_marker'

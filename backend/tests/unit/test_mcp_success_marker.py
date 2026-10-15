"""Unsampled qualified-day boundary, cross-worker claims and capture retry contract."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from unittest.mock import Mock

import pytest

from utils import mcp_analytics as analytics
from utils.mcp_server import transport
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.versions import DEFAULT_PROTOCOL_VERSION


class ClaimRedis:
    """Atomic NX/expiry/compare-and-set semantics, including stale ownership."""

    def __init__(self):
        self.values = {}
        self.clock = 0
        self.lock = Lock()

    def set(self, key, value, *, nx, ex):
        with self.lock:
            prior = self.values.get(key)
            if prior and prior[1] > self.clock:
                return None
            self.values[key] = (value, self.clock + ex)
            return True

    def eval(self, script, numkeys, key, owner, action, ttl):
        with self.lock:
            if self.values.get(key, (None, 0))[0] != owner:
                return 0
            if action == 'done':
                self.values[key] = ('done', self.clock + ttl)
            else:
                del self.values[key]
            return 1


@pytest.fixture
def marker(monkeypatch):
    redis = ClaimRedis()
    capture = Mock(return_value=True)
    monkeypatch.setattr(analytics.redis_db, 'r', redis)
    monkeypatch.setattr(analytics, 'emit_product_event', capture)
    return redis, capture


DAY = datetime(2026, 10, 15, 23, 59, 59, tzinfo=timezone.utc)


def emit(*, uid='user', at=DAY, initiator='unknown', client='codex'):
    analytics.emit_mcp_tool_use_succeeded(
        uid=uid, tool_name='get_memories', client_name=client, initiator=initiator, occurred_at=at
    )


def test_concurrent_workers_emit_once_per_uid_and_utc_day(marker):
    redis, capture = marker
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: emit(), range(32)))
    assert capture.call_count == 1
    assert next(iter(redis.values.values()))[0] == 'done'
    emit(at=DAY + timedelta(seconds=1))
    emit(uid='other')
    assert capture.call_count == 3
    first, next_day, other = [call.kwargs for call in capture.call_args_list]
    assert len({first['event_uuid'], next_day['event_uuid'], other['event_uuid']}) == 3
    assert first['timestamp'] == DAY
    assert first['properties'] == {
        'surface': 'mcp',
        'tool': 'get_memories',
        'client': 'codex',
        'initiator': 'unknown',
        'schema_version': 1,
        'source_platform': 'mcp',
        '$process_person_profile': False,
    }
    assert 'user' not in repr(first['properties'])


def test_capture_failure_releases_claim_and_retry_keeps_uuid(marker):
    redis, capture = marker
    capture.return_value = False
    emit()
    assert not redis.values
    capture.return_value = True
    emit()
    emit()
    assert capture.call_count == 2
    assert capture.call_args_list[0].kwargs['event_uuid'] == capture.call_args_list[1].kwargs['event_uuid']


def test_capture_success_settle_failure_retries_after_lease_with_same_uuid(marker, monkeypatch):
    redis, capture = marker
    original = redis.eval
    monkeypatch.setattr(redis, 'eval', Mock(side_effect=ConnectionError('private')))
    emit()
    emit()
    assert capture.call_count == 1
    redis.clock += analytics.MCP_SUCCESS_CLAIM_SECONDS + 1
    monkeypatch.setattr(redis, 'eval', original)
    emit()
    assert capture.call_count == 2
    assert capture.call_args_list[0].kwargs['event_uuid'] == capture.call_args_list[1].kwargs['event_uuid']


def test_redis_failure_does_not_capture_or_consume_day(marker, monkeypatch):
    redis, capture = marker
    original = redis.set
    monkeypatch.setattr(redis, 'set', Mock(side_effect=ConnectionError('private')))
    emit()
    capture.assert_not_called()
    monkeypatch.setattr(redis, 'set', original)
    emit()
    capture.assert_called_once()


def test_scheduled_agent_does_not_consume_later_qualified_day(marker):
    redis, capture = marker
    emit(initiator='scheduled_agent')
    assert not redis.values
    emit(initiator='user')
    capture.assert_called_once()


def test_client_is_closed_and_anonymous_never_claims(marker):
    redis, capture = marker
    emit(uid='mcp-anonymous')
    assert not redis.values
    emit(client='private-agent@example.com')
    assert capture.call_args.kwargs['properties']['client'] == 'unknown'


def test_scheduler_ignores_diagnostic_sampling_and_preserves_success_day(monkeypatch):
    queued = Mock()
    monkeypatch.setattr(analytics, 'submit_with_context', queued)
    monkeypatch.setenv(analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, '0')
    analytics.schedule_mcp_tool_use_succeeded(uid='u', tool_name='get_memories', client_name='codex')
    queued.assert_called_once()
    assert queued.call_args.kwargs['initiator'] == 'unknown'
    assert queued.call_args.kwargs['occurred_at'].tzinfo == timezone.utc


@pytest.mark.parametrize('method', ['initialize', 'tools/list', 'notifications/initialized', 'ping'])
def test_non_tool_requests_never_schedule_success(monkeypatch, method):
    success = Mock()
    monkeypatch.setattr(transport, 'schedule_mcp_tool_use_succeeded', success)
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=['memories.read'])
    transport.handle_mcp_message(auth, {'jsonrpc': '2.0', 'id': 1, 'method': method})
    success.assert_not_called()


@pytest.mark.parametrize('failure', [ToolExecutionError('private', code=-32001), RuntimeError('private')])
def test_application_failures_never_schedule_success_even_on_http_200(monkeypatch, failure):
    success = Mock()
    monkeypatch.setattr(transport, 'schedule_mcp_tool_use_succeeded', success)
    monkeypatch.setattr(transport, 'schedule_mcp_tool_call', Mock())
    monkeypatch.setattr(transport, 'execute_tool', Mock(side_effect=failure))
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=['memories.read'])
    result = transport._handle_tool_call(
        auth, transport.McpRequestContext(auth), 1, {'name': 'get_memories', 'arguments': {}}, DEFAULT_PROTOCOL_VERSION
    )
    assert result['result']['isError'] is True
    success.assert_not_called()


def test_success_uses_clientinfo_and_never_infers_user_from_auth_or_user_agent(monkeypatch):
    success = Mock()
    monkeypatch.setattr(transport, 'schedule_mcp_tool_use_succeeded', success)
    monkeypatch.setattr(transport, 'schedule_mcp_tool_call', Mock())
    monkeypatch.setattr(transport, 'execute_tool', Mock(return_value={'memories': []}))
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=['memories.read'])
    request = transport.McpRequestContext(auth, client_name='chatgpt', user_agent='ChatGPT')
    transport._handle_tool_call(auth, request, 1, {'name': 'get_memories', 'arguments': {}}, DEFAULT_PROTOCOL_VERSION)
    success.assert_called_once_with(uid='u', tool_name='get_memories', client_name='unknown')
    success.reset_mock()
    transport._handle_tool_call(
        auth,
        request,
        2,
        {'name': 'get_memories', 'arguments': {}, '_meta': {'io.modelcontextprotocol/clientInfo': {'name': 'codex'}}},
        DEFAULT_PROTOCOL_VERSION,
    )
    success.assert_called_once_with(uid='u', tool_name='get_memories', client_name='codex')


def test_top_level_clientinfo_is_attributed_per_tool_message(monkeypatch):
    success = Mock()
    monkeypatch.setattr(transport, 'schedule_mcp_tool_use_succeeded', success)
    monkeypatch.setattr(transport, 'schedule_mcp_tool_call', Mock())
    monkeypatch.setattr(transport, 'execute_tool', Mock(return_value={'memories': []}))
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=['memories.read'])
    transport.handle_mcp_message(
        auth,
        {
            'jsonrpc': '2.0',
            'id': 3,
            'method': 'tools/call',
            'params': {'name': 'get_memories', 'arguments': {}},
            '_meta': {'io.modelcontextprotocol/clientInfo': {'name': 'codex'}},
        },
    )
    success.assert_called_once_with(uid='u', tool_name='get_memories', client_name='codex')


def test_local_http_success_marker_includes_shared_defaults_and_ignores_failed_posts(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import mcp_sse
    from utils import product_telemetry

    fake = Mock()
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=['memories.read'])
    monkeypatch.setattr(analytics.redis_db, 'r', ClaimRedis())
    monkeypatch.setattr(transport, 'authenticate_mcp_request', Mock(return_value=auth))
    monkeypatch.setattr(transport, 'check_rate_limit_inline', Mock())
    monkeypatch.setattr(transport, 'check_rate_limit_context', Mock())
    monkeypatch.setattr(
        transport,
        'execute_tool',
        Mock(
            side_effect=[
                ToolExecutionError('not found', code=-32001),
                {'memories': []},
                {'memories': []},
            ]
        ),
    )
    monkeypatch.setattr(analytics, 'submit_with_context', lambda executor, fn, *args, **kwargs: fn(*args, **kwargs))
    monkeypatch.setenv(analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, '0')
    product_telemetry.set_product_telemetry_client_for_tests(fake)
    app = FastAPI()
    app.include_router(mcp_sse.router)
    try:
        with TestClient(app) as client:
            for method in ('initialize', 'tools/list'):
                assert client.post('/v1/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': method}).status_code == 200
            request = {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/call',
                'params': {'name': 'get_memories', 'arguments': {}},
            }
            failed = client.post('/v1/mcp', json=request)
            assert failed.status_code == 200
            assert failed.json()['result']['isError'] is True
            assert not any(
                call.kwargs['event'] == analytics.MCP_TOOL_USE_SUCCEEDED for call in fake.capture.call_args_list
            )
            assert client.post('/v1/mcp', json=request).status_code == 200
            assert client.post('/v1/mcp', json=request).status_code == 200
        successes = [
            call.kwargs
            for call in fake.capture.call_args_list
            if call.kwargs['event'] == analytics.MCP_TOOL_USE_SUCCEEDED
        ]
        assert len(successes) == 1
        assert successes[0]['properties']['source_platform'] == 'mcp'
        assert successes[0]['properties']['emitter'] == 'server'
        assert successes[0]['properties']['initiator'] == 'unknown'
    finally:
        product_telemetry.set_product_telemetry_client_for_tests(None)

"""Unsampled per-success MCP boundary and dashboard qualification contract."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from utils import mcp_analytics as analytics
from utils.mcp_server import transport
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.versions import DEFAULT_PROTOCOL_VERSION


@pytest.fixture
def marker(monkeypatch):
    capture = Mock(return_value=True)
    # New successes must not depend on Redis availability at all.
    redis = Mock()
    redis.set.side_effect = AssertionError('success must not claim Redis')
    redis.eval.side_effect = AssertionError('success must not settle Redis')
    monkeypatch.setattr(analytics.redis_db, 'r', redis)
    monkeypatch.setattr(analytics, 'emit_product_event', capture)
    return redis, capture


DAY = datetime(2026, 10, 15, 23, 59, 59, tzinfo=timezone.utc)


def emit(*, uid='user', at=DAY, initiator='unknown', client='codex', tool='get_memories'):
    analytics.emit_mcp_tool_use_succeeded(
        uid=uid, tool_name=tool, client_name=client, initiator=initiator, occurred_at=at
    )


def test_every_concurrent_success_emits_with_original_timestamp_and_no_daily_identity(marker):
    redis, capture = marker
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: emit(), range(32)))
    emit(at=DAY + timedelta(seconds=1))
    emit(uid='other')
    assert capture.call_count == 34
    redis.set.assert_not_called()
    redis.eval.assert_not_called()
    first = capture.call_args_list[0].kwargs
    assert first['timestamp'] == DAY
    assert 'event_uuid' not in first
    assert first['properties'] == {
        'surface': 'mcp',
        'tool': 'get_memories',
        'op_type': 'list',
        'client': 'codex',
        'initiator': 'unknown',
        'schema_version': 2,
        'source_platform': 'mcp',
        '$process_person_profile': False,
    }
    assert 'uid' not in first['properties']
    assert capture.call_args_list[-2].kwargs['timestamp'] == DAY + timedelta(seconds=1)


def test_capture_rejection_does_not_suppress_subsequent_success(marker):
    _, capture = marker
    capture.return_value = False
    emit()
    capture.return_value = True
    emit()
    emit()
    assert capture.call_count == 3


def test_dashboard_policy_does_not_filter_raw_successes(marker):
    _, capture = marker
    for initiator in ('scheduled_agent', 'user', 'unknown', 'untrusted-value'):
        emit(initiator=initiator)
    assert [call.kwargs['properties']['initiator'] for call in capture.call_args_list] == [
        'scheduled_agent',
        'user',
        'unknown',
        'unknown',
    ]
    assert analytics.MCP_QUALIFYING_INITIATORS == {'user', 'unknown'}
    assert analytics.MCP_QUALIFYING_CALLS_PER_UTC_DAY == 2


@pytest.mark.parametrize('uid,tool', [('mcp-anonymous', 'get_memories'), ('', 'get_memories'), ('u', 'private-tool')])
def test_anonymous_or_unregistered_never_emits(marker, uid, tool):
    _, capture = marker
    emit(uid=uid, tool=tool)
    capture.assert_not_called()


def test_client_is_closed(marker):
    _, capture = marker
    emit(client='private-agent@example.com')
    assert capture.call_args.kwargs['properties']['client'] == 'unknown'


@pytest.mark.parametrize(
    'tool,op_type',
    [
        ('get_memories', 'list'),
        ('search_memories', 'search'),
        ('get_user_profile', 'read'),
        ('create_memories', 'write'),
        ('private-tool', 'other'),
    ],
)
def test_operation_type_comes_from_registry(tool, op_type):
    assert analytics.mcp_success_op_type(tool) == op_type


def test_scheduler_ignores_diagnostic_sampling_and_preserves_success_time(marker, monkeypatch):
    _, capture = marker
    monkeypatch.setenv(analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, '0')
    for _ in range(3):
        analytics.schedule_mcp_tool_use_succeeded(uid='u', tool_name='get_memories', client_name='codex')
    assert capture.call_count == 3
    assert capture.call_args.kwargs['properties']['initiator'] == 'unknown'
    assert capture.call_args.kwargs['timestamp'].tzinfo == timezone.utc


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


@pytest.mark.parametrize(
    'name,arguments,scopes',
    [
        ('get_memories', {}, []),
        ('get_memories', 'invalid', ['memories.read']),
        ('unregistered-tool', {}, ['memories.read']),
    ],
)
def test_denied_invalid_and_unregistered_calls_never_schedule_success(monkeypatch, name, arguments, scopes):
    success = Mock()
    monkeypatch.setattr(transport, 'schedule_mcp_tool_use_succeeded', success)
    monkeypatch.setattr(transport, 'schedule_mcp_tool_call', Mock())
    execute = Mock(wraps=transport.execute_tool)
    monkeypatch.setattr(transport, 'execute_tool', execute)
    auth = MCPAuthContext(uid='u', auth_type='oauth', scopes=scopes)
    transport._handle_tool_call(
        auth, transport.McpRequestContext(auth), 1, {'name': name, 'arguments': arguments}, DEFAULT_PROTOCOL_VERSION
    )
    if name == 'unregistered-tool':
        execute.assert_called_once()
    else:
        execute.assert_not_called()
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
    monkeypatch.setattr(analytics.redis_db, 'r', Mock())
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
        assert len(successes) == 2
        assert successes[0]['properties']['source_platform'] == 'mcp'
        assert successes[0]['properties']['emitter'] == 'server'
        assert successes[0]['properties']['initiator'] == 'unknown'
    finally:
        product_telemetry.set_product_telemetry_client_for_tests(None)

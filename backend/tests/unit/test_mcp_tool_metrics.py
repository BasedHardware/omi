"""Unsampled per-tool Prometheus metrics for hosted MCP tools/call (synthetic calls, no IO)."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import utils.mcp_analytics as mcp_analytics

import utils.mcp_server.transport as mcp_transport
from utils.mcp_scopes import MCP_SUPPORTED_SCOPES
from utils.mcp_server import tool_metrics
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.errors import ToolExecutionError


def _auth(client_id='test-client', scopes=None):
    return MCPAuthContext(
        uid='uid-metrics',
        auth_type='oauth',
        scopes=list(MCP_SUPPORTED_SCOPES if scopes is None else scopes),
        client_id=client_id,
    )


def _call(name, result=None, error=None, client_id='test-client', scopes=None, cap=None):
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}}
    with (
        patch.object(mcp_transport, 'enforce_daily_cap', return_value=None, side_effect=cap),
        patch.object(mcp_transport, 'schedule_mcp_tool_call'),
        patch.object(mcp_transport, 'schedule_mcp_tool_use_succeeded'),
        patch.object(mcp_transport, 'execute_tool', return_value=result, side_effect=error),
    ):
        return mcp_transport.handle_mcp_message(_auth(client_id, scopes), message)


def calls(*labels):
    return tool_metrics.MCP_TOOL_CALLS_TOTAL.labels(*labels)._value.get()


def histogram_count(histogram, tool):
    return sum(bucket.get() for bucket in histogram.labels(tool)._buckets)


@pytest.fixture(autouse=True)
def no_posthog():
    with patch.object(mcp_analytics, 'emit_mcp_posthog_event'):
        yield


def test_success_counts_the_call_its_duration_size_and_truncation():
    tool = 'get_conversation_by_id'
    before = calls(tool, 'other_registered', 'success', 'none')
    durations = histogram_count(tool_metrics.MCP_TOOL_DURATION_SECONDS, tool)
    sizes = histogram_count(tool_metrics.MCP_TOOL_RESPONSE_CHARS, tool)
    truncated = tool_metrics.MCP_TOOL_TRUNCATED_TOTAL.labels(tool)._value.get()
    response = _call(tool, result={'conversation': {'id': 'c'}, 'truncated': True, 'next_cursor': 'x'})
    assert not response['result'].get('isError')
    assert calls(tool, 'other_registered', 'success', 'none') == before + 1
    assert histogram_count(tool_metrics.MCP_TOOL_DURATION_SECONDS, tool) == durations + 1
    assert histogram_count(tool_metrics.MCP_TOOL_RESPONSE_CHARS, tool) == sizes + 1
    assert tool_metrics.MCP_TOOL_TRUNCATED_TOTAL.labels(tool)._value.get() == truncated + 1


def test_model_visible_errors_are_counted_by_category():
    before = calls('search_conversations', 'other_registered', 'error', 'validation')
    response = _call('search_conversations', error=ToolExecutionError('bad date', code=-32602))
    assert response['result']['isError'] is True
    assert calls('search_conversations', 'other_registered', 'error', 'validation') == before + 1


def test_unknown_tools_collapse_to_one_label():
    before = calls('unknown', 'other_registered', 'error', 'unknown_tool')
    _call('no_such_tool_' + 'x' * 40, error=ToolExecutionError('Unknown tool', code=-32601))
    assert calls('unknown', 'other_registered', 'error', 'unknown_tool') == before + 1


def test_internal_failures_are_counted_and_still_answer():
    before = calls('get_memories', 'other_registered', 'error', 'internal')
    response = _call('get_memories', error=RuntimeError('boom'))
    assert response['result']['isError'] is True
    assert calls('get_memories', 'other_registered', 'error', 'internal') == before + 1


def test_a_broken_metric_never_breaks_the_tool_call():
    with patch.object(tool_metrics.MCP_TOOL_CALLS_TOTAL, 'labels', side_effect=RuntimeError('registry')):
        with patch.object(tool_metrics.MCP_TOOL_RESPONSE_CHARS, 'labels', side_effect=RuntimeError('registry')):
            response = _call('get_goals', result={'goals': []})
    assert response['result']['structuredContent'] == {'goals': []}


def test_capped_calls_are_counted_without_a_latency_sample_from_a_handler():
    before = calls('get_memories', 'other_registered', 'error', 'capped')
    capped = HTTPException(status_code=429, detail={'error': 'mcp_daily_cap', 'limit': 1})
    response = _call('get_memories', result={'memories': []}, cap=capped)
    assert response['result']['isError'] is True
    assert calls('get_memories', 'other_registered', 'error', 'capped') == before + 1


def test_a_quota_store_outage_is_counted_before_its_503():
    before = calls('get_memories', 'other_registered', 'error', 'internal')
    outage = HTTPException(status_code=503, detail='usage_unavailable')
    with pytest.raises(HTTPException):
        _call('get_memories', result={'memories': []}, cap=outage)
    assert calls('get_memories', 'other_registered', 'error', 'internal') == before + 1


def test_scope_denials_are_counted_as_authorization_denied():
    before = calls('get_memories', 'other_registered', 'error', 'authorization_denied')
    response = _call('get_memories', result={'memories': []}, scopes=['conversations.read'])
    assert response['error']['code'] == -32003
    assert calls('get_memories', 'other_registered', 'error', 'authorization_denied') == before + 1


def test_client_family_labels_are_the_bounded_analytics_families():
    chatgpt = next(iter(mcp_analytics._CHATGPT_CLIENT_IDS))
    assert mcp_analytics.mcp_client_family('oauth', chatgpt) == 'chatgpt'
    assert mcp_analytics.mcp_client_family('oauth', 'some-registered-client') == 'other_registered'
    assert mcp_analytics.mcp_client_family('legacy_mcp_key', None) == 'api_key'
    assert mcp_analytics.mcp_client_family('firebase', None) == 'unknown'


def test_reloading_with_a_different_shape_fails_loudly():
    with pytest.raises(ValueError, match='different shape'):
        tool_metrics._registered('omi_mcp_tool_calls_total', tool_metrics.Counter, ['tool'], lambda: None)

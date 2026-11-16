"""Unsampled per-tool Prometheus metrics for hosted MCP tools/call (synthetic calls, no IO)."""

from unittest.mock import patch

import pytest

import utils.mcp_server.transport as mcp_transport
from utils.mcp_scopes import MCP_SUPPORTED_SCOPES
from utils.mcp_server import tool_metrics
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.errors import ToolExecutionError


def _auth(client_id='test-client'):
    return MCPAuthContext(uid='uid-metrics', auth_type='oauth', scopes=list(MCP_SUPPORTED_SCOPES), client_id=client_id)


def _call(name, result=None, error=None, client_id='test-client'):
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}}
    with (
        patch.object(mcp_transport, 'enforce_daily_cap', return_value=None),
        patch.object(mcp_transport, 'schedule_mcp_tool_call'),
        patch.object(mcp_transport, 'schedule_mcp_tool_use_succeeded'),
        patch.object(mcp_transport, 'execute_tool', return_value=result, side_effect=error),
    ):
        return mcp_transport.handle_mcp_message(_auth(client_id), message)


def calls(*labels):
    return tool_metrics.MCP_TOOL_CALLS_TOTAL.labels(*labels)._value.get()


def histogram_count(histogram, tool):
    return sum(bucket.get() for bucket in histogram.labels(tool)._buckets)


@pytest.fixture(autouse=True)
def no_posthog():
    with patch('utils.mcp_analytics.emit_mcp_posthog_event'):
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

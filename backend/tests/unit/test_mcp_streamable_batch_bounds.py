"""Regression tests for the MCP Streamable-HTTP JSON-RPC batch bound.

``POST /v1/mcp/sse`` (``mcp_streamable_http``) charged exactly one ``mcp:sse``
rate-limit token per HTTP request, then iterated the JSON-RPC array in the body
with no length bound. One token therefore bought an arbitrary number of tool
executions -- the array length was a free amplification factor on every metered
tool behind the transport.

The fix bounds the array at ``_MAX_JSONRPC_BATCH`` and charges one token per
message in it, so the rate limit tracks executions instead of HTTP requests.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException


@pytest.fixture(scope="module")
def mcp():
    from routers import mcp_sse

    return mcp_sse


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _notification(index):
    return {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"n": index}}


@pytest.mark.asyncio
async def test_oversized_jsonrpc_batch_is_rejected(mcp):
    auth_context = SimpleNamespace(uid="test-uid")
    body = [_notification(i) for i in range(mcp._MAX_JSONRPC_BATCH + 1)]

    with patch.object(mcp, "authenticate_mcp_request", return_value=auth_context):
        with patch.object(mcp, "check_rate_limit_inline", return_value=None):
            with patch.object(mcp, "handle_mcp_message", return_value=(None, None)) as handler:
                with pytest.raises(HTTPException) as error:
                    await mcp.mcp_streamable_http(_Request(body), authorization="Bearer t")

    assert error.value.status_code == 413
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_each_batched_message_charges_a_rate_limit_token(mcp):
    """A 5-message batch is 5 tool executions, so it must cost 5 tokens, not 1."""
    auth_context = SimpleNamespace(uid="test-uid")
    body = [_notification(i) for i in range(5)]

    with patch.object(mcp, "authenticate_mcp_request", return_value=auth_context):
        with patch.object(mcp, "check_rate_limit_inline", return_value=None) as limiter:
            with patch.object(mcp, "handle_mcp_message", return_value=(None, None)):
                response = await mcp.mcp_streamable_http(_Request(body), authorization="Bearer t")

    assert response.status_code == 202
    assert limiter.call_count == 5
    assert all(call.args[:2] == ("test-uid", "mcp:sse") for call in limiter.call_args_list)


@pytest.mark.asyncio
async def test_single_message_still_charges_exactly_one_token(mcp):
    """Control: the non-batch path must not start charging extra."""
    auth_context = SimpleNamespace(uid="test-uid")

    with patch.object(mcp, "authenticate_mcp_request", return_value=auth_context):
        with patch.object(mcp, "check_rate_limit_inline", return_value=None) as limiter:
            with patch.object(mcp, "handle_mcp_message", return_value=(None, None)):
                response = await mcp.mcp_streamable_http(_Request(_notification(0)), authorization="Bearer t")

    assert response.status_code == 202
    assert limiter.call_count == 1

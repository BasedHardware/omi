"""#10735: a denied hosted-MCP memory read must be an error, not an empty 200.

The denial reasons that reach the fail-closed branch (missing app-key grant,
unreadable rollout state, shadow-only) are server-side authorization states the
caller cannot see. Returning ``{"memories": []}`` made them indistinguishable
from an account with no memories, so the client told the user their data was
gone instead of that it was withheld.

These drive the real client-facing seam -- ``handle_mcp_message('tools/call')``,
the same entry the hosted SSE transport calls -- with only the rollout adapters
stubbed, and assert on the JSON-RPC envelope the MCP client actually receives.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from routers import mcp_sse as sse
from utils.mcp_memories import McpMemoryListResult, McpMemorySearchResult
from utils.memory.default_read_rollout import MemoryReadDecision
from utils.memory.memory_system import MemorySystem

UID = "mcp-user"
MEMORY_SCOPES = ["memories.read", "memories.write"]


def _auth_context():
    return sse.MCPAuthContext(
        uid=UID,
        auth_type="api_key",
        scopes=MEMORY_SCOPES,
        memory_context=SimpleNamespace(uid=UID, app_id="app-1", key_id="key-1"),
    )


def _tools_call(tool_name, arguments):
    response, _ = sse.handle_mcp_message(
        _auth_context(),
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}},
    )
    return response


def _legacy_rollout_patches(list_result, search_result):
    return (
        patch.object(sse, "pin_memory_system", return_value=MemorySystem.LEGACY),
        patch.object(sse, "authorize_memory_external_default_memory_read", return_value=SimpleNamespace(allowed=True)),
        patch.object(sse, "read_default_read_rollout", return_value=SimpleNamespace()),
        patch.object(sse, "list_default_mcp_memories", return_value=list_result),
        patch.object(sse, "search_default_mcp_memories_vector", return_value=search_result),
    )


def _enter(*managers):
    """Enter a set of patches together and close them all on exit."""
    stack = ExitStack()
    for manager in managers:
        stack.enter_context(manager)
    return stack


def _denied(reason='missing_mcp_default_memory_grant', decision=MemoryReadDecision.DENY_MEMORY):
    return (
        McpMemoryListResult(memories=[], read_decision=decision, fallback_reason=reason),
        McpMemorySearchResult(memories=[], read_decision=decision, fallback_reason=reason),
    )


@pytest.mark.parametrize(
    "decision,reason",
    [
        (MemoryReadDecision.DENY_MEMORY, 'missing_mcp_default_memory_grant'),
        (MemoryReadDecision.DENY_MEMORY, 'rollout_read_failed'),
        (MemoryReadDecision.SHADOW_ONLY, 'shadow_only'),
    ],
)
def test_denied_get_memories_returns_jsonrpc_error_not_empty_result(decision, reason):
    list_result, search_result = _denied(reason, decision)
    with _enter(*_legacy_rollout_patches(list_result, search_result)):
        response = _tools_call("get_memories", {})

    assert "result" not in response
    assert response["error"]["code"] == -32009
    assert reason in response["error"]["message"]


def test_denied_search_memories_returns_jsonrpc_error_not_empty_result():
    list_result, search_result = _denied()
    with _enter(*_legacy_rollout_patches(list_result, search_result)):
        response = _tools_call("search_memories", {"query": "anything"})

    assert "result" not in response
    assert response["error"]["code"] == -32009
    assert 'missing_mcp_default_memory_grant' in response["error"]["message"]


def test_authorized_legacy_read_still_serves_memories():
    """The un-enrolled cohort (absent rollout state doc) must keep reading legacy memories."""
    list_result, search_result = _denied('missing_rollout_state')
    legacy_memory = {"id": "m1", "content": "legacy memory", "category": "core"}
    with _enter(
        *_legacy_rollout_patches(list_result, search_result),
        patch.object(sse.memories_db, "get_memories", return_value=[legacy_memory]),
    ):
        response = _tools_call("get_memories", {})

    assert "error" not in response
    assert "legacy memory" in response["result"]["content"][0]["text"]


def test_enabled_memory_read_still_serves_memories():
    """A USE_MEMORY decision returns before the denial branch and is unaffected."""
    memory = {"id": "m2", "content": "canonical memory"}
    list_result = McpMemoryListResult(
        memories=[memory], read_decision=MemoryReadDecision.USE_MEMORY, fallback_reason=None
    )
    search_result = McpMemorySearchResult(
        memories=[memory], read_decision=MemoryReadDecision.USE_MEMORY, fallback_reason=None
    )
    with _enter(*_legacy_rollout_patches(list_result, search_result)):
        get_response = _tools_call("get_memories", {})
        search_response = _tools_call("search_memories", {"query": "anything"})

    for response in (get_response, search_response):
        assert "error" not in response
        assert "canonical memory" in response["result"]["content"][0]["text"]

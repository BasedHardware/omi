"""REST helpers must not return unsuccessful HTTP responses as tool results."""

import logging
import sys
from unittest.mock import MagicMock

if "mcp" not in sys.modules:
    mcp = MagicMock()
    mcp_server = MagicMock()
    mcp_stdio = MagicMock()
    mcp_types = MagicMock()
    sys.modules["mcp"] = mcp
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.server.stdio"] = mcp_stdio
    sys.modules["mcp.types"] = mcp_types

import pytest
import requests

from mcp_server_omi import server


LOGGER = logging.getLogger(__name__)
OPERATIONS = [
    ("get", lambda: server.get_memories(LOGGER, "synthetic-key")),
    ("post", lambda: server.create_memory("synthetic-key", "fixture", server.MemoryCategory.core)),
    ("delete", lambda: server.delete_memory("synthetic-key", "fixture-id")),
    ("patch", lambda: server.edit_memory("synthetic-key", "fixture-id", "fixture")),
    ("get", lambda: server.get_conversations(LOGGER, "synthetic-key")),
    ("get", lambda: server.get_conversation_by_id("synthetic-key", "fixture-id")),
    ("get", lambda: server.search_memories(LOGGER, "synthetic-key", "fixture")),
    ("get", lambda: server.search_conversations(LOGGER, "synthetic-key", "fixture")),
]


@pytest.mark.parametrize("method,operation", OPERATIONS)
@pytest.mark.parametrize("status", [401, 429, 503])
def test_http_errors_propagate(monkeypatch, method, operation, status):
    response = requests.Response()
    response.status_code = status
    response.url = "https://example.invalid/fixture?value=private-memory"
    response._content = b'{"detail":"request failed"}'
    monkeypatch.setattr(server.requests, method, lambda *args, **kwargs: response)
    with pytest.raises(requests.HTTPError) as caught:
        operation()
    assert caught.value.response is response
    assert str(caught.value) == f"Omi API request failed (HTTP {status})"


@pytest.mark.parametrize("method,operation", OPERATIONS)
def test_successful_json_is_preserved(monkeypatch, method, operation):
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"id":"fixture-id"}'
    monkeypatch.setattr(server.requests, method, lambda *args, **kwargs: response)
    assert operation() == {"id": "fixture-id"}

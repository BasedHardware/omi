"""Regression tests for fail-soft handling of transient Typesense failures (issue #9188).

A hosted-Typesense read timeout during `search_conversations` used to bubble out of the generic
`except Exception` as `Exception("Failed to search conversations: ...")`, which the direct search
endpoints (`/v1/conversations/search`, `/v2/integrations/{app_id}/search/conversations`) surfaced as
a 500 traceback. It now raises the typed `ConversationSearchUnavailable`, which those endpoints map
to a 503 and the hybrid keyword path falls open on. A genuine query error (RequestMalformed) must
still surface as a bug, not be masked as "unavailable".

These use the real typesense exception classes and monkeypatch only the module-level client, so the
transient-vs-real classification is exercised exactly as production would hit it.
"""

from unittest.mock import MagicMock

import pytest
import requests
from typesense import exceptions as typesense_exceptions

from utils.conversations import search
from utils.conversations.search import ConversationSearchUnavailable


def _client_raising(exc):
    """A fake Typesense client whose conversations search raises ``exc``."""
    client = MagicMock()
    client.collections.__getitem__.return_value.documents.search.side_effect = exc
    return client


def test_read_timeout_raises_typed_unavailable(monkeypatch):
    monkeypatch.setattr(
        search,
        "client",
        _client_raising(requests.exceptions.ReadTimeout("HTTPSConnectionPool: Read timed out (read timeout=2)")),
    )
    with pytest.raises(ConversationSearchUnavailable):
        search.search_conversations(uid="u1", query="dinner plans")


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectionError("connection refused"),
        typesense_exceptions.ServiceUnavailable(503, "unavailable"),
        typesense_exceptions.ServerError(500, "server error"),
    ],
)
def test_transient_upstream_errors_are_typed_unavailable(monkeypatch, exc):
    monkeypatch.setattr(search, "client", _client_raising(exc))
    with pytest.raises(ConversationSearchUnavailable):
        search.search_conversations(uid="u1", query="dinner plans")


def test_malformed_query_is_not_masked_as_unavailable(monkeypatch):
    # A bad filter/query is a real bug, not a transient blip — it must NOT become a soft 503.
    monkeypatch.setattr(search, "client", _client_raising(typesense_exceptions.RequestMalformed(400, "bad filter_by")))
    with pytest.raises(Exception) as exc_info:
        search.search_conversations(uid="u1", query="dinner plans")
    assert not isinstance(exc_info.value, ConversationSearchUnavailable)
    assert "Failed to search conversations" in str(exc_info.value)


def test_keyword_search_fails_open_on_transient(monkeypatch):
    # Hybrid (keyword + vector) retrieval must degrade to vector-only, not crash the chat request.
    monkeypatch.setattr(search, "client", _client_raising(requests.exceptions.ReadTimeout("Read timed out")))
    assert search.keyword_search_conversation_ids(uid="u1", query="dinner plans") == []

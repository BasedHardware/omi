"""Unit test for the MCP get_conversation_by_id poison-record guard (routers/mcp.py).

A single malformed conversation record (e.g. a structured.category no longer in
CategoryEnum) must not 500 GET /v1/mcp/conversations/{conversation_id} via
response_model coercion. The sibling list/search endpoints
(get_conversations, search_conversations) already validate each record
individually and skip the bad ones (see test_mcp_conversations_poison.py); this
single-item endpoint had no such guard and returned the raw, unvalidated dict,
letting FastAPI's response_model serialization raise a ResponseValidationError
(-> HTTP 500) for a conversation whose stored category predates a CategoryEnum
rename/consolidation (e.g. a legacy 'romance' value before it became
'romantic').

``routers.mcp`` imports cleanly in this environment (no import-time side
effects), so this test imports it directly at module scope and uses
``monkeypatch.setattr`` on its module-level ``conversations_db`` /
``populate_speaker_names`` references plus FastAPI ``app.dependency_overrides``
— the sanctioned seams from ``backend/docs/test_isolation.md`` — instead of
stubbing ``sys.modules``.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import mcp as rest

NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def _conversation(conv_id='conv-good', category='technology'):
    return {
        'id': conv_id,
        'started_at': NOW,
        'finished_at': NOW,
        'structured': {
            'title': 'Standup',
            'overview': 'Daily sync',
            'category': category,
        },
        'language': 'en',
    }


@pytest.fixture
def mcp_test_client(monkeypatch):
    # populate_speaker_names normally reads the user profile / person records;
    # neutralize it so the test only exercises the response-shape guard.
    monkeypatch.setattr(rest, 'populate_speaker_names', lambda uid, conversations: None)

    app = FastAPI()
    app.include_router(rest.router)
    app.dependency_overrides[rest.get_uid_from_mcp_api_key] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


class TestGetConversationByIdPoisonRecord:
    """A single malformed conversation record must not 500 the MCP single-item fetch."""

    def test_poisoned_category_returns_404_not_500(self, monkeypatch, mcp_test_client):
        # structured.category holds a legacy value that predates a CategoryEnum
        # rename/consolidation and is therefore not a valid CategoryEnum member today.
        monkeypatch.setattr(
            rest.conversations_db,
            'get_conversation',
            lambda uid, conversation_id: _conversation('conv-poison', category='not_a_real_category'),
        )

        resp = mcp_test_client.get('/v1/mcp/conversations/conv-poison')

        # Without the per-record guard, response_model coercion 500s here.
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"

    def test_valid_conversation_returns_200(self, monkeypatch, mcp_test_client):
        monkeypatch.setattr(
            rest.conversations_db,
            'get_conversation',
            lambda uid, conversation_id: _conversation('conv-good', category='technology'),
        )

        resp = mcp_test_client.get('/v1/mcp/conversations/conv-good')

        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body['id'] == 'conv-good'
        assert body['structured']['category'] == 'technology'

    def test_direct_call_poisoned_category_raises_http_404(self, monkeypatch):
        """Direct-call form (mirrors the sibling list-endpoint test style)."""
        monkeypatch.setattr(rest, 'populate_speaker_names', lambda uid, conversations: None)
        monkeypatch.setattr(
            rest.conversations_db,
            'get_conversation',
            lambda uid, conversation_id: _conversation('conv-poison', category='not_a_real_category'),
        )

        with pytest.raises(HTTPException) as exc_info:
            rest.get_conversation_by_id(conversation_id='conv-poison', uid=UID)

        assert exc_info.value.status_code == 404

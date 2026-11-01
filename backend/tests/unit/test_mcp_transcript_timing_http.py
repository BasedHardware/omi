"""Real MCP REST validation/serialization over synthetic stored timing metadata."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import mcp as rest


@pytest.fixture(params=[False, True], ids=['numeric-clock', 'numeric-string-clock'])
def timing_client(monkeypatch, request):
    origin = datetime(2026, 10, 26, tzinfo=timezone.utc)
    source = {
        'id': 'synthetic-conversation',
        'created_at': origin,
        'started_at': origin,
        'finished_at': origin + timedelta(minutes=10),
        'structured': {'title': 'Synthetic', 'overview': 'Synthetic', 'category': 'technology'},
        'transcript_segments': [
            {'text': 'synthetic before', 'speaker_id': 0, 'start': -285, 'end': -42},
            {'text': 'synthetic crossing', 'speaker_id': 0, 'start': -1, 'end': 2},
            {'text': 'synthetic after', 'speaker_id': 0, 'start': 2, 'end': 3},
        ],
    }
    if request.param:
        source['transcript_segments'][0]['start'] = '-285'
        source['transcript_segments'][0]['end'] = '-42'
    monkeypatch.setattr(
        rest.mcp_conversation_handlers, 'fetch_conversation_for_detail', lambda *a, **k: deepcopy(source)
    )
    monkeypatch.setattr(rest.mcp_conversation_handlers, 'search_conversations_core', lambda *a, **k: [deepcopy(source)])
    monkeypatch.setattr(rest, 'populate_speaker_names', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(rest.router)
    app.dependency_overrides[rest.get_uid_with_mcp_conversations_read] = lambda: 'synthetic-owner'
    with TestClient(app) as client:
        yield client, source


def test_detail_http_clamps_offsets_and_retains_origin_and_text(timing_client):
    client, stored = timing_client
    response = client.get('/v1/mcp/conversations/synthetic-conversation')
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(s['start'], s['end']) for s in body['transcript_segments']] == [(0, 0), (0, 2), (2, 3)]
    assert [s['text'] for s in body['transcript_segments']] == [s['text'] for s in stored['transcript_segments']]
    assert datetime.fromisoformat(body['started_at'].replace('Z', '+00:00')) == stored['started_at']
    assert float(stored['transcript_segments'][0]['start']) == -285


def test_search_http_clamps_second_and_millisecond_aliases(timing_client):
    client, stored = timing_client
    response = client.get('/v1/mcp/conversations/search', params={'query': 'synthetic', 'timezone': 'UTC'})
    assert response.status_code == 200, response.text
    snippets = response.json()[0]['match_snippets']
    assert snippets
    assert snippets[0]['start'] == snippets[0]['end'] == 0
    assert snippets[0]['start_ms'] == snippets[0]['end_ms'] == 0
    assert all(s[key] is None or s[key] >= 0 for s in snippets for key in ('start', 'end', 'start_ms', 'end_ms'))
    assert float(stored['transcript_segments'][0]['start']) == -285

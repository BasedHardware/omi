"""Every conversation read surface must retain and decay stamped batch captures."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversations, mcp_conversation_pages
from routers import developer, integration
from tests.unit.test_external_list_routes import routes
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from utils.conversations import transcribing_hold
from utils.mcp_server.handlers import conversations as tools

_LIST_WITH_TRANSCRIPT = conversations.get_conversations_without_photos


def capture(overdue=False):
    now = datetime.now(timezone.utc)
    return {
        'id': 'capture',
        'created_at': now - timedelta(minutes=3),
        'started_at': now - timedelta(seconds=45),
        'finished_at': now - timedelta(seconds=20),
        'source': 'desktop',
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'has_content': True,
        'has_photos': False,
        'record_lane_owner': 'batch_live_v1',
        'home_transcription_pending_at': now,
        'home_transcription_deadline_at': now + timedelta(seconds=-1 if overdue else 7200),
        'transcript_segments': [],
        'structured': {'title': '', 'overview': '', 'category': 'other'},
    }


@pytest.mark.parametrize('overdue', [False, True])
@pytest.mark.parametrize('gate', ['on', 'off'])
def test_developer_transcript_list_uses_presentation_collector(routes, monkeypatch, overdue, gate):
    client, _, _, _ = routes
    row = capture(overdue)
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', gate)
    monkeypatch.setattr(conversations, 'get_conversations_without_photos', _LIST_WITH_TRANSCRIPT)
    _install_listing(monkeypatch, {'capture': row})
    assert not conversations.is_visible_conversation(row)
    result = client.get('/v1/dev/user/conversations?include_transcript=true')
    assert result.status_code == 200, result.text
    if gate == 'off':
        assert result.json() == []
    else:
        assert result.json()[0]['structured']['title'] == ("Couldn't transcribe" if overdue else 'Transcribing…')
        assert result.json()[0]['transcript_included'] is True
    assert row['status'] == 'completed' and row['structured']['title'] == ''


@pytest.mark.parametrize('overdue', [False, True])
@pytest.mark.parametrize('gate', ['on', 'off'])
def test_integration_list_uses_presentation_collector(monkeypatch, overdue, gate):
    row = capture(overdue)
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', gate)
    _install_listing(monkeypatch, {'capture': row})
    monkeypatch.setattr(integration, 'verify_api_key', lambda *a: True)
    monkeypatch.setattr(integration.apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id, 'name': 'test'})
    monkeypatch.setattr(integration.redis_db, 'get_enabled_apps', lambda uid: ['app'])
    monkeypatch.setattr(integration.apps_utils, 'app_can_read_conversations', lambda app: True)
    result = integration.get_conversations_via_integration(
        request=MagicMock(),
        app_id='app',
        uid='u',
        limit=10,
        offset=0,
        include_discarded=False,
        statuses=['completed'],
        start_date=None,
        end_date=None,
        max_transcript_segments=100,
        authorization='Bearer synthetic',
    )
    if gate == 'off':
        assert result['conversations'] == []
    else:
        wire = result['conversations'][0]
        assert wire['structured']['title'] == ("Couldn't transcribe" if overdue else 'Transcribing…')
        assert wire['status'] == ('completed' if overdue else 'processing')
    assert row['status'] == 'completed' and row['structured']['title'] == ''


def mcp_store(monkeypatch, row):
    query = MagicMock()
    for name in ('collection', 'document', 'where', 'order_by', 'select', 'limit', 'offset', 'start_after'):
        getattr(query, name).return_value = query

    def document(fields):
        payload = {}
        for path in fields:
            value = row
            for part in path.split('.'):
                if not isinstance(value, dict) or part not in value:
                    break
                value = value[part]
            else:
                target = payload
                parts = path.split('.')
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = deepcopy(value)
        return SimpleNamespace(id='capture', exists=True, update_time=None, to_dict=lambda: deepcopy(payload))

    query.stream.side_effect = lambda **kwargs: [document(query.select.call_args.args[0])]
    query.get_all.side_effect = lambda refs, *, field_paths: [document(field_paths)]
    monkeypatch.setattr(conversations, 'get_firestore_client', lambda: query)
    monkeypatch.setattr(mcp_conversation_pages, 'get_firestore_client', lambda: query)
    monkeypatch.setattr(mcp_conversation_pages, 'lever_enabled', lambda *a: False)
    return query


@pytest.mark.parametrize('overdue', [False, True])
@pytest.mark.parametrize('surface', ['list', 'offset', 'detail', 'batch', 'search'])
@pytest.mark.parametrize('gate', ['on', 'off'])
def test_hosted_mcp_projects_pending_and_overdue_captures(monkeypatch, overdue, surface, gate):
    row = capture(overdue)
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', gate)
    query = mcp_store(monkeypatch, row)
    monkeypatch.setattr(tools, 'local_date_window', lambda *a: (None, None, timezone.utc))
    if surface in ('list', 'offset'):
        result = tools.get_conversations('u', {'limit': 2, 'offset': 1 if surface == 'offset' else 0})
        wire = result['conversations'][0]
        fields = query.select.call_args.args[0]
    elif surface == 'detail':
        result = tools.get_conversation_by_id('u', {'conversation_id': 'capture'})
        wire = result['conversation']
        fields = query.get_all.call_args.kwargs['field_paths']
    elif surface == 'batch':
        result = tools.get_conversations_by_ids('u', {'conversation_ids': ['capture']})
        wire = result['conversations'][0]['conversation']
        fields = query.get_all.call_args.kwargs['field_paths']
    else:
        monkeypatch.setattr(tools, 'resolve_mcp_conversation_search_ids', lambda *a, **k: ['capture'])
        result = tools.search_conversations('u', {'query': 'topic'})
        wire = result['conversations'][0]
        fields = query.get_all.call_args.kwargs['field_paths']
    if gate == 'on':
        assert set(transcribing_hold.READ_FIELDS) <= set(fields)
        assert wire['structured']['title'] == ("Couldn't transcribe" if overdue else 'Transcribing…')
    else:
        assert 'home_transcription_deadline_at' not in fields
        assert wire['structured']['title'] == ''
    assert 'home_transcription_deadline_at' not in wire
    assert row['status'] == 'completed' and row['structured']['title'] == ''

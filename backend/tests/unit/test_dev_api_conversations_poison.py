"""GET /v1/dev/user/conversations must skip a malformed record instead of 500ing the page.

The endpoint declared response_model=List[Conversation] and returned raw Firestore dicts, so one malformed
record made FastAPI raise ResponseValidationError -> HTTP 500 for the whole page.
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models.conversation_enums import CategoryEnum
from tests.unit.dev_api_test_support import isolated_developer_api

BACKEND_DIR = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_VALID_CATEGORY = next(iter(CategoryEnum)).value

conversations_db = None
developer_module = None
developer_router = None
ApiKeyAuth = None
get_auth_with_conversations_read = None
get_uid_with_conversations_write = None


@pytest.fixture(autouse=True)
def _isolated_developer_router(monkeypatch):
    global conversations_db, developer_module, developer_router, ApiKeyAuth
    global get_auth_with_conversations_read, get_uid_with_conversations_write

    with isolated_developer_api(monkeypatch) as api:
        conversations_db = api.conversations_db
        developer_module = api.developer
        developer_router = api.developer.router
        ApiKeyAuth = api.dependencies.ApiKeyAuth
        get_auth_with_conversations_read = api.dependencies.get_auth_with_conversations_read
        get_uid_with_conversations_write = api.dependencies.get_uid_with_conversations_write
        yield


def _read_auth():
    return ApiKeyAuth(
        uid='uid1',
        scopes=['conversations:read'],
        app_id='test-app',
        key_id='test-key',
    )


def _valid(cid):
    return {
        'id': cid,
        'created_at': _NOW,
        'started_at': _NOW,
        'finished_at': _NOW,
        'structured': {'title': 'A Title', 'overview': 'An overview', 'category': _VALID_CATEGORY},
    }


def _build():
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_auth_with_conversations_read] = _read_auth
    app.dependency_overrides[get_uid_with_conversations_write] = lambda: 'uid1'
    return TestClient(app, raise_server_exceptions=False)


def test_malformed_conversation_skipped_not_500():
    missing_structured = _valid('bad')
    del missing_structured['structured']
    page = [_valid('c1'), missing_structured, _valid('c2')]
    with patch.object(conversations_db, 'get_conversations_without_photos', return_value=page), patch.object(
        developer_module, 'populate_folder_names', lambda *a, **k: None
    ), patch.object(developer_module, 'populate_speaker_names', lambda *a, **k: None):
        # Transcript inclusion selects the no-photo compatibility reader; default
        # lists use the projected, shared MCP card reader.
        resp = _build().get('/v1/dev/user/conversations?include_transcript=true')
    assert resp.status_code == 200
    assert [c['id'] for c in resp.json()] == ['c1', 'c2']


def test_pagination_is_clamped_before_firestore():
    # Out-of-range pagination is clamped before the Firestore query: a negative offset/limit
    # would otherwise raise (HTTP 500) and an oversized/zero limit would stream the whole
    # collection. Call the handler directly (the TestClient async path is flaky on Windows; the
    # clamp is what matters).
    with patch.object(conversations_db, 'get_conversations_without_photos', return_value=[]) as m, patch.object(
        developer_module, 'populate_folder_names', lambda *a, **k: None
    ), patch.object(developer_module, 'populate_speaker_names', lambda *a, **k: None):
        developer_module.get_conversations(uid=_read_auth(), limit=99999, offset=-1, folder_id='f1')
        developer_module.get_conversations(uid=_read_auth(), limit=99999, offset=0, include_transcript=True)
        developer_module.get_conversations(uid=_read_auth(), limit=0, offset=5, folder_id='f1')
    high = m.call_args_list[0].args
    assert high[1] == 201 and high[2] == 0  # clamped limit 200 plus one lookahead row
    assert m.call_args_list[1].args[1] == 201  # unified cap (matches CLI --limit max) plus lookahead
    assert m.call_args_list[2].args[1] == 2  # clamped limit 1 plus lookahead


def test_goals_limit_is_clamped_before_firestore():
    # Sibling of the conversations clamp above: GET /v1/dev/user/goals passed the request `limit`
    # straight to get_user_goals -> Firestore .limit(), so ?limit=-1 raised (HTTP 500) and an
    # oversized limit could stream the whole collection. Reuses this file's developer-router
    # harness (database.goals is already stubbed); call the handler directly.
    with patch.object(developer_module.goals_db, 'get_user_goals', return_value=[]) as m:
        developer_module.get_goals(uid='uid1', limit=-1)
        developer_module.get_goals(uid='uid1', limit=99999)
        developer_module.get_goals(uid='uid1', limit=0)
    assert m.call_args_list[0].kwargs['limit'] == 1  # -1 -> 1
    assert m.call_args_list[1].kwargs['limit'] == 1000  # 99999 -> 1000
    assert m.call_args_list[2].kwargs['limit'] == 1  # 0 -> 1


def test_developer_patch_rejects_blank_title():
    # #13933: {"title": "   "} satisfied min_length=1, so the handler persisted '' to both
    # structured.title and user_title while sibling write paths rejected blank text with 422.
    # Blank text must now fail at the request-model boundary and never reach the Firestore update.
    with patch.object(conversations_db, 'get_conversation', return_value=_valid('c1')), patch.object(
        developer_module.lifecycle_service, 'apply_user_conversation_patch'
    ) as patch_user_conversation:
        response = _build().patch('/v1/dev/user/conversations/c1', json={'title': '   '})

    assert response.status_code == 422
    patch_user_conversation.assert_not_called()


def test_developer_patch_strips_padded_title():
    updated = _valid('c1')
    updated['structured']['title'] = 'New Title'

    with patch.object(conversations_db, 'get_conversation', side_effect=[_valid('c1'), updated]), patch.object(
        developer_module.lifecycle_service, 'apply_user_conversation_patch'
    ) as patch_user_conversation, patch.object(developer_module, 'populate_folder_names', lambda *a, **k: None):
        response = _build().patch('/v1/dev/user/conversations/c1', json={'title': '  New Title  '})

    assert response.status_code == 200
    patch_user_conversation.assert_called_once_with('uid1', 'c1', title='New Title', discarded=None)


def test_update_conversation_request_null_title_means_unchanged():
    # The other half of the PATCH contract: an omitted/null title is "leave unchanged",
    # not a rejection — the validator must pass None through.
    request = developer_module.UpdateConversationRequest.model_validate({'title': None, 'discarded': True})
    assert request.title is None
    assert request.discarded is True


def _create_from_text(body):
    captured = []

    def process(_uid, _language, conversation):
        captured.append(conversation)
        return SimpleNamespace(id='c1', status=None, discarded=False, processing_deferred=False)

    with patch.object(developer_module, 'process_conversation', process), patch.object(
        developer_module, 'resolve_geolocation', lambda _geolocation: None
    ):
        response = _build().post('/v1/dev/user/conversations', json={'text': 'hello there', **body})
    return response, captured


@pytest.mark.parametrize(
    'body, finished_at',
    [
        # started_at defaults to now (aware), so the naive finish has to be in the future.
        ({'finished_at': '2099-01-01T00:10:00'}, datetime(2099, 1, 1, 0, 10, tzinfo=timezone.utc)),
        (
            {'started_at': '2026-01-01T00:00:00', 'finished_at': '2026-01-01T00:10:00Z'},
            datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
        ),
        (
            {'started_at': '2026-01-01T00:00:00Z', 'finished_at': '2026-01-01T00:10:00'},
            datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
        ),
    ],
)
def test_create_from_text_reads_a_timestamp_without_an_offset_as_utc(body, finished_at):
    # A naive timestamp next to an aware one (or the aware started_at default) made the handler's
    # finished_at < started_at check raise TypeError, an HTTP 500. Naive values are read as UTC.
    response, captured = _create_from_text(body)

    assert response.status_code == 200
    assert captured[0].finished_at == finished_at


def test_create_from_text_keeps_accepting_two_naive_timestamps_as_utc():
    response, captured = _create_from_text({'started_at': '2026-01-01T00:00:00', 'finished_at': '2026-01-01T00:10:00'})

    assert response.status_code == 200
    assert captured[0].started_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert captured[0].finished_at == datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)


def test_create_from_text_still_rejects_a_finish_before_the_start():
    response, captured = _create_from_text({'started_at': '2026-01-01T00:10:00', 'finished_at': '2026-01-01T00:00:00Z'})

    assert response.status_code == 422
    assert captured == []


@pytest.mark.parametrize('detail', [False, True])
def test_developer_api_preserves_joinable_ids_and_real_owner_name(monkeypatch, detail):
    from utils.conversations import render
    from dependencies import get_auth_with_conversation_detail_read

    conversation = _valid('wire')
    conversation['transcript_segments'] = [
        {'id': 's1', 'speaker': 'SPEAKER_0', 'speaker_id': 0, 'is_user': True, 'text': 'Hello', 'start': 0, 'end': 1},
        {
            'id': 's2',
            'speaker': 'SPEAKER_379',
            'speaker_id': 379,
            'person_id': 'p1',
            'is_user': False,
            'text': 'Hi',
            'start': 1,
            'end': 2,
        },
        {
            'id': 's3',
            'speaker': 'SPEAKER_380',
            'speaker_id': 380,
            'is_user': False,
            'text': 'An unknown voice',
            'start': 2,
            'end': 3,
        },
    ]
    monkeypatch.setattr(render, 'get_user_name', lambda *a, **k: 'David Zhang')
    monkeypatch.setattr(render.users_db, 'get_people_by_ids', lambda *a, **k: [{'id': 'p1', 'name': 'Phong'}])
    monkeypatch.setattr(developer_module, 'populate_folder_names', lambda *a, **k: None)
    monkeypatch.setattr(developer_module, 'populate_speaker_names', render.populate_speaker_names)
    client = _build()
    client.app.dependency_overrides[get_auth_with_conversation_detail_read] = _read_auth
    if detail:
        monkeypatch.setattr(conversations_db, 'get_conversation', lambda *a, **k: conversation)
        response = client.get('/v1/dev/user/conversations/wire?include_transcript=true')
    else:
        monkeypatch.setattr(conversations_db, 'get_conversations_without_photos', lambda *a, **k: [conversation])
        response = client.get('/v1/dev/user/conversations?include_transcript=true')
    assert response.status_code == 200, response.text
    body = response.json() if detail else response.json()[0]
    assert body['participants'] == [
        {'speaker_id': 0, 'person_id': None, 'is_user': True},
        {'speaker_id': 379, 'person_id': 'p1', 'is_user': False},
        {'speaker_id': 380, 'person_id': None, 'is_user': False},
    ]
    assert [row['speaker_id'] for row in body['transcript_segments']] == [0, 379, 380]
    assert [row['speaker_name'] for row in body['transcript_segments']] == ['David Zhang', 'Phong', 'Speaker A']

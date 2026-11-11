"""GET /v1/dev/user/conversations must skip a malformed record instead of 500ing the page.

The endpoint declared response_model=List[Conversation] and returned raw Firestore dicts, so one malformed
record made FastAPI raise ResponseValidationError -> HTTP 500 for the whole page.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name, path):
    module = sys.modules.get(name)
    if module is None or not hasattr(module, "__path__"):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _drop_stale_module(name, expected_file):
    module = sys.modules.get(name)
    if module is None:
        return
    module_file = getattr(module, "__file__", None)
    try:
        module_path = Path(module_file).resolve() if module_file else None
    except TypeError:
        module_path = None
    if module_path == expected_file.resolve():
        return
    sys.modules.pop(name, None)
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, attr_name, None) is module:
            delattr(parent, attr_name)


_stubs = [
    'ulid',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.knowledge_graph',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.storage',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.location',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
]
for _mod_name in _stubs:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _AutoMockModule(_mod_name)

sys.modules['database._client'].document_id_from_seed = MagicMock(return_value='memory-id')
sys.modules['database.vector_db'].upsert_memory_vectors_batch = MagicMock()
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['utils.apps'].update_personas_async = MagicMock()

_endpoints = sys.modules.get('utils.other.endpoints')
if _endpoints is None:
    _endpoints = ModuleType('utils.other.endpoints')
    sys.modules['utils.other.endpoints'] = _endpoints
if not hasattr(_endpoints, 'get_current_user_uid'):
    _endpoints.get_current_user_uid = lambda: 'uid1'
if not hasattr(_endpoints, 'with_rate_limit'):
    _endpoints.with_rate_limit = lambda dependency, _policy: dependency
if not hasattr(_endpoints, 'with_rate_limit_context'):
    setattr(_endpoints, 'with_rate_limit_context', lambda dependency, _policy: dependency)
if not hasattr(_endpoints, 'check_api_key_rate_limit'):
    _endpoints.check_api_key_rate_limit = MagicMock()
if not hasattr(_endpoints, 'get_user'):
    _endpoints.get_user = MagicMock()

_ensure_package_path("models", BACKEND_DIR / "models")
_ensure_package_path("routers", BACKEND_DIR / "routers")
_ensure_package_path("utils", BACKEND_DIR / "utils")
_ensure_package_path("utils.conversations", BACKEND_DIR / "utils" / "conversations")
_drop_stale_module("models.conversation", BACKEND_DIR / "models" / "conversation.py")
_drop_stale_module("models.conversation_enums", BACKEND_DIR / "models" / "conversation_enums.py")
_drop_stale_module("models.dev_api_key", BACKEND_DIR / "models" / "dev_api_key.py")
_drop_stale_module("models.folder", BACKEND_DIR / "models" / "folder.py")
_drop_stale_module("models.geolocation", BACKEND_DIR / "models" / "geolocation.py")
_drop_stale_module("models.memories", BACKEND_DIR / "models" / "memories.py")
_drop_stale_module("models.transcript_segment", BACKEND_DIR / "models" / "transcript_segment.py")
_drop_stale_module("routers.developer", BACKEND_DIR / "routers" / "developer.py")
_drop_stale_module("utils.conversations.render", BACKEND_DIR / "utils" / "conversations" / "render.py")

import database.conversations as conversations_db  # noqa: E402  (the stub)
from models.conversation_enums import CategoryEnum  # noqa: E402  (real enum)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import routers.developer as developer_module  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
from dependencies import (  # noqa: E402
    ApiKeyAuth,
    get_auth_with_conversations_read,
    get_uid_with_conversations_write,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_VALID_CATEGORY = next(iter(CategoryEnum)).value


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
        conversations_db, 'update_conversation_title'
    ) as update_title:
        response = _build().patch('/v1/dev/user/conversations/c1', json={'title': '   '})

    assert response.status_code == 422
    update_title.assert_not_called()


def test_developer_patch_strips_padded_title():
    updated = _valid('c1')
    updated['structured']['title'] = 'New Title'

    with patch.object(conversations_db, 'get_conversation', side_effect=[_valid('c1'), updated]), patch.object(
        conversations_db, 'update_conversation_title'
    ) as update_title, patch.object(developer_module, 'populate_folder_names', lambda *a, **k: None):
        response = _build().patch('/v1/dev/user/conversations/c1', json={'title': '  New Title  '})

    assert response.status_code == 200
    update_title.assert_called_once_with('uid1', 'c1', 'New Title')


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

"""Run the real four FastAPI routes with offline auth/storage dependencies."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from dependencies import ApiKeyAuth
from routers import developer, mcp
from utils import external_list_reads as cache
from utils.mcp_server.cursors import encode_cursor
from utils.mcp_server.handlers import memories as memory_handlers
from utils.observability.external_lists import ExternalListMetricsMiddleware
from utils.other import list_budget as budgets
from utils.other.list_budget import ListReadBudget
from tests.unit.test_external_list_cache import FakeRedis, immediate_population

PATHS = ['/v1/dev/user/conversations', '/v1/dev/user/memories', '/v1/dev/user/action-items', '/v1/mcp/memories']


@pytest.fixture
def routes(monkeypatch):
    storage = FakeRedis()
    monkeypatch.setattr(cache.action_item_versions, 'version', lambda uid: 'stable-' + uid)
    monkeypatch.setattr(cache, 'submit_with_context', immediate_population)
    monkeypatch.setattr(cache, '_client', storage)
    app = FastAPI()
    app.include_router(developer.router)
    app.include_router(mcp.router)
    app.add_middleware(ExternalListMetricsMiddleware)
    calls = Mock()
    state = SimpleNamespace(uid='owner', app_id='app', key_id='key', status=200, grant=True, truncated=False, rows=[])

    async def auth(request: Request):
        calls.auth()
        if state.status != 200:
            raise HTTPException(state.status)
        return ApiKeyAuth(
            state.uid,
            ['memories:read', 'conversations:read', 'action_items:read'],
            app_id=state.app_id,
            key_id=state.key_id,
        )

    async def memory_auth(request: Request):
        return await auth(request)

    async def action_auth(context=Depends(auth)):
        return context.uid

    for dependency in [developer.get_api_key_auth, developer.get_auth_with_conversations_read]:
        app.dependency_overrides[dependency] = auth
    for dependency in [
        developer.get_developer_memory_default_memory_read_context,
        mcp.get_mcp_memory_default_memory_read_context,
    ]:
        app.dependency_overrides[dependency] = memory_auth
    app.dependency_overrides[developer.get_uid_with_action_items_read] = action_auth

    def grant(*args, **kwargs):
        calls.grant()
        return SimpleNamespace(allowed=state.grant, status_code=403, reason='denied', observability='denied')

    monkeypatch.setattr(developer, 'authorize_memory_external_default_memory_read', grant)
    monkeypatch.setattr(mcp, 'authorize_memory_external_default_memory_read', grant)
    monkeypatch.setattr(developer, 'check_conversation_transcript_read_limit', lambda *a, **k: calls.transcript_rate())
    monkeypatch.setattr(developer, 'populate_speaker_names', lambda *a: None)
    monkeypatch.setattr(developer, 'populate_folder_names', lambda *a: None)

    def origin(name):
        def read(*args, **kwargs):
            getattr(calls, name)(*args, **kwargs)
            budget = kwargs.get('budget')
            if budget is not None and state.truncated:
                budget.mark_exhausted('documents')
            return deepcopy(state.rows)

        return read

    def cards(*args, **kwargs):
        return origin('cards')(*args, **kwargs), None

    def mcp_memories(*args, **kwargs):
        return {'memories': origin('mcp_memories')(*args, **kwargs), 'scan_truncated': state.truncated}

    monkeypatch.setattr(developer, 'conversation_cards_page_core', cards)
    monkeypatch.setattr(developer.conversations_db, 'get_conversations_without_photos', origin('legacy'))
    monkeypatch.setattr(developer, 'read_developer_memories', origin('memories'))
    monkeypatch.setattr(developer.action_items_db, 'get_action_items', origin('actions'))
    monkeypatch.setattr(mcp.mcp_memory_handlers, 'memories_page_core', mcp_memories)
    return TestClient(app), state, calls, storage


@pytest.mark.parametrize('path,origin', zip(PATHS, ['cards', 'memories', 'actions', 'mcp_memories']))
def test_real_routes_cache_final_array_bytes_and_still_authorize(routes, path, origin):
    client, state, calls, storage = routes
    first = client.get(path, headers={'Authorization': 'Bearer synthetic-key'})
    second = client.get(path, headers={'Authorization': 'Bearer synthetic-key'})
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == b'[]'
    assert first.headers == second.headers
    assert getattr(calls, origin).call_count == 1
    assert calls.auth.call_count >= 2
    state.status = 429
    assert client.get(path, headers={'Authorization': 'Bearer synthetic-key'}).status_code == 429
    state.status = 401
    assert client.get(path, headers={'Authorization': 'Bearer synthetic-key'}).status_code == 401
    assert getattr(calls, origin).call_count == 1
    assert storage.entries


@pytest.mark.parametrize('path,origin', zip(PATHS, ['cards', 'memories', 'actions', 'mcp_memories']))
def test_real_route_isolation_filters_pages_and_cache_off_parity(routes, monkeypatch, path, origin):
    client, state, calls, _ = routes
    original = client.get(path)
    for attr in ['uid', 'app_id', 'key_id']:
        previous = getattr(state, attr)
        setattr(state, attr, 'other')
        assert client.get(path).status_code == 200
        setattr(state, attr, previous)
    assert client.get(path + '?limit=2').status_code == 200
    assert client.get(path + '?offset=2').status_code == 200
    if path != PATHS[2]:
        assert client.get(path + '?categories=work').status_code == 200
    else:
        assert client.get(path + '?completed=true').status_code == 200
    count = getattr(calls, origin).call_count
    assert count == 7
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    off = client.get(path)
    assert off.content == original.content and off.headers == original.headers
    assert getattr(calls, origin).call_count == count + 1


@pytest.mark.parametrize('path', [PATHS[1], PATHS[3]])
def test_grant_revocation_is_checked_before_hit_and_errors_never_cached(routes, path):
    client, state, calls, _ = routes
    assert client.get(path).status_code == 200
    state.grant = False
    assert client.get(path).status_code == 403
    assert client.get(path + '?limit=10').status_code == 403
    state.grant = True
    assert client.get(path + '?limit=10').status_code == 200
    assert calls.grant.call_count == 4


@pytest.mark.parametrize(
    'query,origin',
    [
        ('', 'cards'),
        ('&include_transcript=true', 'legacy'),
        ('&folder_id=folder', 'legacy'),
        ('&starred=true', 'legacy'),
    ],
)
def test_conversation_offset_budget_guidance_truncation_and_off_switch(routes, monkeypatch, query, origin):
    client, state, calls, storage = routes
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    path = PATHS[0] + '?offset=30000' + query
    state.truncated = True
    result = client.get(path)
    assert result.status_code == 200
    assert result.headers['X-Omi-List-Truncated'] == 'true'
    assert result.headers['X-Omi-Has-More'] == 'true'
    assert 'X-Omi-Next-Offset' not in result.headers
    assert 'cursor' in result.headers['X-Pagination-Guidance']
    assert getattr(calls, origin).call_args.kwargs['budget'].max_documents == 25000
    monkeypatch.setenv('OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED', 'false')
    off = client.get(path)
    assert off.status_code == 200
    assert 'X-Omi-List-Truncated' not in off.headers and 'X-Pagination-Guidance' not in off.headers
    assert 'budget' not in getattr(calls, origin).call_args.kwargs
    assert 'X-Omi-Has-More' in off.headers


def test_mcp_budget_truncation_and_off_switch(routes, monkeypatch):
    client, state, calls, storage = routes
    state.truncated = True
    for _ in range(2):
        result = client.get(PATHS[3])
        assert result.status_code == 200
        assert result.headers['X-Omi-List-Truncated'] == result.headers['X-Scan-Truncated'] == 'true'
    assert calls.mcp_memories.call_count == 2 and not storage.entries
    monkeypatch.setenv('OMI_MCP_MEMORY_LIST_BUDGET_ENABLED', 'false')
    assert 'X-Omi-List-Truncated' not in client.get(PATHS[3]).headers
    assert 'budget' not in calls.mcp_memories.call_args.kwargs


def test_real_query_validation_not_bypassed_on_warm_cache(routes):
    client, _, calls, _ = routes
    assert client.get(PATHS[0]).status_code == 200
    assert client.get(PATHS[0] + '?limit=not-a-number').status_code == 422
    assert client.get(PATHS[0] + '?categories=invalid').status_code == 400
    assert client.get(PATHS[1] + '?offset=5000').status_code == 413
    assert client.get(PATHS[3] + '?sort=invalid').status_code == 400
    # Previously accepted unknown parameters stay accepted and retain per-request count.
    result = client.get(PATHS[0] + '?include_discarded=true&statuses=completed')
    assert result.status_code == 200
    assert result.headers['X-Omi-Ignored-Query-Params'] == '2'
    assert calls.cards.call_count == 1


@pytest.mark.parametrize('path,origin', zip(PATHS, ['cards', 'memories', 'actions', 'mcp_memories']))
def test_real_routes_fail_open_on_cache_read_and_write_outages(routes, path, origin):
    client, _, calls, storage = routes
    storage.fail_get = storage.fail_set = True
    for _ in range(2):
        result = client.get(path)
        assert result.status_code == 200 and result.content == b'[]'
    assert getattr(calls, origin).call_count == 2
    assert not storage.entries


@pytest.mark.parametrize('path', PATHS)
def test_nonempty_final_response_model_bytes_are_cached(routes, monkeypatch, path):
    client, state, _, _ = routes
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    if path == PATHS[0]:
        row = {
            'id': 'synthetic',
            'created_at': now,
            'started_at': None,
            'finished_at': None,
            'structured': {'title': 'Offline', 'overview': 'Synthetic', 'category': 'work'},
        }
    elif path == PATHS[2]:
        row = {'id': 'synthetic', 'description': 'Offline task', 'completed': False, 'created_at': now}
    else:
        row = {'id': 'synthetic', 'content': 'Offline fact', 'category': 'work', 'created_at': now}
    state.rows = [dict(row, internal_secret='must be projected out')]
    first = client.get(path)
    hit = client.get(path)
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    off = client.get(path)
    assert first.status_code == hit.status_code == off.status_code == 200
    assert first.json()[0]['id'] == 'synthetic'
    assert first.content == hit.content == off.content
    assert b'internal_secret' not in hit.content


@pytest.mark.parametrize('path,origin', [(PATHS[0], 'cards'), (PATHS[3], 'mcp_memories')])
def test_category_multiplicity_keeps_cursor_fingerprints_separate(routes, path, origin):
    client, _, calls, _ = routes
    assert client.get(path + '?categories=work').status_code == 200
    assert client.get(path + '?categories=work,work').status_code == 200
    assert getattr(calls, origin).call_count == 2


def test_mcp_signed_continuations_bypass_cache_authority_reuse(routes):
    client, _, calls, storage = routes
    cursor = encode_cursor(
        kind='rest_get_memories',
        uid='owner',
        position={'uml': 'signed-inner-cursor'},
        filters={
            'categories': [],
            'sort': 'updated_desc',
            'reviewed': None,
            'manually_added': None,
            'updated_after': None,
            'include_activity': False,
            'include_sensitive': True,
        },
    )
    for _ in range(2):
        assert client.get(PATHS[3], params={'sort': 'updated_desc', 'cursor': cursor}).status_code == 200
    assert calls.mcp_memories.call_count == 2
    assert not storage.entries


@pytest.mark.parametrize('populated', [False, True])
def test_conversation_cache_hit_retains_successful_audit_count(routes, monkeypatch, populated):
    client, state, calls, _ = routes
    if populated:
        state.rows = [
            {
                'id': 'synthetic',
                'started_at': None,
                'finished_at': None,
                'created_at': datetime(2026, 10, 18, tzinfo=timezone.utc),
                'structured': {'title': 'Offline', 'overview': 'Synthetic', 'category': 'work'},
            }
        ]
    audit = Mock()
    monkeypatch.setattr(developer, '_audit_developer_read', audit)
    first = client.get(PATHS[0])
    hit = client.get(PATHS[0])
    assert first.status_code == hit.status_code == 200
    assert first.content == hit.content and first.headers == hit.headers
    assert calls.cards.call_count == 1
    assert audit.call_count == 2
    assert [call.kwargs['returned_count'] for call in audit.call_args_list] == [int(populated)] * 2
    assert all(call.kwargs['status'] == 200 for call in audit.call_args_list)


@pytest.mark.parametrize(
    'path,origin',
    [
        (PATHS[0] + '?offset=1', 'cards'),
        (PATHS[0] + '?offset=1&include_transcript=true', 'legacy'),
        (PATHS[0] + '?offset=1&folder_id=folder', 'legacy'),
        (PATHS[0] + '?offset=1&starred=true', 'legacy'),
        (PATHS[1], 'memories'),
        (PATHS[2], 'actions'),
        (PATHS[3], 'mcp_memories'),
    ],
)
def test_real_routes_resolve_owner_budget_and_keep_truncated_200(routes, monkeypatch, path, origin):
    client, state, calls, _ = routes
    seen = []

    def resolve(*, owner_uid=None, context=None):
        seen.append((owner_uid, context))
        return 7

    monkeypatch.setattr(budgets, 'resolve_list_read_max_documents', resolve)
    state.truncated = True
    response = client.get(path, headers={'X-Read-Budget': '100000000'})
    assert response.status_code == 200 and response.content == b'[]'
    assert response.headers['X-Omi-List-Truncated'] == 'true'
    assert len(seen) == 1
    owner, context = seen[0]
    assert owner == context.uid == state.uid
    assert context.app_id == state.app_id and context.key_id == state.key_id
    assert getattr(calls, origin).call_args.kwargs['budget'].max_documents == 7


@pytest.mark.parametrize(
    'path,origin',
    [
        (PATHS[0] + '?offset=1', 'cards'),
        (PATHS[1], 'memories'),
        (PATHS[2], 'actions'),
        (PATHS[3], 'mcp_memories'),
    ],
)
def test_real_route_cache_separates_effective_read_limits_and_owner(routes, monkeypatch, path, origin):
    client, state, calls, storage = routes
    allowance = [100]
    seen = []

    def resolve(*, owner_uid=None, context=None):
        seen.append((owner_uid, context.uid))
        return allowance[0]

    monkeypatch.setattr(budgets, 'resolve_list_read_max_documents', resolve)
    first = client.get(path)
    assert client.get(path).content == first.content
    assert getattr(calls, origin).call_count == 1
    allowance[0] = 2
    assert client.get(path).content == first.content
    assert getattr(calls, origin).call_count == 2
    assert getattr(calls, origin).call_args.kwargs['budget'].max_documents == 2
    allowance[0] = 100
    assert client.get(path).content == first.content
    assert getattr(calls, origin).call_count == 2
    state.uid = 'other-owner'
    assert client.get(path).content == first.content
    assert getattr(calls, origin).call_count == 3
    assert seen == [('owner', 'owner')] * 4 + [('other-owner', 'other-owner')]
    assert len(storage.entries) == 3

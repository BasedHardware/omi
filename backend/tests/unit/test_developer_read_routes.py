"""Exercise the new routes with verified-auth and storage seams injected."""

from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]


def module(name, **attrs):
    result = ModuleType(name)
    result.__dict__.update(attrs)
    return result


@pytest.fixture
def routes():
    async def auth():
        return SimpleNamespace(uid='owner', scopes=['conversations:read'], app_id='app', key_id='key')

    async def memory_auth():
        return SimpleNamespace(uid='owner')

    rate = Mock()

    async def charge(**kwargs):
        rate(**kwargs)

    core = Mock(return_value=[{'id': 'matched'}])
    memory_search = Mock(return_value={'memories': [], 'search_coverage': 'eligible_indexed_memories'})
    people = Mock(return_value={'people': []})
    profile = Mock(return_value={'profile': None, 'message': 'No profile'})
    screen = Mock(return_value={'screen_activity': [], 'next_cursor': 'next'})
    grant = Mock(return_value=SimpleNamespace(allowed=True, status_code=403))
    with stub_modules(
        {
            'dependencies': module(
                'dependencies',
                ApiKeyAuth=SimpleNamespace,
                get_api_key_auth=auth,
                get_auth_with_conversations_read=auth,
                get_developer_memory_default_memory_read_context=memory_auth,
                check_developer_api_key_rate_limit=charge,
            ),
            'utils.memory.product_authorization': module(
                'utils.memory.product_authorization',
                ProductAuthorizationContext=SimpleNamespace,
                authorize_memory_external_default_memory_read=grant,
            ),
            'database._client': module('database._client', db=object()),
            'utils.mcp_server.handlers.conversations': module(
                'utils.mcp_server.handlers.conversations', search_conversations_core=core
            ),
            'utils.mcp_server.helpers': module(
                'utils.mcp_server.helpers',
                conversation_card=lambda row, **kwargs: row,
                parse_mcp_date=lambda value, field: (
                    datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None
                ),
            ),
            'utils.mcp_server.handlers.memories': module(
                'utils.mcp_server.handlers.memories', search_memories_core=memory_search
            ),
            'utils.mcp_server.handlers.profile': module('utils.mcp_server.handlers.profile', get_user_profile=profile),
            'utils.mcp_server.handlers.other': module(
                'utils.mcp_server.handlers.other', get_people=people, screen_activity_core=screen
            ),
        }
    ):
        router = load_module_fresh('routers.developer_read', str(BACKEND / 'routers/developer_read.py'))
        app = FastAPI()
        app.include_router(router.router)

        @app.get('/v1/dev/user/conversations/{conversation_id}')
        def dynamic(conversation_id: str):
            return {'dynamic': conversation_id}

        yield TestClient(app), app, router, auth, core, memory_search, grant, people, rate, profile, screen


def test_search_is_a_named_route_and_shared_core_receives_utc_dates(routes):
    client, _, _, _, core, *_ = routes
    response = client.get('/v1/dev/user/conversations/search?query=budget&start_date=2026-10-01T00:00:00&limit=20')
    assert response.status_code == 200
    assert response.json()['conversations'][0]['id'] == 'matched'
    assert core.call_args.args == ('owner', 'budget')
    assert str(core.call_args.kwargs['start_dt'].tzinfo) == 'UTC'
    assert core.call_args.kwargs['limit'] == 20
    assert core.call_args.kwargs['include_transcript'] is False


def test_unknown_parameters_and_blank_search_are_rejected(routes):
    client, _, _, _, core, *_ = routes
    assert client.get('/v1/dev/user/conversations/search?query=budget&surprise=1').status_code == 400
    assert client.get('/v1/dev/user/conversations/search?query=%20%20').status_code == 400
    core.assert_not_called()


def test_memory_search_checks_persisted_grant_before_shared_search(routes):
    client, _, _, _, _, search, grant, *_ = routes
    grant.return_value = SimpleNamespace(allowed=False, status_code=403)
    assert client.get('/v1/dev/user/memories/search?query=budget').status_code == 403
    search.assert_not_called()
    grant.return_value = SimpleNamespace(allowed=True, status_code=200)
    assert client.get('/v1/dev/user/memories/search?query=budget').status_code == 200
    search.assert_called_once_with('owner', 'budget', limit=10)


def test_people_does_not_expand_existing_key_privileges(routes):
    client, app, _, auth, _, _, _, people, rate, *_ = routes
    assert client.get('/v1/dev/user/people').status_code == 403
    people.assert_not_called()
    rate.assert_not_called()

    async def people_auth():
        return SimpleNamespace(uid='owner', scopes=['people:read'])

    app.dependency_overrides[auth] = people_auth
    response = client.get('/v1/dev/user/people')
    assert response.status_code == 200 and response.json() == {'people': []}
    people.assert_called_once_with('owner', {}, None)
    rate.assert_called_once()


def test_profile_and_screen_require_explicit_scopes_and_share_handlers(routes):
    client, app, _, auth, _, _, _, _, _, profile, screen = routes
    assert client.get('/v1/dev/user/profile').status_code == 403
    assert client.get('/v1/dev/user/screen-activity').status_code == 403

    async def scoped_auth():
        return SimpleNamespace(uid='owner', scopes=['profile:read', 'screen_activity:read'])

    app.dependency_overrides[auth] = scoped_auth
    assert client.get('/v1/dev/user/profile').json()['profile'] is None
    profile.assert_called_once_with('owner', {}, None)
    response = client.get('/v1/dev/user/screen-activity?limit=25&cursor=prior')
    assert response.status_code == 200 and response.json()['has_more'] is True
    assert screen.call_args.kwargs['cursor_kind'] == 'developer_screen_activity'
    assert screen.call_args.kwargs['cursor_token'] == 'prior'
    assert screen.call_args.kwargs['limit'] == 25


def test_existing_profile_does_not_fabricate_an_absence_signal(routes):
    client, app, _, auth, _, _, _, _, _, profile, _ = routes

    async def scoped_auth():
        return SimpleNamespace(uid='owner', scopes=['profile:read'])

    app.dependency_overrides[auth] = scoped_auth
    profile.return_value = {'profile_text': 'Synthetic stored profile', 'generated_at': None, 'data_sources_used': 0}
    response = client.get('/v1/dev/user/profile')
    assert response.status_code == 200
    assert response.json() == profile.return_value
    assert 'profile' not in response.json()

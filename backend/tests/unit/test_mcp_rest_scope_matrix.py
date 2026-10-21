"""Exercise real FastAPI dependency graphs; handlers and budgets are hermetic.

Each resource route must match its equivalent hosted tool's registry scope.
Full-access raw keys retain admission, while a future restricted credential
context cannot bypass the permission check through any REST verb.
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import dependencies
from config.mcp_scopes import MCP_FULL_ACCESS_SCOPES, MCP_OPT_IN_SCOPES
from routers import mcp as rest
from utils.mcp_scopes import normalize_mcp_scopes
from utils.mcp_server.registry import TOOL_REQUIRED_SCOPE

# Map transport operations to hosted tool names, never duplicate scope strings.
REST_TO_TOOL = {
    ("GET", "/v1/mcp/profile"): "get_user_profile",
    ("GET", "/v1/mcp/memories"): "get_memories",
    ("GET", "/v1/mcp/memories/search"): "search_memories",
    ("POST", "/v1/mcp/memories"): "create_memory",
    ("PATCH", "/v1/mcp/memories/{memory_id}"): "edit_memory",
    ("DELETE", "/v1/mcp/memories/{memory_id}"): "delete_memory",
    ("GET", "/v1/mcp/conversations"): "get_conversations",
    ("GET", "/v1/mcp/conversations/search"): "search_conversations",
    ("GET", "/v1/mcp/conversations/{conversation_id}"): "get_conversation_by_id",
    ("GET", "/v1/mcp/action-items"): "get_action_items",
    ("GET", "/v1/mcp/action-items/search"): "search_action_items",
    ("POST", "/v1/mcp/action-items"): "create_action_item",
    ("POST", "/v1/mcp/action-items/{action_item_id}/complete"): "complete_action_item",
    ("PATCH", "/v1/mcp/action-items/{action_item_id}"): "update_action_item",
    ("DELETE", "/v1/mcp/action-items/{action_item_id}"): "delete_action_item",
    ("GET", "/v1/mcp/goals"): "get_goals",
    ("GET", "/v1/mcp/chat"): "get_chat_messages",
    ("GET", "/v1/mcp/people"): "get_people",
    ("PATCH", "/v1/mcp/people/{person_id}/name"): "rename_person",
    ("POST", "/v1/mcp/people/{person_id}/dismiss"): "dismiss_person",
    ("GET", "/v1/mcp/screen-activity"): "get_screen_activity",
    ("GET", "/v1/mcp/daily-summaries"): "get_daily_summaries",
}
RESOURCE_ROUTES = list(REST_TO_TOOL)
WRITE_ROUTES = [route for route in RESOURCE_ROUTES if TOOL_REQUIRED_SCOPE[REST_TO_TOOL[route]].endswith(".write")]


def _dependency_calls(dependant):
    for child in dependant.dependencies:
        yield child.call
        yield from _dependency_calls(child)


def test_every_rest_route_has_a_scope_or_documented_firebase_owner_exemption():
    seen = set()
    for route in rest.router.routes:
        assert isinstance(route, APIRoute)
        calls = list(_dependency_calls(route.dependant))
        for method in route.methods:
            operation = (method, route.path)
            seen.add(operation)
            if operation in rest.MCP_REST_SCOPE_EXEMPTIONS:
                assert rest.MCP_REST_SCOPE_EXEMPTIONS[operation]
                assert dependencies.get_current_user_id in calls
                assert dependencies.get_mcp_api_key_auth not in calls
                continue
            assert operation in REST_TO_TOOL, f"Missing scope contract for {operation}"
            expected_scope = TOOL_REQUIRED_SCOPE[REST_TO_TOOL[operation]]
            requirements = []
            for call in calls:
                if call is dependencies.get_mcp_memory_default_memory_read_context:
                    requirements.append(TOOL_REQUIRED_SCOPE["get_memories"])
                elif call is dependencies.get_mcp_memory_default_memory_write_context:
                    requirements.append(TOOL_REQUIRED_SCOPE["create_memory"])
                elif inspect.isfunction(call):
                    scope = inspect.getclosurevars(call).nonlocals.get("required_scope")
                    if scope is not None:
                        requirements.append(scope)
            assert requirements == [expected_scope], (operation, requirements, expected_scope)
            assert dependencies.get_mcp_api_key_auth in calls
            assert dependencies.get_uid_from_mcp_api_key not in calls
    assert seen == set(REST_TO_TOOL) | set(rest.MCP_REST_SCOPE_EXEMPTIONS)


@pytest.fixture
def scope_client(monkeypatch):
    budget = AsyncMock()
    monkeypatch.setattr(dependencies, '_check_api_key_rate_limit_async', budget)
    # Preserve write wrapper execution, replacing only its external budget seam.
    monkeypatch.setattr(dependencies.auth_endpoints, '_enforce_rate_limit', lambda *args, **kwargs: None)
    state = {'scopes': list(MCP_FULL_ACCESS_SCOPES)}

    def verified_auth():
        return dependencies.ApiKeyAuth(uid='scope-user', scopes=state['scopes'], app_id='mcp-api', key_id='scope-key')

    app = FastAPI()
    app.include_router(rest.router)
    app.dependency_overrides[dependencies.get_mcp_api_key_auth] = verified_auth
    handler = Mock(return_value=Response(status_code=204))
    # Replace final business dispatch only. The actual nested dependency graph,
    # request validation, and route exception mapping remain in the request path.
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.dependant.call = handler
    with TestClient(app) as client:
        yield client, state, budget, handler


def _request(client, operation):
    method, path = operation
    path = path.replace('{memory_id}', 'memory-1').replace('{conversation_id}', 'conversation-1')
    path = path.replace('{action_item_id}', 'action-1').replace('{person_id}', 'person-1')
    body = None
    if method == 'POST' and path == '/v1/mcp/memories':
        body = {'content': 'test fact'}
    elif method == 'PATCH' and '/memories/' in path:
        body = {'content': 'updated fact'}
    elif method in {'POST', 'PATCH'} and '/action-items' in path and not path.endswith('/complete'):
        body = {'description': 'test task'}
    elif method == 'PATCH' and path.endswith('/name'):
        body = {'name': 'Renamed Person'}
    params = {}
    if path.endswith('/search'):
        params['query'] = 'test query'
    if '/memories/' in path and method == 'PATCH':
        params['value'] = 'updated fact'
    return client.request(method, path, json=body, params=params)


@pytest.mark.parametrize('operation', RESOURCE_ROUTES)
def test_full_scope_context_passes_each_route(scope_client, operation):
    client, state, budget, handler = scope_client
    response = _request(client, operation)
    if TOOL_REQUIRED_SCOPE[REST_TO_TOOL[operation]] in MCP_OPT_IN_SCOPES:
        # Full access deliberately excludes opt-in scopes; they need an explicit grant.
        assert response.status_code == 403, response.text
        handler.assert_not_called()
        return
    assert response.status_code == 204, response.text
    handler.assert_called_once()
    assert budget.await_count == 1


@pytest.mark.parametrize('operation', RESOURCE_ROUTES)
def test_required_scope_alone_passes_each_route(scope_client, operation):
    client, state, budget, handler = scope_client
    state['scopes'] = [TOOL_REQUIRED_SCOPE[REST_TO_TOOL[operation]]]
    response = _request(client, operation)
    assert response.status_code == 204, response.text
    handler.assert_called_once()


@pytest.mark.parametrize('operation', RESOURCE_ROUTES)
def test_missing_required_scope_denies_each_route_before_budget_or_dispatch(scope_client, operation):
    client, state, budget, handler = scope_client
    required = TOOL_REQUIRED_SCOPE[REST_TO_TOOL[operation]]
    state['scopes'] = [scope for scope in MCP_FULL_ACCESS_SCOPES if scope != required]
    response = _request(client, operation)
    assert response.status_code == 403, response.text
    assert required in response.json()['detail']
    budget.assert_not_awaited()
    handler.assert_not_called()


@pytest.mark.parametrize('operation', WRITE_ROUTES)
def test_read_scope_cannot_satisfy_a_write_route(scope_client, operation):
    client, state, budget, handler = scope_client
    state['scopes'] = [TOOL_REQUIRED_SCOPE[REST_TO_TOOL[operation]].replace('.write', '.read')]
    response = _request(client, operation)
    assert response.status_code == 403, response.text
    budget.assert_not_awaited()
    handler.assert_not_called()


@pytest.mark.parametrize('scopes', [None, [], ['memories.read'], ['unknown.scope']])
def test_raw_key_scope_normalization_still_grants_full_access(scopes):
    assert set(normalize_mcp_scopes(scopes)) == set(MCP_FULL_ACCESS_SCOPES)


@pytest.mark.parametrize('scope', MCP_FULL_ACCESS_SCOPES)
def test_scope_dependency_preserves_identity_budget_and_fails_closed(monkeypatch, scope):
    budget = AsyncMock()
    monkeypatch.setattr(dependencies, '_check_api_key_rate_limit_async', budget)
    dependency = dependencies.require_mcp_scope(scope)
    auth = dependencies.ApiKeyAuth('scope-user', [scope], 'scope-app', 'scope-key')
    assert asyncio.run(dependency(auth)) == 'scope-user'
    budget.assert_awaited_once_with(
        prefix='mcp', uid='scope-user', app_id='scope-app', key_id='scope-key', policy_name='mcp:read'
    )
    budget.reset_mock()
    for missing in [None, []]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(dependency(dependencies.ApiKeyAuth('scope-user', missing)))
        assert error.value.status_code == 403
    budget.assert_not_awaited()

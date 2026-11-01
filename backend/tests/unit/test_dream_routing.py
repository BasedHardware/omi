"""Dream routing is pinned; its narrow exception cannot affect desktop policy."""

import hashlib
import json
from pathlib import Path

import pytest
import httpx

from llm_gateway.main import app
from llm_gateway.routers import dependencies
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider

from llm_gateway.gateway import config_loader
from llm_gateway.gateway.dream_lanes import DREAM_LANES, DREAM_MODEL
from llm_gateway.gateway.errors import GatewayInvalidRequestError, GatewayInvalidRouteConfigError
from llm_gateway.gateway.resolver import is_lkg_eligible, resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass


def test_non_dream_route_artifacts_match_pre_change_snapshot():
    config = config_loader.load_gateway_config()
    actual = {
        key: hashlib.sha256(json.dumps(value.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
        for key, value in config.route_artifacts.items()
        if value.lane_id not in DREAM_LANES
    }
    expected = json.loads(Path(__file__).with_name('fixtures').joinpath('dream_non_dream_routes.json').read_text())
    assert actual == expected


@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
@pytest.mark.parametrize(
    'flag,assertion,allowed',
    [
        (None, True, False),
        ('false', True, False),
        ('true', False, False),
        ('true', 'true', False),
        ('true', True, True),
    ],
)
def test_on_demand_requires_flag_and_backend_allowlist(monkeypatch, lane, flag, assertion, allowed):
    monkeypatch.delenv('DREAM_ON_DEMAND_ENABLED', raising=False)
    if flag:
        monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', flag)
    config = config_loader.load_gateway_config()
    request = {
        'model': lane,
        'messages': [{'role': 'user', 'content': 'synthetic'}],
        'google': {'dream_capacity_mode': 'on_demand', 'dream_owner_allowlisted': assertion},
    }
    if not allowed:
        with pytest.raises(GatewayInvalidRequestError):
            resolve_chat_completion_route(config, request)
        return
    resolved = resolve_chat_completion_route(config, request)
    assert resolved.active_route.provider_options['_dream_capacity_mode'] == 'on_demand'
    assert resolved.active_route.provider_options['reserved_capacity_only'] is False
    assert (
        config.route_artifacts[resolved.active_route.route_artifact_id].provider_options['reserved_capacity_only']
        is True
    )


@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
def test_reserved_default_is_pinned_without_any_fallback(lane):
    config = config_loader.load_gateway_config()
    resolved = resolve_chat_completion_route(
        config, {'model': lane, 'messages': [{'role': 'user', 'content': 'synthetic'}]}
    )
    route = resolved.active_route
    assert route.primary.model == DREAM_MODEL
    assert route.primary.provider == 'gemini'
    assert route.provider_options == {
        'reserved_capacity_only': True,
        '_dream_capacity_mode': 'reserved',
        'location': 'us',
    }
    assert route.fallbacks == []
    assert route.retry.max_attempts == 1
    assert route.route_artifact_id == resolved.last_known_good_route.route_artifact_id
    for failure in FailureClass:
        assert not is_lkg_eligible(route, failure)


@pytest.mark.parametrize('mode', ['invalid', None, True, {}, []])
def test_invalid_mode_fails_before_provider(mode):
    with pytest.raises(GatewayInvalidRequestError):
        resolve_chat_completion_route(
            config_loader.load_gateway_config(),
            {
                'model': 'omi:auto:dream-reasoning',
                'messages': [{'role': 'user', 'content': 'synthetic'}],
                'google': {'dream_capacity_mode': mode},
            },
        )


def test_dream_route_validation_refuses_configured_fallback():
    from llm_gateway.gateway.dream_lanes import validate_dream_route
    from llm_gateway.gateway.schemas import ProviderRef

    config = config_loader.load_gateway_config()
    route = config.route_artifacts['route.dream_reasoning.001']
    with pytest.raises(GatewayInvalidRouteConfigError):
        validate_dream_route(
            route.model_copy(update={'fallbacks': [ProviderRef(provider='openai', model='gpt-6-luna')]})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
@pytest.mark.parametrize('flag,assertion', [('false', True), ('true', False), ('true', 'true')])
async def test_gateway_http_refuses_unauthorized_on_demand_before_provider(monkeypatch, lane, flag, assertion):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-token')
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', flag)
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'gemini': provider})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
            response = await client.post(
                '/v1/chat/completions',
                headers={'Authorization': 'Bearer synthetic-token', 'x-omi-service-caller': 'backend'},
                json={
                    'model': lane,
                    'messages': [{'role': 'user', 'content': 'synthetic'}],
                    'google': {'dream_capacity_mode': 'on_demand', 'dream_owner_allowlisted': assertion},
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert not provider.calls

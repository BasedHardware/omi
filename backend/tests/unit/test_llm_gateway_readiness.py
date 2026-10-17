from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llm_gateway.gateway.config_loader import ConfigValidationError, load_gateway_config
from llm_gateway.gateway.schemas import LaneConfig, RolloutStage, Surface
from llm_gateway.main import app
from llm_gateway.routers import health
from utils.llm.model_config import get_all_configured_features

@pytest.fixture
def client():
    return TestClient(app)


def test_ready_requires_service_auth(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = client.get('/ready')

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


def test_ready_validates_gateway_config(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    assert 'omi:auto:chat-structured' in response.json()['lanes']
    assert len(response.json()['lanes']) >= len(get_all_configured_features())
    assert response.json()['route_artifact_count'] >= len(get_all_configured_features()) + 2
    assert response.json()['managed_messages_provider'] == 'none'
    assert response.json()['managed_chat_provider'] == 'openai'
    assert response.json()['managed_web_search_provider'] == 'perplexity'


def test_ready_does_not_require_anthropic_key_after_chat_agent_migration(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['managed_messages_provider'] == 'none'
    assert response.json()['managed_chat_provider'] == 'openai'


def test_ready_fails_closed_when_managed_openai_key_is_missing(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway managed chat provider is not configured'


def test_ready_fails_closed_when_the_managed_web_search_key_is_missing(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('PERPLEXITY_API_KEY', raising=False)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway managed web search provider is not configured'


def test_managed_web_search_tracks_the_active_web_search_lane(client):
    config = health.get_gateway_config()

    assert health._managed_perplexity_chat_enabled(config) is True
    assert config.route_artifacts[config.lanes['omi:auto:web-search'].active_route].primary.provider == 'perplexity'


def test_ready_fails_closed_when_the_managed_systemone_key_is_missing(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway managed systemone provider is not configured'


def test_ready_passes_with_a_synthetic_systemone_key(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-openrouter-key')

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['status'] == 'ready'


def test_managed_systemone_tracks_the_active_decision_lane(client):
    config = health.get_gateway_config()

    assert health._managed_systemone_provider_enabled(config) is True
    route = config.route_artifacts[config.lanes['omi:auto:jev-decisions'].active_route]
    assert route.primary.provider == 'openrouter'


def test_managed_systemone_ignores_disabled_absent_or_non_openrouter_lanes(client):
    config = load_gateway_config()
    route = config.route_artifacts[config.lanes['omi:auto:jev-decisions'].active_route]
    route.rollout.stage = RolloutStage.DISABLED
    assert health._managed_systemone_provider_enabled(config) is False

    route.rollout.stage = RolloutStage.ACTIVE
    route.primary.provider = 'not-openrouter'
    assert health._managed_systemone_provider_enabled(config) is False

    del config.lanes['omi:auto:jev-decisions']
    assert health._managed_systemone_provider_enabled(config) is False


def test_ready_does_not_demand_the_systemone_key_when_its_route_is_disabled(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    config = load_gateway_config()
    config.route_artifacts[config.lanes['omi:auto:jev-decisions'].active_route].rollout.stage = RolloutStage.DISABLED
    monkeypatch.setattr(health, 'get_gateway_config', lambda: config)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 200


def test_ready_fails_closed_when_an_explicit_anthropic_lane_is_present(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(health, '_managed_anthropic_messages_enabled', lambda _config: True)
    monkeypatch.setattr(health, '_managed_openai_chat_enabled', lambda _config: False)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway managed messages provider is not configured'


def test_ready_fails_closed_on_invalid_gateway_config(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def invalid_config():
        raise ConfigValidationError('bad test config')

    monkeypatch.setattr(health, 'get_gateway_config', invalid_config)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway config is invalid'


def test_ready_fails_closed_on_schema_validation_error(monkeypatch, client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def invalid_config():
        LaneConfig.model_validate({})

    monkeypatch.setattr(health, 'get_gateway_config', invalid_config)

    response = client.get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway config is invalid'


def auth_headers() -> dict[str, str]:
    return {
        'authorization': 'Bearer shared-secret',
        'x-omi-service-caller': 'backend',
    }

def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}



def test_managed_anthropic_messages_enabled_returns_true(monkeypatch):
    config = load_gateway_config()
    lane = list(config.lanes.values())[0]
    lane.surface = Surface.ANTHROPIC_MESSAGES
    route = config.route_artifacts.get(lane.active_route)
    if route:
        route.primary.provider = 'anthropic'
    assert health._managed_anthropic_messages_enabled(config) is True

def test_managed_openai_chat_enabled_returns_true(monkeypatch):
    config = load_gateway_config()
    lane = list(config.lanes.values())[0]
    lane.surface = Surface.OPENAI_CHAT_COMPLETIONS
    route = config.route_artifacts.get(lane.active_route)
    if route:
        route.primary.provider = 'openai'
    assert health._managed_openai_chat_enabled(config) is True

def test_managed_systemone_provider_enabled_returns_true(monkeypatch):
    config = load_gateway_config()
    lane = list(config.lanes.values())[0]
    lane.surface = Surface.OPENROUTER_SYSTEMONE
    route = config.route_artifacts.get(lane.active_route)
    if route:
        route.primary.provider = 'openrouter'
        route.rollout.stage = RolloutStage.ACTIVE
    assert health._managed_systemone_provider_enabled(config) is True

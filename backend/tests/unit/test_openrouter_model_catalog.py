"""Unit tests for the dynamic OpenRouter model catalog."""

from __future__ import annotations

import json

import httpx
import pytest

from utils.llm.openrouter_model_catalog import (
    OpenRouterModelCatalog,
    apply_openrouter_completion_clamp,
    reset_openrouter_model_catalog_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_catalog():
    reset_openrouter_model_catalog_for_tests()
    yield
    reset_openrouter_model_catalog_for_tests()


def _models_payload() -> dict:
    return {
        'data': [
            {
                'id': 'openai/gpt-5.6-luna',
                'context_length': 128000,
                'supported_parameters': ['temperature', 'max_tokens', 'tools'],
                'top_provider': {
                    'context_length': 128000,
                    'max_completion_tokens': 4096,
                },
            },
            {
                'id': 'google/gemini-2.5-flash',
                'context_length': 1000000,
                'top_provider': {'max_completion_tokens': 8192},
            },
        ]
    }


def test_catalog_loads_context_and_completion_limits():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=_models_payload()),
    )
    catalog = OpenRouterModelCatalog(transport=transport, ttl_seconds=60)

    limits = catalog.get('openai/gpt-5.6-luna')
    assert limits is not None
    assert limits.context_length == 128000
    assert limits.max_completion_tokens == 4096
    assert 'tools' in limits.supported_parameters

    by_route = catalog.get_for_route('openrouter', 'gpt-5.6-luna')
    assert by_route == limits


def test_catalog_clamps_completion_tokens_to_provider_ceiling():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=_models_payload()),
    )
    catalog = OpenRouterModelCatalog(transport=transport, ttl_seconds=60)

    assert catalog.clamp_completion_tokens('openai/gpt-5.6-luna', 16000) == 4096
    assert catalog.clamp_completion_tokens('openai/gpt-5.6-luna', 512) == 512
    assert catalog.clamp_completion_tokens('missing/model', 16000) == 16000


def test_apply_openrouter_completion_clamp_only_for_openrouter():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=_models_payload()),
    )
    catalog = OpenRouterModelCatalog(transport=transport, ttl_seconds=60)

    openrouter_request = apply_openrouter_completion_clamp(
        {'model': 'openai/gpt-5.6-luna', 'max_completion_tokens': 16000},
        provider='openrouter',
        model='openai/gpt-5.6-luna',
        catalog=catalog,
    )
    assert openrouter_request['max_completion_tokens'] == 4096

    openai_request = apply_openrouter_completion_clamp(
        {'model': 'gpt-5.6-luna', 'max_completion_tokens': 16000},
        provider='openai',
        model='gpt-5.6-luna',
        catalog=catalog,
    )
    assert openai_request['max_completion_tokens'] == 16000


def test_catalog_keeps_stale_entries_when_refresh_fails():
    calls = {'count': 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls['count'] += 1
        if calls['count'] == 1:
            return httpx.Response(200, json=_models_payload())
        return httpx.Response(500, text='boom')

    catalog = OpenRouterModelCatalog(transport=httpx.MockTransport(handler), ttl_seconds=1)
    assert catalog.get('openai/gpt-5.6-luna') is not None
    catalog._expires_at = 0.0
    assert catalog.get('openai/gpt-5.6-luna') is not None
    assert calls['count'] == 2


def test_catalog_rejects_non_json_shape():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps({'unexpected': True}).encode()),
    )
    catalog = OpenRouterModelCatalog(transport=transport, ttl_seconds=60)
    assert catalog.get('openai/gpt-5.6-luna') is None

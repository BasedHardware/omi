"""An offline deployment must not fall back to the cloud LLM table in silence.

`should_route_features_through_gateway()` returns False whenever OMI_LLM_GATEWAY_FEATURE_MODE is
unset, and the caller then takes the direct branch into utils/llm/model_config.py — a code-owned
feature->model table with no env seam, whose entries are cloud models (gpt-*, gemini via Vertex,
openrouter, perplexity). Three of those providers have no base-URL override at all, so on-prem the
call either fails with an opaque provider error or actually reaches the vendor.

That silence is the bug. The Helm chart ships no llm_gateway workload and renders no OMI_LLM_GATEWAY_*
env (the wiring exists only in compose), so a chart install is precisely the configuration that takes
the direct branch — while declaring PROVIDER_MODE=offline. Refusing loudly names the missing
configuration; going direct pretends the deployment is something it is not.

Cloud behaviour is untouched: a deployment that does not declare itself offline keeps the existing
direct-branch semantics exactly as upstream ships them.
"""

from __future__ import annotations

import pytest

from utils.llm import gateway_client


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        'OMI_LLM_GATEWAY_FEATURE_MODE',
        'OMI_LLM_GATEWAY_URL',
        'OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE',
        'PROVIDER_MODE',
        'OMI_ENV_STAGE',
    ):
        monkeypatch.delenv(var, raising=False)


def test_offline_without_a_gateway_refuses_instead_of_going_direct(monkeypatch):
    monkeypatch.setenv('PROVIDER_MODE', 'offline')

    with pytest.raises(RuntimeError, match='OMI_LLM_GATEWAY'):
        gateway_client.should_route_features_through_gateway()


def test_offline_env_stage_is_the_same_signal(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')

    with pytest.raises(RuntimeError, match='OMI_LLM_GATEWAY'):
        gateway_client.should_route_features_through_gateway()


def test_offline_with_the_gateway_configured_routes_through_it(monkeypatch):
    """The compose posture: feature mode on, url set, prod override acknowledged."""
    monkeypatch.setenv('PROVIDER_MODE', 'offline')
    monkeypatch.setenv('OMI_LLM_GATEWAY_FEATURE_MODE', 'gateway')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://llm_gateway:9080')
    monkeypatch.setenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', 'true')

    assert gateway_client.should_route_features_through_gateway() is True


def test_a_non_offline_deployment_keeps_the_direct_branch(monkeypatch):
    """Upstream's cloud behaviour must not change: unset feature mode simply means direct."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')

    assert gateway_client.should_route_features_through_gateway() is False

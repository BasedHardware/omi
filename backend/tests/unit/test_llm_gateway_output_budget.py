from __future__ import annotations

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.output_budget import (
    OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR,
    apply_output_budget,
    completion_size_bucket,
    output_budget_bucket,
)
from llm_gateway.gateway.schemas import OutputBudgetPolicy


def test_session_titles_has_an_explicit_but_disabled_output_budget_policy():
    route = load_gateway_config(prod_mode=True).route_artifacts['route.session_titles.model_config.001']

    assert route.output_budget == OutputBudgetPolicy(experiment='session_titles', max_completion_tokens=128)


def test_output_budget_policy_is_disabled_until_its_experiment_is_enabled(monkeypatch):
    monkeypatch.delenv(OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR, raising=False)
    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite'},
        OutputBudgetPolicy(experiment='session_titles', max_completion_tokens=128),
    )

    assert 'max_completion_tokens' not in request
    assert decision.source == 'none'
    assert decision.max_completion_tokens is None


def test_output_budget_policy_applies_only_to_an_enabled_route_without_caller_limit(monkeypatch):
    monkeypatch.setenv(OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR, 'unrelated,session_titles')
    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite'},
        OutputBudgetPolicy(experiment='session_titles', max_completion_tokens=128),
    )

    assert request['max_completion_tokens'] == 128
    assert decision.source == 'route_default'
    assert decision.max_completion_tokens == 128


def test_caller_output_limit_wins_over_an_enabled_route_policy(monkeypatch):
    monkeypatch.setenv(OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR, 'session_titles')
    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite', 'max_tokens': 64},
        OutputBudgetPolicy(experiment='session_titles', max_completion_tokens=128),
    )

    assert request['max_tokens'] == 64
    assert 'max_completion_tokens' not in request
    assert decision.source == 'caller'
    assert decision.max_completion_tokens == 64


def test_budget_and_completion_observations_are_bounded():
    assert output_budget_bucket(None) == 'none'
    assert output_budget_bucket(128) == 'le_128'
    assert output_budget_bucket(8193) == 'gt_8192'
    assert completion_size_bucket(None) == 'unknown'
    assert completion_size_bucket(64) == 'le_64'
    assert completion_size_bucket(16385) == 'gt_16384'

from __future__ import annotations

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.output_budget import apply_output_budget, completion_size_bucket, output_budget_bucket
from llm_gateway.gateway.schemas import OutputBudgetPolicy


def test_dormant_session_titles_budget_policy_is_removed():
    route = load_gateway_config(prod_mode=True).route_artifacts['route.session_titles.model_config.001']
    assert route.output_budget is None


def test_output_budget_policy_applies_only_when_route_supplies_one():
    no_policy_request, no_policy_decision = apply_output_budget({'model': 'gemini-2.5-flash-lite'}, None)
    assert 'max_completion_tokens' not in no_policy_request
    assert no_policy_decision.source == 'none'

    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite'}, OutputBudgetPolicy(max_completion_tokens=128)
    )
    assert request['max_completion_tokens'] == 128
    assert decision.source == 'route_default'
    assert decision.max_completion_tokens == 128


def test_caller_output_limit_wins_over_route_policy():
    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite', 'max_tokens': 64}, OutputBudgetPolicy(max_completion_tokens=128)
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


def test_caller_output_limit_with_max_completion_tokens_wins():
    request, decision = apply_output_budget(
        {'model': 'gemini-2.5-flash-lite', 'max_completion_tokens': 64},
        OutputBudgetPolicy(max_completion_tokens=128),
    )
    assert request['max_completion_tokens'] == 64
    assert decision.source == 'caller'
    assert decision.max_completion_tokens == 64


def test_invalid_bool_limits_do_not_override_route_policy():
    for field in ('max_tokens', 'max_completion_tokens'):
        request, decision = apply_output_budget(
            {'model': 'gemini-2.5-flash-lite', field: True}, OutputBudgetPolicy(max_completion_tokens=128)
        )
        assert request['max_completion_tokens'] == 128
        assert decision.source == 'route_default'

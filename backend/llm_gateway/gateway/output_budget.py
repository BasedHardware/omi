"""Route-aware output caps and bounded observations for managed LLM requests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from llm_gateway.gateway.schemas import OutputBudgetPolicy

OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR = 'OMI_LLM_GATEWAY_OUTPUT_BUDGET_EXPERIMENTS'


@dataclass(frozen=True)
class OutputBudgetDecision:
    source: str
    max_completion_tokens: int | None


def apply_output_budget(
    request: Mapping[str, Any],
    policy: OutputBudgetPolicy | None,
) -> tuple[dict[str, Any], OutputBudgetDecision]:
    """Apply only an enabled route policy when a caller supplied no output cap."""
    provider_request = dict(request)
    caller_limit = _caller_limit(provider_request)
    if caller_limit is not None:
        return provider_request, OutputBudgetDecision(source='caller', max_completion_tokens=caller_limit)

    if policy is None or not _experiment_enabled(policy.experiment):
        return provider_request, OutputBudgetDecision(source='none', max_completion_tokens=None)

    provider_request['max_completion_tokens'] = policy.max_completion_tokens
    return provider_request, OutputBudgetDecision(
        source='route_default',
        max_completion_tokens=policy.max_completion_tokens,
    )


def output_budget_bucket(value: int | None) -> str:
    if value is None:
        return 'none'
    for upper_bound in (64, 128, 256, 512, 1024, 2048, 4096, 8192):
        if value <= upper_bound:
            return f'le_{upper_bound}'
    return 'gt_8192'


def completion_size_bucket(value: int | None) -> str:
    if value is None:
        return 'unknown'
    for upper_bound in (64, 256, 1024, 4096, 16384):
        if value <= upper_bound:
            return f'le_{upper_bound}'
    return 'gt_16384'


def _caller_limit(request: Mapping[str, Any]) -> int | None:
    max_tokens = request.get('max_tokens')
    max_completion_tokens = request.get('max_completion_tokens')
    if isinstance(max_completion_tokens, int) and not isinstance(max_completion_tokens, bool):
        return max_completion_tokens
    if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
        return max_tokens
    return None


def _experiment_enabled(experiment: str) -> bool:
    configured = os.getenv(OUTPUT_BUDGET_EXPERIMENTS_ENV_VAR, '')
    enabled = {item.strip().lower() for item in configured.split(',') if item.strip()}
    return experiment in enabled

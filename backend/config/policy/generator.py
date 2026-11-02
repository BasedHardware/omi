"""Seeded valid policy generation and pairwise coverage for batch and listen."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Mapping
from typing import Any, Hashable, cast

from config.policy.batch import BatchUnitPolicy, batch_generation_violations
from config.policy.covering_array import CoveringArray, pairwise_covering_array
from config.policy.listen import ListenSessionPolicy, listen_generation_violations

BATCH_FACTOR_DOMAINS: dict[str, tuple[Hashable, ...]] = {
    'batch_enabled': (False, True),
    'batch_percent': (0.0, 50.0, 100.0),
    'batch_allowlisted': (False, True),
    'live_admission_enabled': (False, True),
    'live_record_enabled': (False, True),
    'retire_percent': (0.0, 50.0, 100.0),
    'live_stt_retired': (False, True),
    'final_pass_enabled': (False, True),
    'final_pass_authoritative': (False, True),
}

_DEFAULT_SERVICE_MODELS: tuple[str, ...] = ('modulate-velma-2', 'soniox', 'dg-nova-3', 'parakeet')
_ROUTING_TARGETS_DEFAULTS = ''
_ROUTING_TARGETS_SONIOX = '[{"id":"soniox","family":"soniox","cost_per_audio_hour":0.0754,"ramp_percent":50}]'

LISTEN_FACTOR_DOMAINS: dict[str, tuple[Hashable, ...]] = {
    'routing_mode_raw': ('off', 'shadow', 'on', 'invalid'),
    'routing_on_percent': (0.0, 50.0, 100.0),
    'routing_on': (False, True),
    'routing_percent_valid': (False, True),
    'window_allocation_percent': (0.0, 50.0, 100.0),
    'window_allocation_valid': (False, True),
    'window_allocation_parse_valid': (False, True),
    'window_allocated': (False, True),
    'hintable_percent': (0.0, 50.0, 100.0),
    'hintable_allocated': (False, True),
    'demand_enabled': (False, True),
    'demand_percent': (0.0, 50.0, 100.0),
    'demand_admitted': (False, True),
    'demand_dwell_seconds': (5.0, 15.0, 60.0),
    'no_text_rescue_enabled': (False, True),
    'no_text_rescue_seconds': (5.0, 60.0, 120.0),
    'no_text_seconds': (1.0, 30.0, 60.0),
    'routing_targets_json': (_ROUTING_TARGETS_DEFAULTS, _ROUTING_TARGETS_SONIOX),
    'routing_disruption_gate': (0.04, 0.08, 0.2),
    'routing_redis_timeout_seconds': (0.01, 0.075, 0.1),
    'service_models': (_DEFAULT_SERVICE_MODELS, ('soniox', 'parakeet')),
    'failover_recovery_enabled': (False, True),
    'fallback_liveness_grace_seconds': (0.1, 0.3, 0.8),
    'paid_spillover_budget_enabled': (False, True),
    'paid_spillover_soniox_per_minute': (0, 30, 60),
    'paid_spillover_modulate_per_minute': (0, 30, 60),
    'paid_spillover_deepgram_per_minute': (0, 30, 60),
    'shed_connect_failures': (1, 3, 8),
    'circuit_half_open_probes': (1, 2, 4),
    'account_circuit_cooldown_seconds': (60.0, 1800.0, 3600.0),
    'learned_language_profile': (False, True),
    'multi_language_hints': (False, True),
}

FACTOR_DOMAINS: dict[str, tuple[Hashable, ...]] = {
    **{f'batch.{name}': values for name, values in BATCH_FACTOR_DOMAINS.items()},
    **{f'listen.{name}': values for name, values in LISTEN_FACTOR_DOMAINS.items()},
}


@dataclass(frozen=True)
class GeneratedPolicyCase:
    index: int
    batch_policy: BatchUnitPolicy
    listen_policy: ListenSessionPolicy


def _valid_assignment(values: Mapping[str, Hashable]) -> bool:
    batch = {name: values[f'batch.{name}'] for name in BATCH_FACTOR_DOMAINS if f'batch.{name}' in values}
    listen = {name: values[f'listen.{name}'] for name in LISTEN_FACTOR_DOMAINS if f'listen.{name}' in values}
    return not batch_generation_violations(batch) and not listen_generation_violations(listen)


def _seed_row(*, active: bool) -> dict[str, Hashable]:
    batch_defaults = {
        'batch_enabled': False,
        'batch_percent': 0.0,
        'batch_allowlisted': False,
        'live_admission_enabled': False,
        'live_record_enabled': False,
        'retire_percent': 0.0,
        'live_stt_retired': False,
        'final_pass_enabled': False,
        'final_pass_authoritative': False,
    }
    listen_defaults = {
        'routing_mode_raw': 'off',
        'routing_on_percent': 0.0,
        'routing_on': False,
        'routing_percent_valid': True,
        'routing_targets_json': _ROUTING_TARGETS_DEFAULTS,
        'routing_disruption_gate': 0.08,
        'routing_redis_timeout_seconds': 0.075,
        'window_allocation_percent': 0.0,
        'window_allocation_valid': True,
        'window_allocation_parse_valid': True,
        'window_allocated': False,
        'service_models': _DEFAULT_SERVICE_MODELS,
        'failover_recovery_enabled': False,
        'fallback_liveness_grace_seconds': 0.3,
        'paid_spillover_budget_enabled': False,
        'paid_spillover_soniox_per_minute': 30,
        'paid_spillover_modulate_per_minute': 30,
        'paid_spillover_deepgram_per_minute': 30,
        'shed_connect_failures': 3,
        'circuit_half_open_probes': 1,
        'account_circuit_cooldown_seconds': 1800.0,
        'no_text_seconds': 30.0,
        'no_text_rescue_enabled': False,
        'no_text_rescue_seconds': 60.0,
        'learned_language_profile': False,
        'multi_language_hints': True,
        'hintable_percent': 0.0,
        'hintable_allocated': False,
        'demand_enabled': False,
        'demand_percent': 0.0,
        'demand_admitted': False,
        'demand_dwell_seconds': 15.0,
    }
    values: dict[str, Hashable] = {
        **{f'batch.{name}': value for name, value in batch_defaults.items()},
        **{f'listen.{name}': value for name, value in listen_defaults.items()},
    }
    if active:
        values.update(
            {
                'batch.batch_enabled': True,
                'batch.batch_percent': 100.0,
                'batch.live_admission_enabled': True,
                'batch.live_record_enabled': True,
                'batch.retire_percent': 100.0,
                'batch.live_stt_retired': True,
                'batch.final_pass_enabled': True,
                'batch.final_pass_authoritative': True,
                'listen.routing_mode_raw': 'on',
                'listen.routing_on_percent': 100.0,
                'listen.routing_on': True,
                'listen.routing_percent_valid': True,
                'listen.window_allocation_percent': 100.0,
                'listen.window_allocation_valid': True,
                'listen.window_allocation_parse_valid': True,
                'listen.window_allocated': True,
                'listen.failover_recovery_enabled': True,
                'listen.paid_spillover_budget_enabled': True,
                'listen.no_text_rescue_enabled': True,
                'listen.learned_language_profile': True,
                'listen.multi_language_hints': True,
                'listen.hintable_percent': 100.0,
                'listen.hintable_allocated': True,
                'listen.demand_enabled': True,
                'listen.demand_percent': 100.0,
                'listen.demand_admitted': True,
            }
        )
    return values


@lru_cache(maxsize=8)
def policy_pairwise_array(seed: int = 1) -> CoveringArray:
    """Return a reproducible pairwise matrix over current admission/listen knobs."""
    return pairwise_covering_array(
        FACTOR_DOMAINS,
        valid=_valid_assignment,
        partial_valid=_valid_assignment,
        seed=seed,
        seed_rows=(_seed_row(active=False), _seed_row(active=True)),
        random_candidates=512,
    )


@lru_cache(maxsize=8)
def generate_policy_cases(seed: int = 1) -> tuple[GeneratedPolicyCase, ...]:
    """Construct immutable policies for every row in the pairwise matrix."""
    array = policy_pairwise_array(seed)
    cases = []
    for index, row in enumerate(array.rows):
        batch_values = {name: row[f'batch.{name}'] for name in BATCH_FACTOR_DOMAINS}
        listen_values = {name: row[f'listen.{name}'] for name in LISTEN_FACTOR_DOMAINS}
        batch_policy = BatchUnitPolicy(source_role='admission', **cast(dict[str, Any], batch_values))
        listen_policy = ListenSessionPolicy(source_role='listen', **cast(dict[str, Any], listen_values))
        batch_violations = batch_generation_violations(batch_policy)
        listen_violations = listen_generation_violations(listen_policy)
        if batch_violations or listen_violations:
            raise AssertionError(f'generated invalid policy: {batch_violations or listen_violations}')
        cases.append(GeneratedPolicyCase(index, batch_policy, listen_policy))
    return tuple(cases)


def policy_case_subset(seed: int = 20261020, limit: int = 12) -> tuple[GeneratedPolicyCase, ...]:
    """Select a stable PR-sized slice, retaining both anchor policies."""
    cases = generate_policy_cases(seed)
    if limit <= 0:
        return ()
    if len(cases) <= limit:
        return cases
    if limit <= 2:
        return cases[:limit]
    remaining_slots = limit - 2
    remaining_count = len(cases) - 2
    indexes = {
        2 + round(position * (remaining_count - 1) / max(1, remaining_slots - 1)) for position in range(remaining_slots)
    }
    selected = [cases[0], cases[1], *(cases[index] for index in sorted(indexes))]
    return tuple(selected[:limit])

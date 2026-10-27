"""Pinned Dream routes and the backend-asserted, allowlisted on-demand exception."""

import os
from collections.abc import Mapping
from typing import Any

from llm_gateway.gateway.errors import GatewayInvalidRequestError, GatewayInvalidRouteConfigError
from llm_gateway.gateway.schemas import RouteArtifact

DREAM_MODEL = 'gemini-3.8-flash'
DREAM_LOCATION = 'us'
DREAM_LANES = frozenset({'omi:auto:dream-reasoning', 'omi:auto:dream-verify'})


def dream_lane_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lanes, artifacts = [], []
    for stage in ('reasoning', 'verify'):
        lane_id = 'omi:auto:dream-' + stage
        route_id = 'route.dream_' + stage + '.001'
        capabilities = {
            'text_input': True,
            'streaming': False,
            'structured_output': 'json_schema',
            'tools': stage == 'reasoning',
            'translation': False,
        }
        credentials = {'mode': 'omi_paid', 'fallback_eligible_failure_classes': []}
        lanes.append(
            {
                'lane_id': lane_id,
                'surface': 'openai.chat_completions',
                'active_route': route_id,
                'last_known_good': route_id,
                'capabilities': capabilities,
                'credential_policy': credentials,
                'objective': {'quality': 0.6, 'latency': 0.1, 'cost': 0.3},
            }
        )
        artifacts.append(
            {
                'lane_id': lane_id,
                'route_artifact_id': route_id,
                'surface': 'openai.chat_completions',
                'primary': {'provider': 'gemini', 'model': DREAM_MODEL},
                'fallbacks': [],
                'provider_options': {
                    'reserved_capacity_only': True,
                    '_dream_capacity_mode': 'reserved',
                    'location': DREAM_LOCATION,
                },
                'capabilities': capabilities,
                'credential_policy': credentials,
                'fallback_policy': {'fallback_on': []},
                'timeouts': {'request_ms': 480000 if stage == 'reasoning' else 120000},
                'retry': {'max_attempts': 1},
                'rollout': {'stage': 'active', 'percent': 100},
                'evidence': {
                    'benchmark_snapshot': 'dream.harness.v2',
                    'eval_report': 'backend.tests.unit.test_dream_session',
                    'benchmark_source': 'omi_eval',
                    'dev_only': False,
                },
            }
        )
    return lanes, artifacts


def validate_dream_route(route: RouteArtifact) -> None:
    if (
        route.primary.provider != 'gemini'
        or route.primary.model != DREAM_MODEL
        or route.fallbacks
        or route.fallback_policy.fallback_on
        or route.credential_policy.mode.value != 'omi_paid'
        or route.credential_policy.fallback_eligible_failure_classes
        or route.provider_options.get('reserved_capacity_only') is not True
        or route.provider_options.get('_dream_capacity_mode') != 'reserved'
        or route.provider_options.get('location') != DREAM_LOCATION
        or route.retry.max_attempts != 1
    ):
        raise GatewayInvalidRouteConfigError('Dream requires pinned 3.8 reserved routes without fallback')


def resolve_dream_route(route: RouteArtifact, request: Mapping[str, Any]) -> RouteArtifact:
    """The private gateway trusts the authenticated backend's allowlist assertion."""
    validate_dream_route(route)
    google = request.get('google', {})
    if not isinstance(google, Mapping):
        raise GatewayInvalidRequestError('Dream google options must be a mapping', param='google')
    mode = google.get('dream_capacity_mode', 'reserved')
    if mode not in ('reserved', 'on_demand'):
        raise GatewayInvalidRequestError('invalid Dream capacity mode', param='google.dream_capacity_mode')
    if mode == 'on_demand' and (
        google.get('dream_owner_allowlisted') is not True
        or os.getenv('DREAM_ON_DEMAND_ENABLED', '').strip().lower() not in {'1', 'true', 'yes'}
    ):
        raise GatewayInvalidRequestError('Dream on-demand is disabled or owner is not allowlisted', param='google')
    return route.model_copy(
        update={
            'provider_options': {
                **route.provider_options,
                '_dream_capacity_mode': mode,
                'reserved_capacity_only': mode == 'reserved',
            }
        }
    )

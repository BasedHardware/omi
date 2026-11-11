"""Validate resolver-owned Dream capacity before any desktop Vertex policy runs."""

import os
from collections.abc import Mapping
from typing import Any

from llm_gateway.gateway.dream_lanes import DREAM_LANES
from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass


def capacity_mode(request: Mapping[str, Any], owner: str | None) -> str | None:
    policy = request.get('_gateway_cache_policy')
    lane = policy.get('lane') if isinstance(policy, Mapping) else None
    marker = request.get('_dream_capacity_mode')
    if lane not in DREAM_LANES:
        if marker is not None:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
        return None
    if marker not in {'reserved', 'on_demand'}:
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
    if marker == 'on_demand':
        google = request.get('google')
        if not (
            owner
            and isinstance(google, Mapping)
            and google.get('dream_owner_allowlisted') is True
            and os.getenv('DREAM_ON_DEMAND_ENABLED', '').strip().lower() in {'1', 'true', 'yes'}
        ):
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
    return marker

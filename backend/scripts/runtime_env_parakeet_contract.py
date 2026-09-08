"""Deployment contract for Parakeet-owned live-stream admission."""

from __future__ import annotations

from typing import Any, cast

from scripts.runtime_env_durable_dispatch_contracts import ValidationError

ConfigDict = dict[str, Any]


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _literal_env_value(env_map: ConfigDict, key: str) -> str | None:
    entry = _as_config_dict(env_map.get(key))
    value = entry.get('value') if entry is not None else None
    return str(value) if value is not None else None


def validate_parakeet_admission_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Require the GPU owner to receive explicit, valid stream limits."""
    scope = f'{env}/gke/parakeet'
    gke = _as_config_dict(env_config.get('gke')) or {}
    parakeet = _as_config_dict(gke.get('parakeet'))
    if parakeet is None:
        return [ValidationError(scope, 'missing Parakeet deploy contract')]
    env_map = _as_config_dict(parakeet.get('env')) or {}
    errors: list[ValidationError] = []

    capacity_raw = _literal_env_value(env_map, 'PARAKEET_STREAM_CAPACITY')
    try:
        if capacity_raw is None or int(capacity_raw) < 1:
            raise ValueError
    except ValueError:
        message = (
            'missing PARAKEET_STREAM_CAPACITY'
            if capacity_raw is None
            else 'PARAKEET_STREAM_CAPACITY must be an integer >= 1'
        )
        errors.append(ValidationError(scope, message))

    allocation_raw = _literal_env_value(env_map, 'PARAKEET_STREAM_ALLOCATION_PERCENT')
    try:
        if allocation_raw is None or not 0 <= int(allocation_raw) <= 100:
            raise ValueError
    except ValueError:
        message = (
            'missing PARAKEET_STREAM_ALLOCATION_PERCENT'
            if allocation_raw is None
            else 'PARAKEET_STREAM_ALLOCATION_PERCENT must be an integer from 0 through 100'
        )
        errors.append(ValidationError(scope, message))
    return errors

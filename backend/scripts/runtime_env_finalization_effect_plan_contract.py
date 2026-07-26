"""Deployment parity contract for durable conversation finalization effects."""

from __future__ import annotations

from typing import Any, cast

from scripts.runtime_env_durable_dispatch_contracts import ValidationError

ConfigDict = dict[str, Any]

MODE_ENV = 'CONVERSATION_FINALIZATION_EFFECT_PLAN_MODE'
MODES = frozenset({'standby', 'active'})
GKE_SERVICES = ('backend-listen', 'pusher')
CLOUD_RUN_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _service_env(services: ConfigDict, service: str) -> ConfigDict:
    service_config = _as_config_dict(services.get(service)) or {}
    return _as_config_dict(service_config.get('env')) or {}


def validate_finalization_effect_plan_mode_contract(
    env: str,
    env_config: ConfigDict,
) -> list[ValidationError]:
    """Keep every finalization producer and worker on one explicit rollout mode."""
    gke = _as_config_dict(env_config.get('gke')) or {}
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    cloud_run_services = _as_config_dict(cloud_run.get('services')) or {}
    surfaces = [
        *((f'{env}/gke/{service}', _service_env(gke, service)) for service in GKE_SERVICES),
        *((f'{env}/cloud_run/{service}', _service_env(cloud_run_services, service)) for service in CLOUD_RUN_SERVICES),
    ]
    errors: list[ValidationError] = []
    expected_mode: str | None = None
    for scope, env_map in surfaces:
        entry = _as_config_dict(env_map.get(MODE_ENV))
        if entry is None:
            errors.append(ValidationError(scope, f'missing {MODE_ENV}'))
            continue
        mode = str(entry.get('value', '')).strip().lower()
        if mode not in MODES:
            errors.append(ValidationError(scope, f'{MODE_ENV} must be a literal standby or active value'))
            continue
        if entry.get('category') != 'rollout':
            errors.append(ValidationError(scope, f'{MODE_ENV} must use category rollout'))
        if expected_mode is None:
            expected_mode = mode
        elif mode != expected_mode:
            errors.append(
                ValidationError(
                    scope,
                    f'{MODE_ENV} mismatch: expected {expected_mode!r}, got {mode!r}',
                )
            )
    return errors

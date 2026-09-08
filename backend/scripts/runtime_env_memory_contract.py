"""Canonical-memory runtime environment retirement contract."""

from __future__ import annotations

from typing import Any, cast

from scripts.runtime_env_durable_dispatch_contracts import ValidationError

ConfigDict = dict[str, Any]

RETIRED_CANONICAL_MEMORY_ENV = frozenset(
    {
        'MEMORY_ENABLED_USERS',
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS',
        'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
    }
)


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def validate_retired_memory_env(*, scope: str, actual: object) -> list[ValidationError]:
    actual_entries = _as_config_dict(actual) or {}
    return [
        ValidationError(
            scope,
            (
                f'retired canonical memory env {name} is forbidden; universal memory has no per-user runtime inventory'
                if name == 'MEMORY_ENABLED_USERS'
                else f'retired canonical memory env {name} is forbidden; use the minimal maintenance contract'
            ),
        )
        for name in sorted(RETIRED_CANONICAL_MEMORY_ENV.intersection(actual_entries))
    ]


def validate_retired_memory_manifest(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Reject old promotion gates anywhere a runtime env can be declared.

    Deploy workflows keep ``--remove-env-vars`` entries for cleanup of existing
    revisions. The retired names must never return as manifest env bindings:
    Scheduler owns cadence, maintenance owns execution, and consolidation owns
    the independently useful L2 step.
    """

    errors: list[ValidationError] = []
    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        errors.extend(
            validate_retired_memory_env(
                scope=f'{env}/gke/{service}',
                actual=service_config.get('env'),
            )
        )

    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    for kind in ('services', 'jobs'):
        for service, raw_service in (_as_config_dict(cloud_run.get(kind)) or {}).items():
            service_config = _as_config_dict(raw_service) or {}
            declared = {
                **(_as_config_dict(service_config.get('env')) or {}),
                **(_as_config_dict(service_config.get('secrets')) or {}),
            }
            errors.extend(
                validate_retired_memory_env(
                    scope=f'{env}/cloud_run/{kind}/{service}',
                    actual=declared,
                )
            )
    return errors

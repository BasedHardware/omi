"""Production deployment contracts for durable Cloud Tasks dispatchers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

ConfigDict = dict[str, Any]

_ACCOUNT_DELETION_PROD_CLOUD_RUN_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
_ACCOUNT_DELETION_LITERAL_ENV = {
    'ACCOUNT_DELETION_DISPATCH_MODE': 'cloud_tasks',
    'ACCOUNT_DELETION_TASKS_QUEUE': 'account-deletion',
    'SYNC_TASKS_PROJECT': 'based-hardware',
    'SYNC_TASKS_LOCATION': 'us-central1',
}
_ACCOUNT_DELETION_DYNAMIC_ENV = frozenset(
    {'ACCOUNT_DELETION_HANDLER_URL', 'SYNC_TASKS_INVOKER_SA', 'SYNC_TASKS_HANDLER_URL'}
)
_LISTEN_FINALIZATION_PROD_CLOUD_RUN_SERVICES = ('backend', 'backend-sync')
_LISTEN_FINALIZATION_LITERAL_ENV = {
    'LISTEN_FINALIZATION_DISPATCH_MODE': 'cloud_tasks',
    'LISTEN_FINALIZATION_TASKS_QUEUE': 'conversation-finalization',
    'LISTEN_FINALIZATION_TASKS_MAX_ATTEMPTS': '5',
    'HTTP_LISTEN_FINALIZATION_RUN_TIMEOUT': '1500',
}
_LISTEN_FINALIZATION_DYNAMIC_ENV = frozenset(
    {'LISTEN_FINALIZATION_TASKS_HANDLER_URL', 'LISTEN_FINALIZATION_TASKS_INVOKER_SA'}
)


@dataclass(frozen=True)
class ValidationError:
    scope: str
    message: str


def validate_account_deletion_dispatch_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep every production API host out of the inline deletion execution path."""
    if env != 'prod':
        return []

    errors: list[ValidationError] = []
    gke = _as_config_dict(env_config.get('gke')) or {}
    backend_listen = _as_config_dict(gke.get('backend-listen')) or {}
    _validate_account_deletion_env_entries(
        errors,
        scope='prod/gke/backend-listen',
        env_entries=_as_config_dict(backend_listen.get('env')) or {},
        dynamic_binding='config_map',
    )

    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    services = _as_config_dict(cloud_run.get('services')) or {}
    for service in _ACCOUNT_DELETION_PROD_CLOUD_RUN_SERVICES:
        service_config = _as_config_dict(services.get(service)) or {}
        _validate_account_deletion_env_entries(
            errors,
            scope=f'prod/cloud_run/{service}',
            env_entries=_as_config_dict(service_config.get('env')) or {},
            dynamic_binding='env_var',
        )
    return errors


def validate_listen_finalization_dispatch_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep the customer exact-ID route on its deployed durable worker boundary."""
    if env != 'prod':
        return []

    errors: list[ValidationError] = []
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    services = _as_config_dict(cloud_run.get('services')) or {}
    for service in _LISTEN_FINALIZATION_PROD_CLOUD_RUN_SERVICES:
        service_config = _as_config_dict(services.get(service)) or {}
        _validate_listen_finalization_env_entries(
            errors,
            scope=f'prod/cloud_run/{service}',
            env_entries=_as_config_dict(service_config.get('env')) or {},
        )
    return errors


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _validate_account_deletion_env_entries(
    errors: list[ValidationError],
    *,
    scope: str,
    env_entries: ConfigDict,
    dynamic_binding: str,
) -> None:
    for name, expected_value in _ACCOUNT_DELETION_LITERAL_ENV.items():
        entry = _as_config_dict(env_entries.get(name))
        if entry is None:
            errors.append(ValidationError(scope, f'missing required account-deletion env {name}'))
        elif entry.get('value') != expected_value:
            errors.append(ValidationError(scope, f'account-deletion env {name} must be literal {expected_value!r}'))

    for name in _ACCOUNT_DELETION_DYNAMIC_ENV:
        entry = _as_config_dict(env_entries.get(name))
        if entry is None:
            errors.append(ValidationError(scope, f'missing required account-deletion env {name}'))
        elif dynamic_binding == 'env_var' and entry.get('env_var') != name:
            errors.append(ValidationError(scope, f'account-deletion env {name} must bind ${name}'))
        elif dynamic_binding == 'config_map':
            config_map = _as_config_dict(entry.get('config_map')) or {}
            if config_map.get('name') != 'prod-omi-backend-config' or config_map.get('key') != name:
                errors.append(
                    ValidationError(
                        scope,
                        f'account-deletion env {name} must bind prod-omi-backend-config/{name}',
                    )
                )


def _validate_listen_finalization_env_entries(
    errors: list[ValidationError], *, scope: str, env_entries: ConfigDict
) -> None:
    for name, expected_value in _LISTEN_FINALIZATION_LITERAL_ENV.items():
        entry = _as_config_dict(env_entries.get(name))
        if entry is None:
            errors.append(ValidationError(scope, f'missing required listen-finalization env {name}'))
        elif entry.get('value') != expected_value:
            errors.append(ValidationError(scope, f'listen-finalization env {name} must be literal {expected_value!r}'))

    for name in _LISTEN_FINALIZATION_DYNAMIC_ENV:
        entry = _as_config_dict(env_entries.get(name))
        if entry is None:
            errors.append(ValidationError(scope, f'missing required listen-finalization env {name}'))
        elif entry.get('env_var') != name:
            errors.append(ValidationError(scope, f'listen-finalization env {name} must bind ${name}'))

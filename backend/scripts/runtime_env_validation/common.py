from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.runtime_env_durable_dispatch_contracts import ValidationError
from scripts.runtime_env_memory_contract import validate_retired_memory_env

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / 'backend'
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
ConfigDict = dict[str, Any]
EnvEntry = dict[str, Any]
EnvEntryMap = dict[str, EnvEntry]
StringMap = dict[str, str]

_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_ENV = frozenset(
    {
        'MEMORY_MODE',
        'MEMORY_ENABLED_USERS',
        'MEMORY_V3_GET_ENABLED',
        'MEMORY_CANONICAL_MAINTENANCE_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'MEMORY_TYPESENSE_COLLECTION',
        'TYPESENSE_HOST',
        'TYPESENSE_HOST_PORT',
        'TYPESENSE_API_KEY',
    }
)
_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_SECRETS = frozenset({'TYPESENSE_HOST', 'TYPESENSE_API_KEY'})
_SYNC_LEDGER_FENCE_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill')
_SYNC_LEDGER_FENCE_MODES = frozenset({'legacy', 'standby', 'active'})
_MEMORY_MAINTENANCE_DEV_REQUIRED_FLAGS = {
    '--task-timeout': '3600s',
    '--cpu': '2',
    '--memory': '2Gi',
}


def compute_project(env_config: ConfigDict) -> str:
    value = env_config.get('compute_project', env_config.get('gcp_project'))
    if not isinstance(value, str) or not value:
        raise ValueError('environment config must define compute_project or gcp_project')
    return value


def data_plane_project(env_config: ConfigDict) -> str:
    value = env_config.get('data_plane_project', env_config.get('runtime_gcp_project'))
    if isinstance(value, str) and value:
        return value
    return compute_project(env_config)


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _as_config_list(value: object) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


def _cloud_run_secret_ref(entry: EnvEntry) -> StringMap | None:
    value_from = _as_config_dict(entry.get('valueFrom'))
    if value_from is None:
        return None
    secret_key_ref = _as_config_dict(value_from.get('secretKeyRef'))
    if secret_key_ref is not None:
        name = secret_key_ref.get('name')
        version = secret_key_ref.get('key', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    secret_ref = _as_config_dict(value_from.get('secretRef'))
    if secret_ref is not None:
        name = secret_ref.get('name')
        version = secret_ref.get('version', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    return None


def _config_map_names(raw_env_from: object) -> set[str]:
    entries = _as_config_list(raw_env_from) or []
    names: set[str] = set()
    for entry in entries:
        config_map_ref = _as_config_dict((_as_config_dict(entry) or {}).get('configMapRef'))
        name = config_map_ref.get('name') if config_map_ref is not None else None
        if isinstance(name, str):
            names.add(name)
    return names


def _env_entries_by_name(raw_env: object) -> EnvEntryMap:
    raw_env_list = _as_config_list(raw_env)
    if raw_env_list is None:
        return {}
    result: EnvEntryMap = {}
    for entry in raw_env_list:
        entry_dict = _as_config_dict(entry)
        if entry_dict is not None and isinstance(entry_dict.get('name'), str):
            result[entry_dict['name']] = entry_dict
    return result


def _expected_flag_value(expected_entry: object) -> str:
    expected_dict = _as_config_dict(expected_entry)
    if expected_dict is not None and 'value' in expected_dict:
        return str(expected_dict['value'])
    return str(expected_entry)


def _get_env_config(manifest: ConfigDict, env: str) -> ConfigDict:
    environments = _as_config_dict(manifest.get('environments'))
    if environments is None or env not in environments:
        raise ValueError(f'manifest has no environments.{env}')
    env_config = _as_config_dict(environments[env])
    if env_config is None:
        raise ValueError(f'environments.{env} must be a mapping')
    return env_config


def _has_literal_value(entry: EnvEntry) -> bool:
    return entry.get('value') not in (None, '')


def _is_provisional(expected_entry: object) -> bool:
    expected_dict = _as_config_dict(expected_entry)
    return expected_dict is not None and bool(expected_dict.get('provisional'))


def _literal_env_entries_by_name(raw_env: object, *, variables: StringMap | None = None) -> EnvEntryMap:
    raw_env_dict = _as_config_dict(raw_env)
    if raw_env_dict is None:
        return {}
    variables = variables or {}
    return {
        name: {'name': name, 'value': variables.get(str(value), str(value))} for name, value in raw_env_dict.items()
    }


def _literal_env_value(entry: dict[str, Any]) -> str:
    value = entry.get('value')
    if value is None:
        return ''
    return str(value)


def _load_json(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return cast(ConfigDict, loaded)


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _manifest_env_value(expected_services: ConfigDict, name: str) -> str:
    for raw_service_config in expected_services.values():
        service_config = _as_config_dict(raw_service_config) or {}
        env_config = _as_config_dict(service_config.get('env')) or {}
        env_entry = _as_config_dict(env_config.get(name))
        if isinstance(env_entry, dict) and 'value' in env_entry:
            return str(env_entry['value'])
    return ''


def _network_flags(env_config: ConfigDict) -> ConfigDict:
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    network = _as_config_dict(cloud_run.get('network')) or {}
    return _as_config_dict(network.get('flags')) or {}


def _secret_ref(entry: EnvEntry) -> StringMap | None:
    value_from = _as_config_dict(entry.get('valueFrom'))
    if value_from is None:
        return None
    secret_ref = _as_config_dict(value_from.get('secretKeyRef'))
    if secret_ref is None:
        return None
    name = secret_ref.get('name')
    key = secret_ref.get('key')
    if not isinstance(name, str) or not isinstance(key, str):
        return None
    return {'name': name, 'key': key}


def _substitute_values(raw: object, *, variables: StringMap) -> StringMap:
    raw_dict = _as_config_dict(raw)
    if raw_dict is None:
        return {}
    return {str(name): variables.get(str(value), str(value)) for name, value in raw_dict.items()}


def _validate_cloud_run_secret_entries(
    *,
    scope: str,
    expected: ConfigDict,
    actual: EnvEntryMap,
) -> list[ValidationError]:
    errors = validate_retired_memory_env(scope=scope, actual=actual)
    for name, expected_entry in expected.items():
        actual_entry = actual.get(name)
        if actual_entry is None:
            errors.append(ValidationError(scope, f'missing secret binding {name}'))
            continue
        actual_secret = _cloud_run_secret_ref(actual_entry)
        expected_secret = {
            'secret': expected_entry['secret'],
            'version': str(expected_entry.get('version', 'latest')),
        }
        if actual_secret != expected_secret:
            errors.append(ValidationError(scope, f'secret binding {name} mismatch: expected {expected_secret!r}'))
    return errors


def _validate_env_entries(
    *,
    scope: str,
    expected: ConfigDict,
    actual: EnvEntryMap,
    strict_provisional: bool,
    config_maps: set[str] | None = None,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        if 'config_map' in expected_entry:
            config_map = _as_config_dict(expected_entry['config_map']) or {}
            expected_name = config_map.get('name')
            if not isinstance(expected_name, str) or expected_name not in (config_maps or set()):
                errors.append(ValidationError(scope, f'env {name} must come from ConfigMap {expected_name!r}'))
            continue
        actual_entry = actual.get(name)
        if actual_entry is None:
            if _is_provisional(expected_entry) and not strict_provisional:
                continue
            errors.append(ValidationError(scope, f'missing env {name}'))
            continue
        if 'value' in expected_entry:
            if expected_entry.get('provisional') and not strict_provisional:
                if not _has_literal_value(actual_entry):
                    errors.append(ValidationError(scope, f'env {name} must have a literal value'))
                continue
            actual_value = _literal_env_value(actual_entry)
            expected_value = str(expected_entry['value'])
            if actual_value != expected_value:
                errors.append(ValidationError(scope, f'env {name} value mismatch: expected {expected_value!r}'))
        elif 'env_var' in expected_entry:
            if not _has_literal_value(actual_entry):
                errors.append(ValidationError(scope, f'env {name} must have a literal value'))
        elif 'secret' in expected_entry:
            expected_secret = expected_entry['secret']
            actual_secret = _secret_ref(actual_entry)
            if actual_secret != expected_secret:
                errors.append(ValidationError(scope, f'env {name} secret mismatch: expected {expected_secret!r}'))
    return errors


def _validate_forbidden_env_entries(
    *,
    scope: str,
    forbidden: object,
    actual: EnvEntryMap,
) -> list[ValidationError]:
    if forbidden is None:
        return []
    forbidden_names = _as_config_list(forbidden)
    if forbidden_names is None or any(not isinstance(name, str) or not name for name in forbidden_names):
        return [ValidationError(scope, 'forbidden_env must be a list of non-empty env names')]
    return [
        ValidationError(scope, f'forbidden env {name} is present')
        for name in sorted(set(forbidden_names).intersection(actual))
    ]

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'


@dataclass(frozen=True)
class ValidationError:
    scope: str
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate backend runtime env manifests against checked-in GKE config and Cloud Run state.'
    )
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--cloud-run-state',
        type=Path,
        help='Offline Cloud Run state JSON. Shape: {"services": {"backend": {"env": [...]} }}.',
    )
    parser.add_argument(
        '--check-live-cloud-run',
        action='store_true',
        help='Fetch Cloud Run service state with gcloud and validate required env/secrets.',
    )
    parser.add_argument(
        '--strict-provisional',
        action='store_true',
        help='Require provisional manifest values to match exactly. By default they only require presence.',
    )
    args = parser.parse_args()

    errors = validate_runtime_env(
        env=args.env,
        manifest_path=args.manifest,
        cloud_run_state_path=args.cloud_run_state,
        check_live_cloud_run=args.check_live_cloud_run,
        strict_provisional=args.strict_provisional,
    )
    for error in errors:
        print(f'ERROR [{error.scope}]: {error.message}', file=sys.stderr)
    if errors:
        return 1
    print(f'backend runtime env validation passed for {args.env}')
    return 0


def validate_runtime_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    cloud_run_state_path: Path | None = None,
    check_live_cloud_run: bool = False,
    strict_provisional: bool = False,
) -> list[ValidationError]:
    manifest = _load_yaml(manifest_path)
    env_config = _get_env_config(manifest, env)
    errors = _validate_manifest_shape(env_config, env)
    if errors:
        return errors

    errors.extend(_validate_gke(env_config, strict_provisional=strict_provisional))

    cloud_run_state = None
    if cloud_run_state_path is not None:
        cloud_run_state = _load_json(cloud_run_state_path)
    elif check_live_cloud_run:
        cloud_run_state = _fetch_live_cloud_run_state(env_config)

    if cloud_run_state is not None:
        errors.extend(_validate_cloud_run(env_config, cloud_run_state, strict_provisional=strict_provisional))
    return errors


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def _load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return loaded


def _get_env_config(manifest: dict[str, Any], env: str) -> dict[str, Any]:
    environments = manifest.get('environments')
    if not isinstance(environments, dict) or env not in environments:
        raise ValueError(f'manifest has no environments.{env}')
    env_config = environments[env]
    if not isinstance(env_config, dict):
        raise ValueError(f'environments.{env} must be a mapping')
    return env_config


def _validate_manifest_shape(env_config: dict[str, Any], env: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key in ('gcp_project', 'region', 'gke', 'cloud_run'):
        if key not in env_config:
            errors.append(ValidationError(env, f'missing {key}'))
    cloud_run_services = env_config.get('cloud_run', {}).get('services')
    if not isinstance(cloud_run_services, dict) or not cloud_run_services:
        errors.append(ValidationError(env, 'cloud_run.services must be a non-empty mapping'))
    return errors


def _validate_gke(env_config: dict[str, Any], *, strict_provisional: bool) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for service, service_config in env_config.get('gke', {}).items():
        values_file = ROOT / service_config['values_file']
        values = _load_yaml(values_file)
        actual_env = _env_entries_by_name(values.get('env', []))
        errors.extend(
            _validate_env_entries(
                scope=f'gke/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
    return errors


def _validate_cloud_run(
    env_config: dict[str, Any],
    cloud_run_state: dict[str, Any],
    *,
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    state_services = cloud_run_state.get('services')
    if not isinstance(state_services, dict):
        return [ValidationError('cloud_run', 'state must contain services mapping')]

    for service, service_config in env_config['cloud_run']['services'].items():
        service_state = state_services.get(service)
        if not isinstance(service_state, dict):
            errors.append(ValidationError(f'cloud_run/{service}', 'missing service state'))
            continue
        actual_env = _env_entries_by_name(service_state.get('env', []))
        errors.extend(
            _validate_env_entries(
                scope=f'cloud_run/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
        errors.extend(
            _validate_cloud_run_secret_entries(
                scope=f'cloud_run/{service}',
                expected=service_config.get('secrets', {}),
                actual=actual_env,
            )
        )
    return errors


def _validate_env_entries(
    *,
    scope: str,
    expected: dict[str, Any],
    actual: dict[str, dict[str, Any]],
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        actual_entry = actual.get(name)
        if actual_entry is None:
            errors.append(ValidationError(scope, f'missing env {name}'))
            continue
        if 'value' in expected_entry:
            if expected_entry.get('provisional') and not strict_provisional:
                if not _has_literal_value(actual_entry):
                    errors.append(ValidationError(scope, f'env {name} must have a literal value'))
                continue
            actual_value = actual_entry.get('value')
            expected_value = str(expected_entry['value'])
            if actual_value != expected_value:
                errors.append(ValidationError(scope, f'env {name} value mismatch: expected {expected_value!r}'))
        elif 'secret' in expected_entry:
            expected_secret = expected_entry['secret']
            actual_secret = _secret_ref(actual_entry)
            if actual_secret != expected_secret:
                errors.append(ValidationError(scope, f'env {name} secret mismatch: expected {expected_secret!r}'))
    return errors


def _validate_cloud_run_secret_entries(
    *,
    scope: str,
    expected: dict[str, Any],
    actual: dict[str, dict[str, Any]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
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


def _env_entries_by_name(raw_env: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_env, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in raw_env:
        if isinstance(entry, dict) and isinstance(entry.get('name'), str):
            result[entry['name']] = entry
    return result


def _has_literal_value(entry: dict[str, Any]) -> bool:
    return entry.get('value') not in (None, '')


def _secret_ref(entry: dict[str, Any]) -> dict[str, str] | None:
    value_from = entry.get('valueFrom')
    if not isinstance(value_from, dict):
        return None
    secret_ref = value_from.get('secretKeyRef')
    if not isinstance(secret_ref, dict):
        return None
    name = secret_ref.get('name')
    key = secret_ref.get('key')
    if not isinstance(name, str) or not isinstance(key, str):
        return None
    return {'name': name, 'key': key}


def _cloud_run_secret_ref(entry: dict[str, Any]) -> dict[str, str] | None:
    value_from = entry.get('valueFrom')
    if not isinstance(value_from, dict):
        return None
    secret_key_ref = value_from.get('secretKeyRef')
    if isinstance(secret_key_ref, dict):
        name = secret_key_ref.get('name')
        version = secret_key_ref.get('key', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    secret_ref = value_from.get('secretRef')
    if isinstance(secret_ref, dict):
        name = secret_ref.get('name')
        version = secret_ref.get('version', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    return None


def _fetch_live_cloud_run_state(env_config: dict[str, Any]) -> dict[str, Any]:
    services: dict[str, Any] = {}
    project = env_config['gcp_project']
    region = env_config['region']
    for service in env_config['cloud_run']['services']:
        command = [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        service_state = json.loads(result.stdout)
        services[service] = {
            'env': service_state.get('spec', {})
            .get('template', {})
            .get('spec', {})
            .get('containers', [{}])[0]
            .get('env', [])
        }
    return {'services': services}


if __name__ == '__main__':
    raise SystemExit(main())

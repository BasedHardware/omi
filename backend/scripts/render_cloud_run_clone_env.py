#!/usr/bin/env python3
"""Clone a live Cloud Run service's complete env contract with explicit overlays."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

_DEPLOY_CLOUD_RUN_ENV_SEPARATORS = frozenset({',', '\n', '\r', '\u2028', '\u2029'})
# Env names that carry an exportable service-account key, or the path to one.
KEY_CREDENTIAL_ENV_NAMES = frozenset({'SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS'})
_DEFAULT_COMPUTE_SERVICE_ACCOUNT = re.compile(r'\d+-compute@developer\.gserviceaccount\.com')


def _pairs(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name, separator, item_value = line.partition('=')
        if not separator or not name:
            raise ValueError(f'invalid NAME=VALUE entry: {raw_line!r}')
        result[name] = item_value
    return result


def _names(value: str) -> set[str]:
    return {name for part in value.split(',') if (name := part.strip())}


def clone_environment(
    service: dict[str, Any], env_overlay: str, secret_overlay: str, remove_env_vars: str = ''
) -> tuple[str, str]:
    literals: dict[str, str] = {}
    secrets: dict[str, str] = {}
    remove_names = _names(remove_env_vars)
    containers = service.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
    if not containers:
        raise ValueError('source Cloud Run service has no container')
    for entry in containers[0].get('env', []):
        name = entry.get('name')
        if not name:
            continue
        if name in remove_names:
            continue
        if 'value' in entry:
            literals[name] = _escape_deploy_cloud_run_env_value(str(entry['value']))
            continue
        secret_ref = entry.get('valueFrom', {}).get('secretKeyRef', {})
        secret_name = secret_ref.get('name')
        if secret_name:
            secrets[name] = f'{secret_name}:{secret_ref.get("key", "latest")}'

    for name, value in _pairs(env_overlay).items():
        literals[name] = value
        secrets.pop(name, None)
    for name, value in _pairs(secret_overlay).items():
        secrets[name] = value
        literals.pop(name, None)
    for name in remove_names:
        literals.pop(name, None)
        secrets.pop(name, None)

    return (
        '\n'.join(f'{name}={value}' for name, value in sorted(literals.items())),
        '\n'.join(f'{name}={value}' for name, value in sorted(secrets.items())),
    )


def target_runs_as_attached_identity(target: dict[str, Any] | None) -> bool:
    """True when the target service's live template runs as a dedicated (non-default) service account.

    Such a runtime identity is granted only the secrets it needs and deliberately cannot read a
    key-credential secret. Cloning the source service's key ref onto it would make the new revision
    fail its secret access check, and gcloud applies --update-secrets after --remove-secrets.
    """
    if not target:
        return False
    service_account = str(target.get('spec', {}).get('template', {}).get('spec', {}).get('serviceAccountName') or '')
    return bool(service_account) and not _DEFAULT_COMPUTE_SERVICE_ACCOUNT.fullmatch(service_account)


def _escape_deploy_cloud_run_env_value(value: str) -> str:
    """Encode raw live Cloud Run literals for deploy-cloudrun's input grammar."""
    return ''.join(
        f'\\{character}' if character == '\\' or character in _DEPLOY_CLOUD_RUN_ENV_SEPARATORS else character
        for character in value
    )


def _emit(name: str, value: str) -> None:
    delimiter = f'__CLONED_CLOUD_RUN_{name.upper()}__'
    print(f'{name}<<{delimiter}')
    print(value)
    print(delimiter)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-json', type=Path, required=True)
    parser.add_argument(
        '--target-json',
        type=Path,
        help='Live spec of the service being deployed; key-credential refs are dropped when it runs as its own identity.',
    )
    args = parser.parse_args()
    service = json.loads(args.source_json.read_text(encoding='utf-8'))
    target = json.loads(args.target_json.read_text(encoding='utf-8')) if args.target_json else None
    remove_env_vars = os.getenv('REMOVE_ENV_VARS', '')
    if target_runs_as_attached_identity(target):
        remove_env_vars = ','.join(filter(None, (remove_env_vars, *sorted(KEY_CREDENTIAL_ENV_NAMES))))
    env_vars, secrets = clone_environment(
        service,
        os.getenv('ENV_OVERLAY', ''),
        os.getenv('SECRET_OVERLAY', ''),
        remove_env_vars,
    )
    _emit('env_vars', env_vars)
    _emit('secrets', secrets)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

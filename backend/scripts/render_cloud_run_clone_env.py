#!/usr/bin/env python3
"""Clone a live Cloud Run service's complete env contract with explicit overlays."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


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
    return {name.strip() for name in value.replace(',', '\n').splitlines() if name.strip()}


def clone_environment(
    service: dict[str, Any],
    env_overlay: str,
    secret_overlay: str,
    *,
    drop_names: str = '',
) -> tuple[str, str]:
    literals: dict[str, str] = {}
    secrets: dict[str, str] = {}
    containers = service.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
    if not containers:
        raise ValueError('source Cloud Run service has no container')
    for entry in containers[0].get('env', []):
        name = entry.get('name')
        if not name:
            continue
        if 'value' in entry:
            literals[name] = str(entry['value'])
            continue
        secret_ref = entry.get('valueFrom', {}).get('secretKeyRef', {})
        secret_name = secret_ref.get('name')
        if secret_name:
            secrets[name] = f'{secret_name}:{secret_ref.get("key", "latest")}'

    # Drop inherited live state first. An explicit manifest overlay may then
    # deliberately restore a name for one environment without leaking that
    # credential into environments whose manifest omits it.
    for name in _names(drop_names):
        literals.pop(name, None)
        secrets.pop(name, None)
    for name, value in _pairs(env_overlay).items():
        literals[name] = value
        secrets.pop(name, None)
    for name, value in _pairs(secret_overlay).items():
        secrets[name] = value
        literals.pop(name, None)

    return (
        '\n'.join(f'{name}={value}' for name, value in sorted(literals.items())),
        '\n'.join(f'{name}={value}' for name, value in sorted(secrets.items())),
    )


def secret_removal_flags(secret_overlay: str, drop_names: str) -> str:
    explicit_secret_names = set(_pairs(secret_overlay))
    names_to_remove = sorted(_names(drop_names) - explicit_secret_names)
    if not names_to_remove:
        return ''
    return f'--remove-secrets={",".join(names_to_remove)}'


def _emit(name: str, value: str) -> None:
    delimiter = f'__CLONED_CLOUD_RUN_{name.upper()}__'
    print(f'{name}<<{delimiter}')
    print(value)
    print(delimiter)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-json', type=Path, required=True)
    args = parser.parse_args()
    service = json.loads(args.source_json.read_text(encoding='utf-8'))
    env_vars, secrets = clone_environment(
        service,
        os.getenv('ENV_OVERLAY', ''),
        os.getenv('SECRET_OVERLAY', ''),
        drop_names=os.getenv('DROP_NAMES', ''),
    )
    _emit('env_vars', env_vars)
    _emit('secrets', secrets)
    _emit('remove_secret_flags', secret_removal_flags(os.getenv('SECRET_OVERLAY', ''), os.getenv('DROP_NAMES', '')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'


def main() -> int:
    parser = argparse.ArgumentParser(description='Render backend Cloud Run runtime env from the manifest.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    manifest = _load_yaml(args.manifest)
    env_config = manifest['environments'][args.env]
    cloud_run = env_config['cloud_run']

    _emit_output('cloud_run_flags', _render_flags(cloud_run.get('network', {}).get('flags', {})))
    for service, service_config in cloud_run['services'].items():
        output_prefix = _output_prefix(service)
        _emit_output(f'{output_prefix}_env_vars', _render_env_vars(service_config.get('env', {})))
        _emit_output(f'{output_prefix}_secrets', _render_secrets(service_config.get('secrets', {})))
    return 0


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def _render_env_vars(env_entries: dict[str, Any]) -> str:
    lines = []
    for name, entry in env_entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f'Cloud Run env {name} must be a mapping')
        value = _runtime_value(name, entry, allow_missing=bool(entry.get('provisional')))
        if value is None:
            # Provisional values belong to services not yet deployed in every environment.
            continue
        lines.append(f'{name}={value}')
    return '\n'.join(lines)


def _render_secrets(secret_entries: dict[str, Any]) -> str:
    lines = []
    for name, entry in secret_entries.items():
        if not isinstance(entry, dict) or 'secret' not in entry:
            raise ValueError(f'Cloud Run secret binding {name} must have a secret entry')
        version = entry.get('version', 'latest')
        lines.append(f'{name}={entry["secret"]}:{version}')
    return '\n'.join(lines)


def _render_flags(flag_entries: dict[str, Any]) -> str:
    flags = []
    for name, entry in flag_entries.items():
        if isinstance(entry, dict):
            value = _runtime_value(name, entry)
        else:
            value = entry
        if value in (None, ''):
            raise ValueError(f'Cloud Run flag {name} must have a value')
        flags.append(f'{name}={value}')
    return ' '.join(flags)


def _runtime_value(name: str, entry: dict[str, Any], *, allow_missing: bool = False) -> str | None:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        value = os.environ.get(env_var, '')
        if value:
            return value
        if allow_missing:
            return None
        raise ValueError(f'{name} requires ${env_var} to be set')
    raise ValueError(f'{name} must define value or env_var')


def _emit_output(name: str, value: str) -> None:
    delimiter = f'__BACKEND_RUNTIME_ENV_{name}__'
    print(f'{name}<<{delimiter}')
    print(value)
    print(delimiter)


def _output_prefix(service: str) -> str:
    return service.replace('-', '_')


if __name__ == '__main__':
    raise SystemExit(main())

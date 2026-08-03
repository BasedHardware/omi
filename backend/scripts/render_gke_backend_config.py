#!/usr/bin/env python3
"""Extract GKE backend ConfigMap keys and values from the composed runtime manifest."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'

ConfigDict = dict[str, Any]


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def config_map_entries(env: str, manifest_path: Path = DEFAULT_MANIFEST) -> tuple[str, dict[str, str]]:
    manifest = _load_yaml(manifest_path)
    environments = _as_config_dict(manifest.get('environments')) or {}
    env_config = _as_config_dict(environments.get(env))
    if env_config is None:
        raise ValueError(f'manifest has no environments.{env}')

    gke = _as_config_dict(env_config.get('gke')) or {}
    config_map = _as_config_dict(gke.get('config_map'))
    if config_map is None:
        raise ValueError(f'environments.{env}.gke.config_map is required')

    name = config_map.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError(f'environments.{env}.gke.config_map.name must be a non-empty string')

    entries = _as_config_dict(config_map.get('entries'))
    if not entries:
        raise ValueError(f'environments.{env}.gke.config_map.entries must be a non-empty mapping')

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for key, raw_entry in entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None:
            raise ValueError(f'config_map entry {key} must be a mapping')
        source = entry.get('source')
        if source == 'literal':
            value = entry.get('value')
            if not isinstance(value, str):
                raise ValueError(f'config_map entry {key} with source=literal requires string value')
            resolved[key] = value
            continue
        if source == 'environment':
            value = os.environ.get(key)
            if value is None or value == '':
                missing.append(key)
                continue
            resolved[key] = value
            continue
        raise ValueError(f'config_map entry {key} has unsupported source {source!r}')

    if missing:
        raise ValueError(f'Missing required non-secret deployment variables: {" ".join(missing)}')

    return name, resolved


def main() -> int:
    parser = argparse.ArgumentParser(description='Render GKE backend ConfigMap data from runtime manifest.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--format',
        choices=('env', 'keys'),
        default='env',
        help='env: KEY=value lines for kubectl --from-env-file; keys: one key name per line',
    )
    args = parser.parse_args()

    try:
        _name, entries = config_map_entries(args.env, args.manifest)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == 'keys':
        for key in entries:
            print(key)
        return 0

    for key in entries:
        print(f'{key}={entries[key]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

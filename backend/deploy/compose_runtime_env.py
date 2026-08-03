#!/usr/bin/env python3
"""Compose backend/deploy/runtime_env.yaml from base + per-environment overlays."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENV_DIR = ROOT / 'backend/deploy/runtime_env'
DEFAULT_BASE = RUNTIME_ENV_DIR / '_base.yaml'
DEFAULT_OUTPUT = ROOT / 'backend/deploy/runtime_env.yaml'
GENERATED_HEADER = '# generated — do not edit; run: python3 backend/deploy/compose_runtime_env.py\n'

ConfigDict = dict[str, Any]
ENVIRONMENTS = ('dev', 'prod')
_CLOUD_RUN_SERVICE_ORDER = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
_GKE_SERVICE_ORDER = ('backend-listen', 'parakeet', 'pusher')


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _deep_merge(base: object, overlay: object) -> object:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = deepcopy(base)
        for key, value in overlay.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(overlay)


def _substitute_placeholders(obj: object, *, env: str, compute_project: str, data_plane_project: str) -> object:
    if isinstance(obj, str):
        return (
            obj.replace('{env}', env)
            .replace('{compute_project}', compute_project)
            .replace('{data_plane_project}', data_plane_project)
        )
    if isinstance(obj, dict):
        return {
            key: _substitute_placeholders(
                value,
                env=env,
                compute_project=compute_project,
                data_plane_project=data_plane_project,
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [
            _substitute_placeholders(
                item,
                env=env,
                compute_project=compute_project,
                data_plane_project=data_plane_project,
            )
            for item in obj
        ]
    return obj


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _stabilize_mapping_order(mapping: dict[str, Any], preferred: tuple[str, ...]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in preferred:
        if key in mapping:
            ordered[key] = mapping[key]
    for key, value in mapping.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _stabilize_env_config(env_config: ConfigDict) -> ConfigDict:
    stabilized = cast(ConfigDict, deepcopy(env_config))
    cloud_run = _as_config_dict(stabilized.get('cloud_run'))
    if cloud_run is not None:
        services = _as_config_dict(cloud_run.get('services'))
        if services is not None:
            cloud_run['services'] = _stabilize_mapping_order(services, _CLOUD_RUN_SERVICE_ORDER)
    gke = _as_config_dict(stabilized.get('gke'))
    if gke is not None:
        gke_services = {key: value for key, value in gke.items() if key != 'config_map'}
        stabilized_gke = _stabilize_mapping_order(gke_services, _GKE_SERVICE_ORDER)
        if 'config_map' in gke:
            stabilized_gke['config_map'] = gke['config_map']
        stabilized['gke'] = stabilized_gke
    return stabilized


def _overlay_path(env: str, runtime_env_dir: Path = RUNTIME_ENV_DIR) -> Path:
    return runtime_env_dir / f'{env}.overlay.yaml'


def _compose_environment(
    shared: object,
    overlay_doc: ConfigDict,
    *,
    expected_env: str,
) -> ConfigDict:
    env = str(overlay_doc['environment'])
    if env != expected_env:
        raise ValueError(f'overlay environment {env!r} does not match requested env {expected_env!r}')
    compute_project = str(overlay_doc['compute_project'])
    data_plane_project = str(overlay_doc['data_plane_project'])
    overlay_body = overlay_doc.get('overlay', {})

    substituted_shared = _substitute_placeholders(
        shared,
        env=env,
        compute_project=compute_project,
        data_plane_project=data_plane_project,
    )
    merged = _deep_merge(substituted_shared, overlay_body)
    if not isinstance(merged, dict):
        raise ValueError(f'composed environment {env} must be a mapping')

    env_config = cast(ConfigDict, merged)
    env_config['compute_project'] = compute_project
    env_config['data_plane_project'] = data_plane_project
    # Legacy aliases consumed by deploy scripts and validators.
    env_config['gcp_project'] = compute_project
    env_config['runtime_gcp_project'] = data_plane_project
    return _stabilize_env_config(env_config)


def compose_manifest(
    *,
    base_path: Path = DEFAULT_BASE,
    runtime_env_dir: Path = RUNTIME_ENV_DIR,
) -> ConfigDict:
    base_doc = _load_yaml(base_path)
    shared = base_doc.get('environment_shared', {})
    environments: ConfigDict = {}
    for env in ENVIRONMENTS:
        overlay_doc = _load_yaml(_overlay_path(env, runtime_env_dir))
        environments[env] = _compose_environment(shared, overlay_doc, expected_env=env)
    return {
        'schema_version': base_doc.get('schema_version', 1),
        'environments': environments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Compose backend/deploy/runtime_env.yaml from base + overlays.')
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--runtime-env-dir', type=Path, default=RUNTIME_ENV_DIR)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--check', action='store_true', help='exit 1 when output would change')
    args = parser.parse_args()

    manifest = compose_manifest(base_path=args.base, runtime_env_dir=args.runtime_env_dir)
    rendered = GENERATED_HEADER + yaml.safe_dump(
        manifest,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    if args.check:
        current = args.output.read_text(encoding='utf-8') if args.output.exists() else ''
        if current != rendered:
            print(f'{args.output} is out of date; run compose_runtime_env.py', file=__import__('sys').stderr)
            return 1
        print(f'{args.output} is up to date')
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding='utf-8')
    print(f'Wrote {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

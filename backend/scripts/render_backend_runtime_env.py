#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
ConfigDict = dict[str, Any]


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description='Render backend Cloud Run runtime env from the manifest.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--job', help='Render only the named Cloud Run job and shared network flags.')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    manifest = _load_yaml(args.manifest)
    environments = _as_config_dict(manifest['environments']) or {}
    env_config = _as_config_dict(environments[args.env]) or {}
    cloud_run = _as_config_dict(env_config['cloud_run']) or {}

    services = _as_config_dict(cloud_run.get('services')) or {}
    jobs = _as_config_dict(cloud_run.get('jobs')) or {}
    if args.job is not None and args.job not in jobs:
        raise ValueError(f'Cloud Run job {args.job} is not defined for {args.env}')

    network = _as_config_dict(cloud_run.get('network')) or {}
    _emit_output('cloud_run_flags', _render_flags(_as_config_dict(network.get('flags')) or {}))
    if args.job is None:
        for service, raw_service_config in services.items():
            service_config = _as_config_dict(raw_service_config)
            if service_config is None:
                raise ValueError(f'Cloud Run service {service} must be a mapping')
            output_prefix = _output_prefix(service)
            _emit_output(f'{output_prefix}_env_vars', _render_env_vars(service_config.get('env', {})))
            _emit_output(f'{output_prefix}_secrets', _render_secrets(service_config.get('secrets', {})))
            _emit_output(f'{output_prefix}_secret_names', _render_secret_names(service_config.get('secrets', {})))

    jobs_to_render = {args.job: jobs[args.job]} if args.job is not None else jobs
    for job, raw_job_config in jobs_to_render.items():
        job_config = _as_config_dict(raw_job_config)
        if job_config is None:
            raise ValueError(f'Cloud Run job {job} must be a mapping')
        output_prefix = _output_prefix(job)
        _emit_output(f'{output_prefix}_flags', _render_flags(_as_config_dict(job_config.get('flags')) or {}))
        _emit_output(f'{output_prefix}_env_vars', _render_env_vars(job_config.get('env', {})))
        _emit_output(f'{output_prefix}_secrets', _render_secrets(job_config.get('secrets', {})))
        _emit_output(f'{output_prefix}_secret_names', _render_secret_names(job_config.get('secrets', {})))
    return 0


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _render_env_vars(env_entries: ConfigDict) -> str:
    lines: list[str] = []
    for name, raw_entry in env_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None:
            raise ValueError(f'Cloud Run env {name} must be a mapping')
        value = _runtime_value(name, entry, allow_missing=bool(entry.get('provisional')))
        if value is None:
            # Provisional values belong to services not yet deployed in every environment.
            continue
        lines.append(f'{name}={value}')
    return '\n'.join(lines)


def _render_secrets(secret_entries: ConfigDict) -> str:
    lines: list[str] = []
    for name, raw_entry in secret_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None or 'secret' not in entry:
            raise ValueError(f'Cloud Run secret binding {name} must have a secret entry')
        version = entry.get('version', 'latest')
        lines.append(f'{name}={entry["secret"]}:{version}')
    return '\n'.join(lines)


def _render_secret_names(secret_entries: ConfigDict) -> str:
    return ','.join(secret_entries.keys())


def _render_flags(flag_entries: ConfigDict) -> str:
    flags: list[str] = []
    for name, raw_entry in flag_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None:
            value = _runtime_value(name, entry)
        else:
            value = raw_entry
        if value in (None, ''):
            raise ValueError(f'Cloud Run flag {name} must have a value')
        flags.append(f'{name}={value}')
    return ' '.join(flags)


def _runtime_value(name: str, entry: ConfigDict, *, allow_missing: bool = False) -> str | None:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        value = os.environ.get(env_var, '')
        if value:
            return value
        default = entry.get('default')
        if default is not None:
            return str(default)
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

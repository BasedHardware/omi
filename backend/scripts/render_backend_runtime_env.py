#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
ConfigDict = dict[str, Any]
_DEPLOY_CLOUD_RUN_ENV_SEPARATORS = frozenset({',', '\n', '\r', '\u2028', '\u2029'})


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description='Render backend Cloud Run runtime env from the manifest.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument(
        '--job',
        help='render only this Cloud Run job and the shared network flags; services remain full-environment only',
    )
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--state-output',
        type=Path,
        help='Write the exact rendered Cloud Run service env, secret refs, and flags as validator state JSON.',
    )
    parser.add_argument(
        '--desktop-state-output',
        type=Path,
        help=(
            'Write the rendered desktop-backend env as expected-env-state JSON for '
            'attach_cloud_run_gmp_sidecar.py --expected-env-state.'
        ),
    )
    args = parser.parse_args()
    if args.job and args.state_output:
        parser.error('--state-output is supported only for the full service render')
    if args.job and args.desktop_state_output:
        parser.error('--desktop-state-output is supported only for the full service render')

    manifest = _load_yaml(args.manifest)
    environments = _as_config_dict(manifest['environments']) or {}
    env_config = _as_config_dict(environments[args.env]) or {}

    if args.desktop_state_output:
        args.desktop_state_output.write_text(
            json.dumps(_render_desktop_backend_state(env_config), indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        # desktop-backend deploys from its own workflow and does not set the
        # backend service env this script otherwise requires. Rendering the
        # sidecar guard must not force those callers to supply it, so stop here
        # unless a backend render was also asked for.
        if not args.state_output and not args.job:
            return 0

    cloud_run = _as_config_dict(env_config['cloud_run']) or {}

    jobs = _as_config_dict(cloud_run.get('jobs')) or {}
    selected_jobs = jobs
    if args.job:
        raw_job_config = jobs.get(args.job)
        if raw_job_config is None:
            raise ValueError(f'unknown Cloud Run job {args.job!r} for environment {args.env}')
        selected_jobs = {args.job: raw_job_config}

    # Render everything before emitting output. A selected job with an invalid
    # contract must fail without leaving a partial GITHUB_OUTPUT file behind.
    rendered_outputs: list[tuple[str, str]] = []
    network = _as_config_dict(cloud_run.get('network')) or {}
    rendered_outputs.append(('cloud_run_flags', _render_flags(_as_config_dict(network.get('flags')) or {})))
    services = _as_config_dict(cloud_run.get('services')) or {}
    if not args.job:
        desktop_backend = _as_config_dict(env_config.get('desktop_backend')) or {}
        desktop_env = _as_config_dict(desktop_backend.get('env')) or {}
        desktop_secrets = _as_config_dict(desktop_backend.get('secrets')) or {}
        if desktop_env:
            rendered_outputs.append(('desktop_backend_env_vars', _render_env_vars(desktop_env)))
        if desktop_secrets:
            rendered_outputs.extend(
                (
                    ('desktop_backend_secrets', _render_secrets(desktop_secrets)),
                    ('desktop_backend_secret_names', _render_secret_names(desktop_secrets)),
                )
            )
        for service, raw_service_config in services.items():
            service_config = _as_config_dict(raw_service_config)
            if service_config is None:
                raise ValueError(f'Cloud Run service {service} must be a mapping')
            output_prefix = _output_prefix(service)
            rendered_outputs.extend(
                (
                    (f'{output_prefix}_env_vars', _render_env_vars(service_config.get('env', {}))),
                    (f'{output_prefix}_secrets', _render_secrets(service_config.get('secrets', {}))),
                    (f'{output_prefix}_secret_names', _render_secret_names(service_config.get('secrets', {}))),
                )
            )
    for job, raw_job_config in selected_jobs.items():
        job_config = _as_config_dict(raw_job_config)
        if job_config is None:
            raise ValueError(f'Cloud Run job {job} must be a mapping')
        output_prefix = _output_prefix(job)
        rendered_outputs.extend(
            (
                (f'{output_prefix}_flags', _render_flags(_as_config_dict(job_config.get('flags')) or {})),
                (f'{output_prefix}_env_vars', _render_env_vars(job_config.get('env', {}))),
                (f'{output_prefix}_secrets', _render_secrets(job_config.get('secrets', {}))),
                (f'{output_prefix}_secret_names', _render_secret_names(job_config.get('secrets', {}))),
            )
        )
    if args.state_output:
        args.state_output.write_text(
            json.dumps(_render_cloud_run_state(env_config), indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
    for name, value in rendered_outputs:
        _emit_output(name, value)
    return 0


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _render_env_entries(env_entries: ConfigDict) -> list[ConfigDict]:
    rendered: list[ConfigDict] = []
    for name, raw_entry in env_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None:
            raise ValueError(f'Cloud Run env {name} must be a mapping')
        value = _runtime_value(name, entry, allow_missing=bool(entry.get('provisional')))
        if value is None:
            # Provisional values belong to services not yet deployed in every environment.
            continue
        rendered.append({'name': str(name), 'value': value})
    return rendered


def _render_env_vars(env_entries: ConfigDict) -> str:
    return '\n'.join(
        f'{entry["name"]}={_escape_deploy_cloud_run_env_value(entry["value"])}'
        for entry in _render_env_entries(env_entries)
    )


def _escape_deploy_cloud_run_env_value(value: str) -> str:
    """Encode a value for deploy-cloudrun's escaped key/value input grammar."""
    return ''.join(
        f'\\{character}' if character == '\\' or character in _DEPLOY_CLOUD_RUN_ENV_SEPARATORS else character
        for character in value
    )


def _render_secret_entries(secret_entries: ConfigDict) -> list[ConfigDict]:
    rendered: list[ConfigDict] = []
    for name, raw_entry in secret_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None or 'secret' not in entry:
            raise ValueError(f'Cloud Run secret binding {name} must have a secret entry')
        version = entry.get('version', 'latest')
        rendered.append(
            {
                'name': str(name),
                'valueFrom': {
                    'secretKeyRef': {
                        'name': str(entry['secret']),
                        'key': str(version),
                    }
                },
            }
        )
    return rendered


def _render_secrets(secret_entries: ConfigDict) -> str:
    return '\n'.join(
        f'{entry["name"]}={entry["valueFrom"]["secretKeyRef"]["name"]}:{entry["valueFrom"]["secretKeyRef"]["key"]}'
        for entry in _render_secret_entries(secret_entries)
    )


def _render_secret_names(secret_entries: ConfigDict) -> str:
    return ','.join(secret_entries.keys())


def _render_flag_values(flag_entries: ConfigDict) -> dict[str, str]:
    flags: dict[str, str] = {}
    for name, raw_entry in flag_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None:
            value = _runtime_value(name, entry)
        else:
            value = raw_entry
        if value in (None, ''):
            raise ValueError(f'Cloud Run flag {name} must have a value')
        flags[str(name)] = str(value)
    return flags


def _render_flags(flag_entries: ConfigDict) -> str:
    return ' '.join(f'{name}={value}' for name, value in _render_flag_values(flag_entries).items())


def _render_cloud_run_state(env_config: ConfigDict) -> ConfigDict:
    """Build validator state from the same values emitted to deploy-cloudrun."""
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    network = _as_config_dict(cloud_run.get('network')) or {}
    network_flags = _render_flag_values(_as_config_dict(network.get('flags')) or {})
    services: ConfigDict = {}
    for service_name, raw_service_config in (_as_config_dict(cloud_run.get('services')) or {}).items():
        service_config = _as_config_dict(raw_service_config)
        if service_config is None:
            raise ValueError(f'Cloud Run service {service_name} must be a mapping')
        services[str(service_name)] = {
            'env': _render_state_env(service_config),
            'flags': dict(network_flags),
        }
    # Jobs ship from their own workflows, but their env, secret and forbidden_env contract is
    # declared in this manifest and validated against this state; omitting them retires that check.
    jobs: ConfigDict = {}
    for job_name, raw_job_config in (_as_config_dict(cloud_run.get('jobs')) or {}).items():
        job_config = _as_config_dict(raw_job_config)
        if job_config is None:
            raise ValueError(f'Cloud Run job {job_name} must be a mapping')
        jobs[str(job_name)] = {
            'env': _render_state_env(job_config),
            'flags': _render_flag_values(_as_config_dict(job_config.get('flags')) or {}),
        }
    return {'services': services, 'jobs': jobs}


def _render_state_env(config: ConfigDict) -> list[ConfigDict]:
    return [
        *_render_env_entries(_as_config_dict(config.get('env')) or {}),
        *_render_secret_entries(_as_config_dict(config.get('secrets')) or {}),
    ]


def _render_desktop_backend_state(env_config: ConfigDict) -> ConfigDict:
    """Build sidecar-guard state for desktop-backend from the same manifest values.

    Deliberately separate from _render_cloud_run_state: that file is also read by
    validate-backend-runtime-env.py, which walks cloud_run.services, and
    desktop-backend is not one of those. Keeping them apart means adding this
    guard cannot perturb the backend deploy path.

    The manifest owns only part of desktop-backend's env today, and that is fine:
    attach_cloud_run_gmp_sidecar.py checks the names it is given and ignores the
    rest, so this asserts a real subset rather than nothing.
    """
    desktop_backend = _as_config_dict(env_config.get('desktop_backend')) or {}
    env_entries = _render_env_entries(_as_config_dict(desktop_backend.get('env')) or {})
    return {'services': {'desktop-backend': {'env': env_entries}}}


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

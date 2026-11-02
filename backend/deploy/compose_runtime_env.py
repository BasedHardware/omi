#!/usr/bin/env python3
"""Compose backend/deploy/runtime_env.yaml from base + per-environment overlays."""

from __future__ import annotations

import argparse
import re
import sys
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
_SafeLoader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
ENVIRONMENTS = ('dev', 'prod')
_CLOUD_RUN_SERVICE_ORDER = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
_GKE_SERVICE_ORDER = ('backend-listen', 'parakeet', 'pusher')


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.load(handle, Loader=_SafeLoader)  # noqa: S506 - a SafeLoader (libyaml when available)
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


def compose_environment(
    env: str,
    *,
    base_path: Path = DEFAULT_BASE,
    runtime_env_dir: Path = RUNTIME_ENV_DIR,
) -> ConfigDict:
    """Compose one environment (as it appears under ``environments`` in runtime_env.yaml)."""
    shared = _load_yaml(base_path).get('environment_shared', {})
    return _compose_environment(shared, _load_yaml(_overlay_path(env, runtime_env_dir)), expected_env=env)


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


STAGING_ENV = 'staging'
_STAGING_PLACEHOLDER = re.compile(r'\{(run_url|input):([A-Za-z0-9_-]+)\}')


class StagingComposeError(ValueError):
    """The staging overlay does not fully isolate a prod value; the message names variables, never values."""


def _staging_substitute(value: str, *, run_url_template: str, inputs: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        if kind == 'run_url':
            return run_url_template.format(service=name)
        if name not in inputs:
            raise StagingComposeError(f'staging input {name} is required')
        return inputs[name]

    return _STAGING_PLACEHOLDER.sub(replace, value)


def compose_staging(
    *,
    base_path: Path = DEFAULT_BASE,
    runtime_env_dir: Path = RUNTIME_ENV_DIR,
    inputs: dict[str, str] | None = None,
) -> ConfigDict:
    """Compose staging = prod (with staging projects) + the allowlisted staging transforms (contract (i)).

    Only Cloud Run services are composed here (M1). The result is validated against the staging
    isolation fence; any prod-pointing value left in it raises ``StagingComposeError``.
    """
    inputs = dict(inputs or {})
    staging_doc = _load_yaml(_overlay_path(STAGING_ENV, runtime_env_dir))
    if staging_doc.get('environment') != STAGING_ENV:
        raise StagingComposeError('staging overlay must declare environment: staging')
    base_env = str(staging_doc.get('base_environment', 'prod'))
    prod_doc = _load_yaml(_overlay_path(base_env, runtime_env_dir))
    compute_project = str(staging_doc['compute_project'])
    data_plane_project = str(staging_doc['data_plane_project'])
    shared = _load_yaml(base_path).get('environment_shared', {})
    # ``{env}`` resolves to the base environment: staging runs prod's code paths and values
    # (OMI_ENV_STAGE=prod); its identity is OMI_DEPLOYMENT=staging, not the env placeholder.
    substituted = _substitute_placeholders(
        shared, env=base_env, compute_project=compute_project, data_plane_project=data_plane_project
    )
    merged = cast(
        ConfigDict, _deep_merge(_deep_merge(substituted, prod_doc.get('overlay', {})), staging_doc.get('overlay', {}))
    )

    spec = _as_config_dict(staging_doc.get('cloud_run')) or {}
    run_url_template = str(staging_doc['run_url_template'])
    suffix = str(staging_doc.get('service_suffix', '-staging'))
    service_account = str(staging_doc['service_account'])

    def sub(value: object) -> str:
        return _staging_substitute(str(value), run_url_template=run_url_template, inputs=inputs)

    env_inputs = {name: sub(value) for name, value in (_as_config_dict(spec.get('env_inputs')) or {}).items()}
    env_all = {name: sub(value) for name, value in (_as_config_dict(spec.get('env_all')) or {}).items()}
    # Per-service inputs, like the prod deploy action that hands each service its own handler URL.
    env_inputs_by_service = {
        str(service): {name: sub(value) for name, value in (_as_config_dict(values) or {}).items()}
        for service, values in (_as_config_dict(spec.get('env_inputs_by_service')) or {}).items()
    }
    queue_map = {str(k): str(v) for k, v in (_as_config_dict(spec.get('queue_map')) or {}).items()}
    secret_map = {str(k): str(v) for k, v in (_as_config_dict(spec.get('secret_map')) or {}).items()}
    secret_add = [str(name) for name in spec.get('secret_add') or []]
    scale_flags = {str(k): str(v) for k, v in (_as_config_dict(spec.get('scale_flags')) or {}).items()}
    scale_flags_by_service = {
        str(service): {str(k): str(v) for k, v in (_as_config_dict(values) or {}).items()}
        for service, values in (_as_config_dict(spec.get('scale_flags_by_service')) or {}).items()
    }

    cloud_run = _as_config_dict(merged.get('cloud_run')) or {}
    services_out: ConfigDict = {}
    report: ConfigDict = {'dropped_secrets': {}, 'dropped_env': {}, 'queue_mapped': {}}
    errors: list[str] = []
    for service, raw in (_as_config_dict(cloud_run.get('services')) or {}).items():
        config = cast(ConfigDict, deepcopy(raw))
        env_out: ConfigDict = {}
        dropped_env: list[str] = []
        service_inputs = {**env_inputs, **env_inputs_by_service.get(service, {})}
        for name, raw_entry in (_as_config_dict(config.get('env')) or {}).items():
            entry = dict(_as_config_dict(raw_entry) or {})
            if 'env_var' in entry:
                source = str(entry['env_var'])
                if source in service_inputs:
                    entry = {'value': service_inputs[source], 'category': entry.get('category', 'service_discovery')}
                elif entry.get('provisional'):
                    dropped_env.append(name)
                    continue
                else:
                    errors.append(f'{service}: env {name} reads ${source}, which the staging overlay does not supply')
                    continue
            env_out[name] = entry
        for name, value in env_all.items():
            env_out[name] = {**(_as_config_dict(env_out.get(name)) or {}), 'value': value}
            env_out[name].pop('env_var', None)
        for name, entry in env_out.items():
            if not name.endswith('_QUEUE') or 'value' not in entry:
                continue
            queue = str(entry['value'])
            if queue.startswith('staging-'):
                continue
            if queue not in queue_map:
                errors.append(f'{service}: queue env {name} has no staging mapping')
                continue
            entry['value'] = queue_map[queue]
            report['queue_mapped'].setdefault(service, []).append(name)
        secrets_out: ConfigDict = {}
        dropped: list[str] = []
        secret_names = list((_as_config_dict(config.get('secrets')) or {}).keys())
        for name in secret_names + [n for n in secret_add if n not in secret_names]:
            if name in secret_map:
                secrets_out[name] = {'secret': secret_map[name], 'version': 'latest'}
                env_out.pop(name, None)
            else:
                dropped.append(name)
        if dropped:
            report['dropped_secrets'][service] = sorted(dropped)
        if dropped_env:
            report['dropped_env'][service] = sorted(dropped_env)
        flags = {
            **{str(k): v for k, v in (_as_config_dict(config.get('flags')) or {}).items()},
            **scale_flags,
            **scale_flags_by_service.get(service, {}),
        }
        services_out[service] = {
            'deploy_name': f'{service}{suffix}',
            'url': run_url_template.format(service=service),
            'service_account': service_account,
            'env': env_out,
            'secrets': secrets_out,
            'flags': flags,
            'forbidden_env': list(config.get('forbidden_env') or []),
        }

    composed: ConfigDict = {
        'environment': STAGING_ENV,
        'base_environment': base_env,
        'compute_project': compute_project,
        'data_plane_project': data_plane_project,
        'gcp_project': compute_project,
        'runtime_gcp_project': data_plane_project,
        'region': merged.get('region', 'us-central1'),
        'cloud_run': {
            'network': {
                'flags': {str(k): str(v) for k, v in (_as_config_dict(spec.get('network_flags')) or {}).items()}
            },
            'services': _stabilize_mapping_order(services_out, _CLOUD_RUN_SERVICE_ORDER),
        },
        'staging_report': report,
    }
    errors.extend(staging_fence_errors(composed))
    if errors:
        raise StagingComposeError('staging overlay is not isolated:\n  ' + '\n  '.join(sorted(set(errors))))
    return composed


def staging_fence_errors(composed: ConfigDict) -> list[str]:
    """Run the boot-time staging fence over every composed Cloud Run service's env (names only in errors)."""
    backend_root = str(ROOT / 'backend')
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from utils.staging_fence import staging_violations

    errors: list[str] = []
    services = _as_config_dict(_as_config_dict(composed.get('cloud_run')).get('services')) or {}
    flags = (
        _as_config_dict(_as_config_dict(_as_config_dict(composed.get('cloud_run')).get('network')).get('flags')) or {}
    )
    for service, raw in services.items():
        config = _as_config_dict(raw) or {}
        env = {name: str(entry.get('value', '')) for name, entry in (_as_config_dict(config.get('env')) or {}).items()}
        for name, entry in (_as_config_dict(config.get('secrets')) or {}).items():
            env[f'secret:{name}'] = str(entry.get('secret', ''))
        for name, value in {**flags, **(_as_config_dict(config.get('flags')) or {})}.items():
            env[f'flag:{name}'] = str(value)
        env['flag:service_account'] = str(config.get('service_account', ''))
        env['flag:url'] = str(config.get('url', ''))
        for reason, name in staging_violations(env):
            errors.append(f'{service}: fence {reason} on {name}')
    return errors


class RuntimeEnvDumper(yaml.SafeDumper):
    """Keep small literal rollout entries readable without expanding the manifest."""


def _represent_mapping(dumper, mapping):
    compact = set(mapping) == {'value', 'category'} and mapping['category'] == 'rollout'
    return dumper.represent_mapping('tag:yaml.org,2002:map', mapping, flow_style=compact)


RuntimeEnvDumper.add_representer(dict, _represent_mapping)


def main() -> int:
    parser = argparse.ArgumentParser(description='Compose backend/deploy/runtime_env.yaml from base + overlays.')
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--runtime-env-dir', type=Path, default=RUNTIME_ENV_DIR)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--check', action='store_true', help='exit 1 when output would change')
    parser.add_argument(
        '--env',
        choices=(STAGING_ENV,),
        help='compose only this environment to --output (staging is never written into runtime_env.yaml)',
    )
    parser.add_argument(
        '--input',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='staging input referenced as {input:NAME} in the staging overlay (repeatable)',
    )
    args = parser.parse_args()

    if args.env == STAGING_ENV:
        if args.output == DEFAULT_OUTPUT:
            parser.error('--env staging requires an explicit --output (never runtime_env.yaml)')
        inputs = dict(item.split('=', 1) for item in args.input)
        try:
            staging = compose_staging(base_path=args.base, runtime_env_dir=args.runtime_env_dir, inputs=inputs)
        except StagingComposeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            GENERATED_HEADER.replace('compose_runtime_env.py', 'compose_runtime_env.py --env staging')
            + yaml.dump(staging, Dumper=RuntimeEnvDumper, sort_keys=False, default_flow_style=False, width=120),
            encoding='utf-8',
        )
        print(f'Wrote {args.output}')
        return 0

    manifest = compose_manifest(base_path=args.base, runtime_env_dir=args.runtime_env_dir)
    rendered = GENERATED_HEADER + yaml.dump(
        manifest,
        Dumper=RuntimeEnvDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=120,  # Avoid wrapping compact rollout maps in the oversized generated manifest.
    )
    if args.check:
        current = args.output.read_text(encoding='utf-8') if args.output.exists() else ''
        if current != rendered:
            print(f'{args.output} is out of date; run compose_runtime_env.py', file=sys.stderr)
            return 1
        print(f'{args.output} is up to date')
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding='utf-8')
    print(f'Wrote {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

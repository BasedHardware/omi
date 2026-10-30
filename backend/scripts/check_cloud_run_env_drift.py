#!/usr/bin/env python3
"""Read-only operator check for live Cloud Run env keys missing from runtime_env.yaml.

Lists only environment variable key names (never values or secret contents)
present on live Cloud Run services that are absent from the rendered manifest,
separating explicitly allowlisted live-managed keys from unallowlisted drift.

By default this script is a non-blocking visibility report (exits 0); pass
--strict to exit 1 when unallowlisted drift or fetch errors are present.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_backend_runtime_env  # noqa: E402
from attach_cloud_run_gmp_sidecar import SIDECAR_NAME  # noqa: E402
from runtime_env_validation.common import compute_project  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')

# Keys intentionally set outside backend/deploy/runtime_env.yaml (for example,
# per-revision provenance markers, sidecar ports attached post-deploy, or
# live-managed canary UID allowlists that must not live in the public repo).
LIVE_MANAGED_ENV_ALLOWLIST: dict[str, frozenset[str]] = {
    '*': frozenset(
        {
            'BATCH_PIPELINE_UID_ALLOWLIST',
        }
    ),
    'backend': frozenset(
        {
            'OMI_BACKEND_RELEASE_SHA',
        }
    ),
    'backend-sync': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-sync-backfill': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-integration': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
        }
    ),
}


@dataclass(frozen=True)
class ServiceEnvDrift:
    service: str
    manifest_key_count: int
    live_key_count: int
    allowlisted_live_only: tuple[str, ...]
    unallowlisted_live_only: tuple[str, ...]
    error: str | None = None


def allowlist_for_service(
    service: str,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
) -> frozenset[str]:
    return allowlist_map.get('*', frozenset()) | allowlist_map.get(service, frozenset())


def load_allowlist_file(path: Path) -> dict[str, frozenset[str]]:
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError(f'{path} must contain a mapping of service name (or "*") to key lists')
    merged: dict[str, set[str]] = {key: set(values) for key, values in LIVE_MANAGED_ENV_ALLOWLIST.items()}
    for scope, keys in raw.items():
        if not isinstance(scope, str) or not isinstance(keys, list) or not all(isinstance(k, str) and k for k in keys):
            raise ValueError(f'{path}: allowlist entry for {scope!r} must be a list of non-empty key names')
        merged.setdefault(scope, set()).update(keys)
    return {scope: frozenset(names) for scope, names in merged.items()}


def declared_manifest_keys(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
) -> tuple[str, str, dict[str, frozenset[str]]]:
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest.get('environments')) or {}
    env_config = render_backend_runtime_env._as_config_dict(environments.get(env))
    if env_config is None:
        raise ValueError(f'Missing {env!r} environment in {manifest_path}')
    project = compute_project(env_config)
    region = str(env_config.get('region') or DEFAULT_REGION)
    cloud_run = render_backend_runtime_env._as_config_dict(env_config.get('cloud_run')) or {}
    services = render_backend_runtime_env._as_config_dict(cloud_run.get('services')) or {}

    rendered_services: dict[str, Any] = {}
    if rendered_state_path is not None and rendered_state_path.is_file():
        loaded_state = json.loads(rendered_state_path.read_text(encoding='utf-8'))
        if isinstance(loaded_state, dict) and isinstance(loaded_state.get('services'), dict):
            rendered_services = loaded_state['services']

    declared: dict[str, frozenset[str]] = {}
    for service_name, raw_service_config in services.items():
        service_config = render_backend_runtime_env._as_config_dict(raw_service_config) or {}
        env_map = render_backend_runtime_env._as_config_dict(service_config.get('env')) or {}
        secrets_map = render_backend_runtime_env._as_config_dict(service_config.get('secrets')) or {}
        names = {str(k) for k in env_map} | {str(k) for k in secrets_map}
        rendered_service = render_backend_runtime_env._as_config_dict(rendered_services.get(service_name)) or {}
        for entry in rendered_service.get('env', []) or []:
            if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']:
                names.add(entry['name'])
        declared[str(service_name)] = frozenset(names)
    return project, region, declared


def _extract_application_env_names(document: Mapping[str, Any], *, service: str) -> frozenset[str]:
    """Extract only env variable names from the application container; never read values."""
    if isinstance(document.get('env'), list):
        env_entries = document['env']
    else:
        spec = document.get('spec')
        template = spec.get('template') if isinstance(spec, dict) else None
        template_spec = template.get('spec') if isinstance(template, dict) else None
        containers = template_spec.get('containers') if isinstance(template_spec, dict) else None
        if not isinstance(containers, list):
            raise ValueError(f'Cloud Run service {service} has no containers list')
        app_containers = [c for c in containers if isinstance(c, dict) and c.get('name') != SIDECAR_NAME]
        if len(app_containers) != 1:
            raise ValueError(
                f'Cloud Run service {service} expected 1 application container, found {len(app_containers)}'
            )
        env_entries = app_containers[0].get('env', [])
    if not isinstance(env_entries, list):
        raise ValueError(f'Cloud Run service {service} env must be a list')
    return frozenset(
        entry['name']
        for entry in env_entries
        if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']
    )


def _describe_service_env_names(
    *,
    service: str,
    project: str,
    region: str,
    runner: Any = subprocess.run,
) -> frozenset[str]:
    result = runner(
        [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    document = json.loads(result.stdout)
    if not isinstance(document, dict):
        raise ValueError(f'Cloud Run service {service} describe did not return a JSON object')
    return _extract_application_env_names(document, service=service)


def inspect_services_drift(
    *,
    env: str,
    services: Sequence[str] = DEFAULT_SERVICES,
    project: str | None = None,
    region: str | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
    cloud_run_state: Mapping[str, Any] | None = None,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
    runner: Any = subprocess.run,
) -> tuple[str, str, tuple[ServiceEnvDrift, ...]]:
    manifest_project, manifest_region, declared_by_service = declared_manifest_keys(
        env=env,
        manifest_path=manifest_path,
        rendered_state_path=rendered_state_path,
    )
    resolved_project = project or manifest_project
    resolved_region = region or manifest_region

    state_services: Mapping[str, Any] | None = None
    if cloud_run_state is not None:
        raw_services = cloud_run_state.get('services') if isinstance(cloud_run_state, Mapping) else None
        state_services = raw_services if isinstance(raw_services, Mapping) else cloud_run_state

    results: list[ServiceEnvDrift] = []
    for service in services:
        if service not in declared_by_service:
            raise ValueError(f'Service {service!r} is not declared in {manifest_path} for env {env!r}')
        declared = declared_by_service[service]
        allowed = allowlist_for_service(service, allowlist_map)
        try:
            if state_services is not None:
                service_doc = state_services.get(service)
                if not isinstance(service_doc, Mapping):
                    raise ValueError(f'Missing service {service!r} in offline Cloud Run state')
                live_names = _extract_application_env_names(service_doc, service=service)
            else:
                live_names = _describe_service_env_names(
                    service=service,
                    project=resolved_project,
                    region=resolved_region,
                    runner=runner,
                )
        except Exception as exc:
            results.append(
                ServiceEnvDrift(
                    service=service,
                    manifest_key_count=len(declared),
                    live_key_count=0,
                    allowlisted_live_only=(),
                    unallowlisted_live_only=(),
                    error=str(exc),
                )
            )
            continue

        missing_from_manifest = live_names - declared
        allowlisted = tuple(sorted(missing_from_manifest & allowed))
        unallowlisted = tuple(sorted(missing_from_manifest - allowed))
        results.append(
            ServiceEnvDrift(
                service=service,
                manifest_key_count=len(declared),
                live_key_count=len(live_names),
                allowlisted_live_only=allowlisted,
                unallowlisted_live_only=unallowlisted,
            )
        )
    return resolved_project, resolved_region, tuple(results)


def render_markdown_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    lines = [
        f'## Cloud Run runtime env manifest drift ({env} / `{project}` / `{region}`)',
        '',
        'Read-only key-name comparison between live Cloud Run application containers and `backend/deploy/runtime_env.yaml` (values redacted).',
        '',
        '| Service | Manifest keys | Live keys | Allowlisted live-only | Unallowlisted live-only (drift) | Status |',
        '| --- | ---: | ---: | ---: | ---: | --- |',
    ]
    for item in results:
        if item.error:
            status = f'ERROR ({item.error})'
        elif item.unallowlisted_live_only:
            status = 'DRIFT'
        else:
            status = 'OK'
        lines.append(
            f'| `{item.service}` | {item.manifest_key_count} | {item.live_key_count} | '
            f'{len(item.allowlisted_live_only)} | {len(item.unallowlisted_live_only)} | {status} |'
        )
    lines.append('')
    for item in results:
        lines.append(f'### `{item.service}`')
        if item.error:
            lines.append(f'- Fetch error: `{item.error}`')
            lines.append('')
            continue
        allowlisted_str = ', '.join(f'`{name}`' for name in item.allowlisted_live_only) or 'none'
        lines.append(f'- Allowlisted live-managed keys ({len(item.allowlisted_live_only)}): {allowlisted_str}')
        if item.unallowlisted_live_only:
            drift_str = ', '.join(f'`{name}`' for name in item.unallowlisted_live_only)
            lines.append(
                f'- Unallowlisted live keys missing from manifest ({len(item.unallowlisted_live_only)}): {drift_str}'
            )
        else:
            lines.append('- Unallowlisted live keys missing from manifest (0): none')
        lines.append('')
    return '\n'.join(lines)


def render_json_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    payload = {
        'env': env,
        'project': project,
        'region': region,
        'services': {
            item.service: {
                'manifest_key_count': item.manifest_key_count,
                'live_key_count': item.live_key_count,
                'allowlisted_live_only': list(item.allowlisted_live_only),
                'unallowlisted_live_only': list(item.unallowlisted_live_only),
                **({'error': item.error} if item.error else {}),
            }
            for item in results
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', choices=('dev', 'prod'), default='prod')
    parser.add_argument('--project', help='GCP project ID (defaults to manifest compute_project for --env).')
    parser.add_argument('--region', help='Cloud Run region (defaults to manifest region for --env).')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--rendered-state',
        type=Path,
        help='Optional state JSON from render_backend_runtime_env.py --state-output.',
    )
    parser.add_argument(
        '--cloud-run-state',
        type=Path,
        help='Offline Cloud Run state JSON fixture for hermetic tests.',
    )
    parser.add_argument(
        '--allowlist-file',
        type=Path,
        help='Optional YAML/JSON file extending the live-managed key allowlist.',
    )
    parser.add_argument('--service', action='append', dest='services', help='Cloud Run service name (repeatable).')
    parser.add_argument('--format', choices=('markdown', 'json'), default='markdown')
    parser.add_argument(
        '--summary-file', type=Path, help='Append markdown report to this file (e.g. GITHUB_STEP_SUMMARY).'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit 1 if any service has unallowlisted live keys missing from the manifest or a fetch error.',
    )
    args = parser.parse_args(argv)

    allowlist_map = load_allowlist_file(args.allowlist_file) if args.allowlist_file else LIVE_MANAGED_ENV_ALLOWLIST
    offline_state = (
        cast(Mapping[str, Any], json.loads(args.cloud_run_state.read_text(encoding='utf-8')))
        if args.cloud_run_state
        else None
    )
    services = tuple(args.services or DEFAULT_SERVICES)

    project, region, results = inspect_services_drift(
        env=args.env,
        services=services,
        project=args.project,
        region=args.region,
        manifest_path=args.manifest,
        rendered_state_path=args.rendered_state,
        cloud_run_state=offline_state,
        allowlist_map=allowlist_map,
    )

    markdown = render_markdown_report(env=args.env, project=project, region=region, results=results)
    if args.format == 'json':
        sys.stdout.write(render_json_report(env=args.env, project=project, region=region, results=results))
    else:
        sys.stdout.write(markdown)

    if args.summary_file is not None:
        try:
            with args.summary_file.open('a', encoding='utf-8') as handle:
                handle.write(markdown)
                if not markdown.endswith('\n'):
                    handle.write('\n')
        except OSError as exc:
            print(f'WARNING: could not write summary file {args.summary_file}: {exc}', file=sys.stderr)

    if args.strict and any(item.unallowlisted_live_only or item.error for item in results):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

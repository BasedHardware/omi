#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-integration')


@dataclass(frozen=True)
class SecretBinding:
    env_name: str
    secret_name: str
    version: str


def main() -> int:
    parser = argparse.ArgumentParser(description='Preflight checks for backend Cloud Run deploys.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--service', action='append', dest='services')
    parser.add_argument('--check-secrets', action='store_true')
    parser.add_argument('--check-traffic', action='store_true')
    parser.add_argument('--repair-traffic', action='store_true')
    parser.add_argument('--wait-revision-ready', action='append', metavar='SERVICE=REVISION')
    parser.add_argument('--timeout-seconds', type=int, default=600)
    parser.add_argument('--poll-interval-seconds', type=float, default=5.0)
    args = parser.parse_args()

    services = tuple(args.services or DEFAULT_SERVICES)
    exit_code = 0

    if args.check_secrets:
        missing = check_rendered_secrets(
            env=args.env,
            manifest_path=args.manifest,
            project=args.project,
        )
        if missing:
            for item in missing:
                print(
                    f'ERROR [secret/{item.env_name}]: Secret Manager secret {item.secret_name!r} not found',
                    file=sys.stderr,
                )
            exit_code = 1
        else:
            print(f'secret preflight passed for {args.env}')

    if args.check_traffic or args.repair_traffic:
        repair_module = _load_repair_module()
        results = repair_module.repair_live(
            project=args.project,
            region=args.region,
            services=services,
            repair=args.repair_traffic,
        )
        for result in results:
            print(repair_module._format_result(result))
            if result.action == 'failed':
                exit_code = 1

    if args.wait_revision_ready:
        targets = _parse_revision_targets(args.wait_revision_ready)
        for service, revision in targets.items():
            if not wait_revision_ready(
                project=args.project,
                region=args.region,
                service=service,
                revision=revision,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            ):
                print(f'ERROR [revision/{service}]: {revision} did not become Ready=True', file=sys.stderr)
                exit_code = 1

    return exit_code


def check_rendered_secrets(*, env: str, manifest_path: Path, project: str) -> list[SecretBinding]:
    render_module = _load_render_module()
    manifest = render_module._load_yaml(manifest_path)
    environments = render_module._as_config_dict(manifest['environments']) or {}
    env_config = render_module._as_config_dict(environments[env]) or {}
    cloud_run = render_module._as_config_dict(env_config['cloud_run']) or {}
    service_configs = render_module._as_config_dict(cloud_run.get('services')) or {}

    missing: list[SecretBinding] = []
    seen: set[tuple[str, str]] = set()
    for raw_service_config in service_configs.values():
        service_config = render_module._as_config_dict(raw_service_config) or {}
        secret_entries = render_module._as_config_dict(service_config.get('secrets')) or {}
        for env_name, raw_entry in secret_entries.items():
            entry = render_module._as_config_dict(raw_entry)
            if entry is None or 'secret' not in entry:
                continue
            binding = SecretBinding(
                env_name=str(env_name),
                secret_name=str(entry['secret']),
                version=str(entry.get('version', 'latest')),
            )
            key = (binding.secret_name, binding.version)
            if key in seen:
                continue
            seen.add(key)
            if not _secret_exists(project=project, secret_name=binding.secret_name, version=binding.version):
                missing.append(binding)
    return missing


def wait_revision_ready(
    *,
    project: str,
    region: str,
    service: str,
    revision: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ready, reason = _revision_ready_state(project=project, region=region, revision=revision)
        if ready:
            print(f'{service}: revision {revision} is Ready=True')
            return True
        time.sleep(poll_interval_seconds)
    ready, reason = _revision_ready_state(project=project, region=region, revision=revision)
    print(f'{service}: revision {revision} ready={ready} reason={reason or "unknown"}', file=sys.stderr)
    return False


def _revision_ready_state(*, project: str, region: str, revision: str) -> tuple[bool, str | None]:
    command = [
        'gcloud',
        'run',
        'revisions',
        'describe',
        revision,
        f'--project={project}',
        f'--region={region}',
        '--format=json',
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return False, f'describe failed with exit code {result.returncode}'
    import json

    revision_doc = cast(dict[str, Any], json.loads(result.stdout))
    conditions = cast(list[Any], revision_doc.get('status', {}).get('conditions') or [])
    ready_condition = next(
        (cast(dict[str, Any], condition) for condition in conditions if condition.get('type') == 'Ready'),
        None,
    )
    if ready_condition is None:
        return False, 'Ready condition missing'
    status = str(ready_condition.get('status') or '')
    reason = ready_condition.get('reason')
    return status == 'True', str(reason) if reason else None


def _secret_exists(*, project: str, secret_name: str, version: str) -> bool:
    describe = subprocess.run(
        ['gcloud', 'secrets', 'describe', secret_name, f'--project={project}', '--format=value(name)'],
        check=False,
        capture_output=True,
        text=True,
    )
    if describe.returncode != 0:
        return False
    if version == 'latest':
        versions = subprocess.run(
            [
                'gcloud',
                'secrets',
                'versions',
                'list',
                secret_name,
                f'--project={project}',
                '--filter=state:ENABLED',
                '--format=value(name)',
                '--limit=1',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return versions.returncode == 0 and bool(versions.stdout.strip())
    version_result = subprocess.run(
        [
            'gcloud',
            'secrets',
            'versions',
            'describe',
            version,
            f'--secret={secret_name}',
            f'--project={project}',
            '--format=value(state)',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return version_result.returncode == 0 and version_result.stdout.strip() == 'ENABLED'


def _parse_revision_targets(entries: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        if '=' not in entry:
            raise ValueError(f'revision target must be SERVICE=REVISION: {entry}')
        service, revision = entry.split('=', 1)
        result[service.strip()] = revision.strip()
    return result


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_render_module():
    return _load_module('render_backend_runtime_env', ROOT / 'backend/scripts/render-backend-runtime-env.py')


def _load_repair_module():
    return _load_module('repair_cloud_run_traffic', ROOT / 'backend/scripts/repair_cloud_run_traffic.py')


if __name__ == '__main__':
    os.chdir(ROOT)
    raise SystemExit(main())

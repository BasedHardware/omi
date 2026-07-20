#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_backend_runtime_env  # noqa: E402
import repair_cloud_run_traffic  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@dataclass(frozen=True)
class SecretBinding:
    env_name: str
    secret_name: str
    version: str


@dataclass(frozen=True)
class RuntimeBindingContract:
    """Expected pre-candidate Cloud Run binding state for one service."""

    public_names: frozenset[str]
    secret_references: dict[str, str]


def main() -> int:
    parser = argparse.ArgumentParser(description='Preflight checks for backend Cloud Run deploys.')
    parser.add_argument('--env', choices=('dev', 'beta', 'prod'), required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--service', action='append', dest='services')
    parser.add_argument('--migrate-legacy-public-binding', action='append', dest='legacy_public_binding_services')
    parser.add_argument('--check-runtime-bindings', action='store_true')
    parser.add_argument('--check-secrets', action='store_true')
    parser.add_argument('--check-traffic', action='store_true')
    parser.add_argument('--repair-traffic', action='store_true')
    parser.add_argument('--wait-revision-ready', action='append', metavar='SERVICE=REVISION')
    parser.add_argument('--timeout-seconds', type=int, default=600)
    parser.add_argument('--poll-interval-seconds', type=float, default=5.0)
    args = parser.parse_args()

    services = tuple(args.services or DEFAULT_SERVICES)
    exit_code = 0

    if args.legacy_public_binding_services:
        try:
            migrated = migrate_legacy_public_bindings(
                services=args.legacy_public_binding_services,
                env=args.env,
                project=args.project,
                region=args.region,
                manifest_path=args.manifest,
            )
        except ValueError as exc:
            parser.error(str(exc))
        for service in migrated:
            print(f'migrated legacy GOOGLE_CLIENT_ID binding for {service}')

    if args.check_runtime_bindings:
        try:
            drift = check_runtime_bindings(
                services=services,
                env=args.env,
                project=args.project,
                region=args.region,
                manifest_path=args.manifest,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if drift:
            for error in drift:
                print(f'ERROR [{error}]', file=sys.stderr)
            exit_code = 1
        else:
            print('development Cloud Run runtime-binding contract passed')

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
        results = repair_cloud_run_traffic.repair_live(
            project=args.project,
            region=args.region,
            services=services,
            repair=args.repair_traffic,
        )
        for result in results:
            print(repair_cloud_run_traffic._format_result(result))
            if result.action == 'failed':
                exit_code = 1

    if args.wait_revision_ready:
        try:
            targets = _parse_revision_targets(args.wait_revision_ready)
        except ValueError as exc:
            parser.error(str(exc))
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


DEVELOPMENT_PROJECT = 'based-hardware-dev'


def migrate_legacy_public_bindings(
    *,
    services: tuple[str, ...] | list[str],
    env: str,
    project: str,
    region: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    runner: Any = subprocess.run,
) -> list[str]:
    _require_manifest_scope(
        env=env, project=project, manifest_path=manifest_path, check_name='Legacy public-binding migration'
    )
    service_configs = _cloud_run_service_configs(env=env, manifest_path=manifest_path)

    migrated: list[str] = []
    for service in services:
        service_config = service_configs.get(service)
        if not isinstance(service_config, dict):
            raise ValueError(f'Missing Cloud Run service config for {service}')
        public_env = service_config.get('env')
        if not isinstance(public_env, dict):
            raise ValueError(f'Missing public environment config for {service}')
        public_binding_names = set(public_env)
        document = _describe_cloud_run_service(service=service, project=project, region=region, runner=runner)
        containers = _single_container(document, operation='Legacy public-binding migration')
        legacy_binding_names = sorted(
            entry['name']
            for entry in _container_env_entries(containers, operation='Legacy public-binding migration')
            if isinstance(entry, dict)
            and entry.get('name') in public_binding_names
            and entry.get('valueFrom', {}).get('secretKeyRef', {}).get('name') == entry.get('name')
        )
        if not legacy_binding_names:
            continue
        runner(
            [
                'gcloud',
                'run',
                'services',
                'update',
                service,
                f'--project={project}',
                f'--region={region}',
                f'--remove-secrets={",".join(legacy_binding_names)}',
                '--no-traffic',
                '--quiet',
            ],
            check=True,
        )
        migrated.append(service)
    return migrated


def check_runtime_bindings(
    *,
    services: tuple[str, ...] | list[str],
    env: str,
    project: str,
    region: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    runner: Any = subprocess.run,
) -> list[str]:
    """Check only manifest-declared development bindings before candidate deploy.

    The workflow removes legacy Secret Manager bindings for public values before
    it deploys the candidate revision.  At this point a declared public value
    is therefore valid when it is literal or absent; a Secret Manager or other
    value source is still drift.  Declared secrets must already match exactly.
    This is deliberately not a full live-service inventory: normal retained
    Cloud Run bindings absent from runtime_env.yaml are outside this check.
    """
    _require_development_scope(env=env, project=project, check_name='Runtime binding check')
    service_configs = _cloud_run_service_configs(env=env, manifest_path=manifest_path)
    drift: list[str] = []

    for service in services:
        raw_service_config = service_configs.get(service)
        service_config = render_backend_runtime_env._as_config_dict(raw_service_config)
        if service_config is None:
            raise ValueError(f'Missing Cloud Run service config for {service}')
        expected = _expected_runtime_bindings(service=service, service_config=service_config)
        declared_names = expected.public_names | set(expected.secret_references)
        document = _describe_cloud_run_service(service=service, project=project, region=region, runner=runner)
        container = _single_container(document, operation='Runtime binding check')
        actual = _actual_runtime_bindings(
            service=service,
            env_entries=_container_env_entries(container, operation='Runtime binding check'),
            declared_names=declared_names,
            drift=drift,
        )

        for env_name in sorted(expected.public_names):
            observed_binding = actual.get(env_name)
            if observed_binding not in (None, 'public literal'):
                drift.append(
                    f'runtime-binding/{service}/{env_name}: expected public literal or absent before candidate deploy, '
                    f'observed {observed_binding}'
                )

        for env_name in sorted(expected.secret_references):
            expected_binding = expected.secret_references[env_name]
            observed_binding = actual.get(env_name)
            if observed_binding is None:
                drift.append(f'runtime-binding/{service}/{env_name}: expected {expected_binding}, binding is missing')
            elif observed_binding != expected_binding:
                drift.append(
                    f'runtime-binding/{service}/{env_name}: expected {expected_binding}, observed {observed_binding}'
                )

    return drift


def _require_development_scope(*, env: str, project: str, check_name: str) -> None:
    if env != 'dev' or project != DEVELOPMENT_PROJECT:
        raise ValueError(f'{check_name} is development-only')


def _require_manifest_scope(*, env: str, project: str, manifest_path: Path, check_name: str) -> None:
    """Bind an operation to the project the manifest declares for `env`.

    Migration is value-preserving but rewrites live service bindings, so the
    caller must not be able to aim one environment's contract at another's
    project.
    """
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest.get('environments'))
    if environments is None:
        raise ValueError(f'Missing environments in {manifest_path}')
    environment_config = render_backend_runtime_env._as_config_dict(environments.get(env))
    if environment_config is None:
        raise ValueError(f'{check_name} has no {env} environment in {manifest_path}')
    expected_project = environment_config.get('gcp_project')
    if project != expected_project:
        raise ValueError(f'{check_name} for {env} expects project {expected_project!r}, got {project!r}')


def _cloud_run_service_configs(*, env: str, manifest_path: Path) -> dict[str, Any]:
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest.get('environments'))
    if environments is None:
        raise ValueError(f'Missing environments in {manifest_path}')
    environment_config = render_backend_runtime_env._as_config_dict(environments.get(env))
    if environment_config is None:
        raise ValueError(f'Missing {env} environment in {manifest_path}')
    cloud_run = render_backend_runtime_env._as_config_dict(environment_config.get('cloud_run'))
    if cloud_run is None:
        raise ValueError(f'Missing Cloud Run config for {env} in {manifest_path}')
    service_configs = render_backend_runtime_env._as_config_dict(cloud_run.get('services'))
    if service_configs is None:
        raise ValueError(f'Missing Cloud Run services for {env} in {manifest_path}')
    return service_configs


def _expected_runtime_bindings(*, service: str, service_config: dict[str, Any]) -> RuntimeBindingContract:
    public_env = render_backend_runtime_env._as_config_dict(service_config.get('env')) or {}
    secrets = render_backend_runtime_env._as_config_dict(service_config.get('secrets')) or {}
    public_names = frozenset(str(env_name) for env_name in public_env)
    secret_names = {str(env_name) for env_name in secrets}
    overlap = sorted(public_names & secret_names)
    if overlap:
        raise ValueError(f'Cloud Run service {service} has public/secret binding overlap: {", ".join(overlap)}')

    secret_references: dict[str, str] = {}
    for env_name, raw_secret in secrets.items():
        secret = render_backend_runtime_env._as_config_dict(raw_secret)
        if secret is None or not isinstance(secret.get('secret'), str) or not secret['secret']:
            raise ValueError(f'Cloud Run secret binding {env_name} must have a secret entry')
        secret_references[str(env_name)] = (
            f'Secret Manager reference {secret["secret"]}:{secret.get("version", "latest")}'
        )
    return RuntimeBindingContract(public_names=public_names, secret_references=secret_references)


def _describe_cloud_run_service(*, service: str, project: str, region: str, runner: Any) -> dict[str, Any]:
    document = json.loads(
        runner(
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
        ).stdout
    )
    if not isinstance(document, dict):
        raise ValueError(f'Cloud Run service {service} describe did not return a mapping')
    return cast(dict[str, Any], document)


def _single_container(document: dict[str, Any], *, operation: str) -> dict[str, Any]:
    spec = document.get('spec')
    template = spec.get('template') if isinstance(spec, dict) else None
    template_spec = template.get('spec') if isinstance(template, dict) else None
    containers = template_spec.get('containers') if isinstance(template_spec, dict) else None
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise ValueError(f'{operation} requires exactly one container per Cloud Run service')
    return cast(dict[str, Any], containers[0])


def _container_env_entries(container: dict[str, Any], *, operation: str) -> list[Any]:
    env_entries = container.get('env', [])
    if not isinstance(env_entries, list):
        raise ValueError(f'{operation} requires a list of Cloud Run environment bindings')
    return env_entries


def _actual_runtime_bindings(
    *, service: str, env_entries: list[Any], declared_names: set[str] | frozenset[str], drift: list[str]
) -> dict[str, str]:
    actual: dict[str, str] = {}
    for entry in env_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not entry['name']:
            continue
        env_name = entry['name']
        if env_name not in declared_names:
            continue
        if env_name in actual:
            drift.append(f'runtime-binding/{service}/{env_name}: duplicate Cloud Run environment binding')
            continue
        actual[env_name] = _observed_binding(entry)
    return actual


def _observed_binding(entry: dict[str, Any]) -> str:
    if 'value' in entry:
        return 'public literal'
    value_from = entry.get('valueFrom')
    secret_ref = value_from.get('secretKeyRef') if isinstance(value_from, dict) else None
    secret_name = secret_ref.get('name') if isinstance(secret_ref, dict) else None
    if isinstance(secret_name, str) and secret_name:
        version = secret_ref.get('key', 'latest')
        return f'Secret Manager reference {secret_name}:{version}'
    return 'unsupported value source'


def check_rendered_secrets(*, env: str, manifest_path: Path, project: str) -> list[SecretBinding]:
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest['environments']) or {}
    env_config = render_backend_runtime_env._as_config_dict(environments[env]) or {}
    cloud_run = render_backend_runtime_env._as_config_dict(env_config['cloud_run']) or {}
    service_configs = render_backend_runtime_env._as_config_dict(cloud_run.get('services')) or {}

    missing: list[SecretBinding] = []
    seen: set[tuple[str, str]] = set()
    for raw_service_config in service_configs.values():
        service_config = render_backend_runtime_env._as_config_dict(raw_service_config) or {}
        secret_entries = render_backend_runtime_env._as_config_dict(service_config.get('secrets')) or {}
        for env_name, raw_entry in secret_entries.items():
            entry = render_backend_runtime_env._as_config_dict(raw_entry)
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
        service = service.strip()
        revision = revision.strip()
        if not service or not revision:
            raise ValueError(f'revision target must include non-empty SERVICE and REVISION: {entry}')
        result[service] = revision
    return result


if __name__ == '__main__':
    os.chdir(ROOT)
    raise SystemExit(main())

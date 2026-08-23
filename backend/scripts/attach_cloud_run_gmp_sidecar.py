#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Attach the pinned GMP sidecar to an already-created zero-traffic revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence, cast

import yaml

SIDECAR_IMAGE = (
    'us-docker.pkg.dev/cloud-ops-agents-artifacts/cloud-run-gmp-sidecar/'
    'cloud-run-gmp-sidecar@sha256:f782d8c67ad3f0e54d791fbf7cc6c8d36bc9e15c4b68d8b38ef372674defe452'
)
SIDECAR_NAME = 'collector'
CONFIG_VOLUME_NAME = 'cloud-run-gmp-config'

ConfigDict = dict[str, Any]


def _run(args: Sequence[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        text=True,
        capture_output=capture_output,
    )


def _check(result: subprocess.CompletedProcess[str], *, action: str) -> str:
    if result.returncode != 0:
        detail = (result.stderr or '').strip()
        raise RuntimeError(f'{action} failed: {detail or "gcloud returned a non-zero exit code"}')
    return result.stdout or ''


def _project_number(project: str) -> str:
    """Resolve a project to its number for the run.googleapis.com/secrets annotation.

    gcloud parses that annotation with `^projects/[0-9]{1,19}/secrets/...`, so a
    project ID in the path makes every later `gcloud run deploy` on the service
    crash with "Invalid secret path". Cloud Run itself accepts either form, so
    the breakage only surfaces on the next deploy, not on the attach.
    """
    if project.isdigit():
        return project
    result = _run(
        [
            'gcloud',
            'projects',
            'describe',
            project,
            '--format=value(projectNumber)',
        ],
        capture_output=True,
    )
    number = _check(result, action=f'resolving the {project} project number').strip()
    if not number.isdigit():
        raise RuntimeError(f'project number for {project} was not numeric')
    return number


def _latest_secret_version(*, project: str, secret: str) -> str:
    result = _run(
        [
            'gcloud',
            'secrets',
            'versions',
            'describe',
            'latest',
            f'--secret={secret}',
            '--project',
            project,
            '--format=value(name)',
        ],
        capture_output=True,
    )
    resource = _check(result, action=f'reading the latest {secret} version').strip()
    version = resource.rsplit('/', 1)[-1]
    if not version.isdigit():
        raise RuntimeError(f'latest {secret} version was not numeric')
    return version


def ensure_config_secret(*, project: str, secret: str, config_path: Path) -> str:
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:63]
    describe = _run(
        ['gcloud', 'secrets', 'describe', secret, '--project', project, '--format=json'],
        capture_output=True,
    )
    if describe.returncode != 0:
        create = _run(
            [
                'gcloud',
                'secrets',
                'create',
                secret,
                '--project',
                project,
                '--replication-policy=automatic',
                f'--data-file={config_path}',
                f'--labels=config-sha={config_hash}',
            ],
            capture_output=True,
        )
        if create.returncode == 0:
            return _latest_secret_version(project=project, secret=secret)
        # Backend and desktop deploy in separate concurrency groups and can
        # both create this shared secret on the first rollout. Treat a
        # concurrent successful create as success, but preserve the original
        # create failure when the secret still cannot be read.
        describe = _run(
            ['gcloud', 'secrets', 'describe', secret, '--project', project, '--format=json'],
            capture_output=True,
        )
        if describe.returncode != 0:
            _check(create, action=f'creating {secret}')

    metadata = json.loads(describe.stdout)
    if metadata.get('labels', {}).get('config-sha') == config_hash:
        return _latest_secret_version(project=project, secret=secret)
    add_version = _run(
        [
            'gcloud',
            'secrets',
            'versions',
            'add',
            secret,
            '--project',
            project,
            f'--data-file={config_path}',
        ],
        capture_output=True,
    )
    _check(add_version, action=f'adding a version to {secret}')
    update = _run(
        [
            'gcloud',
            'secrets',
            'update',
            secret,
            '--project',
            project,
            f'--update-labels=config-sha={config_hash}',
        ],
        capture_output=True,
    )
    _check(update, action=f'labelling {secret}')
    return _latest_secret_version(project=project, secret=secret)


def _cloud_run_string(value: object) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _normalize_string_mapping(raw: object) -> None:
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        raw[key] = _cloud_run_string(value)


def _merge_secret_annotation(existing: object, *, project_number: str, secret: str) -> str:
    entries: dict[str, str] = {}
    if isinstance(existing, str):
        for raw_entry in existing.split(','):
            name, separator, resource = raw_entry.strip().partition(':')
            if name and separator and resource:
                entries[name] = resource
    entries[secret] = f'projects/{project_number}/secrets/{secret}'
    return ','.join(f'{name}:{resource}' for name, resource in sorted(entries.items()))


def _merge_container_dependencies(existing: object, *, ingress_container_name: str) -> str:
    dependencies: dict[str, list[str]] = {}
    if isinstance(existing, str) and existing.strip():
        try:
            parsed = json.loads(existing)
        except json.JSONDecodeError as exc:
            raise ValueError('container-dependencies annotation was not valid JSON') from exc
        if not isinstance(parsed, dict) or not all(
            isinstance(name, str) and isinstance(required, list) and all(isinstance(item, str) for item in required)
            for name, required in parsed.items()
        ):
            raise ValueError('container-dependencies annotation had an unexpected shape')
        dependencies.update(cast(dict[str, list[str]], parsed))
    dependencies[SIDECAR_NAME] = [ingress_container_name]
    return json.dumps(dependencies, separators=(',', ':'), sort_keys=True)


def patch_service(
    service: Mapping[str, Any],
    *,
    project_number: str,
    base_revision: str,
    latest_created_revision: str,
    final_revision: str,
    ingress_container_name: str,
    config_secret: str,
    config_secret_version: str,
) -> ConfigDict:
    patched = cast(ConfigDict, json.loads(json.dumps(service)))
    patched.pop('status', None)
    metadata = cast(ConfigDict, patched.setdefault('metadata', {}))
    for field in ('creationTimestamp', 'generation', 'resourceVersion', 'selfLink', 'uid'):
        metadata.pop(field, None)
    _normalize_string_mapping(metadata.get('labels'))
    metadata_annotations = cast(ConfigDict, metadata.setdefault('annotations', {}))
    _normalize_string_mapping(metadata_annotations)
    metadata_annotations['run.googleapis.com/launch-stage'] = 'ALPHA'

    spec = cast(ConfigDict, patched['spec'])
    for traffic in cast(list[ConfigDict], spec.get('traffic', [])):
        if traffic.get('latestRevision') and int(traffic.get('percent', 0)) > 0:
            raise ValueError('zero-traffic attachment refuses a service whose traffic follows latestRevision')

    template = cast(ConfigDict, spec['template'])
    template_metadata = cast(ConfigDict, template.setdefault('metadata', {}))
    if latest_created_revision != base_revision:
        raise ValueError(f'expected base revision {base_revision!r}, found {latest_created_revision!r}')
    template_metadata['name'] = final_revision
    _normalize_string_mapping(template_metadata.get('labels'))
    template_annotations = cast(ConfigDict, template_metadata.setdefault('annotations', {}))
    _normalize_string_mapping(template_annotations)
    template_annotations['run.googleapis.com/execution-environment'] = 'gen2'
    template_annotations['run.googleapis.com/cpu-throttling'] = 'false'
    template_annotations['run.googleapis.com/container-dependencies'] = _merge_container_dependencies(
        template_annotations.get('run.googleapis.com/container-dependencies'),
        ingress_container_name=ingress_container_name,
    )
    template_annotations['run.googleapis.com/secrets'] = _merge_secret_annotation(
        template_annotations.get('run.googleapis.com/secrets'),
        project_number=project_number,
        secret=config_secret,
    )

    template_spec = cast(ConfigDict, template['spec'])
    containers = cast(list[ConfigDict], template_spec['containers'])
    ingress = next((container for container in containers if container.get('name') == ingress_container_name), None)
    if ingress is None:
        candidates = [container for container in containers if container.get('name') != SIDECAR_NAME]
        if len(candidates) != 1:
            raise ValueError(f'service export has no unambiguous ingress container named {ingress_container_name!r}')
        ingress = candidates[0]
        ingress['name'] = ingress_container_name
    retained_containers = [
        container for container in containers if container is not ingress and container.get('name') != SIDECAR_NAME
    ]
    for container in [ingress, *retained_containers]:
        for env_var in cast(list[ConfigDict], container.get('env', [])):
            if 'value' in env_var:
                env_var['value'] = _cloud_run_string(env_var['value'])
    collector: ConfigDict = {
        'image': SIDECAR_IMAGE,
        'name': SIDECAR_NAME,
        'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
        'livenessProbe': {
            'httpGet': {'path': '/liveness', 'port': 13133},
            'timeoutSeconds': 30,
            'periodSeconds': 30,
        },
        'volumeMounts': [{'mountPath': '/etc/rungmp/', 'name': CONFIG_VOLUME_NAME}],
    }
    template_spec['containers'] = [ingress, *retained_containers, collector]

    volumes = [
        volume
        for volume in cast(list[ConfigDict], template_spec.get('volumes', []))
        if volume.get('name') != CONFIG_VOLUME_NAME
    ]
    volumes.append(
        {
            'name': CONFIG_VOLUME_NAME,
            'secret': {
                'items': [{'key': config_secret_version, 'path': 'config.yaml'}],
                'secretName': config_secret,
            },
        }
    )
    template_spec['volumes'] = volumes
    return patched


def attach_sidecar(args: argparse.Namespace) -> None:
    config_secret_version = ensure_config_secret(
        project=args.project, secret=args.config_secret, config_path=args.config
    )
    export = _run(
        [
            'gcloud',
            'run',
            'services',
            'describe',
            args.service,
            '--project',
            args.project,
            '--region',
            args.region,
            '--format=export',
        ],
        capture_output=True,
    )
    service = yaml.safe_load(_check(export, action=f'exporting {args.service}'))
    if not isinstance(service, dict):
        raise RuntimeError('Cloud Run service export was not a mapping')
    latest_created = _run(
        [
            'gcloud',
            'run',
            'services',
            'describe',
            args.service,
            '--project',
            args.project,
            '--region',
            args.region,
            '--format=value(status.latestCreatedRevisionName)',
        ],
        capture_output=True,
    )
    latest_created_revision = _check(
        latest_created,
        action=f'reading the latest {args.service} revision',
    ).strip()
    patched = patch_service(
        service,
        project_number=_project_number(args.project),
        base_revision=args.base_revision,
        latest_created_revision=latest_created_revision,
        final_revision=args.final_revision,
        ingress_container_name=args.ingress_container,
        config_secret=args.config_secret,
        config_secret_version=config_secret_version,
    )

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile('w', prefix='cloud-run-gmp-', suffix='.yaml', delete=False) as handle:
            path = Path(handle.name)
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            yaml.safe_dump(patched, handle, sort_keys=False)
        replace = _run(
            [
                'gcloud',
                'run',
                'services',
                'replace',
                str(path),
                '--project',
                args.project,
                '--region',
                args.region,
                '--format=json',
            ],
            capture_output=True,
        )
        _check(replace, action=f'attaching GMP sidecar to {args.service}')
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

    if args.tag:
        update_tag = _run(
            [
                'gcloud',
                'run',
                'services',
                'update-traffic',
                args.service,
                '--project',
                args.project,
                '--region',
                args.region,
                f'--update-tags={args.tag}={args.final_revision}',
                '--format=json',
            ],
            capture_output=True,
        )
        _check(update_tag, action=f'moving tag {args.tag}')

    url_result = _run(
        [
            'gcloud',
            'run',
            'services',
            'describe',
            args.service,
            '--project',
            args.project,
            '--region',
            args.region,
            '--format=value(status.url)',
        ],
        capture_output=True,
    )
    service_url = _check(url_result, action=f'reading {args.service} URL').strip()
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with Path(github_output).open('a', encoding='utf-8') as output:
            output.write(f'revision={args.final_revision}\n')
            output.write(f'url={service_url}\n')
    print(f'Attached pinned GMP sidecar to zero-traffic revision {args.final_revision}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='us-central1')
    parser.add_argument('--service', required=True)
    parser.add_argument('--base-revision', required=True)
    parser.add_argument('--final-revision', required=True)
    parser.add_argument('--ingress-container', required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-secret', default='cloud-run-gmp-config')
    parser.add_argument('--tag', default='')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.config.is_file():
        raise SystemExit(f'RunMonitoring config not found: {args.config}')
    attach_sidecar(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

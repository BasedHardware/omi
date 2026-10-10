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

import re
import yaml


class GcloudExportLoader(yaml.SafeLoader):
    """Read gcloud's YAML export under YAML 1.2 core semantics.

    gcloud emits plain `on` / `off` for *string* env values -- production's
    export literally contains `value: on` for MEMORY_ENABLED. PyYAML implements
    YAML 1.1, where `on`/`off`/`yes`/`no` are booleans, so `yaml.safe_load`
    turns those into True/False and dumping back through `services replace`
    rewrites the live value to 'true'/'false'.

    Nothing fails at attach time: Cloud Run stores the rewritten string happily
    and every consumer of these three flags accepts the coerced spelling. It
    surfaces one step later, when the post-deploy runtime-env validator compares
    the live value against the manifest's 'on' and finds 'true' -- on a service
    nobody edited. Restricting the bool resolver to the YAML 1.2 core set makes
    the round trip preserve exactly what gcloud wrote. Genuine unquoted numbers
    (containerPort, periodSeconds) and real booleans still load as themselves.
    """


GcloudExportLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != 'tag:yaml.org,2002:bool']
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
GcloudExportLoader.add_implicit_resolver(
    'tag:yaml.org,2002:bool',
    re.compile(r'^(?:true|True|TRUE|false|False|FALSE)$'),
    list('tTfF'),
)


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


def _expected_literal_env(state_path: Path, *, service_name: str) -> dict[str, str]:
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        raw_entries = state['services'][service_name]['env']
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f'{state_path} did not contain rendered env state for {service_name}') from exc
    if not isinstance(raw_entries, list):
        raise ValueError(f'{state_path} rendered env state for {service_name} was not a list')
    expected: dict[str, str] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get('name'), str):
            raise ValueError(f'{state_path} rendered env state for {service_name} had an invalid entry')
        if 'value' not in raw_entry:
            continue
        value = raw_entry['value']
        if not isinstance(value, str):
            raise ValueError(f'{state_path} rendered env {raw_entry["name"]} was not a string')
        expected[raw_entry['name']] = value
    return expected


def _ingress_literal_env(service: Mapping[str, Any], *, ingress_container_name: str) -> dict[str, str]:
    try:
        containers = service['spec']['template']['spec']['containers']
    except (KeyError, TypeError) as exc:
        raise ValueError('Cloud Run service export had no container list') from exc
    if not isinstance(containers, list):
        raise ValueError('Cloud Run service export had no container list')
    ingress = next(
        (
            container
            for container in containers
            if isinstance(container, dict) and container.get('name') == ingress_container_name
        ),
        None,
    )
    if ingress is None:
        raise ValueError(f'Cloud Run service export had no ingress container named {ingress_container_name!r}')
    raw_env = ingress.get('env', [])
    if not isinstance(raw_env, list):
        raise ValueError('Cloud Run ingress env was not a list')
    actual: dict[str, str] = {}
    for raw_entry in raw_env:
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get('name'), str):
            continue
        if 'valueFrom' in raw_entry:
            # Secret-backed reference, not a literal value -- must not be folded
            # into the literal-env map (and must not be coerced to '').
            continue
        # Cloud Run's export omits the `value` key entirely for an env var whose
        # literal value is the empty string -- it does not write `value: ''`.
        # Reading a missing key as None here would make a legitimately empty
        # literal look identical to a var that was never set at all, which is
        # exactly the false-positive "<missing>" this check reported for
        # OMI_PARITY_PACK_ALLOWED_PRINCIPALS. Absence of the key on a literal
        # entry means empty string, not absence of the variable.
        actual[raw_entry['name']] = _cloud_run_string(raw_entry.get('value', ''))
    return actual


def _validate_expected_literal_env(
    service: Mapping[str, Any],
    *,
    expected: Mapping[str, str],
    ingress_container_name: str,
    phase: str,
) -> None:
    actual = _ingress_literal_env(service, ingress_container_name=ingress_container_name)
    for name, expected_value in expected.items():
        actual_value = actual.get(name)
        if actual_value != expected_value:
            found = '<missing>' if actual_value is None else actual_value
            raise ValueError(
                f'{phase} env {name} mismatch before GMP sidecar replace: '
                f'expected {expected_value!r}, found {found!r}'
            )


SECRET_ANNOTATION = 'run.googleapis.com/secrets'

_SECRET_RESOURCE_RE = re.compile(r'^projects/(?P<project>[^/]+)/secrets/(?P<secret>.+)$')


def _normalize_secret_resource(resource: str, *, project_number: str) -> str:
    """Rewrite a secret path that names the project by ID into one naming it by number.

    gcloud validates this annotation against ``^projects/[0-9]{1,19}/secrets/...``.
    Cloud Run itself accepts a project ID, so an ID written here is stored happily
    and then crashes the *next* ``gcloud run deploy`` with "Invalid secret path".
    """
    match = _SECRET_RESOURCE_RE.match(resource)
    if not match or match.group('project').isdigit():
        return resource
    return f"projects/{project_number}/secrets/{match.group('secret')}"


def _parse_secret_annotation(existing: object) -> dict[str, str] | None:
    """Parse the annotation into {name: resource}, or None when it is absent or malformed.

    Returning None for a malformed value is deliberate: a repair pass must refuse to
    guess at a shape it does not recognise rather than rewrite it into something new.
    """
    if not isinstance(existing, str) or not existing.strip():
        return None
    entries: dict[str, str] = {}
    for raw_entry in existing.split(','):
        candidate = raw_entry.strip()
        if not candidate:
            continue
        name, separator, resource = candidate.partition(':')
        if not (name and separator and resource):
            return None
        entries[name] = resource
    return entries or None


def _render_secret_annotation(entries: Mapping[str, str]) -> str:
    return ','.join(f'{name}:{resource}' for name, resource in sorted(entries.items()))


def _normalize_secret_annotation(existing: object, *, project_number: str) -> str | None:
    """Return a repaired annotation, or None when nothing needs to change.

    Normalizes *every* entry, not just the sidecar's own: a bad path under any
    secret name breaks the same deploy.
    """
    entries = _parse_secret_annotation(existing)
    if entries is None:
        return None
    repaired = {
        name: _normalize_secret_resource(resource, project_number=project_number) for name, resource in entries.items()
    }
    if repaired == entries:
        return None
    return _render_secret_annotation(repaired)


def _merge_secret_annotation(existing: object, *, project_number: str, secret: str) -> str:
    entries: dict[str, str] = {}
    if isinstance(existing, str):
        for raw_entry in existing.split(','):
            name, separator, resource = raw_entry.strip().partition(':')
            if name and separator and resource:
                entries[name] = resource
    entries = {
        name: _normalize_secret_resource(resource, project_number=project_number) for name, resource in entries.items()
    }
    entries[secret] = f'projects/{project_number}/secrets/{secret}'
    return _render_secret_annotation(entries)


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


def _drop_startup_probe_initial_delay(ingress: ConfigDict) -> None:
    """Let the ingress startup probe run as soon as the container starts.

    uvicorn binds its port only after ``import main`` and the startup hooks
    finish, so an open TCP port already means the app is ready. A fixed
    ``initialDelaySeconds`` only holds every new instance out of service for
    longer. Production ``backend`` carried a hand-set 60 s delay that each
    export/replace preserved, pinning its cold start at about 61 s while the app
    was ready at about 48 s (p50, 2026-09-29/30).
    """
    probe = ingress.get('startupProbe')
    if isinstance(probe, dict):
        cast(ConfigDict, probe).pop('initialDelaySeconds', None)


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
    template_annotations[SECRET_ANNOTATION] = _merge_secret_annotation(
        template_annotations.get(SECRET_ANNOTATION),
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
    _drop_startup_probe_initial_delay(ingress)
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


JOB_DONE_VOLUME = 'gmp-job-lifecycle'
JOB_DONE_FILE = '/var/run/gmp-job/done'
JOB_COLLECTOR_COMMAND = (
    'export K_SERVICE="${CLOUD_RUN_JOB:?Cloud Run job identity missing}"; '
    '/run-gmp-entrypoint & collector=$!; '
    'trap "kill -TERM $collector; wait $collector" TERM INT; '
    'while [ ! -f /var/run/gmp-job/done ]; do '
    'kill -0 "$collector" || { wait "$collector"; exit 1; }; sleep 1; done; '
    'sleep 35; kill -TERM "$collector"; wait "$collector"'
)


def patch_job(
    job: Mapping[str, Any], *, project_number: str, config_secret: str, config_secret_version: str
) -> ConfigDict:
    """Reuse the service patch for the Job's nested task template, without traffic."""
    patched = cast(ConfigDict, json.loads(json.dumps(job)))
    if patched.get('kind') != 'Job':
        raise ValueError('expected a Cloud Run Job export')
    execution_template = patched['spec']['template']
    task_template = execution_template['spec']['template']
    containers = task_template['spec']['containers']
    applications = [c for c in containers if c.get('name') != SIDECAR_NAME]
    if len(applications) != 1:
        raise ValueError('job must have exactly one application container')
    application_name = applications[0].get('name') or 'notifications-job'
    # Jobs put annotations on the execution template, containers on the task.
    # https://cloud.google.com/run/docs/reference/yaml/v1#cloud_run_job_yaml
    synthetic = {
        'spec': {'template': {'metadata': execution_template.get('metadata', {}), 'spec': task_template['spec']}}
    }
    rendered = patch_service(
        synthetic,
        project_number=project_number,
        base_revision='job',
        latest_created_revision='job',
        final_revision='job',
        ingress_container_name=application_name,
        config_secret=config_secret,
        config_secret_version=config_secret_version,
    )['spec']['template']
    rendered['metadata'].pop('name', None)
    rendered['metadata']['annotations'].pop('run.googleapis.com/cpu-throttling', None)
    rendered['metadata']['annotations'].pop('run.googleapis.com/execution-environment', None)
    app, collector = rendered['spec']['containers']
    env = [
        e for e in app.get('env', []) if e['name'] not in ('PROMETHEUS_SIDECAR_PORT', 'PROMETHEUS_SIDECAR_DONE_FILE')
    ]
    app['env'] = [
        *env,
        {'name': 'PROMETHEUS_SIDECAR_PORT', 'value': '9090'},
        {'name': 'PROMETHEUS_SIDECAR_DONE_FILE', 'value': JOB_DONE_FILE},
    ]
    # Job probes cannot reach the loopback metrics listener. Also remove any
    # probe retained from an earlier attachment so it cannot terminate the task.
    app.pop('startupProbe', None)
    # Cloud Run rejects depends_on when the depended-upon container lacks a
    # startup probe (run.googleapis.com/container-dependencies), and jobs
    # cannot carry a reachable probe for this app (no serving port; TCP
    # probes cannot reach the loopback listener). Drop the dependency on the
    # job path: the collector's done-file handshake plus its 30s scrape loop
    # already sequence it, and failed early scrapes are retried harmlessly.
    rendered['metadata']['annotations'].pop('run.googleapis.com/container-dependencies', None)
    app['volumeMounts'] = [m for m in app.get('volumeMounts', []) if m['name'] != JOB_DONE_VOLUME]
    app['volumeMounts'].append({'name': JOB_DONE_VOLUME, 'mountPath': '/var/run/gmp-job'})
    # GMP reads K_SERVICE for namespace; jobs provide CLOUD_RUN_JOB instead.
    # Set K_SERVICE inside the process, not the deployed env (reserved on services).
    # CLOUD_RUN_JOB is supplied by Cloud Run to every job container.
    collector.pop('livenessProbe', None)
    collector['command'] = ['/bin/sh', '-c']
    collector['args'] = [JOB_COLLECTOR_COMMAND]
    collector['volumeMounts'].append({'name': JOB_DONE_VOLUME, 'mountPath': '/var/run/gmp-job'})
    rendered['spec']['volumes'] = [v for v in rendered['spec']['volumes'] if v['name'] != JOB_DONE_VOLUME]
    rendered['spec']['volumes'].append({'name': JOB_DONE_VOLUME, 'emptyDir': {'medium': 'Memory', 'sizeLimit': '1Mi'}})
    execution_template['metadata'] = rendered['metadata']
    task_template['spec'] = rendered['spec']
    patched.pop('status', None)
    for field in ('creationTimestamp', 'generation', 'resourceVersion', 'selfLink', 'uid'):
        patched['metadata'].pop(field, None)
    return patched


def detach_job(job: Mapping[str, Any]) -> ConfigDict:
    """Restore a singleton task for an action deploy that cannot select a container."""
    patched = cast(ConfigDict, json.loads(json.dumps(job)))
    if patched.get('kind') != 'Job':
        raise ValueError('expected a Cloud Run Job export')
    execution = patched['spec']['template']
    task = execution['spec']['template']['spec']
    containers = task['containers']
    applications = [c for c in containers if c.get('name') != SIDECAR_NAME]
    collectors = [c for c in containers if c.get('name') == SIDECAR_NAME]
    if len(applications) != 1 or len(collectors) > 1:
        raise ValueError('job must have exactly one application container and at most one collector')
    if not collectors:
        return patched
    app = applications[0]
    app['env'] = [
        e for e in app.get('env', []) if e['name'] not in ('PROMETHEUS_SIDECAR_PORT', 'PROMETHEUS_SIDECAR_DONE_FILE')
    ]
    app['volumeMounts'] = [
        m for m in app.get('volumeMounts', []) if m['name'] not in (JOB_DONE_VOLUME, CONFIG_VOLUME_NAME)
    ]
    task['containers'] = applications
    task['volumes'] = [v for v in task.get('volumes', []) if v['name'] not in (JOB_DONE_VOLUME, CONFIG_VOLUME_NAME)]
    annotations = execution.get('metadata', {}).get('annotations', {})
    dependency_key = 'run.googleapis.com/container-dependencies'
    if dependency_key in annotations:
        # Reuse the attach parser's shape validation before removing the collector.
        dependencies = json.loads(
            _merge_container_dependencies(annotations[dependency_key], ingress_container_name=app['name'])
        )
        dependencies.pop(SIDECAR_NAME)
        dependencies = {name: [d for d in required if d != SIDECAR_NAME] for name, required in dependencies.items()}
        dependencies = {name: required for name, required in dependencies.items() if required}
        if dependencies:
            annotations[dependency_key] = json.dumps(dependencies, separators=(',', ':'), sort_keys=True)
        else:
            annotations.pop(dependency_key)
    # Keep unrelated annotations (including secret aliases) and all runtime bindings.
    patched.pop('status', None)
    for field in ('creationTimestamp', 'generation', 'resourceVersion', 'selfLink', 'uid'):
        patched['metadata'].pop(field, None)
    return patched


def detach_job_sidecar(args: argparse.Namespace) -> None:
    # List distinguishes absence from auth/network failures without interpreting stderr.
    names = _check(
        _run(
            [
                'gcloud',
                'run',
                'jobs',
                'list',
                '--project',
                args.project,
                '--region',
                args.region,
                f'--filter=metadata.name={args.service}',
                '--format=value(metadata.name)',
            ],
            capture_output=True,
        ),
        action='checking job existence',
    ).splitlines()
    if args.service not in names:
        if names:
            raise ValueError('job existence query returned an unexpected name')
        return
    export = _check(
        _run(
            [
                'gcloud',
                'run',
                'jobs',
                'describe',
                args.service,
                '--project',
                args.project,
                '--region',
                args.region,
                '--format=export',
            ],
            capture_output=True,
        ),
        action='exporting job for detach',
    )
    job = yaml.load(export, Loader=GcloudExportLoader)
    patched = detach_job(job)
    if patched == job:
        return
    with tempfile.TemporaryDirectory(prefix='gmp-job-detach-') as directory:
        target = Path(directory) / 'job.yaml'
        target.write_text(yaml.safe_dump(patched, sort_keys=False), encoding='utf-8')
        target.chmod(0o600)
        _check(
            _run(
                [
                    'gcloud',
                    'run',
                    'jobs',
                    'replace',
                    str(target),
                    '--project',
                    args.project,
                    '--region',
                    args.region,
                    '--quiet',
                ],
                capture_output=True,
            ),
            action='detaching job sidecar',
        )


def attach_job_sidecar(args: argparse.Namespace) -> None:
    export = _check(
        _run(
            [
                'gcloud',
                'run',
                'jobs',
                'describe',
                args.service,
                '--project',
                args.project,
                '--region',
                args.region,
                '--format=export',
            ],
            capture_output=True,
        ),
        action='exporting job',
    )
    job = yaml.load(export, Loader=GcloudExportLoader)
    version = ensure_config_secret(project=args.project, secret=args.config_secret, config_path=args.config)
    patched = patch_job(
        job,
        project_number=_project_number(args.project),
        config_secret=args.config_secret,
        config_secret_version=version,
    )
    # Exports include secret references and literal env: keep the temporary file private.
    with tempfile.TemporaryDirectory(prefix='gmp-job-') as directory:
        target = Path(directory) / 'job.yaml'
        target.write_text(yaml.safe_dump(patched, sort_keys=False), encoding='utf-8')
        target.chmod(0o600)
        _check(
            _run(
                [
                    'gcloud',
                    'run',
                    'jobs',
                    'replace',
                    str(target),
                    '--project',
                    args.project,
                    '--region',
                    args.region,
                    '--quiet',
                ],
                capture_output=True,
            ),
            action='attaching job sidecar',
        )


def attach_sidecar(args: argparse.Namespace) -> None:
    expected_env = _expected_literal_env(args.expected_env_state, service_name=args.service)
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
    service = yaml.load(_check(export, action=f'exporting {args.service}'), Loader=GcloudExportLoader)
    if not isinstance(service, dict):
        raise RuntimeError('Cloud Run service export was not a mapping')
    _validate_expected_literal_env(
        service,
        expected=expected_env,
        ingress_container_name=args.ingress_container,
        phase='exported base revision',
    )
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
    config_secret_version = ensure_config_secret(
        project=args.project, secret=args.config_secret, config_path=args.config
    )
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
        with path.open('r', encoding='utf-8') as handle:
            serialized = yaml.load(handle, Loader=GcloudExportLoader)
        if not isinstance(serialized, dict):
            raise RuntimeError('rendered Cloud Run service replacement was not a mapping')
        _validate_expected_literal_env(
            serialized,
            expected=expected_env,
            ingress_container_name=args.ingress_container,
            phase='rendered sidecar replacement',
        )
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


def _drop_pinned_revision_name(service: dict[str, Any]) -> str | None:
    """Remove spec.template.metadata.name, returning what was removed.

    Cloud Run refuses `services replace` when the spec pins a revision name that
    already exists with different configuration, which is exactly the state a
    failed deploy leaves behind.
    """
    template = service.get('spec', {}).get('template') if isinstance(service.get('spec'), dict) else None
    if not isinstance(template, dict):
        return None
    metadata = template.get('metadata')
    if not isinstance(metadata, dict):
        return None
    name = metadata.pop('name', None)
    return name if isinstance(name, str) and name else None


def repair_secret_annotations(args: argparse.Namespace) -> int:
    """Rewrite project-ID secret paths on a live service into project-number paths.

    A previous sidecar attach persisted `projects/<id>/secrets/...` into the
    template annotation. Cloud Run stored it, but every subsequent
    `gcloud run deploy` on that service crashes with "Invalid secret path", so no
    code change can unblock a deploy - the damage is in the live service and has
    to be repaired there.

    Idempotent: when nothing needs repair it reports so and writes nothing.
    """
    project_number = _project_number(args.project)
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
    service = yaml.load(_check(export, action=f'exporting {args.service}'), Loader=GcloudExportLoader)
    if not isinstance(service, dict):
        raise RuntimeError('Cloud Run service export was not a mapping')

    scopes: list[tuple[str, dict[str, Any]]] = []
    service_meta = service.get('metadata')
    if isinstance(service_meta, dict) and isinstance(service_meta.get('annotations'), dict):
        scopes.append(('service', cast(dict[str, Any], service_meta['annotations'])))
    template = service.get('spec', {}).get('template') if isinstance(service.get('spec'), dict) else None
    if isinstance(template, dict):
        template_meta = template.get('metadata')
        if isinstance(template_meta, dict) and isinstance(template_meta.get('annotations'), dict):
            scopes.append(('template', cast(dict[str, Any], template_meta['annotations'])))

    changes: list[str] = []
    for scope, annotations in scopes:
        current = annotations.get(SECRET_ANNOTATION)
        if current is None:
            continue
        repaired = _normalize_secret_annotation(current, project_number=project_number)
        if repaired is None:
            if _parse_secret_annotation(current) is None:
                print(f'[{scope}] {SECRET_ANNOTATION} is absent or unrecognised; leaving it untouched')
            else:
                print(f'[{scope}] {SECRET_ANNOTATION} already uses project numbers; no change')
            continue
        changes.append(f'[{scope}] {current}  ->  {repaired}')
        annotations[SECRET_ANNOTATION] = repaired

    if not changes:
        print(f'{args.service} needs no secret-annotation repair')
        return 0

    for change in changes:
        print(change)
    if args.dry_run:
        print('--dry-run: no changes applied')
        return 0

    # A failed deploy leaves its pinned revision name in the exported spec.
    # `services replace` then tries to recreate that exact name with different
    # config and Cloud Run rejects it:
    #   ALREADY_EXISTS: Revision named '<name>' with different configuration
    #   already exists.
    # Repair is not creating a named release, so drop the pin and let Cloud Run
    # assign a fresh name. Traffic is unaffected: the traffic block in the export
    # still pins whatever revision is currently serving.
    pinned = _drop_pinned_revision_name(service)
    if pinned:
        print(f'dropping stale pinned revision name {pinned} so Cloud Run can assign a fresh one')

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile('w', prefix='cloud-run-repair-', suffix='.yaml', delete=False) as handle:
            path = Path(handle.name)
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            yaml.safe_dump(service, handle, sort_keys=False)
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
        _check(replace, action=f'repairing secret annotations on {args.service}')
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

    verify = _run(
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
    after = yaml.load(_check(verify, action=f're-reading {args.service}'), Loader=GcloudExportLoader)
    if not isinstance(after, dict):
        raise RuntimeError('Cloud Run service re-read was not a mapping')
    for scope, annotations in (
        ('service', after.get('metadata', {}).get('annotations', {})),
        ('template', after.get('spec', {}).get('template', {}).get('metadata', {}).get('annotations', {})),
    ):
        current = annotations.get(SECRET_ANNOTATION) if isinstance(annotations, dict) else None
        if current is None:
            continue
        if _normalize_secret_annotation(current, project_number=project_number) is not None:
            raise RuntimeError(f'[{scope}] {SECRET_ANNOTATION} still needs repair after replace: {current}')
    print(f'Repaired secret annotations on {args.service}')
    return 0


_ATTACH_REQUIRED = (
    'base_revision',
    'final_revision',
    'ingress_container',
    'config',
    'expected_env_state',
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='us-central1')
    parser.add_argument('--service', required=True)
    parser.add_argument('--job', action='store_true', help='Attach to a Cloud Run Job, not a service revision.')
    parser.add_argument('--detach', action='store_true', help='With --job, restore a singleton before deploying.')
    # Attach-only. Not argparse-required so --repair-secret-annotations can run
    # standalone; main() enforces them for the attach path instead.
    parser.add_argument('--base-revision')
    parser.add_argument('--final-revision')
    parser.add_argument('--ingress-container')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--config-secret', default='cloud-run-gmp-config')
    parser.add_argument('--expected-env-state', type=Path)
    parser.add_argument('--tag', default='')
    parser.add_argument(
        '--repair-secret-annotations',
        action='store_true',
        help='Repair project-ID secret paths on the live service and exit. Does not attach a sidecar.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='With --repair-secret-annotations, report the change without applying it.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.detach:
        if not args.job or args.repair_secret_annotations or args.dry_run:
            raise SystemExit('--detach is only supported with --job')
        detach_job_sidecar(args)
        return 0
    if args.job:
        if args.repair_secret_annotations or args.dry_run or args.config is None or not args.config.is_file():
            raise SystemExit('--job requires an existing --config and cannot repair service annotations')
        attach_job_sidecar(args)
        return 0
    if args.repair_secret_annotations:
        return repair_secret_annotations(args)
    if args.dry_run:
        raise SystemExit('--dry-run is only supported with --repair-secret-annotations')
    missing = [f"--{name.replace('_', '-')}" for name in _ATTACH_REQUIRED if getattr(args, name) is None]
    if missing:
        raise SystemExit(f"attach mode requires: {', '.join(missing)}")
    if not args.config.is_file():
        raise SystemExit(f'RunMonitoring config not found: {args.config}')
    attach_sidecar(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

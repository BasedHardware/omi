#!/usr/bin/env python3
"""Read-only verification of a converged Cloud Run and backend-listen release vector."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

CLOUD_RUN_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
MIN_CLOUD_RUN_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class DeploymentExpectation:
    commit_sha: str
    deploy_run_id: str
    deploy_run_attempt: str
    project: str
    region: str
    environment: str
    namespace: str
    image: str
    revisions: Mapping[str, str]
    listener_deployment: str
    listener_service: str


def build_expectation(
    *,
    commit_sha: str,
    deploy_run_id: str,
    deploy_run_attempt: str,
    project: str,
    region: str,
    environment: str,
    short_sha: str | None = None,
) -> DeploymentExpectation:
    """Derive an immutable desired release vector from deploy-run metadata.

    ``short_sha`` is the exact abbreviated SHA the deploy workflow used to tag
    the image and build the revision suffix (``git rev-parse --short=7 HEAD``).
    Git documents ``--short=N`` as a prefix of *at least* N characters: when the
    N-character prefix is ambiguous Git extends it, so the deployed revision can
    carry 8+ characters while a naive ``commit_sha[:7]`` truncation would expect
    exactly seven and reject a correctly deployed release. Passing the
    workflow's computed short SHA keeps the verifier aligned with what was
    actually deployed; when omitted it falls back to the seven-character prefix
    for local/manual invocations.
    """
    normalized_sha = commit_sha.strip().lower()
    if len(normalized_sha) < 7 or any(char not in '0123456789abcdef' for char in normalized_sha):
        raise ValueError('commit SHA must be a hexadecimal value with at least seven characters')
    if not deploy_run_id.isdigit() or not deploy_run_attempt.isdigit():
        raise ValueError('deploy run ID and attempt must be decimal integers')
    if environment not in {'dev', 'prod'}:
        raise ValueError("environment must be 'dev' or 'prod'")
    if short_sha is not None:
        normalized_short = short_sha.strip().lower()
        if len(normalized_short) < 7 or any(char not in '0123456789abcdef' for char in normalized_short):
            raise ValueError('short SHA must be a hexadecimal value with at least seven characters')
        if not normalized_sha.startswith(normalized_short):
            raise ValueError('short SHA must be a prefix of the commit SHA')
        resolved_short_sha = normalized_short
    else:
        resolved_short_sha = normalized_sha[:7]
    suffix = f'{resolved_short_sha}-{deploy_run_id}-{deploy_run_attempt}'
    return DeploymentExpectation(
        commit_sha=normalized_sha,
        deploy_run_id=deploy_run_id,
        deploy_run_attempt=deploy_run_attempt,
        project=project,
        region=region,
        environment=environment,
        namespace=f'{environment}-omi-backend',
        image=f'gcr.io/{project}/backend:{resolved_short_sha}',
        revisions={service: f'{service}-{suffix}' for service in CLOUD_RUN_SERVICES},
        listener_deployment=f'{environment}-omi-backend-listen',
        listener_service=f'{environment}-omi-backend-listen',
    )


def build_read_only_commands(
    expectation: DeploymentExpectation,
    *,
    include_listener: bool = True,
) -> dict[str, list[str]]:
    commands = {
        f'cloud_run/{service}': [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={expectation.project}',
            f'--region={expectation.region}',
            '--format=json',
        ]
        for service in CLOUD_RUN_SERVICES
    }
    if include_listener:
        commands.update(
            {
                'gke/deployment': [
                    'kubectl',
                    '-n',
                    expectation.namespace,
                    'get',
                    'deployment',
                    expectation.listener_deployment,
                    '-o',
                    'json',
                ],
                'gke/service': [
                    'kubectl',
                    '-n',
                    expectation.namespace,
                    'get',
                    'service',
                    expectation.listener_service,
                    '-o',
                    'json',
                ],
                'gke/endpointslices': [
                    'kubectl',
                    '-n',
                    expectation.namespace,
                    'get',
                    'endpointslice',
                    '-l',
                    f'kubernetes.io/service-name={expectation.listener_service}',
                    '-o',
                    'json',
                ],
            }
        )
    return commands


def assert_commands_are_read_only(commands: Mapping[str, Sequence[str]]) -> None:
    for name, command in commands.items():
        rendered = ' '.join(command)
        allowed = rendered.startswith('gcloud run services describe ') or rendered.startswith('kubectl -n ')
        is_query = rendered.startswith('gcloud run services describe ') or ' get ' in f' {rendered} '
        if not allowed or not is_query:
            raise ValueError(f'{name} is not a read-only acceptance command: {rendered}')
        if any(term in f' {rendered} ' for term in (' apply ', ' delete ', ' patch ', ' create ', ' update ')):
            raise ValueError(f'{name} contains a mutating command: {rendered}')


def collect_documents(commands: Mapping[str, Sequence[str]]) -> dict[str, Mapping[str, Any]]:
    documents: dict[str, Mapping[str, Any]] = {}
    for name, command in commands.items():
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f'exit code {completed.returncode}'
            raise RuntimeError(f'{name} query failed: {detail}')
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'{name} did not return JSON: {exc}') from exc
        if not isinstance(parsed, Mapping):
            raise RuntimeError(f'{name} returned a non-object JSON document')
        documents[name] = parsed
    return documents


def evaluate(
    expectation: DeploymentExpectation,
    documents: Mapping[str, Mapping[str, Any]],
    *,
    require_serving_traffic: bool = True,
    include_listener: bool = True,
) -> list[str]:
    errors: list[str] = []
    for service, expected_revision in expectation.revisions.items():
        document = documents.get(f'cloud_run/{service}')
        if document is None:
            errors.append(f'cloud_run/{service}: result missing')
        else:
            errors.extend(
                evaluate_cloud_run_service(
                    service,
                    expected_revision,
                    expectation.image,
                    document,
                    expected_environment=expectation.environment,
                    require_serving_traffic=require_serving_traffic,
                )
            )
    if include_listener:
        for key, evaluator in (
            ('gke/deployment', evaluate_listener_deployment),
            ('gke/service', evaluate_listener_service),
            ('gke/endpointslices', evaluate_listener_endpoints),
        ):
            document = documents.get(key)
            if document is None:
                errors.append(f'{key}: result missing')
            else:
                errors.extend(evaluator(expectation, document))
    return errors


def evaluate_cloud_run_service(
    service: str,
    expected_revision: str,
    expected_image: str,
    document: Mapping[str, Any],
    *,
    expected_environment: str,
    require_serving_traffic: bool = True,
) -> list[str]:
    status = _mapping(document.get('status'))
    template_spec = _mapping(_mapping(_mapping(document.get('spec')).get('template')).get('spec'))
    containers = _list(template_spec.get('containers'))
    image = _mapping(containers[0]).get('image') if containers else None
    traffic = _list(status.get('traffic'))
    expected_traffic = [entry for entry in traffic if _mapping(entry).get('revisionName') == expected_revision]
    errors: list[str] = []
    if status.get('latestCreatedRevisionName') != expected_revision:
        errors.append(f'cloud_run/{service}: latest created revision is not {expected_revision}')
    if status.get('latestReadyRevisionName') != expected_revision:
        errors.append(f'cloud_run/{service}: latest ready revision is not {expected_revision}')
    if image != expected_image:
        errors.append(f'cloud_run/{service}: template image is not {expected_image}')
    if require_serving_traffic and (not expected_traffic or _mapping(expected_traffic[0]).get('percent') != 100):
        errors.append(f'cloud_run/{service}: expected revision does not receive 100% traffic')
    timeout = template_spec.get('timeoutSeconds')
    if not isinstance(timeout, int) or timeout < MIN_CLOUD_RUN_TIMEOUT_SECONDS:
        errors.append(f'cloud_run/{service}: timeoutSeconds must be at least {MIN_CLOUD_RUN_TIMEOUT_SECONDS}')
    if _container_env(containers).get('OMI_ENV_STAGE') != expected_environment:
        errors.append(f'cloud_run/{service}: OMI_ENV_STAGE must be {expected_environment}')
    return errors


def evaluate_listener_deployment(expectation: DeploymentExpectation, document: Mapping[str, Any]) -> list[str]:
    metadata = _mapping(document.get('metadata'))
    spec = _mapping(document.get('spec'))
    status = _mapping(document.get('status'))
    template_spec = _mapping(_mapping(spec.get('template')).get('spec'))
    containers = _list(template_spec.get('containers'))
    image = _mapping(containers[0]).get('image') if containers else None
    desired = spec.get('replicas')
    errors: list[str] = []
    if metadata.get('name') != expectation.listener_deployment:
        errors.append(f'gke/deployment: name is not {expectation.listener_deployment}')
    if image != expectation.image:
        errors.append(f'gke/deployment: template image is not {expectation.image}')
    if not template_spec.get('serviceAccountName'):
        errors.append('gke/deployment: service account is missing')
    if not isinstance(desired, int) or desired < 1 or status.get('availableReplicas') != desired:
        errors.append('gke/deployment: desired replicas are not all available')
    if not isinstance(desired, int) or desired < 1 or status.get('updatedReplicas') != desired:
        errors.append('gke/deployment: desired replicas are not all updated')
    if status.get('observedGeneration') != metadata.get('generation'):
        errors.append('gke/deployment: controller has not observed the latest generation')
    if _container_env(containers).get('OMI_ENV_STAGE') != expectation.environment:
        errors.append(f'gke/deployment: OMI_ENV_STAGE must be {expectation.environment}')
    return errors


def evaluate_listener_service(expectation: DeploymentExpectation, document: Mapping[str, Any]) -> list[str]:
    metadata = _mapping(document.get('metadata'))
    spec = _mapping(document.get('spec'))
    ports = _list(spec.get('ports'))
    errors: list[str] = []
    if metadata.get('name') != expectation.listener_service:
        errors.append(f'gke/service: name is not {expectation.listener_service}')
    if spec.get('type') != 'ClusterIP':
        errors.append('gke/service: type must be ClusterIP')
    if not any(_mapping(port).get('port') == 8080 for port in ports):
        errors.append('gke/service: port 8080 is missing')
    if not _mapping(spec.get('selector')):
        errors.append('gke/service: selector is missing')
    return errors


def evaluate_listener_endpoints(expectation: DeploymentExpectation, document: Mapping[str, Any]) -> list[str]:
    for item in _list(document.get('items')):
        labels = _mapping(_mapping(item).get('metadata')).get('labels')
        if _mapping(labels).get('kubernetes.io/service-name') != expectation.listener_service:
            continue
        for endpoint in _list(_mapping(item).get('endpoints')):
            conditions = _mapping(_mapping(endpoint).get('conditions'))
            addresses = _list(_mapping(endpoint).get('addresses'))
            if conditions.get('ready') is True and addresses:
                return []
    return ['gke/endpointslices: no ready endpoint for backend-listen service']


def evidence(
    expectation: DeploymentExpectation,
    documents: Mapping[str, Mapping[str, Any]],
    errors: Sequence[str],
    *,
    require_serving_traffic: bool = True,
    include_listener: bool = True,
) -> dict[str, Any]:
    cloud_run: dict[str, dict[str, Any]] = {}
    for service in CLOUD_RUN_SERVICES:
        document = documents.get(f'cloud_run/{service}', {})
        status = _mapping(document.get('status'))
        template_spec = _mapping(_mapping(_mapping(document.get('spec')).get('template')).get('spec'))
        containers = _list(template_spec.get('containers'))
        cloud_run[service] = {
            'expected_revision': expectation.revisions[service],
            'latest_created_revision': status.get('latestCreatedRevisionName'),
            'latest_ready_revision': status.get('latestReadyRevisionName'),
            'image': _mapping(containers[0]).get('image') if containers else None,
            'timeout_seconds': template_spec.get('timeoutSeconds'),
            'traffic': [
                {'revision': _mapping(entry).get('revisionName'), 'percent': _mapping(entry).get('percent')}
                for entry in _list(status.get('traffic'))
            ],
        }
    report = {
        'scope': 'backend deploy (read-only)',
        'release_vector': {
            'schema_version': 1,
            'commit_sha': expectation.commit_sha,
            'deploy_run_id': expectation.deploy_run_id,
            'deploy_run_attempt': expectation.deploy_run_attempt,
            'environment': expectation.environment,
            'immutable_image': expectation.image,
            'cloud_run_revisions': dict(expectation.revisions),
            'require_serving_traffic': require_serving_traffic,
        },
        'cloud_run': cloud_run,
        'result': 'pass' if not errors else 'fail',
        'errors': list(errors),
    }
    if include_listener:
        deployment = documents.get('gke/deployment', {})
        deployment_spec = _mapping(deployment.get('spec'))
        deployment_status = _mapping(deployment.get('status'))
        template_spec = _mapping(_mapping(deployment_spec.get('template')).get('spec'))
        containers = _list(template_spec.get('containers'))
        report['release_vector']['backend_listen'] = {
            'deployment': expectation.listener_deployment,
            'image': expectation.image,
        }
        report['gke_listener'] = {
            'deployment': expectation.listener_deployment,
            'image': _mapping(containers[0]).get('image') if containers else None,
            'service_account': template_spec.get('serviceAccountName'),
            'desired_replicas': deployment_spec.get('replicas'),
            'available_replicas': deployment_status.get('availableReplicas'),
            'updated_replicas': deployment_status.get('updatedReplicas'),
        }
    else:
        report['release_vector']['backend_listen_required'] = False
    return report


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _container_env(containers: Sequence[Any]) -> dict[str, str]:
    if not containers:
        return {}
    return {
        str(_mapping(entry).get('name')): str(_mapping(entry).get('value'))
        for entry in _list(_mapping(containers[0]).get('env'))
        if _mapping(entry).get('name') and 'value' in _mapping(entry)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit-sha', required=True)
    parser.add_argument(
        '--short-sha',
        help=(
            'exact abbreviated SHA the deploy workflow used to tag the image and '
            'revision suffix; must be a prefix of --commit-sha. Matches the workflow '
            'git rev-parse --short=7 HEAD, which Git may extend past seven characters.'
        ),
    )
    parser.add_argument('--deploy-run-id', required=True)
    parser.add_argument('--deploy-run-attempt', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='us-central1')
    parser.add_argument('--environment', choices=('dev', 'prod'), required=True)
    parser.add_argument(
        '--candidate',
        action='store_true',
        help='verify a ready no-traffic candidate release vector before promotion',
    )
    parser.add_argument(
        '--cloud-run-only',
        action='store_true',
        help='verify only the no-traffic Cloud Run candidate before GKE serving mutations',
    )
    parser.add_argument('--evidence-path', type=Path)
    args = parser.parse_args()
    try:
        expectation = build_expectation(
            commit_sha=args.commit_sha,
            short_sha=args.short_sha,
            deploy_run_id=args.deploy_run_id,
            deploy_run_attempt=args.deploy_run_attempt,
            project=args.project,
            region=args.region,
            environment=args.environment,
        )
        if args.cloud_run_only and not args.candidate:
            raise ValueError('--cloud-run-only is valid only for a no-traffic candidate')
        commands = build_read_only_commands(expectation, include_listener=not args.cloud_run_only)
        assert_commands_are_read_only(commands)
        documents = collect_documents(commands)
        errors = evaluate(
            expectation,
            documents,
            require_serving_traffic=not args.candidate,
            include_listener=not args.cloud_run_only,
        )
    except (RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    rendered = json.dumps(
        evidence(
            expectation,
            documents,
            require_serving_traffic=not args.candidate,
            include_listener=not args.cloud_run_only,
        ),
        indent=2,
        sort_keys=True,
    )
    print(rendered)
    if args.evidence_path:
        args.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_path.write_text(f'{rendered}\n', encoding='utf-8')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())

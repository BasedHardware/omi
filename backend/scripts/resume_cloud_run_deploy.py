#!/usr/bin/env python3
"""Safely resume an interrupted Cloud Run rollout without rebuilding its image."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib import error, request

DEFAULT_REGION = 'us-central1'
DEFAULT_SMOKE_PATH = '/v1/health'
CONTROL_PLANE_PATHS = ('/v2/desktop/releases', '/v2/desktop/channels/promote')
PROMOTION_ORDER = ('backend-integration', 'backend-sync-backfill', 'backend-sync', 'backend')
REQUIRED_SERVICES = frozenset(PROMOTION_ORDER)
EXISTING_CANDIDATE_ORDER = ('backend-sync-backfill', 'backend-sync', 'backend')
EXISTING_CANDIDATE_SERVICES = frozenset(EXISTING_CANDIDATE_ORDER)
SOURCE_SHA_RE = re.compile(r'^[0-9a-f]{40}$')
DIGEST_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
TAG_RE = re.compile(r'^[a-z][a-z0-9-]{0,61}[a-z0-9]$')


@dataclass(frozen=True)
class Candidate:
    service: str
    revision: str


def main() -> int:
    parser = argparse.ArgumentParser(description='Resume an interrupted Cloud Run candidate rollout.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    gke_gate = subparsers.add_parser('gke-gate', help='Require a continuously healthy backend-listen rollout.')
    gke_gate.add_argument('--namespace', required=True)
    gke_gate.add_argument('--deployment', required=True)
    gke_gate.add_argument('--hpa', required=True)
    gke_gate.add_argument('--selector', default='app.kubernetes.io/name=backend-listen')
    gke_gate.add_argument('--expected-image', required=True)
    gke_gate.add_argument('--expected-runtime-project', required=True)
    gke_gate.add_argument('--dwell-seconds', type=float, default=120)
    gke_gate.add_argument('--poll-interval-seconds', type=float, default=15)
    gke_gate.add_argument('--timeout-seconds', type=float, default=900)

    integration = subparsers.add_parser(
        'integration-plan', help='Decide whether an exact integration candidate is reusable.'
    )
    _add_identity_args(integration)
    integration.add_argument('--service', required=True)
    integration.add_argument('--revision', required=True)

    verify_existing = subparsers.add_parser(
        'verify-existing', help='Verify the exact three candidates left by the interrupted rollout.'
    )
    _add_identity_args(verify_existing)
    verify_existing.add_argument('--candidate', action='append', required=True, metavar='SERVICE=REVISION')

    validate = subparsers.add_parser('validate', help='Verify and smoke-test the exact four candidate revisions.')
    _add_candidate_args(validate)
    validate.add_argument('--candidate-tag', required=True)

    promote = subparsers.add_parser('promote', help='Shift traffic in dependency order with verified rollback.')
    _add_candidate_args(promote)
    promote.add_argument('--control-plane-url', required=True)

    args = parser.parse_args()
    try:
        if args.command == 'gke-gate':
            gate_gke_rollout(
                namespace=args.namespace,
                deployment=args.deployment,
                hpa=args.hpa,
                selector=args.selector,
                expected_image=args.expected_image,
                expected_runtime_project=args.expected_runtime_project,
                dwell_seconds=args.dwell_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == 'integration-plan':
            _validate_source_sha(args.source_sha)
            _validate_digest(args.expected_digest)
            print(
                integration_plan(
                    Candidate(args.service, args.revision),
                    project=args.project,
                    region=args.region,
                    source_sha=args.source_sha,
                    expected_digest=args.expected_digest,
                )
            )
        elif args.command == 'verify-existing':
            _validate_source_sha(args.source_sha)
            _validate_digest(args.expected_digest)
            candidates = parse_existing_candidates(args.candidate)
            _validate_candidate_set(
                candidates,
                project=args.project,
                region=args.region,
                source_sha=args.source_sha,
                expected_digest=args.expected_digest,
                expected_order=EXISTING_CANDIDATE_ORDER,
            )
            print('existing Cloud Run candidate identity checks passed')
        else:
            candidates = parse_candidates(args.candidate)
            _validate_source_sha(args.source_sha)
            _validate_digest(args.expected_digest)
            if args.command == 'validate':
                validate_candidates(
                    candidates,
                    project=args.project,
                    region=args.region,
                    source_sha=args.source_sha,
                    expected_digest=args.expected_digest,
                    candidate_tag=args.candidate_tag,
                    smoke_path=args.smoke_path,
                )
            else:
                promote_candidates(
                    candidates,
                    project=args.project,
                    region=args.region,
                    source_sha=args.source_sha,
                    expected_digest=args.expected_digest,
                    smoke_path=args.smoke_path,
                    control_plane_url=args.control_plane_url,
                )
    except (RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


def _add_identity_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--expected-digest', required=True)


def _add_candidate_args(parser: argparse.ArgumentParser) -> None:
    _add_identity_args(parser)
    parser.add_argument('--candidate', action='append', required=True, metavar='SERVICE=REVISION')
    parser.add_argument('--smoke-path', default=DEFAULT_SMOKE_PATH)


def parse_candidates(entries: list[str]) -> list[Candidate]:
    return _parse_candidate_set(entries, required=REQUIRED_SERVICES, order=PROMOTION_ORDER, description='four backend')


def parse_existing_candidates(entries: list[str]) -> list[Candidate]:
    return _parse_candidate_set(
        entries,
        required=EXISTING_CANDIDATE_SERVICES,
        order=EXISTING_CANDIDATE_ORDER,
        description='three existing',
    )


def _parse_candidate_set(
    entries: list[str], *, required: frozenset[str], order: tuple[str, ...], description: str
) -> list[Candidate]:
    candidates: dict[str, Candidate] = {}
    for entry in entries:
        if '=' not in entry:
            raise ValueError(f'candidate must be SERVICE=REVISION: {entry}')
        service, revision = (part.strip() for part in entry.split('=', 1))
        if not service or not revision:
            raise ValueError(f'candidate must include a non-empty service and revision: {entry}')
        if service in candidates:
            raise ValueError(f'duplicate candidate service: {service}')
        if not revision.startswith(f'{service}-'):
            raise ValueError(f'revision {revision!r} does not belong to service {service!r}')
        candidates[service] = Candidate(service, revision)

    observed: set[str] = set(candidates)
    required_set: set[str] = set(required)
    if observed != required_set:
        missing = ', '.join(sorted(required_set - observed)) or 'none'
        unexpected = ', '.join(sorted(observed - required_set)) or 'none'
        raise ValueError(
            f'candidate set must be exactly the {description} services; missing={missing}; unexpected={unexpected}'
        )
    return [candidates[service] for service in order]


def integration_plan(
    candidate: Candidate,
    *,
    project: str,
    region: str,
    source_sha: str,
    expected_digest: str,
) -> str:
    if candidate.service != 'backend-integration':
        raise ValueError('integration-plan only accepts backend-integration')
    revision = _try_describe_revision(candidate.revision, project=project, region=region)
    if revision is None:
        return 'create'
    service = _describe_service(candidate.service, project=project, region=region)
    _validate_candidate_identity(
        candidate,
        revision=revision,
        service=service,
        source_sha=source_sha,
        expected_digest=expected_digest,
    )
    return 'reuse'


def validate_candidates(
    candidates: list[Candidate],
    *,
    project: str,
    region: str,
    source_sha: str,
    expected_digest: str,
    candidate_tag: str,
    smoke_path: str = DEFAULT_SMOKE_PATH,
) -> None:
    _validate_candidate_tag(candidate_tag)
    previous = _validate_candidate_set(
        candidates,
        project=project,
        region=region,
        source_sha=source_sha,
        expected_digest=expected_digest,
    )

    attempted_tags: list[Candidate] = []
    original_error: Exception | None = None
    try:
        for candidate in candidates:
            # Treat the command as ambiguous once attempted: gcloud can report a
            # transport error after Cloud Run has already applied the tag.
            attempted_tags.append(candidate)
            _run(
                [
                    'gcloud',
                    'run',
                    'services',
                    'update-traffic',
                    candidate.service,
                    f'--project={project}',
                    f'--region={region}',
                    f'--update-tags={candidate_tag}={candidate.revision}',
                    '--quiet',
                ]
            )
            service = _describe_service(candidate.service, project=project, region=region)
            _verify_serving_revision(service, candidate.service, previous[candidate.service])
            tagged_url = _tagged_url(service, candidate_tag, candidate.revision)
            base_url = str(service.get('status', {}).get('url') or '')
            if not tagged_url or not base_url:
                raise RuntimeError(f'{candidate.service} did not expose the candidate tag URL')
            token = _identity_token(base_url)
            status = _http_status(f'{tagged_url.rstrip("/")}{smoke_path}', token=token)
            if status != 200:
                raise RuntimeError(f'{candidate.service} candidate health returned HTTP {status}')
            if candidate.service == 'backend':
                verify_control_plane(tagged_url, token=token)
            print(f'{candidate.service}: {candidate.revision} identity and candidate smoke passed')
    except Exception as exc:
        original_error = exc

    cleanup_errors = _remove_candidate_tags(
        attempted_tags,
        project=project,
        region=region,
        candidate_tag=candidate_tag,
        previous=previous,
    )
    if original_error is not None:
        if cleanup_errors:
            raise RuntimeError(
                f'candidate validation failed ({original_error}); tag cleanup failed: {"; ".join(cleanup_errors)}'
            ) from original_error
        raise original_error
    if cleanup_errors:
        raise RuntimeError(f'candidate tag cleanup failed: {"; ".join(cleanup_errors)}')


def promote_candidates(
    candidates: list[Candidate],
    *,
    project: str,
    region: str,
    source_sha: str,
    expected_digest: str,
    control_plane_url: str,
    smoke_path: str = DEFAULT_SMOKE_PATH,
) -> None:
    previous = _validate_candidate_set(
        candidates,
        project=project,
        region=region,
        source_sha=source_sha,
        expected_digest=expected_digest,
    )
    try:
        for candidate in candidates:
            _set_traffic(candidate.service, candidate.revision, project=project, region=region)
            service = _describe_service(candidate.service, project=project, region=region)
            _verify_serving_revision(service, candidate.service, candidate.revision)
            base_url = str(service.get('status', {}).get('url') or '')
            if not base_url:
                raise RuntimeError(f'{candidate.service} is missing its service URL')
            token = _identity_token(base_url)
            status = _http_status(f'{base_url.rstrip("/")}{smoke_path}', token=token)
            if status != 200:
                raise RuntimeError(f'{candidate.service} post-shift health returned HTTP {status}')
            print(f'{candidate.service}: shifted 100% traffic to {candidate.revision}')
        verify_control_plane(control_plane_url)
    except Exception as exc:
        # Reconcile every service from the pre-mutation snapshot. The currently
        # attempted gcloud command may have applied remotely before returning an
        # error, and rolling back only commands that returned successfully would
        # leave that service serving an unverified candidate.
        rollback_errors = _rollback_candidates(
            candidates,
            previous=previous,
            project=project,
            region=region,
        )
        if rollback_errors:
            raise RuntimeError(f'promotion failed ({exc}); rollback also failed: {"; ".join(rollback_errors)}') from exc
        raise RuntimeError(f'promotion failed and serving traffic was rolled back: {exc}') from exc


def verify_control_plane(base_url: str, *, token: str | None = None) -> None:
    base_url = base_url.rstrip('/')
    openapi = _http_json(f'{base_url}/openapi.json', token=token)
    paths = cast(dict[str, Any], openapi.get('paths') or {})
    for path in CONTROL_PLANE_PATHS:
        operations = paths.get(path)
        if not isinstance(operations, dict) or 'post' not in operations:
            raise RuntimeError(f'OpenAPI is missing POST {path}')
        status = _http_status(f'{base_url}{path}', token=token)
        if status != 405:
            raise RuntimeError(f'GET {path} returned HTTP {status}, expected 405')
    print('desktop release-control API smoke passed')


def gate_gke_rollout(
    *,
    namespace: str,
    deployment: str,
    hpa: str,
    selector: str,
    expected_image: str,
    expected_runtime_project: str,
    dwell_seconds: float,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> None:
    if dwell_seconds < 0 or poll_interval_seconds <= 0 or timeout_seconds <= 0:
        raise ValueError('GKE gate timing values must be positive')
    deadline = time.monotonic() + timeout_seconds
    healthy_since: float | None = None
    stable_signature: tuple[Any, ...] | None = None
    last_errors: list[str] = ['no GKE sample collected']

    while True:
        documents = _load_gke_documents(namespace=namespace, deployment=deployment, hpa=hpa, selector=selector)
        errors = validate_gke_documents(
            *documents,
            expected_image=expected_image,
            expected_runtime_project=expected_runtime_project,
        )
        signature = _gke_stability_signature(*documents)
        now = time.monotonic()
        if errors:
            healthy_since = None
            stable_signature = None
            last_errors = errors
        elif signature != stable_signature:
            stable_signature = signature
            healthy_since = now
            last_errors = []
        elif healthy_since is not None and now - healthy_since >= dwell_seconds:
            print(f'backend-listen remained fully healthy for {dwell_seconds:g}s at image {expected_image}')
            return

        if now >= deadline:
            detail = (
                '; '.join(last_errors) if last_errors else 'healthy state did not remain stable for the dwell window'
            )
            raise RuntimeError(f'GKE rollout gate timed out: {detail}')
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - now)))


def validate_gke_documents(
    deployment: dict[str, Any],
    hpa: dict[str, Any],
    replica_sets: dict[str, Any],
    pods: dict[str, Any],
    *,
    expected_image: str,
    expected_runtime_project: str,
) -> list[str]:
    errors: list[str] = []
    metadata = cast(dict[str, Any], deployment.get('metadata') or {})
    spec = cast(dict[str, Any], deployment.get('spec') or {})
    status = cast(dict[str, Any], deployment.get('status') or {})
    desired = int(spec.get('replicas') or 0)
    generation = int(metadata.get('generation') or 0)
    if int(status.get('observedGeneration') or 0) != generation:
        errors.append('deployment observedGeneration is stale')
    for field in ('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas'):
        if int(status.get(field) or 0) != desired:
            errors.append(f'deployment {field}={int(status.get(field) or 0)} expected={desired}')
    if int(status.get('unavailableReplicas') or 0) != 0:
        errors.append(f'deployment unavailableReplicas={int(status.get("unavailableReplicas") or 0)}')
    if _deployment_image(deployment) != expected_image:
        errors.append(f'deployment image {_deployment_image(deployment) or "missing"} expected={expected_image}')
    observed_runtime_project = _deployment_env_value(deployment, 'GOOGLE_CLOUD_PROJECT')
    if observed_runtime_project != expected_runtime_project:
        errors.append(
            'deployment GOOGLE_CLOUD_PROJECT='
            f'{observed_runtime_project or "missing"} expected={expected_runtime_project}'
        )
    if _condition_status(deployment, 'Available') != 'True':
        errors.append('deployment Available condition is not True')

    hpa_status = cast(dict[str, Any], hpa.get('status') or {})
    if int(hpa_status.get('currentReplicas') or 0) != desired:
        errors.append(f'HPA currentReplicas={int(hpa_status.get("currentReplicas") or 0)} expected={desired}')
    if int(hpa_status.get('desiredReplicas') or 0) != desired:
        errors.append(f'HPA desiredReplicas={int(hpa_status.get("desiredReplicas") or 0)} expected={desired}')
    for condition_type in ('AbleToScale', 'ScalingActive'):
        if _condition_status(hpa, condition_type) != 'True':
            errors.append(f'HPA {condition_type} condition is not True')

    current_rs = 0
    for raw_rs in cast(list[Any], replica_sets.get('items') or []):
        if not isinstance(raw_rs, dict):
            continue
        rs = cast(dict[str, Any], raw_rs)
        rs_spec = cast(dict[str, Any], rs.get('spec') or {})
        rs_status = cast(dict[str, Any], rs.get('status') or {})
        rs_desired = int(rs_spec.get('replicas') or 0)
        rs_actual = int(rs_status.get('replicas') or 0)
        if _deployment_image(rs) == expected_image and rs_desired == desired:
            current_rs += 1
            if int(rs_status.get('readyReplicas') or 0) != desired:
                errors.append('current ReplicaSet is not fully ready')
        elif rs_desired != 0 or rs_actual != 0:
            name = str(cast(dict[str, Any], rs.get('metadata') or {}).get('name') or 'unknown')
            errors.append(f'old ReplicaSet {name} still has desired={rs_desired} actual={rs_actual}')
    if current_rs != 1:
        errors.append(f'expected one current ReplicaSet, observed {current_rs}')

    pod_items = cast(list[Any], pods.get('items') or [])
    if len(pod_items) != desired:
        errors.append(f'pod count={len(pod_items)} expected={desired}')
    for raw_pod in pod_items:
        if not isinstance(raw_pod, dict):
            continue
        pod = cast(dict[str, Any], raw_pod)
        pod_name = str(cast(dict[str, Any], pod.get('metadata') or {}).get('name') or 'unknown')
        pod_status = cast(dict[str, Any], pod.get('status') or {})
        if pod_status.get('phase') != 'Running' or _condition_status(pod, 'Ready') != 'True':
            errors.append(f'pod {pod_name} is not Running and Ready')
        for raw_container in cast(list[Any], pod_status.get('containerStatuses') or []):
            if not isinstance(raw_container, dict):
                continue
            container = cast(dict[str, Any], raw_container)
            state = cast(dict[str, Any], container.get('state') or {})
            if container.get('ready') is not True or 'running' not in state:
                errors.append(f'pod {pod_name} has a non-ready or restarting container')
    return errors


def _validate_candidate_set(
    candidates: list[Candidate],
    *,
    project: str,
    region: str,
    source_sha: str,
    expected_digest: str,
    expected_order: tuple[str, ...] = PROMOTION_ORDER,
) -> dict[str, str]:
    if [candidate.service for candidate in candidates] != list(expected_order):
        raise ValueError('candidates must be the exact required set in promotion order')
    previous: dict[str, str] = {}
    for candidate in candidates:
        revision = _describe_revision(candidate.revision, project=project, region=region)
        service = _describe_service(candidate.service, project=project, region=region)
        _validate_candidate_identity(
            candidate,
            revision=revision,
            service=service,
            source_sha=source_sha,
            expected_digest=expected_digest,
        )
        previous[candidate.service] = _serving_revision(service)
    return previous


def _validate_candidate_identity(
    candidate: Candidate,
    *,
    revision: dict[str, Any],
    service: dict[str, Any],
    source_sha: str,
    expected_digest: str,
) -> None:
    ready = _condition_status(revision, 'Ready')
    if ready != 'True':
        raise RuntimeError(f'{candidate.revision} is not Ready=True (observed {ready or "missing"})')
    observed_digest = _revision_digest(revision)
    if observed_digest != expected_digest:
        raise RuntimeError(
            f'{candidate.revision} image digest {observed_digest or "missing"} does not match {expected_digest}'
        )
    labels = cast(dict[str, Any], cast(dict[str, Any], revision.get('metadata') or {}).get('labels') or {})
    observed_source = str(labels.get('release-source-sha') or labels.get('commit-sha') or '')
    if observed_source != source_sha:
        raise RuntimeError(
            f'{candidate.revision} source label {observed_source or "missing"} does not match {source_sha}'
        )
    latest_created = str(cast(dict[str, Any], service.get('status') or {}).get('latestCreatedRevisionName') or '')
    if latest_created != candidate.revision:
        raise RuntimeError(
            f'{candidate.service} latestCreated={latest_created or "missing"} expected={candidate.revision}'
        )
    serving = _serving_revision(service)
    if serving == candidate.revision or _traffic_percent(service, candidate.revision) != 0:
        raise RuntimeError(f'{candidate.revision} must remain a zero-percent candidate before promotion')
    spec_serving = _serving_revision(service, section='spec')
    if spec_serving != serving:
        raise RuntimeError(f'{candidate.service} spec/status traffic mismatch: spec={spec_serving} status={serving}')


def _remove_candidate_tags(
    attempted: list[Candidate],
    *,
    project: str,
    region: str,
    candidate_tag: str,
    previous: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    for candidate in reversed(attempted):
        command = [
            'gcloud',
            'run',
            'services',
            'update-traffic',
            candidate.service,
            f'--project={project}',
            f'--region={region}',
            f'--remove-tags={candidate_tag}',
            '--quiet',
        ]
        try:
            _run(command)
            service = _describe_service(candidate.service, project=project, region=region)
            _verify_serving_revision(service, candidate.service, previous[candidate.service])
            if _tagged_url(service, candidate_tag, candidate.revision):
                raise RuntimeError('candidate tag still exists after cleanup')
        except RuntimeError as exc:
            errors.append(f'{candidate.service}: {exc}; manual recovery: {shlex.join(command)}')
    return errors


def _rollback_candidates(
    candidates: list[Candidate],
    *,
    previous: dict[str, str],
    project: str,
    region: str,
) -> list[str]:
    errors: list[str] = []
    for candidate in reversed(candidates):
        old_revision = previous[candidate.service]
        command = _traffic_command(candidate.service, old_revision, project=project, region=region)
        try:
            _run(command)
            service = _describe_service(candidate.service, project=project, region=region)
            _verify_serving_revision(service, candidate.service, old_revision)
        except RuntimeError as exc:
            errors.append(f'{candidate.service}: {exc}; manual recovery: {shlex.join(command)}')
    return errors


def _load_gke_documents(
    *, namespace: str, deployment: str, hpa: str, selector: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    common = ['kubectl', '-n', namespace, 'get']
    return (
        _run_json([*common, 'deployment', deployment, '-o', 'json']),
        _run_json([*common, 'hpa', hpa, '-o', 'json']),
        _run_json([*common, 'replicasets', '-l', selector, '-o', 'json']),
        _run_json([*common, 'pods', '-l', selector, '-o', 'json']),
    )


def _gke_stability_signature(
    deployment: dict[str, Any], hpa: dict[str, Any], replica_sets: dict[str, Any], pods: dict[str, Any]
) -> tuple[Any, ...]:
    del replica_sets
    metadata = cast(dict[str, Any], deployment.get('metadata') or {})
    hpa_status = cast(dict[str, Any], hpa.get('status') or {})
    pod_signature: list[tuple[str, int]] = []
    for raw_pod in cast(list[Any], pods.get('items') or []):
        if not isinstance(raw_pod, dict):
            continue
        pod = cast(dict[str, Any], raw_pod)
        name = str(cast(dict[str, Any], pod.get('metadata') or {}).get('name') or '')
        restarts = sum(
            int(container.get('restartCount') or 0)
            for container in cast(
                list[Any], cast(dict[str, Any], pod.get('status') or {}).get('containerStatuses') or []
            )
            if isinstance(container, dict)
        )
        pod_signature.append((name, restarts))
    return (
        int(metadata.get('generation') or 0),
        int(hpa_status.get('desiredReplicas') or 0),
        tuple(sorted(pod_signature)),
    )


def _deployment_image(document: dict[str, Any]) -> str:
    spec = cast(dict[str, Any], document.get('spec') or {})
    template = cast(dict[str, Any], spec.get('template') or {})
    template_spec = cast(dict[str, Any], template.get('spec') or {})
    containers = cast(list[Any], template_spec.get('containers') or [])
    if not containers or not isinstance(containers[0], dict):
        return ''
    return str(containers[0].get('image') or '')


def _deployment_env_value(document: dict[str, Any], name: str) -> str:
    spec = cast(dict[str, Any], document.get('spec') or {})
    template = cast(dict[str, Any], spec.get('template') or {})
    template_spec = cast(dict[str, Any], template.get('spec') or {})
    containers = cast(list[Any], template_spec.get('containers') or [])
    if not containers or not isinstance(containers[0], dict):
        return ''
    for raw_entry in cast(list[Any], containers[0].get('env') or []):
        if isinstance(raw_entry, dict) and raw_entry.get('name') == name:
            return str(raw_entry.get('value') or '')
    return ''


def _condition_status(document: dict[str, Any], condition_type: str) -> str:
    conditions = cast(list[Any], cast(dict[str, Any], document.get('status') or {}).get('conditions') or [])
    for raw_condition in conditions:
        if isinstance(raw_condition, dict) and raw_condition.get('type') == condition_type:
            return str(raw_condition.get('status') or '')
    return ''


def _revision_digest(document: dict[str, Any]) -> str:
    containers = cast(list[Any], document.get('spec', {}).get('containers') or [])
    if not containers or not isinstance(containers[0], dict):
        return ''
    image = str(containers[0].get('image') or '')
    return image.rsplit('@', 1)[-1] if '@' in image else ''


def _describe_revision(revision: str, *, project: str, region: str) -> dict[str, Any]:
    return _run_json(
        [
            'gcloud',
            'run',
            'revisions',
            'describe',
            revision,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ]
    )


def _try_describe_revision(revision: str, *, project: str, region: str) -> dict[str, Any] | None:
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
    if result.returncode == 0:
        try:
            return cast(dict[str, Any], json.loads(result.stdout))
        except json.JSONDecodeError as exc:
            raise RuntimeError('gcloud returned invalid integration revision JSON') from exc
    detail = f'{result.stdout}\n{result.stderr}'.lower()
    if 'not found' in detail or 'cannot find' in detail:
        return None
    raise RuntimeError(f'{shlex.join(command)} failed: {_result_summary(result)}')


def _describe_service(service: str, *, project: str, region: str) -> dict[str, Any]:
    return _run_json(
        [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ]
    )


def _tagged_url(service: dict[str, Any], tag: str, revision: str) -> str:
    traffic = cast(list[Any], cast(dict[str, Any], service.get('status') or {}).get('traffic') or [])
    for raw_target in traffic:
        if isinstance(raw_target, dict) and raw_target.get('tag') == tag and raw_target.get('revisionName') == revision:
            return str(raw_target.get('url') or '')
    return ''


def _traffic_percent(service: dict[str, Any], revision: str, *, section: str = 'status') -> int:
    traffic = cast(list[Any], cast(dict[str, Any], service.get(section) or {}).get('traffic') or [])
    return sum(
        int(target.get('percent') or 0)
        for target in traffic
        if isinstance(target, dict) and target.get('revisionName') == revision
    )


def _serving_revision(service: dict[str, Any], *, section: str = 'status') -> str:
    traffic = cast(list[Any], cast(dict[str, Any], service.get(section) or {}).get('traffic') or [])
    serving = [
        str(target.get('revisionName') or '')
        for target in traffic
        if isinstance(target, dict) and int(target.get('percent') or 0) == 100
    ]
    serving = [revision for revision in serving if revision]
    if len(serving) != 1:
        raise RuntimeError(f'expected exactly one 100% {section} serving revision, observed {serving or "none"}')
    return serving[0]


def _verify_serving_revision(service: dict[str, Any], service_name: str, expected: str) -> None:
    status_revision = _serving_revision(service)
    spec_revision = _serving_revision(service, section='spec')
    if status_revision != expected or spec_revision != expected:
        raise RuntimeError(
            f'{service_name} traffic did not converge to {expected}: spec={spec_revision} status={status_revision}'
        )


def _traffic_command(service: str, revision: str, *, project: str, region: str) -> list[str]:
    return [
        'gcloud',
        'run',
        'services',
        'update-traffic',
        service,
        f'--project={project}',
        f'--region={region}',
        f'--to-revisions={revision}=100',
        '--quiet',
    ]


def _set_traffic(service: str, revision: str, *, project: str, region: str) -> None:
    _run(_traffic_command(service, revision, project=project, region=region))


def _identity_token(audience: str) -> str:
    token = _run_text(['gcloud', 'auth', 'print-identity-token', f'--audiences={audience}']).strip()
    if not token:
        raise RuntimeError(f'failed to mint an identity token for {audience}')
    return token


def _http_status(url: str, *, token: str | None = None, attempts: int = 12) -> int:
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    last_status = 0
    for attempt in range(attempts):
        try:
            with request.urlopen(request.Request(url, headers=headers), timeout=20) as response:
                last_status = int(response.status)
        except error.HTTPError as exc:
            last_status = int(exc.code)
        except error.URLError:
            last_status = 0
        if last_status in {200, 405}:
            return last_status
        if attempt + 1 < attempts:
            time.sleep(5)
    return last_status


def _http_json(url: str, *, token: str | None = None, attempts: int = 12) -> dict[str, Any]:
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    last_error = 'unknown error'
    for attempt in range(attempts):
        try:
            with request.urlopen(request.Request(url, headers=headers), timeout=20) as response:
                return cast(dict[str, Any], json.load(response))
        except (error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        if attempt + 1 < attempts:
            time.sleep(5)
    raise RuntimeError(f'failed to read JSON from {url}: {last_error}')


def _validate_source_sha(value: str) -> None:
    if not SOURCE_SHA_RE.fullmatch(value):
        raise ValueError('source SHA must be exactly 40 lowercase hexadecimal characters')


def _validate_digest(value: str) -> None:
    if not DIGEST_RE.fullmatch(value):
        raise ValueError('expected digest must be an immutable sha256:<64 lowercase hex> child digest')


def _validate_candidate_tag(value: str) -> None:
    if not TAG_RE.fullmatch(value):
        raise ValueError('candidate tag must be a lowercase Cloud Run tag starting with a letter')


def _run(command: list[str]) -> None:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'{shlex.join(command)} failed: {_result_summary(result)}')


def _run_text(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'{shlex.join(command)} failed: {_result_summary(result)}')
    return result.stdout


def _run_json(command: list[str]) -> dict[str, Any]:
    output = _run_text(command)
    try:
        return cast(dict[str, Any], json.loads(output))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{command[0]} returned invalid JSON') from exc


def _result_summary(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout).strip().splitlines()
    return detail[-1] if detail else f'exit code {result.returncode}'


if __name__ == '__main__':
    raise SystemExit(main())

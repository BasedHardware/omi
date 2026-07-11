#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

DEFAULT_REGION = 'us-central1'
DEFAULT_GKE_SERVICES = (
    'backend-listen',
    'pusher',
    'llm-gateway',
    'agent-proxy',
    'parakeet',
    'diarizer',
    'vad',
)
DEFAULT_CLOUD_RUN_SERVICES = (
    'backend',
    'backend-sync',
    'backend-sync-backfill',
    'backend-integration',
    'desktop-backend',
)
BAD_WAITING_REASONS = {'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull', 'CreateContainerConfigError'}


@dataclass(frozen=True)
class Finding:
    severity: str
    scope: str
    message: str


@dataclass(frozen=True)
class CloudRunFetchError:
    service: str
    exit_code: int


def main() -> int:
    parser = argparse.ArgumentParser(description='Read-only deploy rollout/status reporter for Omi services.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--project', help='GCP project id for live Cloud Run reads.')
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--namespace', help='Kubernetes namespace. Defaults to <env>-omi-backend.')
    parser.add_argument('--include-gke', action='store_true')
    parser.add_argument('--include-cloud-run', action='store_true')
    parser.add_argument('--gke-service', action='append', dest='gke_services')
    parser.add_argument('--cloud-run-service', action='append', dest='cloud_run_services')
    parser.add_argument('--stale-rs-threshold-minutes', type=int, default=15)
    parser.add_argument('--expect-cloud-run-traffic', action='append', default=[], metavar='SERVICE=REVISION')
    parser.add_argument('--k8s-state', type=Path, help='Offline Kubernetes state JSON fixture.')
    parser.add_argument('--cloud-run-state', type=Path, help='Offline Cloud Run state JSON fixture.')
    parser.add_argument('--now', help='ISO timestamp used by tests for age calculations.')
    args = parser.parse_args()

    include_gke = args.include_gke or bool(args.k8s_state)
    include_cloud_run = args.include_cloud_run or bool(args.cloud_run_state)
    if not include_gke and not include_cloud_run:
        include_gke = True
        include_cloud_run = True

    now = parse_timestamp(args.now) if args.now else datetime.now(timezone.utc)
    namespace = args.namespace or f'{args.env}-omi-backend'
    findings: list[Finding] = []
    sections: list[str] = []

    if include_gke:
        k8s_state = load_json(args.k8s_state) if args.k8s_state else fetch_k8s_state(namespace)
        gke_services = cast(list[str], args.gke_services or list(DEFAULT_GKE_SERVICES))
        section, gke_findings = render_gke_report(
            k8s_state,
            namespace=namespace,
            services=gke_services,
            now=now,
            stale_rs_threshold_minutes=args.stale_rs_threshold_minutes,
        )
        sections.append(section)
        findings.extend(gke_findings)

    if include_cloud_run:
        if args.cloud_run_state:
            cloud_run_state = load_json(args.cloud_run_state)
        else:
            if not args.project:
                print('--project is required for live Cloud Run reads', file=sys.stderr)
                return 2
            cloud_run_state = fetch_cloud_run_state(
                project=args.project,
                region=args.region,
                services=args.cloud_run_services or list(DEFAULT_CLOUD_RUN_SERVICES),
            )
        cloud_run_services = cast(list[str], args.cloud_run_services or list(DEFAULT_CLOUD_RUN_SERVICES))
        expected_traffic = parse_expected_traffic(args.expect_cloud_run_traffic)
        report_project = args.project or ''
        report_region = args.region
        section, cloud_findings = render_cloud_run_report(
            cloud_run_state,
            services=cloud_run_services,
            expected_traffic=expected_traffic,
            project=report_project,
            region=report_region,
        )
        sections.append(section)
        findings.extend(cloud_findings)

    print('\n\n'.join(sections))
    if findings:
        print('\nFindings')
        for finding in findings:
            print(f'- {finding.severity} [{finding.scope}] {finding.message}')

    return 1 if any(f.severity == 'FAIL' for f in findings) else 0


def render_gke_report(
    state: dict[str, Any],
    *,
    namespace: str,
    services: list[str],
    now: datetime,
    stale_rs_threshold_minutes: int,
) -> tuple[str, list[Finding]]:
    deployments = items_by_name(state.get('deployments'))
    replica_sets = state.get('replicaSets', [])
    pods = state.get('pods', [])
    events = state.get('events', [])
    lines = [
        f'GKE rollout status ({namespace})',
        '| Deployment | Desired | Updated | Available | Image | Status |',
        '|---|---:|---:|---:|---|---|',
    ]
    findings: list[Finding] = []
    release_prefix = namespace.removesuffix('-backend')

    for service in services:
        deployment_name = service if service.startswith(release_prefix) else f'{release_prefix}-{service}'
        if service == 'backend-listen':
            deployment_name = f'{release_prefix}-backend-listen'
        deployment = deployments.get(deployment_name)
        if not deployment:
            lines.append(f'| `{deployment_name}` | - | - | - | - | missing |')
            findings.append(Finding('WARN', deployment_name, 'deployment not found in report input'))
            continue

        spec = deployment.get('spec', {})
        metadata = deployment.get('metadata', {})
        status = deployment.get('status', {})
        desired = int(spec.get('replicas') or 0)
        updated = int(status.get('updatedReplicas') or 0)
        available = int(status.get('availableReplicas') or 0)
        unavailable = int(status.get('unavailableReplicas') or 0)
        generation = int(metadata.get('generation') or 0)
        observed_generation = int(status.get('observedGeneration') or 0)
        image = first_container_image(deployment)
        deploy_status = 'ok'
        if desired and (updated < desired or available < desired):
            deploy_status = 'degraded'
            findings.append(
                Finding(
                    'FAIL',
                    deployment_name,
                    f'rollout incomplete: desired={desired} updated={updated} available={available}',
                )
            )
        if unavailable > 0:
            deploy_status = 'degraded'
            findings.append(Finding('FAIL', deployment_name, f'unavailable replicas remain: {unavailable}'))
        if generation and observed_generation < generation:
            deploy_status = 'stale-controller'
            findings.append(
                Finding(
                    'FAIL',
                    deployment_name,
                    f'controller has not observed latest generation: generation={generation} observed={observed_generation}',
                )
            )
        lines.append(f'| `{deployment_name}` | {desired} | {updated} | {available} | `{image}` | {deploy_status} |')

        findings.extend(find_bad_pods(deployment_name, pods))
        findings.extend(
            find_stale_replica_sets(
                deployment,
                replica_sets,
                now=now,
                threshold_minutes=stale_rs_threshold_minutes,
            )
        )

    event_lines = summarize_events(events)
    lines.extend(['', 'Recent warning events'])
    lines.extend(event_lines or ['- none'])
    return '\n'.join(lines), findings


def render_cloud_run_report(
    state: dict[str, Any],
    *,
    services: list[str],
    expected_traffic: dict[str, str],
    project: str = '',
    region: str = DEFAULT_REGION,
) -> tuple[str, list[Finding]]:
    project = project or str(state.get('project') or '')
    region = str(state.get('region') or region)
    service_map = normalize_cloud_run_services(state)
    fetch_errors = cloud_run_fetch_errors_by_service(state)
    lines = [
        'Cloud Run revision status',
        '| Service | Latest created | Latest ready | Spec traffic | Status traffic | Template image | Status |',
        '|---|---|---|---|---|---|---|',
    ]
    findings: list[Finding] = []

    for service_name in services:
        service = service_map.get(service_name)
        if not service:
            lines.append(f'| `{service_name}` | - | - | - | - | - | missing |')
            fetch_error = fetch_errors.get(service_name)
            if fetch_error:
                findings.append(
                    Finding(
                        'FAIL',
                        service_name,
                        f'gcloud run services describe failed with exit code {fetch_error.exit_code}',
                    )
                )
            elif service_name in expected_traffic:
                findings.append(
                    Finding(
                        'FAIL',
                        service_name,
                        f'expected revision {expected_traffic[service_name]} to serve 100% traffic, but service data is missing',
                    )
                )
            else:
                findings.append(Finding('WARN', service_name, 'Cloud Run service not found in report input'))
            continue

        status = service.get('status', {})
        spec = service.get('spec', {})
        latest_created = str(status.get('latestCreatedRevisionName') or '')
        latest_ready = str(status.get('latestReadyRevisionName') or '')
        status_traffic = cast(list[Any], status.get('traffic') or [])
        spec_traffic = cast(list[Any], spec.get('traffic') or [])
        status_traffic_text = format_cloud_run_traffic(status_traffic)
        spec_traffic_text = format_cloud_run_traffic(spec_traffic)
        image = cloud_run_image(service)
        ready_status = 'ok' if latest_ready and latest_ready == latest_created else 'not-ready'
        findings.extend(
            traffic_spec_status_findings(
                service_name=service_name,
                spec_traffic=spec_traffic,
                status_traffic=status_traffic,
                project=project,
                region=region,
                latest_ready_revision=latest_ready,
            )
        )
        if latest_created and latest_ready != latest_created:
            findings.append(
                Finding(
                    'FAIL',
                    service_name,
                    f'latest created revision {latest_created} is not latest ready ({latest_ready or "missing"})',
                )
            )

        expected_revision = expected_traffic.get(service_name)
        if expected_revision:
            served = traffic_percent_for_revision(status_traffic, expected_revision)
            if served != 100:
                findings.append(
                    Finding(
                        'FAIL',
                        service_name,
                        f'expected revision {expected_revision} to serve 100% traffic, observed {served}%',
                    )
                )
            elif latest_ready != expected_revision:
                findings.append(
                    Finding(
                        'FAIL',
                        service_name,
                        f'expected served revision {expected_revision} to be latest ready, observed {latest_ready or "missing"}',
                    )
                )

        lines.append(
            f'| `{service_name}` | `{latest_created or "-"}` | `{latest_ready or "-"}` | {spec_traffic_text} | {status_traffic_text} | `{image}` | {ready_status} |'
        )

    return '\n'.join(lines), findings


def traffic_spec_status_findings(
    *,
    service_name: str,
    spec_traffic: list[Any],
    status_traffic: list[Any],
    project: str,
    region: str,
    latest_ready_revision: str = '',
) -> list[Finding]:
    findings: list[Finding] = []
    spec_revision = primary_traffic_revision(spec_traffic, fallback_revision=latest_ready_revision)
    status_revision = primary_traffic_revision(status_traffic, fallback_revision=latest_ready_revision)
    if spec_revision and status_revision and spec_revision != status_revision:
        repair_command = format_traffic_repair_command(
            service=service_name,
            revision=status_revision,
            project=project,
            region=region,
        )
        findings.append(
            Finding(
                'FAIL',
                service_name,
                f'spec.traffic ({spec_revision}) != status.traffic ({status_revision}); repair: {repair_command}',
            )
        )
    return findings


def primary_traffic_revision(traffic: list[Any], *, fallback_revision: str = '') -> str | None:
    for raw_target in traffic:
        if not isinstance(raw_target, dict):
            continue
        target = cast(dict[str, Any], raw_target)
        if int(target.get('percent') or 0) != 100:
            continue
        revision_name = target.get('revisionName')
        if isinstance(revision_name, str) and revision_name:
            return revision_name
        if target.get('latestRevision') and fallback_revision:
            return fallback_revision
    return None


def format_traffic_repair_command(*, service: str, revision: str, project: str, region: str) -> str:
    project_flag = f' --project={project}' if project else ''
    return (
        f'gcloud run services update-traffic {service}{project_flag} '
        f'--region={region} --to-revisions={revision}=100 --quiet'
    )


def find_bad_pods(deployment_name: str, pods: Any) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(pods, list):
        return findings
    for raw_pod in cast(list[Any], pods):
        if not isinstance(raw_pod, dict):
            continue
        pod = cast(dict[str, Any], raw_pod)
        if owner_name(pod) != deployment_name and deployment_name not in pod_name(pod):
            continue
        statuses = cast(list[Any], pod.get('status', {}).get('containerStatuses') or [])
        for status in statuses:
            status = cast(dict[str, Any], status)
            state = cast(dict[str, Any], status.get('state') or {})
            waiting = cast(dict[str, Any], state.get('waiting') or {})
            reason = waiting.get('reason')
            if reason in BAD_WAITING_REASONS:
                findings.append(Finding('FAIL', pod_name(pod), f'container waiting reason {reason}'))
    return findings


def find_stale_replica_sets(
    deployment: dict[str, Any],
    replica_sets: Any,
    *,
    now: datetime,
    threshold_minutes: int,
) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(replica_sets, list):
        return findings
    deployment_name = object_name(deployment)
    current_revision = deployment.get('metadata', {}).get('annotations', {}).get('deployment.kubernetes.io/revision')
    for rs in cast(list[Any], replica_sets):
        if not isinstance(rs, dict):
            continue
        rs_dict = cast(dict[str, Any], rs)
        if owner_name(rs_dict) != deployment_name:
            continue
        replicas = int(rs_dict.get('status', {}).get('replicas') or 0)
        if replicas <= 0:
            continue
        rs_revision = rs_dict.get('metadata', {}).get('annotations', {}).get('deployment.kubernetes.io/revision')
        if current_revision and rs_revision == current_revision:
            continue
        age_minutes = age_in_minutes(rs_dict.get('metadata', {}).get('creationTimestamp'), now)
        if age_minutes is not None and age_minutes >= threshold_minutes:
            findings.append(
                Finding(
                    'WARN',
                    object_name(rs_dict),
                    f'old ReplicaSet still has {replicas} replica(s) after {age_minutes}m',
                )
            )
    return findings


def summarize_events(events: Any) -> list[str]:
    if not isinstance(events, list):
        return []
    counter: Counter[tuple[str, str]] = Counter()
    for raw_event in cast(list[Any], events):
        if not isinstance(raw_event, dict):
            continue
        event = cast(dict[str, Any], raw_event)
        event_type = event.get('type') or event.get('regarding', {}).get('type')
        if event_type and event_type != 'Warning':
            continue
        reason = str(event.get('reason') or 'Unknown')
        message = str(event.get('message') or '').replace('\n', ' ')
        counter[(reason, message[:140])] += int(event.get('count') or 1)
    return [f'- {count}x `{reason}`: {message}' for (reason, message), count in counter.most_common(8)]


def fetch_k8s_state(namespace: str) -> dict[str, Any]:
    return {
        'deployments': kubectl_json(namespace, 'deployments').get('items', []),
        'replicaSets': kubectl_json(namespace, 'replicasets').get('items', []),
        'pods': kubectl_json(namespace, 'pods').get('items', []),
        'events': kubectl_json(namespace, 'events').get('items', []),
    }


def fetch_cloud_run_state(*, project: str, region: str, services: list[str]) -> dict[str, Any]:
    fetched: list[Any] = []
    errors: list[dict[str, Any]] = []
    for service in services:
        command = [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            fetched.append(json.loads(result.stdout))
        else:
            errors.append({'service': service, 'exitCode': result.returncode})
    return {'services': fetched, 'errors': errors, 'project': project, 'region': region}


def kubectl_json(namespace: str, resource: str) -> dict[str, Any]:
    result = subprocess.run(
        ['kubectl', '-n', namespace, 'get', resource, '-o', 'json'],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return cast(dict[str, Any], loaded)


def parse_expected_traffic(entries: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        if '=' not in entry:
            raise ValueError(f'expected traffic entry must be SERVICE=REVISION: {entry}')
        service, revision = entry.split('=', 1)
        result[service] = revision
    return result


def normalize_cloud_run_services(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_services = state.get('services', [])
    if isinstance(raw_services, dict):
        services_map = cast(dict[str, Any], raw_services)
        return {
            str(name): cast(dict[str, Any], service)
            for name, service in services_map.items()
            if isinstance(service, dict)
        }
    if not isinstance(raw_services, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw_service in cast(list[Any], raw_services):
        if not isinstance(raw_service, dict):
            continue
        service = cast(dict[str, Any], raw_service)
        name = object_name(service)
        if name:
            result[name] = service
    return result


def cloud_run_fetch_errors_by_service(state: dict[str, Any]) -> dict[str, CloudRunFetchError]:
    raw_errors = state.get('errors') or state.get('fetchErrors')
    if not isinstance(raw_errors, list):
        return {}
    result: dict[str, CloudRunFetchError] = {}
    for raw_error in cast(list[Any], raw_errors):
        if not isinstance(raw_error, dict):
            continue
        error = cast(dict[str, Any], raw_error)
        service = str(error.get('service') or '')
        if not service:
            continue
        result[service] = CloudRunFetchError(service=service, exit_code=int(error.get('exitCode') or 1))
    return result


def items_by_name(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw_item in cast(list[Any], items):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        name = object_name(item)
        if name:
            result[name] = item
    return result


def object_name(obj: dict[str, Any]) -> str:
    return str(obj.get('metadata', {}).get('name') or '')


def pod_name(pod: dict[str, Any]) -> str:
    return object_name(pod)


def owner_name(obj: dict[str, Any]) -> str:
    owners = obj.get('metadata', {}).get('ownerReferences')
    if isinstance(owners, list) and owners:
        first = cast(list[Any], owners)[0]
        if isinstance(first, dict):
            return str(cast(dict[str, Any], first).get('name') or '')
    return ''


def first_container_image(deployment: dict[str, Any]) -> str:
    containers = cast(list[Any], deployment.get('spec', {}).get('template', {}).get('spec', {}).get('containers') or [])
    if containers and isinstance(containers[0], dict):
        return str(cast(dict[str, Any], containers[0]).get('image') or '-')
    return '-'


def cloud_run_image(service: dict[str, Any]) -> str:
    containers = cast(list[Any], service.get('spec', {}).get('template', {}).get('spec', {}).get('containers') or [])
    image = '-'
    if containers and isinstance(containers[0], dict):
        first = cast(dict[str, Any], containers[0])
        image = str(first.get('image') or '-')
        digest = first.get('imageDigest')
        if isinstance(digest, str) and digest:
            return f'{image}@{digest}'
    digest = service.get('status', {}).get('imageDigest')
    if isinstance(digest, str) and digest:
        return f'{image}@{digest}'
    return image


def format_cloud_run_traffic(traffic: Any) -> str:
    if not isinstance(traffic, list) or not traffic:
        return '-'
    parts: list[str] = []
    for raw_target in cast(list[Any], traffic):
        if not isinstance(raw_target, dict):
            continue
        target = cast(dict[str, Any], raw_target)
        revision = target.get('revisionName') or ('latest' if target.get('latestRevision') else '-')
        parts.append(f'`{revision}`={int(target.get("percent") or 0)}%')
    return ', '.join(parts) or '-'


def traffic_percent_for_revision(traffic: Any, revision: str) -> int:
    if not isinstance(traffic, list):
        return 0
    total = 0
    for raw_target in cast(list[Any], traffic):
        if not isinstance(raw_target, dict):
            continue
        target = cast(dict[str, Any], raw_target)
        if target.get('revisionName') == revision:
            total += int(target.get('percent') or 0)
    return total


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_in_minutes(timestamp: Any, now: datetime) -> int | None:
    if not isinstance(timestamp, str) or not timestamp:
        return None
    created_at = parse_timestamp(timestamp)
    return int((now - created_at).total_seconds() // 60)


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, cast

DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-integration')


@dataclass(frozen=True)
class TrafficTarget:
    revision_name: str | None
    percent: int
    latest_revision: bool


@dataclass(frozen=True)
class ServiceTrafficState:
    service: str
    serving_revision: str | None
    spec_revision: str | None
    status_revision: str | None
    mismatched: bool


@dataclass(frozen=True)
class RepairResult:
    service: str
    action: str
    serving_revision: str | None
    spec_revision: str | None


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Detect and repair Cloud Run spec.traffic vs status.traffic mismatches.'
    )
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--service', action='append', dest='services')
    parser.add_argument('--repair', action='store_true', help='Apply traffic repair to serving revisions.')
    parser.add_argument('--state', help='Offline Cloud Run services JSON list/object for tests.')
    args = parser.parse_args()

    services = tuple(args.services or DEFAULT_SERVICES)
    if args.state:
        state = _load_state(args.state)
        results = repair_from_state(
            state,
            services=services,
            repair=args.repair,
            project=args.project,
            region=args.region,
        )
    else:
        results = repair_live(
            project=args.project,
            region=args.region,
            services=services,
            repair=args.repair,
        )

    exit_code = 0
    for result in results:
        print(_format_result(result))
        if result.action == 'failed':
            exit_code = 1
    return exit_code


def repair_live(
    *,
    project: str,
    region: str,
    services: tuple[str, ...],
    repair: bool,
) -> list[RepairResult]:
    results: list[RepairResult] = []
    for service in services:
        try:
            service_doc = _fetch_service(project=project, region=region, service=service)
        except subprocess.CalledProcessError as exc:
            print(f'ERROR [{service}]: gcloud describe failed with exit code {exc.returncode}', file=sys.stderr)
            results.append(RepairResult(service=service, action='failed', serving_revision=None, spec_revision=None))
            continue
        try:
            results.append(
                _repair_service_doc(service_doc, service=service, project=project, region=region, repair=repair)
            )
        except subprocess.CalledProcessError as exc:
            print(f'ERROR [{service}]: traffic repair failed with exit code {exc.returncode}', file=sys.stderr)
            state = analyze_service_traffic(service_doc, service=service)
            results.append(
                RepairResult(
                    service=service,
                    action='failed',
                    serving_revision=state.serving_revision,
                    spec_revision=state.spec_revision,
                )
            )
    return results


def repair_from_state(
    state: dict[str, Any],
    *,
    services: tuple[str, ...],
    repair: bool,
    project: str = 'example',
    region: str = DEFAULT_REGION,
) -> list[RepairResult]:
    service_map = _normalize_services(state)
    results: list[RepairResult] = []
    for service in services:
        service_doc = service_map.get(service)
        if service_doc is None:
            results.append(
                RepairResult(
                    service=service,
                    action='failed',
                    serving_revision=None,
                    spec_revision=None,
                )
            )
            continue
        results.append(_repair_service_doc(service_doc, service=service, project=project, region=region, repair=repair))
    return results


def analyze_service_traffic(service_doc: dict[str, Any], *, service: str) -> ServiceTrafficState:
    status_traffic = cast(list[Any], service_doc.get('status', {}).get('traffic') or [])
    spec_traffic = cast(list[Any], service_doc.get('spec', {}).get('traffic') or [])
    status = service_doc.get('status', {})
    latest_ready = str(status.get('latestReadyRevisionName') or '')
    serving_revision = _primary_revision(status_traffic, fallback_revision=latest_ready)
    spec_revision = _primary_revision(spec_traffic, fallback_revision=latest_ready)
    mismatched = bool(serving_revision and spec_revision and serving_revision != spec_revision)
    return ServiceTrafficState(
        service=service,
        serving_revision=serving_revision,
        spec_revision=spec_revision,
        status_revision=serving_revision,
        mismatched=mismatched,
    )


def repair_command(*, project: str, region: str, service: str, revision: str) -> str:
    return (
        f'gcloud run services update-traffic {service} '
        f'--project={project} --region={region} --to-revisions={revision}=100 --quiet'
    )


def _repair_service_doc(
    service_doc: dict[str, Any],
    *,
    service: str,
    project: str,
    region: str,
    repair: bool,
) -> RepairResult:
    state = analyze_service_traffic(service_doc, service=service)
    if not state.serving_revision:
        return RepairResult(
            service=service,
            action='skipped_no_serving_revision',
            serving_revision=None,
            spec_revision=state.spec_revision,
        )
    if not state.mismatched:
        return RepairResult(
            service=service,
            action='already_aligned',
            serving_revision=state.serving_revision,
            spec_revision=state.spec_revision,
        )

    command = repair_command(
        project=project,
        region=region,
        service=service,
        revision=state.serving_revision,
    )
    if not repair:
        print(
            f'ERROR [{service}]: spec.traffic={state.spec_revision!r} status.traffic={state.serving_revision!r}',
            file=sys.stderr,
        )
        print(f'Repair command: {command}', file=sys.stderr)
        return RepairResult(
            service=service,
            action='failed',
            serving_revision=state.serving_revision,
            spec_revision=state.spec_revision,
        )

    subprocess.run(command.split(), check=True)
    return RepairResult(
        service=service,
        action='repaired',
        serving_revision=state.serving_revision,
        spec_revision=state.spec_revision,
    )


def _format_result(result: RepairResult) -> str:
    if result.action == 'already_aligned':
        return f'{result.service}: spec already points to serving revision {result.serving_revision}'
    if result.action == 'skipped_no_serving_revision':
        return f'{result.service}: no concrete serving revision found; skipping'
    if result.action == 'repaired':
        return (
            f'{result.service}: restored spec traffic from {result.spec_revision} '
            f'to currently serving {result.serving_revision}'
        )
    if result.action == 'failed':
        return f'{result.service}: traffic mismatch requires repair'
    return f'{result.service}: {result.action}'


def _primary_revision(traffic: list[Any], *, fallback_revision: str = '') -> str | None:
    for raw_target in traffic:
        if not isinstance(raw_target, dict):
            continue
        target = cast(dict[str, Any], raw_target)
        percent = int(target.get('percent') or 0)
        if percent != 100:
            continue
        revision_name = target.get('revisionName')
        if isinstance(revision_name, str) and revision_name:
            return revision_name
        if target.get('latestRevision') and fallback_revision:
            return fallback_revision
    return None


def _fetch_service(*, project: str, region: str, service: str) -> dict[str, Any]:
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
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return cast(dict[str, Any], json.loads(result.stdout))


def _load_state(path: str) -> dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        loaded = json.load(handle)
    if isinstance(loaded, list):
        return {'services': loaded}
    if not isinstance(loaded, dict):
        raise ValueError('state file must contain a JSON object or list of services')
    return loaded


def _normalize_services(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_services = state.get('services', [])
    if isinstance(raw_services, dict):
        return {
            str(name): cast(dict[str, Any], service)
            for name, service in raw_services.items()
            if isinstance(service, dict)
        }
    if not isinstance(raw_services, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw_service in raw_services:
        if not isinstance(raw_service, dict):
            continue
        service = cast(dict[str, Any], raw_service)
        name = str(service.get('metadata', {}).get('name') or '')
        if name:
            result[name] = service
    return result


if __name__ == '__main__':
    raise SystemExit(main())

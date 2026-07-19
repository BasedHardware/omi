#!/usr/bin/env python3
"""Capture and restore the four backend Cloud Run services' traffic specifications.

The capture deliberately records only traffic-routing metadata. Cloud Run service
documents also contain environment values and Secret Manager references, neither
of which belongs in deployment evidence artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
SNAPSHOT_SCHEMA_VERSION = 1

RunCommand = Callable[[Sequence[str]], None]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _traffic_entries(value: Any) -> list[dict[str, Any]]:
    """Keep only routing fields that are safe and sufficient for restoration."""
    entries: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return entries
    for raw_entry in value:
        entry = _mapping(raw_entry)
        revision = entry.get('revisionName')
        latest = entry.get('latestRevision')
        percent = entry.get('percent')
        if not isinstance(percent, int) or isinstance(percent, bool) or not 0 <= percent <= 100:
            continue
        if not (isinstance(revision, str) and revision) and latest is not True:
            continue
        sanitized: dict[str, Any] = {'percent': percent}
        if isinstance(revision, str) and revision:
            sanitized['revisionName'] = revision
        if latest is True:
            sanitized['latestRevision'] = True
        entries.append(sanitized)
    return entries


def sanitize_service_document(service: str, document: Mapping[str, Any]) -> dict[str, Any]:
    """Produce a bounded artifact with no Cloud Run template or secret data."""
    spec = _mapping(document.get('spec'))
    status = _mapping(document.get('status'))
    latest_ready = status.get('latestReadyRevisionName')
    latest_created = status.get('latestCreatedRevisionName')
    return {
        'service': service,
        'spec': {'traffic': _traffic_entries(spec.get('traffic'))},
        'status': {
            'traffic': _traffic_entries(status.get('traffic')),
            'latestReadyRevisionName': latest_ready if isinstance(latest_ready, str) and latest_ready else None,
            'latestCreatedRevisionName': latest_created if isinstance(latest_created, str) and latest_created else None,
        },
    }


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
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    loaded = json.loads(completed.stdout)
    if not isinstance(loaded, dict):
        raise ValueError(f'{service}: Cloud Run describe returned a non-object JSON document')
    return cast(dict[str, Any], loaded)


def capture_snapshot(
    *,
    project: str,
    region: str,
    services: Sequence[str],
    fetcher: Callable[..., Mapping[str, Any]] = _fetch_service,
) -> dict[str, Any]:
    """Capture only the durable routing state needed to undo a promotion."""
    if not services:
        raise ValueError('at least one Cloud Run service is required')
    if len(set(services)) != len(services):
        raise ValueError('Cloud Run services must not be repeated')
    captured = {
        service: sanitize_service_document(service, fetcher(project=project, region=region, service=service))
        for service in services
    }
    for service, service_snapshot in captured.items():
        try:
            restore_targets(service_snapshot)
        except ValueError as exc:
            raise ValueError(f'{service}: cannot capture a restorable traffic snapshot: {exc}') from exc
    return {
        'schema_version': SNAPSHOT_SCHEMA_VERSION,
        'scope': 'backend Cloud Run pre-promotion traffic snapshot',
        'captured_at': datetime.now(UTC).isoformat(),
        'project': project,
        'region': region,
        'services': captured,
    }


def _load_snapshot(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'could not read traffic snapshot {path}: {exc}') from exc
    if not isinstance(loaded, dict):
        raise ValueError('traffic snapshot must be a JSON object')
    if loaded.get('schema_version') != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError('traffic snapshot has an unsupported schema version')
    if not isinstance(loaded.get('project'), str) or not loaded['project']:
        raise ValueError('traffic snapshot is missing project')
    if not isinstance(loaded.get('region'), str) or not loaded['region']:
        raise ValueError('traffic snapshot is missing region')
    if not isinstance(loaded.get('services'), dict) or not loaded['services']:
        raise ValueError('traffic snapshot is missing services')
    return cast(dict[str, Any], loaded)


def restore_targets(service_snapshot: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Resolve a recorded spec.traffic entry to immutable revision percentages."""
    spec = _mapping(service_snapshot.get('spec'))
    status = _mapping(service_snapshot.get('status'))
    fallback = status.get('latestReadyRevisionName')
    targets: list[tuple[str, int]] = []
    seen: set[str] = set()
    for entry in _traffic_entries(spec.get('traffic')):
        percent = cast(int, entry['percent'])
        if percent == 0:
            continue
        revision = entry.get('revisionName')
        if not isinstance(revision, str) or not revision:
            if entry.get('latestRevision') is True and isinstance(fallback, str) and fallback:
                revision = fallback
            else:
                raise ValueError('snapshot has a latestRevision traffic target without a captured ready revision')
        if revision in seen:
            raise ValueError(f'snapshot repeats traffic target {revision}')
        seen.add(revision)
        targets.append((revision, percent))
    if not targets or sum(percent for _, percent in targets) != 100:
        raise ValueError('snapshot traffic targets must resolve to exactly 100 percent')
    return targets


def restore_command(*, project: str, region: str, service: str, targets: Sequence[tuple[str, int]]) -> list[str]:
    rendered_targets = ','.join(f'{revision}={percent}' for revision, percent in targets)
    return [
        'gcloud',
        'run',
        'services',
        'update-traffic',
        service,
        f'--project={project}',
        f'--region={region}',
        f'--to-revisions={rendered_targets}',
        '--quiet',
    ]


def restore_snapshot(
    snapshot: Mapping[str, Any],
    *,
    runner: RunCommand | None = None,
) -> dict[str, Any]:
    """Restore every recorded traffic spec, retaining bounded per-service evidence."""
    project = cast(str, snapshot['project'])
    region = cast(str, snapshot['region'])
    services = cast(Mapping[str, Any], snapshot['services'])
    execute = runner or (lambda command: subprocess.run(command, check=True, capture_output=True, text=True))
    results: dict[str, dict[str, Any]] = {}
    for service, raw_service_snapshot in services.items():
        if not isinstance(service, str) or not service:
            raise ValueError('traffic snapshot contains an invalid service name')
        if not isinstance(raw_service_snapshot, Mapping):
            raise ValueError(f'{service}: traffic snapshot service entry is invalid')
        targets = restore_targets(raw_service_snapshot)
        command = restore_command(project=project, region=region, service=service, targets=targets)
        result: dict[str, Any] = {
            'targets': [{'revision': revision, 'percent': percent} for revision, percent in targets],
            'command': ' '.join(command),
        }
        try:
            execute(command)
        except subprocess.CalledProcessError as exc:
            result.update({'result': 'failed', 'error': f'gcloud exited with code {exc.returncode}'})
        else:
            result['result'] = 'restored'
        results[service] = result
    failures = [service for service, result in results.items() if result['result'] != 'restored']
    return {
        'schema_version': SNAPSHOT_SCHEMA_VERSION,
        'scope': 'backend Cloud Run traffic restoration',
        'snapshot_sha256': _snapshot_digest(snapshot),
        'result': 'pass' if not failures else 'fail',
        'failed_services': failures,
        'services': results,
    }


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{json.dumps(value, indent=2, sort_keys=True)}\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('capture', help='capture a sanitized pre-promotion Cloud Run traffic snapshot')
    capture.add_argument('--project', required=True)
    capture.add_argument('--region', default=DEFAULT_REGION)
    capture.add_argument('--service', action='append', dest='services', default=[])
    capture.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore', help='restore Cloud Run traffic from a recorded snapshot')
    restore.add_argument('--snapshot', type=Path, required=True)
    restore.add_argument('--evidence-path', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            snapshot = capture_snapshot(
                project=args.project,
                region=args.region,
                services=tuple(args.services or DEFAULT_SERVICES),
            )
            _write_json(args.output, snapshot)
            print(f'captured sanitized Cloud Run traffic snapshot at {args.output}')
            return 0
        snapshot = _load_snapshot(args.snapshot)
        evidence = restore_snapshot(snapshot)
        _write_json(args.evidence_path, evidence)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if evidence['result'] == 'pass' else 1
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

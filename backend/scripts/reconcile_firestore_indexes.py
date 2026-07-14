#!/usr/bin/env python3
"""Deploy the generated Firestore index manifest and wait until every index is READY."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from database.firestore_index_registry import firebase_index_manifest  # noqa: E402

DEFAULT_DATABASE = '(default)'
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_POLL_INTERVAL_SECONDS = 10.0

IndexSignature = tuple[str, str, tuple[tuple[str, str], ...]]
CommandRunner = Callable[..., Any]


def _collection_group_from_resource_name(index: Mapping[str, Any]) -> str:
    collection_group = index.get('collectionGroup')
    if isinstance(collection_group, str):
        return collection_group
    name = index.get('name')
    marker = '/collectionGroups/'
    if isinstance(name, str) and marker in name:
        collection_group = name.split(marker, 1)[1].split('/', 1)[0]
        if collection_group:
            return collection_group
    raise ValueError('Firestore index entry must contain collectionGroup or a collectionGroups resource name')


def _index_signature(index: Mapping[str, Any]) -> IndexSignature:
    collection_group = _collection_group_from_resource_name(index)
    query_scope = index.get('queryScope')
    fields = index.get('fields')
    if not isinstance(query_scope, str) or not isinstance(fields, list):
        raise ValueError('Firestore index entry must contain collectionGroup, queryScope, and fields')
    normalized_fields: list[tuple[str, str]] = []
    for field in fields:
        if not isinstance(field, Mapping) or not isinstance(field.get('fieldPath'), str):
            raise ValueError('Firestore index field must contain fieldPath')
        direction = field.get('order') or field.get('arrayConfig')
        if not isinstance(direction, str):
            raise ValueError(f"Firestore index field {field['fieldPath']!r} has no order or arrayConfig")
        normalized_fields.append((field['fieldPath'], direction))
    return (collection_group, query_scope, tuple(normalized_fields))


def expected_index_signatures(manifest: Mapping[str, Any]) -> set[IndexSignature]:
    indexes = manifest.get('indexes')
    if not isinstance(indexes, list):
        raise ValueError('Firestore manifest must contain an indexes list')
    return {_index_signature(index) for index in indexes if isinstance(index, Mapping)}


def verify_manifest_source(manifest_path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'{manifest_path} is not valid JSON') from exc
    if not isinstance(loaded, dict):
        raise ValueError(f'{manifest_path} must contain an object')
    generated = firebase_index_manifest()
    if loaded != generated:
        raise ValueError('firestore.indexes.json is not generated from the repository index registry')
    return generated


def deploy_indexes(*, project: str, manifest_path: Path, runner: CommandRunner = subprocess.run) -> None:
    command = [
        'npx',
        '--no-install',
        'firebase',
        'deploy',
        '--only',
        'firestore:indexes',
        '--project',
        project,
        '--config',
        str(ROOT / 'firebase.json'),
        '--non-interactive',
    ]
    result = runner(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError('Firebase index deployment failed')


def list_live_indexes(
    *,
    project: str,
    database: str,
    runner: CommandRunner = subprocess.run,
) -> dict[IndexSignature, str]:
    command = [
        'gcloud',
        'firestore',
        'indexes',
        'composite',
        'list',
        f'--project={project}',
        f'--database={database}',
        '--format=json',
    ]
    result = runner(command, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('Firestore composite-index listing failed')
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Firestore composite-index listing did not return JSON') from exc
    if not isinstance(payload, list):
        raise RuntimeError('Firestore composite-index listing did not return a list')
    states: dict[IndexSignature, str] = {}
    for index in payload:
        if not isinstance(index, Mapping):
            continue
        try:
            signature = _index_signature(index)
        except ValueError:
            continue
        state = index.get('state')
        states[signature] = state if isinstance(state, str) else 'UNKNOWN'
        if (
            len(signature[2]) > 1
            and signature[2][-1][0] == '__name__'
            and signature[2][-1][1] == signature[2][-2][1]
            and signature[2][-1][1] in {'ASCENDING', 'DESCENDING'}
        ):
            states[(signature[0], signature[1], signature[2][:-1])] = states[signature]
    return states


def format_signature(signature: IndexSignature) -> str:
    collection_group, query_scope, fields = signature
    field_text = ', '.join(f'{field}:{direction}' for field, direction in fields)
    return f'{query_scope}/{collection_group} ({field_text})'


def wait_for_indexes(
    *,
    expected: Iterable[IndexSignature],
    project: str,
    database: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    runner: CommandRunner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    if timeout_seconds <= 0:
        raise ValueError('timeout_seconds must be positive')
    if poll_interval_seconds <= 0:
        raise ValueError('poll_interval_seconds must be positive')
    expected_set = set(expected)
    deadline = monotonic() + timeout_seconds
    while True:
        states = list_live_indexes(project=project, database=database, runner=runner)
        pending = {
            signature: states.get(signature, 'MISSING')
            for signature in expected_set
            if states.get(signature) != 'READY'
        }
        if not pending:
            print(f'Firestore index readiness passed: {len(expected_set)} composite indexes READY')
            return
        if monotonic() >= deadline:
            details = '; '.join(
                f'{format_signature(signature)}={state}' for signature, state in sorted(pending.items())
            )
            raise RuntimeError(f'Firestore indexes did not become READY before timeout: {details}')
        sleep(poll_interval_seconds)


def reconcile(
    *,
    project: str,
    database: str,
    manifest_path: Path,
    timeout_seconds: float,
    poll_interval_seconds: float,
    runner: CommandRunner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    manifest = verify_manifest_source(manifest_path)
    deploy_indexes(project=project, manifest_path=manifest_path, runner=runner)
    wait_for_indexes(
        expected=expected_index_signatures(manifest),
        project=project,
        database=database,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        runner=runner,
        sleep=sleep,
        monotonic=monotonic,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--database', default=DEFAULT_DATABASE)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'firestore.indexes.json')
    parser.add_argument('--timeout-seconds', type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument('--poll-interval-seconds', type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args()
    try:
        reconcile(
            project=args.project,
            database=args.database,
            manifest_path=args.manifest.resolve(),
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

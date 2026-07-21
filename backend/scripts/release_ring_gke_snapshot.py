#!/usr/bin/env python3
"""Capture, restore, and verify the release ring's pre-mutation GKE state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

SCHEMA_VERSION = 1

CommandRunner = Callable[[Sequence[str], str | None], str]


def _run(command: Sequence[str], input_text: str | None = None) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, input=input_text)
    return completed.stdout


def _is_not_found(exc: subprocess.CalledProcessError) -> bool:
    evidence = f"{getattr(exc, 'stderr', '')} {getattr(exc, 'output', '')}".lower()
    return 'not found' in evidence or 'notfound' in evidence or 'release: not found' in evidence


def _load_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{label} returned invalid JSON') from exc


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _sanitize_config_map(value: object, *, namespace: str, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f'{name}: ConfigMap is not an object')
    metadata = value.get('metadata')
    if not isinstance(metadata, Mapping) or metadata.get('name') != name:
        raise ValueError(f'{name}: ConfigMap identity does not match the requested object')
    observed_namespace = metadata.get('namespace')
    if observed_namespace not in (None, namespace):
        raise ValueError(f'{name}: ConfigMap namespace does not match {namespace}')
    sanitized: dict[str, Any] = {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {'name': name, 'namespace': namespace},
        'data': {},
        'binaryData': {},
    }
    for field in ('data', 'binaryData'):
        raw = value.get(field)
        if raw is None:
            continue
        if not isinstance(raw, Mapping) or any(
            not isinstance(key, str) or not isinstance(item, str) for key, item in raw.items()
        ):
            raise ValueError(f'{name}: ConfigMap {field} must contain string values')
        sanitized[field] = dict(sorted(cast(Mapping[str, str], raw).items()))
    return sanitized


def _capture_config_map(*, namespace: str, name: str, runner: CommandRunner) -> dict[str, Any]:
    command = ['kubectl', '-n', namespace, 'get', 'configmap', name, '-o', 'json']
    try:
        raw = runner(command, None)
    except subprocess.CalledProcessError as exc:
        if _is_not_found(exc):
            return {'name': name, 'present': False}
        raise
    config_map = _sanitize_config_map(_load_json(raw, label=f'{name} ConfigMap'), namespace=namespace, name=name)
    return {
        'name': name,
        'present': True,
        'sha256': _sha256_text(_canonical_json(config_map)),
        'object': config_map,
    }


def _capture_helm_release(*, namespace: str, name: str, runner: CommandRunner) -> dict[str, Any]:
    try:
        history_text = runner(['helm', '-n', namespace, 'history', name, '--output', 'json'], None)
    except subprocess.CalledProcessError as exc:
        if _is_not_found(exc):
            return {'name': name, 'present': False}
        raise
    history = _load_json(history_text, label=f'{name} Helm history')
    if not isinstance(history, list):
        raise ValueError(f'{name}: Helm history is not a list')
    deployed_revisions: list[int] = []
    for entry in history:
        if not isinstance(entry, Mapping) or entry.get('status') != 'deployed':
            continue
        raw_revision = entry.get('revision')
        try:
            revision = int(raw_revision)
        except (TypeError, ValueError):
            raise ValueError(f'{name}: deployed Helm revision is invalid') from None
        if revision <= 0:
            raise ValueError(f'{name}: deployed Helm revision is invalid')
        deployed_revisions.append(revision)
    if not deployed_revisions:
        raise ValueError(f'{name}: Helm release exists without a deployed revision')
    revision = max(deployed_revisions)
    manifest = runner(['helm', '-n', namespace, 'get', 'manifest', name, '--revision', str(revision)], None)
    if not manifest.strip():
        raise ValueError(f'{name}: deployed Helm manifest is empty')
    return {
        'name': name,
        'present': True,
        'revision': revision,
        'manifest_sha256': _sha256_text(manifest),
    }


def capture_snapshot(
    *,
    namespace: str,
    config_map_name: str,
    releases: Mapping[str, str],
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    if not namespace or not config_map_name:
        raise ValueError('namespace and ConfigMap name are required')
    if not releases or any(not component or not name for component, name in releases.items()):
        raise ValueError('at least one named Helm release is required')
    return {
        'schema_version': SCHEMA_VERSION,
        'scope': 'release ring GKE pre-mutation state',
        'captured_at': datetime.now(UTC).isoformat(),
        'namespace': namespace,
        'config_map': _capture_config_map(namespace=namespace, name=config_map_name, runner=runner),
        'helm_releases': {
            component: _capture_helm_release(namespace=namespace, name=name, runner=runner)
            for component, name in releases.items()
        },
    }


def _restore_config_map(snapshot: Mapping[str, Any], *, namespace: str, runner: CommandRunner) -> dict[str, Any]:
    name = snapshot.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError('GKE snapshot contains an invalid ConfigMap name')
    if snapshot.get('present') is True:
        raw_object = snapshot.get('object')
        config_map = _sanitize_config_map(raw_object, namespace=namespace, name=name)
        expected_sha = snapshot.get('sha256')
        if expected_sha != _sha256_text(_canonical_json(config_map)):
            raise ValueError(f'{name}: ConfigMap snapshot digest does not match its object')
        runner(['kubectl', '-n', namespace, 'apply', '-f', '-'], _canonical_json(config_map))
        observed = runner(['kubectl', '-n', namespace, 'get', 'configmap', name, '-o', 'json'], None)
        observed_map = _sanitize_config_map(
            _load_json(observed, label=f'{name} restored ConfigMap'), namespace=namespace, name=name
        )
        if _sha256_text(_canonical_json(observed_map)) != expected_sha:
            raise ValueError(f'{name}: observed ConfigMap does not match the snapshot')
        return {'result': 'restored', 'sha256': expected_sha}

    runner(['kubectl', '-n', namespace, 'delete', 'configmap', name, '--ignore-not-found=true'], None)
    try:
        runner(['kubectl', '-n', namespace, 'get', 'configmap', name, '-o', 'json'], None)
    except subprocess.CalledProcessError as exc:
        if _is_not_found(exc):
            return {'result': 'deleted'}
        raise
    raise ValueError(f'{name}: ConfigMap still exists after delete')


def _restore_helm_release(snapshot: Mapping[str, Any], *, namespace: str, runner: CommandRunner) -> dict[str, Any]:
    name = snapshot.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError('GKE snapshot contains an invalid Helm release name')
    if snapshot.get('present') is True:
        revision = snapshot.get('revision')
        digest = snapshot.get('manifest_sha256')
        if not isinstance(revision, int) or revision <= 0 or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f'{name}: Helm snapshot is incomplete')
        runner(
            ['helm', '-n', namespace, 'rollback', name, str(revision), '--wait', '--timeout', '1800s'],
            None,
        )
        observed_manifest = runner(['helm', '-n', namespace, 'get', 'manifest', name], None)
        if _sha256_text(observed_manifest) != digest:
            raise ValueError(f'{name}: observed Helm manifest does not match the snapshot')
        return {'result': 'restored', 'revision': revision, 'manifest_sha256': digest}

    try:
        runner(['helm', '-n', namespace, 'status', name, '--output', 'json'], None)
    except subprocess.CalledProcessError as exc:
        if _is_not_found(exc):
            return {'result': 'absent'}
        raise
    runner(['helm', '-n', namespace, 'uninstall', name, '--wait', '--timeout', '1800s'], None)
    try:
        runner(['helm', '-n', namespace, 'status', name, '--output', 'json'], None)
    except subprocess.CalledProcessError as exc:
        if _is_not_found(exc):
            return {'result': 'deleted'}
        raise
    raise ValueError(f'{name}: Helm release still exists after uninstall')


def restore_snapshot(snapshot: Mapping[str, Any], *, runner: CommandRunner = _run) -> dict[str, Any]:
    if snapshot.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('GKE snapshot has an unsupported schema version')
    namespace = snapshot.get('namespace')
    config_map = snapshot.get('config_map')
    releases = snapshot.get('helm_releases')
    if not isinstance(namespace, str) or not namespace:
        raise ValueError('GKE snapshot is missing namespace')
    if not isinstance(config_map, Mapping) or not isinstance(releases, Mapping):
        raise ValueError('GKE snapshot is incomplete')

    results: dict[str, dict[str, Any]] = {}

    def attempt(component: str, operation: Callable[[], dict[str, Any]]) -> None:
        try:
            results[component] = operation()
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                error = f'command exited with code {exc.returncode}'
            else:
                error = str(exc)
            results[component] = {'result': 'failed', 'error': error}

    secret_snapshot = releases.get('backend-secrets')
    if isinstance(secret_snapshot, Mapping):
        attempt(
            'backend-secrets',
            lambda: _restore_helm_release(secret_snapshot, namespace=namespace, runner=runner),
        )
    attempt('backend-config', lambda: _restore_config_map(config_map, namespace=namespace, runner=runner))
    for component, raw_release in releases.items():
        if component == 'backend-secrets':
            continue
        if not isinstance(component, str) or not isinstance(raw_release, Mapping):
            results[str(component)] = {'result': 'failed', 'error': 'invalid Helm release snapshot'}
            continue
        attempt(
            component,
            lambda raw_release=raw_release: _restore_helm_release(raw_release, namespace=namespace, runner=runner),
        )

    failures = sorted(component for component, result in results.items() if result.get('result') == 'failed')
    return {
        'schema_version': SCHEMA_VERSION,
        'scope': 'release ring GKE restoration',
        'result': 'pass' if not failures else 'fail',
        'failed_components': failures,
        'components': results,
    }


def _parse_releases(values: Sequence[str]) -> dict[str, str]:
    releases: dict[str, str] = {}
    for value in values:
        component, separator, name = value.partition('=')
        if not separator or not component or not name or component in releases:
            raise ValueError(f'--release must be unique COMPONENT=NAME: {value!r}')
        releases[component] = name
    return releases


def _read_snapshot(path: Path) -> dict[str, Any]:
    loaded = _load_json(path.read_text(encoding='utf-8'), label=str(path))
    if not isinstance(loaded, dict):
        raise ValueError('GKE snapshot must be an object')
    return cast(dict[str, Any], loaded)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{json.dumps(value, indent=2, sort_keys=True)}\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('capture')
    capture.add_argument('--namespace', required=True)
    capture.add_argument('--config-map', required=True)
    capture.add_argument('--release', action='append', default=[])
    capture.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--snapshot', type=Path, required=True)
    restore.add_argument('--evidence-path', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            releases = _parse_releases(args.release)
            snapshot = capture_snapshot(
                namespace=args.namespace,
                config_map_name=args.config_map,
                releases=releases,
            )
            _write_json(args.output, snapshot)
            return 0
        evidence = restore_snapshot(_read_snapshot(args.snapshot))
        _write_json(args.evidence_path, evidence)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if evidence['result'] == 'pass' else 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

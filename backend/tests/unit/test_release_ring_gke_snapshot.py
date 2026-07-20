from __future__ import annotations

import json
import subprocess

from scripts import release_ring_gke_snapshot as snapshots

NAMESPACE = 'prod-omi-backend'
CONFIG_NAME = 'prod-omi-backend-config'


def _config_map(value: str) -> dict:
    return {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {'name': CONFIG_NAME, 'namespace': NAMESPACE},
        'data': {'PUBLIC_VALUE': value},
    }


def _config_snapshot(value: str) -> dict:
    sanitized = snapshots._sanitize_config_map(_config_map(value), namespace=NAMESPACE, name=CONFIG_NAME)
    return {
        'name': CONFIG_NAME,
        'present': True,
        'sha256': snapshots._sha256_text(snapshots._canonical_json(sanitized)),
        'object': sanitized,
    }


def test_capture_records_exact_config_and_helm_restore_targets() -> None:
    calls: list[list[str]] = []

    def runner(command, _input):
        command = list(command)
        calls.append(command)
        if command[:6] == ['kubectl', '-n', NAMESPACE, 'get', 'configmap', CONFIG_NAME]:
            return json.dumps(_config_map('before'))
        if command[:5] == ['helm', '-n', NAMESPACE, 'history', 'prod-omi-backend-secrets']:
            return json.dumps([{'revision': 3, 'status': 'superseded'}, {'revision': 4, 'status': 'deployed'}])
        if command[:6] == ['helm', '-n', NAMESPACE, 'get', 'manifest', 'prod-omi-backend-secrets']:
            return 'old-secret-manifest\n'
        if command[:5] == ['helm', '-n', NAMESPACE, 'history', 'prod-omi-pusher']:
            raise subprocess.CalledProcessError(1, command, stderr='release: not found')
        raise AssertionError(command)

    snapshot = snapshots.capture_snapshot(
        namespace=NAMESPACE,
        config_map_name=CONFIG_NAME,
        releases={
            'backend-secrets': 'prod-omi-backend-secrets',
            'pusher': 'prod-omi-pusher',
        },
        runner=runner,
    )

    assert snapshot['config_map']['object']['data'] == {'PUBLIC_VALUE': 'before'}
    assert snapshot['helm_releases']['backend-secrets'] == {
        'name': 'prod-omi-backend-secrets',
        'present': True,
        'revision': 4,
        'manifest_sha256': snapshots._sha256_text('old-secret-manifest\n'),
    }
    assert snapshot['helm_releases']['pusher'] == {'name': 'prod-omi-pusher', 'present': False}
    assert calls[-1] == ['helm', '-n', NAMESPACE, 'history', 'prod-omi-pusher', '--output', 'json']


def test_restore_reverts_config_and_secrets_then_removes_bootstrap_release() -> None:
    old_secret_manifest = 'old-secret-manifest\n'
    snapshot = {
        'schema_version': 1,
        'namespace': NAMESPACE,
        'config_map': _config_snapshot('before'),
        'helm_releases': {
            'backend-secrets': {
                'name': 'prod-omi-backend-secrets',
                'present': True,
                'revision': 4,
                'manifest_sha256': snapshots._sha256_text(old_secret_manifest),
            },
            'pusher': {'name': 'prod-omi-pusher', 'present': False},
        },
    }
    calls: list[list[str]] = []
    current_config = _config_map('candidate')
    current_secret_manifest = 'candidate-secret-manifest\n'
    pusher_exists = True

    def runner(command, input_text):
        nonlocal current_config, current_secret_manifest, pusher_exists
        command = list(command)
        calls.append(command)
        if command[:5] == ['helm', '-n', NAMESPACE, 'rollback', 'prod-omi-backend-secrets']:
            current_secret_manifest = old_secret_manifest
            return ''
        if command[:6] == ['helm', '-n', NAMESPACE, 'get', 'manifest', 'prod-omi-backend-secrets']:
            return current_secret_manifest
        if command[:6] == ['kubectl', '-n', NAMESPACE, 'apply', '-f', '-']:
            current_config = json.loads(input_text)
            return ''
        if command[:6] == ['kubectl', '-n', NAMESPACE, 'get', 'configmap', CONFIG_NAME]:
            return json.dumps(current_config)
        if command[:5] == ['helm', '-n', NAMESPACE, 'status', 'prod-omi-pusher']:
            if pusher_exists:
                return json.dumps({'info': {'status': 'deployed'}})
            raise subprocess.CalledProcessError(1, command, stderr='release: not found')
        if command[:5] == ['helm', '-n', NAMESPACE, 'uninstall', 'prod-omi-pusher']:
            pusher_exists = False
            return ''
        raise AssertionError(command)

    evidence = snapshots.restore_snapshot(snapshot, runner=runner)

    assert evidence['result'] == 'pass'
    assert evidence['components']['backend-secrets']['result'] == 'restored'
    assert evidence['components']['backend-config']['result'] == 'restored'
    assert evidence['components']['pusher']['result'] == 'deleted'
    assert calls.index(
        ['helm', '-n', NAMESPACE, 'rollback', 'prod-omi-backend-secrets', '4', '--wait', '--timeout', '1800s']
    ) < calls.index(['kubectl', '-n', NAMESPACE, 'apply', '-f', '-'])


def test_restore_fails_when_helm_reports_success_without_manifest_convergence() -> None:
    snapshot = {
        'schema_version': 1,
        'namespace': NAMESPACE,
        'config_map': {'name': CONFIG_NAME, 'present': False},
        'helm_releases': {
            'pusher': {
                'name': 'prod-omi-pusher',
                'present': True,
                'revision': 7,
                'manifest_sha256': snapshots._sha256_text('old-manifest\n'),
            }
        },
    }

    def runner(command, _input):
        command = list(command)
        if command[:6] == ['kubectl', '-n', NAMESPACE, 'delete', 'configmap', CONFIG_NAME]:
            return ''
        if command[:6] == ['kubectl', '-n', NAMESPACE, 'get', 'configmap', CONFIG_NAME]:
            raise subprocess.CalledProcessError(1, command, stderr='NotFound')
        if command[:5] == ['helm', '-n', NAMESPACE, 'rollback', 'prod-omi-pusher']:
            return ''
        if command[:6] == ['helm', '-n', NAMESPACE, 'get', 'manifest', 'prod-omi-pusher']:
            return 'still-candidate\n'
        raise AssertionError(command)

    evidence = snapshots.restore_snapshot(snapshot, runner=runner)

    assert evidence['result'] == 'fail'
    assert evidence['failed_components'] == ['pusher']
    assert (
        evidence['components']['pusher']['error']
        == 'prod-omi-pusher: observed Helm manifest does not match the snapshot'
    )

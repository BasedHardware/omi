from __future__ import annotations

import subprocess

from scripts import cloud_run_traffic_snapshot as snapshots


def _service_document(*, revision: str, secret_value: str = 'not-for-artifacts') -> dict:
    return {
        'spec': {
            'traffic': [{'revisionName': revision, 'percent': 100, 'tag': 'stable'}],
            'template': {'spec': {'containers': [{'env': [{'name': 'SECRET', 'value': secret_value}]}]}},
        },
        'status': {
            'traffic': [{'revisionName': revision, 'percent': 100, 'url': 'https://not-an-artifact.example'}],
            'latestReadyRevisionName': revision,
            'latestCreatedRevisionName': revision,
        },
    }


def test_capture_snapshot_is_limited_to_restorable_traffic_metadata() -> None:
    documents = {'backend': _service_document(revision='backend-stable')}

    snapshot = snapshots.capture_snapshot(
        project='based-hardware-dev',
        region='us-central1',
        services=('backend',),
        fetcher=lambda **kwargs: documents[kwargs['service']],
    )

    service = snapshot['services']['backend']
    assert service == {
        'service': 'backend',
        'spec': {'traffic': [{'percent': 100, 'revisionName': 'backend-stable'}]},
        'status': {
            'traffic': [{'percent': 100, 'revisionName': 'backend-stable'}],
            'latestReadyRevisionName': 'backend-stable',
            'latestCreatedRevisionName': 'backend-stable',
        },
    }
    assert 'tag' not in service['spec']['traffic'][0]
    assert 'not-for-artifacts' not in str(snapshot)
    assert 'not-an-artifact.example' not in str(snapshot)


def test_restore_snapshot_resolves_latest_revision_before_the_new_candidate_exists() -> None:
    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware-dev',
        'region': 'us-central1',
        'services': {
            'backend': {
                'spec': {'traffic': [{'latestRevision': True, 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-pre-promotion'},
            },
            'backend-sync': {
                'spec': {'traffic': [{'revisionName': 'backend-sync-pre-promotion', 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-sync-pre-promotion'},
            },
        },
    }
    calls: list[list[str]] = []

    evidence = snapshots.restore_snapshot(snapshot, runner=lambda command: calls.append(list(command)))

    assert evidence['result'] == 'pass'
    assert evidence['failed_services'] == []
    assert calls == [
        [
            'gcloud',
            'run',
            'services',
            'update-traffic',
            'backend',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--to-revisions=backend-pre-promotion=100',
            '--quiet',
        ],
        [
            'gcloud',
            'run',
            'services',
            'update-traffic',
            'backend-sync',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--to-revisions=backend-sync-pre-promotion=100',
            '--quiet',
        ],
    ]


def test_restore_snapshot_attempts_every_service_and_sanitizes_a_failed_command() -> None:
    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware-dev',
        'region': 'us-central1',
        'services': {
            'backend': {
                'spec': {'traffic': [{'revisionName': 'backend-pre-promotion', 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-pre-promotion'},
            },
            'backend-sync': {
                'spec': {'traffic': [{'revisionName': 'backend-sync-pre-promotion', 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-sync-pre-promotion'},
            },
        },
    }
    calls: list[str] = []

    def runner(command: list[str]) -> None:
        calls.append(command[4])
        if command[4] == 'backend':
            raise subprocess.CalledProcessError(17, command, stderr='sensitive remote response')

    evidence = snapshots.restore_snapshot(snapshot, runner=runner)

    assert calls == ['backend', 'backend-sync']
    assert evidence['result'] == 'fail'
    assert evidence['failed_services'] == ['backend']
    assert evidence['services']['backend'] == {
        'targets': [{'revision': 'backend-pre-promotion', 'percent': 100}],
        'command': (
            'gcloud run services update-traffic backend --project=based-hardware-dev '
            '--region=us-central1 --to-revisions=backend-pre-promotion=100 --quiet'
        ),
        'result': 'failed',
        'error': 'gcloud exited with code 17',
    }
    assert 'sensitive remote response' not in str(evidence)

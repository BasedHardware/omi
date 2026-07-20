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

    revisions = {
        'backend': 'backend-pre-promotion',
        'backend-sync': 'backend-sync-pre-promotion',
    }
    evidence = snapshots.restore_snapshot(
        snapshot,
        runner=lambda command: calls.append(list(command)),
        fetcher=lambda **kwargs: _service_document(revision=revisions[kwargs['service']]),
    )

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


def test_bootstrap_snapshot_records_missing_services_and_has_no_traffic_to_restore() -> None:
    def missing(**_kwargs):
        raise subprocess.CalledProcessError(1, ["gcloud"], stderr="NOT_FOUND: resource was not found")

    snapshot = snapshots.capture_snapshot(
        project='based-hardware',
        region='us-central1',
        services=('backend-beta',),
        allow_missing=True,
        fetcher=missing,
    )

    assert snapshot['services'] == {}
    assert snapshot['missing_services'] == ['backend-beta']
    assert snapshots.restore_snapshot(snapshot)['result'] == 'pass'


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

    evidence = snapshots.restore_snapshot(
        snapshot,
        runner=runner,
        fetcher=lambda **kwargs: _service_document(revision=f"{kwargs['service']}-pre-promotion"),
    )

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


def test_restore_removes_candidate_tag_and_rejects_unconverged_observation() -> None:
    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware',
        'region': 'us-central1',
        'services': {
            'backend': {
                'spec': {'traffic': [{'revisionName': 'backend-stable', 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-stable'},
            }
        },
        'missing_services': [],
    }
    calls: list[list[str]] = []
    observed = _service_document(revision='backend-stable')
    observed['spec']['traffic'][0]['tag'] = 'ring-12345'

    evidence = snapshots.restore_snapshot(
        snapshot,
        runner=lambda command: calls.append(list(command)),
        fetcher=lambda **_kwargs: observed,
        remove_tag='ring-12345',
    )

    assert '--remove-tags=ring-12345' in calls[0]
    assert evidence['result'] == 'fail'
    assert evidence['services']['backend']['error'] == 'candidate traffic tag remains after restore'


def test_restore_detects_wedged_status_traffic_after_update() -> None:
    """A wedged Cloud Run service: spec.traffic reflects our restore request but
    status.traffic still serves the candidate. The read-back must resolve
    status.traffic, not spec.traffic, so convergence is not falsely claimed."""
    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware',
        'region': 'us-central1',
        'services': {
            'backend': {
                'spec': {'traffic': [{'revisionName': 'backend-stable', 'percent': 100}]},
                'status': {'latestReadyRevisionName': 'backend-stable'},
            }
        },
        'missing_services': [],
    }

    # After restore, spec.traffic matches our target (gcloud accepted the
    # update), but status.traffic still serves the candidate revision.
    wedged = {
        'spec': {'traffic': [{'revisionName': 'backend-stable', 'percent': 100}]},
        'status': {
            'traffic': [{'revisionName': 'backend-candidate', 'percent': 100}],
            'latestReadyRevisionName': 'backend-stable',
            'latestCreatedRevisionName': 'backend-candidate',
        },
    }

    evidence = snapshots.restore_snapshot(
        snapshot,
        runner=lambda command: None,
        fetcher=lambda **_kwargs: wedged,
    )

    assert evidence['result'] == 'fail'
    assert evidence['failed_services'] == ['backend']
    assert evidence['services']['backend']['error'] == 'observed traffic does not match snapshot'
    assert evidence['services']['backend']['observed_targets'] == [{'revision': 'backend-candidate', 'percent': 100}]


def test_restore_deletes_and_observes_services_missing_before_bootstrap() -> None:
    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware',
        'region': 'us-central1',
        'services': {},
        'missing_services': ['backend-beta'],
    }
    calls: list[list[str]] = []

    def missing(**_kwargs):
        raise subprocess.CalledProcessError(1, ['gcloud'], stderr='NOT_FOUND: service was not found')

    evidence = snapshots.restore_snapshot(
        snapshot,
        runner=lambda command: calls.append(list(command)),
        fetcher=missing,
        delete_missing=True,
    )

    assert calls == [
        [
            'gcloud',
            'run',
            'services',
            'delete',
            'backend-beta',
            '--project=based-hardware',
            '--region=us-central1',
            '--quiet',
        ]
    ]
    assert evidence['result'] == 'pass'
    assert evidence['deleted_services']['backend-beta']['result'] == 'deleted'

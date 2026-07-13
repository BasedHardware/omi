from __future__ import annotations

from scripts import verify_dev_backend_deployment as verifier


def _expectation() -> verifier.DeploymentExpectation:
    return verifier.build_expectation(
        commit_sha='abcdef1234567890',
        deploy_run_id='12345',
        deploy_run_attempt='1',
        project='based-hardware-dev',
        region='us-central1',
    )


def _cloud_run_document(*, revision: str, image: str) -> dict:
    return {
        'spec': {
            'template': {
                'spec': {
                    'timeoutSeconds': 300,
                    'containers': [{'image': image, 'env': [{'name': 'OMI_ENV_STAGE', 'value': 'dev'}]}],
                }
            }
        },
        'status': {
            'latestCreatedRevisionName': revision,
            'latestReadyRevisionName': revision,
            'traffic': [{'revisionName': revision, 'percent': 100}],
        },
    }


def _documents(expectation: verifier.DeploymentExpectation) -> dict:
    documents = {
        f'cloud_run/{service}': _cloud_run_document(revision=revision, image=expectation.image)
        for service, revision in expectation.revisions.items()
    }
    documents.update(
        {
            'gke/deployment': {
                'metadata': {'name': expectation.listener_deployment, 'generation': 4},
                'spec': {
                    'replicas': 1,
                    'template': {
                        'spec': {
                            'serviceAccountName': expectation.listener_deployment,
                            'containers': [
                                {'image': expectation.image, 'env': [{'name': 'OMI_ENV_STAGE', 'value': 'dev'}]}
                            ],
                        }
                    },
                },
                'status': {'observedGeneration': 4, 'availableReplicas': 1},
            },
            'gke/service': {
                'metadata': {'name': expectation.listener_service},
                'spec': {'type': 'ClusterIP', 'ports': [{'port': 8080}], 'selector': {'app': 'backend'}},
            },
            'gke/endpointslices': {
                'items': [
                    {
                        'metadata': {'labels': {'kubernetes.io/service-name': expectation.listener_service}},
                        'endpoints': [{'addresses': ['10.1.2.3'], 'conditions': {'ready': True}}],
                    }
                ]
            },
        }
    )
    return documents


def test_expectation_binds_commit_to_deploy_run_revision_and_image() -> None:
    expectation = _expectation()

    assert expectation.image == 'gcr.io/based-hardware-dev/backend:abcdef1'
    assert expectation.revisions['backend-sync'] == 'backend-sync-abcdef1-12345-1'
    assert expectation.listener_deployment == 'dev-omi-backend-listen'


def test_read_only_commands_are_limited_to_queries() -> None:
    commands = verifier.build_read_only_commands(_expectation())

    verifier.assert_commands_are_read_only(commands)
    assert all('delete' not in ' '.join(command) for command in commands.values())
    assert commands['cloud_run/backend'][:4] == ['gcloud', 'run', 'services', 'describe']


def test_evaluate_accepts_matching_deployed_composition() -> None:
    expectation = _expectation()

    assert verifier.evaluate(expectation, _documents(expectation)) == []


def test_evaluate_fails_closed_when_a_stale_revision_is_serving() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['cloud_run/backend']['status']['latestReadyRevisionName'] = 'backend-old'
    documents['cloud_run/backend']['status']['traffic'] = [{'revisionName': 'backend-old', 'percent': 100}]
    documents['gke/deployment']['status']['availableReplicas'] = 0

    errors = verifier.evaluate(expectation, documents)

    assert 'cloud_run/backend: latest ready revision is not backend-abcdef1-12345-1' in errors
    assert 'cloud_run/backend: expected revision does not receive 100% traffic' in errors
    assert 'gke/deployment: desired replicas are not all available' in errors

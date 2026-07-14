from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import verify_dev_backend_deployment as verifier

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFLIGHT_SCRIPT = BACKEND_DIR / 'scripts' / 'preflight-cloud-run-deploy.py'


def _load_preflight():
    spec = importlib.util.spec_from_file_location('preflight_cloud_run_deploy', PREFLIGHT_SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
                'status': {'observedGeneration': 4, 'availableReplicas': 1, 'updatedReplicas': 1},
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


def test_dev_deploy_migrates_only_exact_legacy_google_client_id_secrets_without_traffic() -> None:
    preflight = _load_preflight()
    legacy_service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'env': [
                                {
                                    'name': 'GOOGLE_CLIENT_ID',
                                    'valueFrom': {'secretKeyRef': {'name': 'GOOGLE_CLIENT_ID', 'key': 'latest'}},
                                },
                                {
                                    'name': 'STT_PRERECORDED_MODEL',
                                    'valueFrom': {'secretKeyRef': {'name': 'STT_PRERECORDED_MODEL', 'key': 'latest'}},
                                },
                            ]
                        }
                    ]
                }
            }
        }
    }
    literal_service = {
        'spec': {'template': {'spec': {'containers': [{'env': [{'name': 'GOOGLE_CLIENT_ID', 'value': 'public'}]}]}}}
    }
    commands: list[list[str]] = []

    def runner(command: list[str], **_kwargs):
        commands.append(command)
        if command[:4] == ['gcloud', 'run', 'services', 'describe']:
            service = command[4]
            document = legacy_service if service == 'backend' else literal_service
            return SimpleNamespace(stdout=json.dumps(document))
        return SimpleNamespace(stdout='')

    migrated = preflight.migrate_legacy_public_bindings(
        services=('backend', 'backend-sync'),
        env='dev',
        project='based-hardware-dev',
        region='us-central1',
        runner=runner,
    )

    assert migrated == ['backend']
    assert commands == [
        [
            'gcloud',
            'run',
            'services',
            'describe',
            'backend',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--format=json',
        ],
        [
            'gcloud',
            'run',
            'services',
            'update',
            'backend',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--remove-secrets=GOOGLE_CLIENT_ID,STT_PRERECORDED_MODEL',
            '--no-traffic',
            '--quiet',
        ],
        [
            'gcloud',
            'run',
            'services',
            'describe',
            'backend-sync',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--format=json',
        ],
    ]


def test_legacy_binding_migration_is_idempotent_after_removal() -> None:
    preflight = _load_preflight()
    state = {'legacy': True}
    updates: list[list[str]] = []

    def runner(command: list[str], **_kwargs):
        if command[:4] == ['gcloud', 'run', 'services', 'describe']:
            entry = (
                {'name': 'GOOGLE_CLIENT_ID', 'valueFrom': {'secretKeyRef': {'name': 'GOOGLE_CLIENT_ID'}}}
                if state['legacy']
                else {'name': 'GOOGLE_CLIENT_ID', 'value': 'public'}
            )
            document = {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {'env': [entry]},
                            ]
                        }
                    }
                }
            }
            return SimpleNamespace(stdout=json.dumps(document))
        updates.append(command)
        state['legacy'] = False
        return SimpleNamespace(stdout='')

    first = preflight.migrate_legacy_public_bindings(
        services=('backend',), env='dev', project='based-hardware-dev', region='us-central1', runner=runner
    )
    second = preflight.migrate_legacy_public_bindings(
        services=('backend',), env='dev', project='based-hardware-dev', region='us-central1', runner=runner
    )

    assert first == ['backend']
    assert second == []
    assert updates == [
        [
            'gcloud',
            'run',
            'services',
            'update',
            'backend',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--remove-secrets=GOOGLE_CLIENT_ID',
            '--no-traffic',
            '--quiet',
        ]
    ]


def test_legacy_binding_migration_rejects_multi_container_services_without_mutation() -> None:
    preflight = _load_preflight()
    commands: list[list[str]] = []
    multi_container_service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {'env': []},
                        {
                            'env': [
                                {
                                    'name': 'GOOGLE_CLIENT_ID',
                                    'valueFrom': {'secretKeyRef': {'name': 'GOOGLE_CLIENT_ID'}},
                                }
                            ]
                        },
                    ]
                }
            }
        }
    }

    def runner(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=json.dumps(multi_container_service))

    with pytest.raises(ValueError, match='exactly one container'):
        preflight.migrate_legacy_public_bindings(
            services=('backend',), env='dev', project='based-hardware-dev', region='us-central1', runner=runner
        )

    assert commands == [
        [
            'gcloud',
            'run',
            'services',
            'describe',
            'backend',
            '--project=based-hardware-dev',
            '--region=us-central1',
            '--format=json',
        ]
    ]


def test_legacy_binding_migration_rejects_non_dev_projects_without_gcloud_calls() -> None:
    preflight = _load_preflight()
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match='development-only'):
        preflight.migrate_legacy_public_bindings(
            services=('backend',),
            env='prod',
            project='based-hardware',
            region='us-central1',
            runner=lambda command, **_kwargs: calls.append(command),
        )

    assert calls == []


def test_dev_deploy_invokes_legacy_binding_migration_only_for_dev_services() -> None:
    workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend_auto_dev.yml'
    production_workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml'
    text = workflow.read_text(encoding='utf-8')

    assert 'environment: development' in text
    assert 'backend/scripts/preflight-cloud-run-deploy.py' in text
    assert text.count('--migrate-legacy-public-binding') == 4
    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        assert f'--migrate-legacy-public-binding {service}' in text
    assert text.index('migrate-legacy-public-binding') < text.index('Deploy ${{ env.SERVICE }} to Cloud Run')
    assert '--check-runtime-bindings' in text
    assert text.index('migrate-legacy-public-binding') < text.index('--check-runtime-bindings')
    assert text.index('--check-runtime-bindings') < text.index('Deploy ${{ env.SERVICE }} to Cloud Run')
    assert '--check-runtime-bindings' not in production_workflow.read_text(encoding='utf-8')


def test_dev_deploy_uses_manifest_derived_gcloud_index_provisioning_only() -> None:
    workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend_auto_dev.yml'
    production_workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml'
    text = workflow.read_text(encoding='utf-8')

    assert 'environment: development' in text
    assert 'backend/scripts/reconcile_firestore_indexes.py' in text
    assert '--provision-missing' in text
    assert 'firebase' not in text
    assert 'setup-node' not in text
    assert '--provision-missing' not in production_workflow.read_text(encoding='utf-8')


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
    documents['gke/deployment']['status']['updatedReplicas'] = 0

    errors = verifier.evaluate(expectation, documents)

    assert 'cloud_run/backend: latest ready revision is not backend-abcdef1-12345-1' in errors
    assert 'cloud_run/backend: expected revision does not receive 100% traffic' in errors
    assert 'gke/deployment: desired replicas are not all available' in errors
    assert 'gke/deployment: desired replicas are not all updated' in errors


def test_evaluate_fails_closed_when_available_replicas_are_not_the_updated_template() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['gke/deployment']['status']['updatedReplicas'] = 0

    errors = verifier.evaluate(expectation, documents)

    assert 'gke/deployment: desired replicas are not all available' not in errors
    assert 'gke/deployment: desired replicas are not all updated' in errors

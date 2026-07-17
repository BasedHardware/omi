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


def test_static_backend_deploys_only_check_the_serving_firestore_schema() -> None:
    workflows = (
        BACKEND_DIR.parent / '.github/workflows/gcp_backend_auto_dev.yml',
        BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml',
    )

    for workflow in workflows:
        text = workflow.read_text(encoding='utf-8')
        assert text.count('backend/scripts/reconcile_firestore_indexes.py') == 2
        assert '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}"' in text
        assert text.count('--check-only') == 1
        assert text.count('--validate-proposal') == 1
        assert '--provision-missing' not in text
        assert '--proposal-output "$FIRESTORE_PROPOSAL_PATH"' in text
        assert '--source-commit "$FIRESTORE_SOURCE_COMMIT"' in text
        assert '--proposal-ttl-seconds 3600' in text
        assert 'actions/upload-artifact@v7' in text
        assert 'steps.validate_firestore_proposal.outcome == \'success\'' in text
        assert 'if-no-files-found: error' in text
        assert 'retention-days: 1' in text
        assert 'credentials_json: ${{ secrets.GCP_FIRESTORE_READONLY_CREDENTIALS }}' in text
        assert 'needs: firestore_readiness' in text


def test_firestore_readiness_fails_before_checkout_when_read_only_credentials_are_missing() -> None:
    workflows = (
        BACKEND_DIR.parent / '.github/workflows/gcp_backend_auto_dev.yml',
        BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml',
    )

    for workflow in workflows:
        text = workflow.read_text(encoding='utf-8')
        readiness = text.split('\n  firestore_readiness:\n', 1)[1].split('\n  deploy:\n', 1)[0]

        assert 'Require read-only Firestore credentials' in readiness
        assert 'GCP_FIRESTORE_READONLY_CREDENTIALS: ${{ secrets.GCP_FIRESTORE_READONLY_CREDENTIALS }}' in readiness
        assert 'if [ -z "$GCP_FIRESTORE_READONLY_CREDENTIALS" ]; then' in readiness
        assert readiness.index('Require read-only Firestore credentials') < readiness.index(
            'Checkout approved Firestore'
        )
        assert readiness.index('Require read-only Firestore credentials') < readiness.index(
            'Google Auth for read-only Firestore inventory'
        )


def test_static_firestore_index_migration_is_manual_and_main_scoped() -> None:
    """Static guard: serving-schema writes stay outside backend deployment workflows."""

    workflow = BACKEND_DIR.parent / '.github/workflows/gcp_firestore_indexes.yml'
    text = workflow.read_text(encoding='utf-8')

    assert 'workflow_dispatch:' in text
    assert 'APPLY_FIRESTORE_INDEXES' in text
    assert "if: github.ref == 'refs/heads/main'" in text
    assert 'group: deploy-backend-stack-${{ github.event.inputs.environment }}' in text
    assert 'environment: ${{ github.event.inputs.environment }}' in text
    assert 'ref: ${{ github.sha }}' in text
    assert 'git rev-parse HEAD' in text
    assert 'if [[ "$checked_sha" != "$GITHUB_SHA" ]]; then' in text
    assert 'credentials_json: ${{ secrets.GCP_CREDENTIALS }}' in text
    assert text.count('--provision-missing') == 2
    assert text.count('--dry-run') == 1
    assert '--check-only' not in text
    assert 'vars.RUNTIME_GCP_PROJECT_ID' in text

    plan_step = '- name: Show create-only Firestore schema plan'
    apply_step = '- name: Apply approved Firestore schema plan and wait for readiness'
    verification_step = '- name: Verify dispatched Firestore control plane'
    plan = text.split(plan_step, 1)[1].split(apply_step, 1)[0]
    apply = text.split(apply_step, 1)[1]
    assert text.index(verification_step) < text.index(plan_step)
    assert text.index(plan_step) < text.index(apply_step)
    assert '--provision-missing' in plan
    assert '--dry-run' in plan
    assert '--dry-run' not in apply
    assert '--timeout-seconds 3600' in apply


def test_static_manual_branch_deploy_requires_the_approved_main_schema() -> None:
    workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml'
    text = workflow.read_text(encoding='utf-8')
    readiness = text.split('\n  firestore_readiness:\n', 1)[1].split('\n  deploy:\n', 1)[0]
    deploy = text.split('\n  deploy:\n', 1)[1]

    schema_guard = 'git diff --quiet "$approved_sha" "$candidate_sha" -- firestore.indexes.json'
    assert 'ref: main' in readiness
    assert 'refs/heads/${DEPLOY_BRANCH}:refs/remotes/origin/firestore-candidate' in readiness
    assert schema_guard in readiness
    assert "printf 'candidate_sha=%s\\n' \"$candidate_sha\" >> \"$GITHUB_OUTPUT\"" in readiness
    assert 'ref: ${{ needs.firestore_readiness.outputs.candidate_sha }}' in deploy
    assert readiness.index(schema_guard) < readiness.index('Google Auth for read-only Firestore inventory')
    assert readiness.index(schema_guard) < readiness.index('--check-only')
    assert 'secrets.GCP_CREDENTIALS' not in readiness


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


def test_candidate_evaluation_accepts_ready_revision_before_traffic_promotion() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['cloud_run/backend']['status']['traffic'] = [{'revisionName': 'backend-old', 'percent': 100}]

    errors = verifier.evaluate(expectation, documents, require_serving_traffic=False)

    assert errors == []


def test_evaluate_fails_closed_when_available_replicas_are_not_the_updated_template() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['gke/deployment']['status']['updatedReplicas'] = 0

    errors = verifier.evaluate(expectation, documents)

    assert 'gke/deployment: desired replicas are not all available' not in errors
    assert 'gke/deployment: desired replicas are not all updated' in errors

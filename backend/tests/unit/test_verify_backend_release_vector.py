from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import verify_backend_release_vector as verifier

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
        environment='dev',
    )


def _cloud_run_document(*, revision: str, image: str, environment: str = 'dev') -> dict:
    return {
        'spec': {
            'template': {
                'spec': {
                    'timeoutSeconds': 300,
                    'containers': [{'image': image, 'env': [{'name': 'OMI_ENV_STAGE', 'value': environment}]}],
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
        f'cloud_run/{service}': _cloud_run_document(
            revision=revision,
            image=expectation.image,
            environment=expectation.environment,
        )
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
                                {
                                    'image': expectation.image,
                                    'env': [{'name': 'OMI_ENV_STAGE', 'value': expectation.environment}],
                                }
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


def test_legacy_binding_migration_rejects_mismatched_projects_without_gcloud_calls() -> None:
    preflight = _load_preflight()
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="prod expects project 'based-hardware'"):
        preflight.migrate_legacy_public_bindings(
            services=('backend',),
            env='prod',
            project='based-hardware-dev',
            region='us-central1',
            runner=lambda command, **_kwargs: calls.append(command),
        )

    assert calls == []


def test_legacy_binding_migration_strips_prod_legacy_bindings() -> None:
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
                                    'name': 'GOOGLE_CLIENT_SECRET',
                                    'valueFrom': {'secretKeyRef': {'name': 'GOOGLE_CLIENT_SECRET', 'key': 'latest'}},
                                },
                            ]
                        }
                    ]
                }
            }
        }
    }
    commands: list[list[str]] = []

    def runner(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=json.dumps(legacy_service))

    migrated = preflight.migrate_legacy_public_bindings(
        services=('backend',),
        env='prod',
        project='based-hardware',
        region='us-central1',
        runner=runner,
    )

    assert migrated == ['backend']
    update = commands[-1]
    assert update[:5] == ['gcloud', 'run', 'services', 'update', 'backend']
    assert '--project=based-hardware' in update
    assert '--no-traffic' in update
    # Only the manifest-declared public setting is stripped; the real secret stays bound.
    assert '--remove-secrets=GOOGLE_CLIENT_ID' in update


def test_prod_deploy_invokes_legacy_binding_migration_before_deploy() -> None:
    workflow = BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml'
    text = workflow.read_text(encoding='utf-8')

    assert 'backend/scripts/preflight-cloud-run-deploy.py' in text
    assert text.count('--migrate-legacy-public-binding') == 4
    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        assert f'--migrate-legacy-public-binding {service}' in text
    assert text.index('migrate-legacy-public-binding') < text.index('Deploy ${{ env.SERVICE }} to Cloud Run')


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


def test_static_release_vector_verify_binds_the_workflow_short_sha() -> None:
    # git rev-parse --short=7 HEAD can extend past seven characters; the verifier
    # must receive the exact short SHA the workflow used to tag the image and
    # revision suffix, so it does not reject a correctly deployed release whose
    # 7-character prefix is ambiguous. Every release-vector verify call in the
    # backend deploy workflows must pass --short-sha bound to image-tag output.
    workflows = (
        BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml',
        BACKEND_DIR.parent / '.github/workflows/gcp_backend_auto_dev.yml',
    )
    for workflow in workflows:
        text = workflow.read_text(encoding='utf-8')
        assert 'verify_backend_release_vector.py' in text, f'{workflow.name} must invoke the release-vector verifier'
        # Count verify invocations and the --short-sha wiring; require a 1:1 match.
        invocations = text.count('verify_backend_release_vector.py \\\n')
        wired = text.count('--short-sha "${{ steps.image-tag.outputs.short_sha }}"')
        assert invocations == wired, (
            f'{workflow.name}: {invocations} release-vector verify call(s) but '
            f'{wired} --short-sha wiring(s); each verify must bind the workflow short SHA'
        )


def test_expectation_binds_commit_to_deploy_run_revision_and_image() -> None:
    expectation = _expectation()

    assert expectation.image == 'gcr.io/based-hardware-dev/backend:abcdef1'
    assert expectation.revisions['backend-sync'] == 'backend-sync-abcdef1-12345-1'
    assert expectation.listener_deployment == 'dev-omi-backend-listen'


def test_expectation_derives_a_prod_vector_with_the_matching_environment() -> None:
    expectation = verifier.build_expectation(
        commit_sha='abcdef1234567890',
        deploy_run_id='54321',
        deploy_run_attempt='2',
        project='based-hardware',
        region='us-central1',
        environment='prod',
    )

    assert expectation.image == 'gcr.io/based-hardware/backend:abcdef1'
    assert expectation.revisions['backend'] == 'backend-abcdef1-54321-2'
    assert expectation.listener_deployment == 'prod-omi-backend-listen'
    assert verifier.evaluate(expectation, _documents(expectation)) == []


def test_expectation_uses_the_workflow_short_sha_when_ambiguous() -> None:
    # git rev-parse --short=7 HEAD can return 8+ characters when the 7-character
    # prefix is ambiguous; the workflow tags the image with that longer suffix.
    # The verifier must bind to the workflow's exact short SHA rather than a
    # naive 7-character truncation of the commit SHA.
    expectation = verifier.build_expectation(
        commit_sha='abcdef1234567890',
        short_sha='abcdef12',
        deploy_run_id='12345',
        deploy_run_attempt='1',
        project='based-hardware-dev',
        region='us-central1',
        environment='dev',
    )

    assert expectation.image == 'gcr.io/based-hardware-dev/backend:abcdef12'
    assert expectation.revisions['backend'] == 'backend-abcdef12-12345-1'
    assert verifier.evaluate(expectation, _documents(expectation)) == []


def test_expectation_rejects_a_short_sha_that_is_not_a_prefix() -> None:
    with pytest.raises(ValueError, match='short SHA must be a prefix of the commit SHA'):
        verifier.build_expectation(
            commit_sha='abcdef1234567890',
            short_sha='deadbeef',
            deploy_run_id='12345',
            deploy_run_attempt='1',
            project='based-hardware-dev',
            region='us-central1',
            environment='dev',
        )


def test_expectation_rejects_a_malformed_short_sha() -> None:
    with pytest.raises(ValueError, match='short SHA must be a hexadecimal value'):
        verifier.build_expectation(
            commit_sha='abcdef1234567890',
            short_sha='abcdefg',
            deploy_run_id='12345',
            deploy_run_attempt='1',
            project='based-hardware-dev',
            region='us-central1',
            environment='dev',
        )


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


def test_evaluate_rejects_a_partial_cloud_run_traffic_apply() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['cloud_run/backend-sync']['status']['traffic'] = [{'revisionName': 'backend-sync-old', 'percent': 100}]

    errors = verifier.evaluate(expectation, documents)

    assert errors == ['cloud_run/backend-sync: expected revision does not receive 100% traffic']


def test_candidate_evaluation_accepts_ready_revision_before_traffic_promotion() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['cloud_run/backend']['status']['traffic'] = [{'revisionName': 'backend-old', 'percent': 100}]

    errors = verifier.evaluate(expectation, documents, require_serving_traffic=False)

    assert errors == []


def test_evaluate_rejects_a_listener_rollout_timeout_when_updated_replicas_lag() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    documents['gke/deployment']['status']['updatedReplicas'] = 0

    errors = verifier.evaluate(expectation, documents)

    assert 'gke/deployment: desired replicas are not all available' not in errors
    assert 'gke/deployment: desired replicas are not all updated' in errors


def test_retry_derives_a_new_vector_and_accepts_only_the_converged_attempt() -> None:
    first_attempt = _expectation()
    partial_documents = _documents(first_attempt)
    partial_documents['cloud_run/backend-integration']['status']['traffic'] = [
        {'revisionName': 'backend-integration-old', 'percent': 100}
    ]

    retry = verifier.build_expectation(
        commit_sha=first_attempt.commit_sha,
        deploy_run_id=first_attempt.deploy_run_id,
        deploy_run_attempt='2',
        project=first_attempt.project,
        region=first_attempt.region,
        environment=first_attempt.environment,
    )

    assert verifier.evaluate(first_attempt, partial_documents) == [
        'cloud_run/backend-integration: expected revision does not receive 100% traffic'
    ]
    assert retry.revisions['backend-integration'] != first_attempt.revisions['backend-integration']
    assert verifier.evaluate(retry, _documents(retry)) == []


def test_evidence_records_the_derived_release_vector() -> None:
    expectation = _expectation()

    report = verifier.evidence(expectation, _documents(expectation), [])

    assert report['release_vector'] == {
        'schema_version': 1,
        'commit_sha': 'abcdef1234567890',
        'deploy_run_id': '12345',
        'deploy_run_attempt': '1',
        'environment': 'dev',
        'immutable_image': 'gcr.io/based-hardware-dev/backend:abcdef1',
        'cloud_run_revisions': dict(expectation.revisions),
        'backend_listen': {
            'deployment': 'dev-omi-backend-listen',
            'image': 'gcr.io/based-hardware-dev/backend:abcdef1',
        },
        'require_serving_traffic': True,
    }


def test_candidate_cloud_run_only_verification_does_not_require_listener_mutations() -> None:
    expectation = _expectation()
    documents = _documents(expectation)
    cloud_run_only = {key: value for key, value in documents.items() if key.startswith('cloud_run/')}

    commands = verifier.build_read_only_commands(expectation, include_listener=False)
    errors = verifier.evaluate(
        expectation,
        cloud_run_only,
        require_serving_traffic=False,
        include_listener=False,
    )
    report = verifier.evidence(
        expectation,
        cloud_run_only,
        errors,
        require_serving_traffic=False,
        include_listener=False,
    )

    assert set(commands) == set(cloud_run_only)
    assert errors == []
    assert report['release_vector']['backend_listen_required'] is False
    assert 'gke_listener' not in report


def test_full_backend_deploys_verify_the_serving_release_vector_after_promotion() -> None:
    root = BACKEND_DIR.parent
    workflows = {
        'gcp_backend.yml': '--commit-sha "${{ needs.firestore_readiness.outputs.candidate_sha }}"',
        'gcp_backend_auto_dev.yml': '--commit-sha "${{ github.sha }}"',
    }

    for filename, commit_marker in workflows.items():
        text = (root / '.github' / 'workflows' / filename).read_text(encoding='utf-8')
        promotion = text.index('Shift Cloud Run traffic to validated revisions')
        verification = text.index('Verify serving backend release vector')
        assert promotion < verification
        release_vector_step = text[verification : text.index('\n      - name:', verification + 1)]
        assert 'backend/scripts/verify_backend_release_vector.py' in release_vector_step
        assert commit_marker in release_vector_step
        assert '--environment' in release_vector_step

    manual = (root / '.github' / 'workflows' / 'gcp_backend.yml').read_text(encoding='utf-8')
    manual_verification = manual[manual.index('Verify serving backend release vector') :]
    assert "github.event.inputs.deploy_targets == 'all'" in manual_verification


def test_backend_promotions_are_phase_aware_and_restore_the_recorded_traffic_snapshot() -> None:
    """Static workflow contract for #9950; live traffic mutation remains CI-owned."""
    root = BACKEND_DIR.parent
    workflows = (
        '.github/workflows/gcp_backend.yml',
        '.github/workflows/gcp_backend_auto_dev.yml',
    )

    for relative in workflows:
        text = (root / relative).read_text(encoding='utf-8')

        candidate_acceptance = text.index('Accept no-traffic Cloud Run candidate')
        runtime_config = text.index('Apply non-secret backend runtime config')
        backend_secrets = text.index('Deploy backend-secrets')
        backend_listen = text.index('Deploy ${{ env.SERVICE }}-listen to GKE')
        snapshot = text.index('Capture Cloud Run pre-promotion traffic snapshot')
        promotion = text.index('Shift Cloud Run traffic to validated revisions')
        serving_vector = text.index('Verify serving backend release vector')
        restore = text.index('Restore Cloud Run traffic snapshot after failed promotion')

        assert candidate_acceptance < runtime_config, relative
        assert candidate_acceptance < backend_secrets, relative
        assert candidate_acceptance < backend_listen, relative
        assert candidate_acceptance < snapshot < promotion < serving_vector < restore, relative

        snapshot_step = text[snapshot : text.index('\n      - name:', snapshot + 1)]
        assert 'backend/scripts/cloud_run_traffic_snapshot.py capture' in snapshot_step
        for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            assert f'--service {service}' in snapshot_step

        restore_step = text[restore : text.index('\n      - name:', restore + 1)]
        expected_restore_condition = (
            "if: ${{ failure() && steps.cloud-run-traffic-snapshot.outcome == 'success' "
            "&& (steps.shift-cloud-run-traffic.outcome == 'failure' "
            "|| steps.verify-serving-release-vector.outcome == 'failure') }}"
        )
        assert expected_restore_condition in restore_step
        assert 'backend/scripts/cloud_run_traffic_snapshot.py restore' in restore_step

        evidence_upload = text[text.index('Upload ') :]
        assert 'cloud-run-pre-promotion-traffic-snapshot.json' in evidence_upload
        assert 'cloud-run-traffic-restore.json' in evidence_upload


def test_backend_listen_rollout_wait_can_cover_a_real_rollout():
    """The rollout wait must outlast a healthy roll, not just one pod's startup.

    backend-listen rolls `maxSurge + maxUnavailable` pods at a time and its
    startupProbe alone permits `failureThreshold * periodSeconds` per pod, so a
    wait sized for a single pod fails a healthy deploy (2026-07-17, run
    29576112586: 28 replicas, `timed out waiting for the condition`, rollout
    converged on its own minutes later). A stalled rollout is caught by the
    deployment's progressDeadlineSeconds, not by this bound.
    """
    import re

    import yaml

    root = BACKEND_DIR.parent
    values = yaml.safe_load(
        (root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml').read_text(encoding='utf-8')
    )
    startup = values['startupProbe']
    per_pod_startup_seconds = startup['failureThreshold'] * startup['periodSeconds']
    min_replicas = values['autoscaling']['minReplicas']
    rolling = values['strategy']['rollingUpdate']
    pods_in_flight = rolling['maxSurge'] + rolling['maxUnavailable']

    # Even at the HPA floor the roll needs this many sequential waves.
    waves = -(-min_replicas // pods_in_flight)
    required_seconds = waves * per_pod_startup_seconds

    workflows = (
        '.github/workflows/gcp_backend.yml',
        '.github/workflows/gcp_backend_listen_helm.yml',
        '.github/workflows/gcp_backend_auto_dev.yml',
    )
    pattern = re.compile(r'rollout status deploy/\$\{\{ vars\.ENV \}\}-omi-backend-listen --timeout=(\d+)s')
    for relative in workflows:
        text = (root / relative).read_text(encoding='utf-8')
        found = pattern.findall(text)
        assert found, f'{relative} must wait on the backend-listen rollout'
        for value in found:
            assert int(value) >= required_seconds, (
                f'{relative} waits {value}s on backend-listen, but a roll at the HPA floor needs '
                f'>= {required_seconds}s ({waves} waves x {per_pod_startup_seconds}s startup budget)'
            )

    # The k8s deadline is the actual failure point (kubectl returns
    # ProgressDeadlineExceeded the moment it trips, regardless of the CLI
    # --timeout). It defaults to 600s and must be raised to cover a real roll,
    # or a healthy-but-slow rollout fails at the deployment level even though the
    # CLI would wait (2026-07-17, runs 29591891153 / 29611750428).
    progress_deadline = values.get('progressDeadlineSeconds')
    assert progress_deadline is not None, (
        'backend-listen chart must set progressDeadlineSeconds; the k8s default (600s) '
        f'is below the {required_seconds}s a real roll needs'
    )
    assert progress_deadline >= required_seconds, (
        f'progressDeadlineSeconds={progress_deadline}s is below the {required_seconds}s a roll at '
        f'the HPA floor needs ({waves} waves x {per_pod_startup_seconds}s startup budget)'
    )

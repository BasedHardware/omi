from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/validate-backend-runtime-env.py'
READINESS_PROPOSAL_ARGS = (
    ' --proposal-output "$FIRESTORE_PROPOSAL_PATH"'
    ' --source-commit "$FIRESTORE_SOURCE_COMMIT"'
    ' --proposal-ttl-seconds 3600'
)


def load_validator():
    spec = importlib.util.spec_from_file_location('validate_backend_runtime_env', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_yaml(path: Path, payload: dict) -> None:
    with path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def with_memory_env(payload: str) -> str:
    memory_env = '''\
        {"name": "DESKTOP_UPDATE_POINTERS_MODE", "value": "primary"},
        {"name": "DESKTOP_UPDATE_RECONCILE_SAMPLE_RATE", "value": "0.01"},
        {"name": "OMI_ENV_STAGE", "value": "dev"},
        {"name": "HOSTED_PARAKEET_API_URL", "value": "http://parakeet.omiapi.com"},
        {"name": "OMI_LLM_GATEWAY_FEATURE_MODE", "value": "gateway"},
        {"name": "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION", "value": "true"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_SAMPLE_RATE", "value": "1.0"},
        {"name": "POSTHOG_HOST", "value": "https://app.posthog.com"},
        {"name": "STT_PRERECORDED_MODEL", "value": "parakeet,dg-nova-3"},
        {"name": "HOSTED_PARAKEET_API_URL", "value": "http://parakeet.omiapi.com"},
        {"name": "DEEPGRAM_API_KEY", "valueFrom": {"secretKeyRef": {"name": "DEEPGRAM_API_KEY", "key": "latest"}}},
        {"name": "MODULATE_API_KEY", "valueFrom": {"secretKeyRef": {"name": "MODULATE_API_KEY", "key": "latest"}}},
        {"name": "GOOGLE_CLIENT_ID", "value": "fake-public-client-id"},
        {"name": "GOOGLE_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_SECRET", "key": "latest"}}},
        {"name": "POSTHOG_PROJECT_API_KEY", "valueFrom": {"secretKeyRef": {"name": "POSTHOG_PROJECT_API_KEY", "key": "latest"}}},
        {"name": "MEMORY_MODE", "value": "read"},
        {"name": "MEMORY_ENABLED_USERS", "value": "vi7SA9ckQCe4ccobWNxlbdcNdC23"},
        {"name": "MEMORY_V3_GET_ENABLED", "value": "true"},
        {"name": "MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "value": "false"},
        {"name": "MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED", "value": "true"},'''
    return payload.replace(
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},',
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},\n'
        '        {"name": "GCP_LOCATION", "value": "us-central1"},\n'
        '        {"name": "USE_VERTEX_AI", "value": "true"},\n' + memory_env,
    )


def with_sync_ledger_fence_mode(payload: str) -> str:
    """Keep offline Cloud Run state fixtures aligned with the protected rollout default."""
    return payload.replace(
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},',
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},\n'
        '        {"name": "SYNC_LEDGER_FENCE_MODE", "value": "legacy"},',
    )


GOOGLE_OAUTH_SECRETS = '''\
        {"name": "GOOGLE_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_SECRET"}}},
        {"name": "DEEPGRAM_API_KEY", "valueFrom": {"secretKeyRef": {"name": "DEEPGRAM_API_KEY", "key": "latest"}}},
        {"name": "MODULATE_API_KEY", "valueFrom": {"secretKeyRef": {"name": "MODULATE_API_KEY", "key": "latest"}}},'''


def with_cloud_run_oauth_secrets(payload: str) -> str:
    payload = with_memory_env(with_sync_ledger_fence_mode(payload))
    return re.sub(
        r'^(\s*\{"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN".*\}\s*\})\s*,?\s*$',
        r'\1,\n' + GOOGLE_OAUTH_SECRETS.rstrip(','),
        payload,
        flags=re.MULTILINE,
    )


def validate_cloud_run_workflows_only(validator, *, env: str, manifest_path: Path):
    """Exercise a workflow fixture without unrelated full-manifest rollout contracts."""
    manifest = validator._load_yaml(manifest_path)
    return validator._validate_cloud_run_workflows(
        env,
        validator._get_env_config(manifest, env),
        strict_provisional=False,
        manifest_path=manifest_path,
        manifest=manifest,
    )


STANDARD_CLOUD_RUN_SECRETS = {
    'GOOGLE_CLIENT_ID': {'secret': 'GOOGLE_CLIENT_ID', 'version': 'latest'},
    'GOOGLE_CLIENT_SECRET': {'secret': 'GOOGLE_CLIENT_SECRET', 'version': 'latest'},
    'DEEPGRAM_API_KEY': {'secret': 'DEEPGRAM_API_KEY', 'version': 'latest'},
    'MODULATE_API_KEY': {'secret': 'MODULATE_API_KEY', 'version': 'latest'},
}


def memory_maintenance_job_block(*, mode: str = 'off', cron: str = 'false', users: str = '') -> dict:
    """Minimal job contract for fixture manifests (keeps validator happy)."""
    return {
        'env': {
            'MEMORY_MODE': {'value': mode, 'category': 'memory_rollout'},
            'MEMORY_ENABLED_USERS': {'value': users, 'category': 'memory_rollout'},
            'MEMORY_V3_GET_ENABLED': {'value': 'false' if mode == 'off' else 'true', 'category': 'memory_rollout'},
            'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED': {'value': cron, 'category': 'memory_rollout'},
            'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED': {
                'value': 'false',
                'category': 'memory_rollout',
            },
            'MEMORY_CANONICAL_CONSOLIDATION_ENABLED': {'value': 'true', 'category': 'memory_rollout'},
        },
        'secrets': {
            'SERVICE_ACCOUNT_JSON': {'secret': 'SERVICE_ACCOUNT_JSON', 'version': 'latest'},
            'ENCRYPTION_SECRET': {'secret': 'ENCRYPTION_SECRET', 'version': 'latest'},
            'OPENAI_API_KEY': {'secret': 'OPENAI_API_KEY', 'version': 'latest'},
            'PINECONE_API_KEY': {'secret': 'PINECONE_API_KEY', 'version': 'latest'},
            'TYPESENSE_HOST': {'secret': 'TYPESENSE_HOST', 'version': 'latest'},
            'TYPESENSE_API_KEY': {'secret': 'TYPESENSE_API_KEY', 'version': 'latest'},
        },
    }


def test_repo_gke_values_match_manifest():
    validator = load_validator()

    errors = validator.validate_runtime_env(env='dev')

    assert errors == []


def test_repo_prod_gke_values_match_manifest():
    validator = load_validator()

    errors = validator.validate_runtime_env(env='prod')

    assert errors == []


def test_prod_account_deletion_dispatch_contract_rejects_missing_or_inline_profile():
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)
    prod = manifest['environments']['prod']

    assert validator._validate_account_deletion_dispatch_contract('prod', prod) == []

    backend_env = prod['cloud_run']['services']['backend']['env']
    missing_entry = backend_env.pop('ACCOUNT_DELETION_DISPATCH_MODE')
    try:
        assert validator.ValidationError(
            'prod/cloud_run/backend',
            'missing required account-deletion env ACCOUNT_DELETION_DISPATCH_MODE',
        ) in validator._validate_account_deletion_dispatch_contract('prod', prod)
    finally:
        backend_env['ACCOUNT_DELETION_DISPATCH_MODE'] = missing_entry

    dispatch_mode = prod['gke']['backend-listen']['env']['ACCOUNT_DELETION_DISPATCH_MODE']
    original_mode = dispatch_mode['value']
    dispatch_mode['value'] = 'inline'
    try:
        assert validator.ValidationError(
            'prod/gke/backend-listen',
            "account-deletion env ACCOUNT_DELETION_DISPATCH_MODE must be literal 'cloud_tasks'",
        ) in validator._validate_account_deletion_dispatch_contract('prod', prod)
    finally:
        dispatch_mode['value'] = original_mode


def test_gke_config_map_contract_rejects_missing_config_map(tmp_path):
    validator = load_validator()
    values_path = tmp_path / 'values.yaml'
    write_yaml(
        values_path,
        {
            'envFrom': [{'configMapRef': {'name': 'test-omi-backend-config'}}],
            'env': [],
        },
    )
    env_config = {
        'gke': {
            'backend-listen': {
                'values_file': str(values_path),
                'env': {
                    'FAKE_RUNTIME_CONFIG': {
                        'config_map': {
                            'name': 'test-omi-backend-config',
                            'key': 'FAKE_RUNTIME_CONFIG',
                        }
                    }
                },
            }
        }
    }

    assert validator._validate_gke(env_config, strict_provisional=False) == []

    write_yaml(values_path, {'envFrom': [], 'env': []})

    assert validator._validate_gke(env_config, strict_provisional=False) == [
        validator.ValidationError(
            'gke/backend-listen',
            "env FAKE_RUNTIME_CONFIG must come from ConfigMap 'test-omi-backend-config'",
        )
    ]


def test_repo_cloud_run_workflows_match_manifest():
    validator = load_validator()

    errors = validator.validate_runtime_env(env='dev', check_workflows=True)

    assert errors == []


def test_repo_prod_cloud_run_workflows_match_manifest(monkeypatch):
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)
    env_config = validator._get_env_config(manifest, 'prod')
    load_yaml = validator._load_yaml

    def load_workflow_only(path):
        if path == validator.DEFAULT_MANIFEST:
            pytest.fail('workflow validation must reuse the already-loaded runtime manifest')
        return load_yaml(path)

    monkeypatch.setattr(
        validator,
        '_load_yaml',
        load_workflow_only,
    )

    errors = validator._validate_cloud_run_workflows(
        'prod',
        env_config,
        strict_provisional=False,
        manifest_path=validator.DEFAULT_MANIFEST,
        manifest=manifest,
    )

    assert errors == []


@pytest.mark.parametrize(
    ('run', 'message'),
    [
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.GCP_PROJECT_ID }}" --check-only' + READINESS_PROPOSAL_ARGS,
            'Firestore index reconciliation must target vars.RUNTIME_GCP_PROJECT_ID',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py ' '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}"',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only'
            + READINESS_PROPOSAL_ARGS.replace('3600', '7200'),
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only --provision-missing',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only --dry-run',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only' + READINESS_PROPOSAL_ARGS + '\n'
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}"',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            '# readiness check\n'
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only' + READINESS_PROPOSAL_ARGS + '\n'
            '# the writer below must remain visible\n'
            'python3 backend/scripts/reconcile_firestore_indexes.py '
            '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}"',
            'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
        ),
        (
            'npx firebase deploy --only firestore:indexes',
            'backend deploy Firestore operations must be read-only (--check-only)',
        ),
        (
            'npx firebase deploy',
            'backend deploy Firestore operations must be read-only (--check-only)',
        ),
        (
            'npx firebase deploy --project prod --only=firestore:indexes',
            'backend deploy Firestore operations must be read-only (--check-only)',
        ),
        (
            'gcloud --project=prod firestore indexes composite create --collection-group=memories',
            'backend deploy Firestore operations must be read-only (--check-only)',
        ),
    ],
)
def test_firestore_index_reconciliation_preserves_the_read_only_runtime_boundary(tmp_path, run, message):
    validator = load_validator()
    workflow_path = tmp_path / 'deploy.yml'
    manifest_path = tmp_path / 'runtime_env.yaml'
    workflow = {'jobs': {'deploy': {'steps': [{'run': run}]}}}
    manifest = {
        'schema_version': 1,
        'environments': {
            'dev': {
                'gcp_project': 'deployment-project',
                'runtime_gcp_project': 'serving-project',
                'region': 'us-central1',
                'gke': {},
                'cloud_run': {
                    'workflow_files': [str(workflow_path)],
                    'services': {},
                    'jobs': {},
                },
            }
        },
    }
    write_yaml(workflow_path, workflow)
    write_yaml(manifest_path, manifest)

    errors = validate_cloud_run_workflows_only(validator, env='dev', manifest_path=manifest_path)

    assert errors == [
        validator.ValidationError(
            f'cloud_run_workflow/{workflow_path}',
            message,
        )
    ]

    workflow['jobs']['deploy']['steps'][0]['run'] = (
        'python3 backend/scripts/reconcile_firestore_indexes.py '
        '--project "${{ vars.RUNTIME_GCP_PROJECT_ID }}" --check-only' + READINESS_PROPOSAL_ARGS
    )
    write_yaml(workflow_path, workflow)

    assert validate_cloud_run_workflows_only(validator, env='dev', manifest_path=manifest_path) == []


@pytest.mark.parametrize('workflow_name', ['gcp_backend.yml', 'gcp_backend_auto_dev.yml'])
def test_firestore_readiness_contract_requires_isolated_job_dependency(workflow_name):
    validator = load_validator()
    workflow_path = ROOT.parent / '.github/workflows' / workflow_name
    workflow = validator._load_yaml(workflow_path)
    workflow['jobs']['deploy'].pop('needs')

    errors = validator._validate_firestore_index_reconciliation_boundary(str(workflow_path), workflow)

    assert any('deploy must depend on the isolated Firestore readiness job' in error.message for error in errors)


@pytest.mark.parametrize('workflow_name', ['gcp_backend.yml', 'gcp_backend_auto_dev.yml'])
def test_firestore_readiness_contract_requires_validation_before_artifact_upload(workflow_name):
    validator = load_validator()
    workflow_path = ROOT.parent / '.github/workflows' / workflow_name
    workflow = validator._load_yaml(workflow_path)
    steps = workflow['jobs']['firestore_readiness']['steps']
    upload_index = next(index for index, step in enumerate(steps) if step.get('uses') == 'actions/upload-artifact@v7')
    upload = steps.pop(upload_index)
    validation_index = next(
        index for index, step in enumerate(steps) if step.get('id') == 'validate_firestore_proposal'
    )
    steps.insert(validation_index, upload)

    errors = validator._validate_firestore_index_reconciliation_boundary(str(workflow_path), workflow)

    assert any('only a successfully validated bounded proposal may be uploaded' in error.message for error in errors)


@pytest.mark.parametrize('workflow_name', ['gcp_backend.yml', 'gcp_backend_auto_dev.yml'])
def test_firestore_readiness_contract_rejects_backend_deployment_credentials(workflow_name):
    validator = load_validator()
    workflow_path = ROOT.parent / '.github/workflows' / workflow_name
    workflow = validator._load_yaml(workflow_path)
    auth = next(
        step
        for step in workflow['jobs']['firestore_readiness']['steps']
        if step.get('uses') == 'google-github-actions/auth@v3'
    )
    auth['with']['credentials_json'] = '${{ secrets.GCP_CREDENTIALS }}'

    errors = validator._validate_firestore_index_reconciliation_boundary(str(workflow_path), workflow)

    assert any('must not receive backend deployment credentials' in error.message for error in errors)


def test_repo_prod_rendered_cloud_run_state_matches_manifest():
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)
    env_config = validator._get_env_config(manifest, 'prod')
    rendered_state = validator._build_rendered_cloud_run_state(env_config)

    errors = validator._validate_cloud_run(env_config, rendered_state, strict_provisional=False)

    assert errors == []


def test_parakeet_cloud_run_surface_requires_hosted_endpoint():
    validator = load_validator()
    env_config = {
        'gke': {},
        'cloud_run': {
            'services': {
                service: {
                    'env': {'HOSTED_PARAKEET_API_URL': {'value': 'http://parakeet.omiapi.com'}},
                    'secrets': {
                        'STT_PRERECORDED_MODEL': {
                            'secret': 'STT_PRERECORDED_MODEL',
                            'version': 'latest',
                        },
                        'DEEPGRAM_API_KEY': {'secret': 'DEEPGRAM_API_KEY', 'version': 'latest'},
                        'MODULATE_API_KEY': {'secret': 'MODULATE_API_KEY', 'version': 'latest'},
                    },
                }
                for service in ('backend', 'backend-sync', 'backend-integration')
            }
        },
    }
    del env_config['cloud_run']['services']['backend']['env']['HOSTED_PARAKEET_API_URL']

    for environment in ('dev', 'prod'):
        errors = validator._validate_prerecorded_stt_contract(environment, env_config)

        assert errors == [
            validator.ValidationError(
                f'{environment}/cloud_run/backend',
                'required Cloud Run service is missing non-empty HOSTED_PARAKEET_API_URL',
            )
        ]


def test_dev_cloud_run_prerecorded_stt_services_require_both_bindings():
    validator = load_validator()
    env_config = {
        'cloud_run': {
            'services': {
                'backend': {'env': {}, 'secrets': {}},
                'backend-sync': {'env': {}, 'secrets': {}},
                'backend-integration': {'env': {}, 'secrets': {}},
            }
        }
    }

    errors = validator._validate_prerecorded_stt_contract('dev', env_config)

    assert len(errors) == 12
    assert {error.scope for error in errors} == {
        'dev/cloud_run/backend',
        'dev/cloud_run/backend-sync',
        'dev/cloud_run/backend-integration',
    }
    assert {error.message for error in errors} == {
        'required Cloud Run service is missing STT_PRERECORDED_MODEL',
        'required Cloud Run service is missing non-empty DEEPGRAM_API_KEY',
        'required Cloud Run service is missing non-empty MODULATE_API_KEY',
        'required Cloud Run service is missing non-empty HOSTED_PARAKEET_API_URL',
    }


def test_literal_deepgram_model_does_not_require_parakeet_endpoint():
    validator = load_validator()
    env_config = {
        'gke': {
            'backend-listen': {
                'env': {
                    'STT_PRERECORDED_MODEL': {'value': 'dg-nova-3'},
                    'DEEPGRAM_API_KEY': {'secret': {'name': 'secret', 'key': 'DEEPGRAM_API_KEY'}},
                },
            }
        },
        'cloud_run': {'services': {}},
    }

    assert validator._validate_prerecorded_stt_contract('prod', env_config) == []


def test_literal_modulate_model_requires_its_declared_api_key_binding():
    validator = load_validator()
    env_config = {
        'gke': {
            'backend-listen': {
                'env': {
                    'STT_PRERECORDED_MODEL': {'value': 'modulate-velma-2'},
                    'DEEPGRAM_API_KEY': {'secret': {'name': 'secret', 'key': 'DEEPGRAM_API_KEY'}},
                },
            }
        },
        'cloud_run': {'services': {}},
    }

    assert validator._validate_prerecorded_stt_contract('prod', env_config) == [
        validator.ValidationError(
            'prod/gke/backend-listen',
            'STT_PRERECORDED_MODEL requires non-empty MODULATE_API_KEY',
        )
    ]


def test_literal_model_configs_require_deepgram_language_and_unknown_token_fallback():
    validator = load_validator()
    cases = (
        ('parakeet', {'HOSTED_PARAKEET_API_URL': {'value': 'http://parakeet.local'}}),
        ('modulate-velma-2', {'MODULATE_API_KEY': {'secret': {'name': 'secret', 'key': 'MODULATE_API_KEY'}}}),
        ('unknown-model', {}),
    )

    for models, provider_env in cases:
        env_config = {
            'gke': {
                'backend-listen': {
                    'env': {
                        'STT_PRERECORDED_MODEL': {'value': models},
                        **provider_env,
                    },
                }
            },
            'cloud_run': {'services': {}},
        }

        assert validator._validate_prerecorded_stt_contract('prod', env_config) == [
            validator.ValidationError(
                'prod/gke/backend-listen',
                'STT_PRERECORDED_MODEL requires non-empty DEEPGRAM_API_KEY',
            )
        ]


def test_full_validation_reports_missing_provider_binding_once():
    """Missing HOSTED_PARAKEET_API_URL must surface once per service, not fan out.

    Uses the pure STT contract helper with a tiny synthetic env so this stays under
    the fast-unit CPU budget (full-manifest validate_runtime_env is covered elsewhere).
    """
    validator = load_validator()
    env_config = {
        'gke': {},
        'cloud_run': {
            'services': {
                service: {
                    'env': {'HOSTED_PARAKEET_API_URL': {'value': 'http://parakeet.local'}},
                    'secrets': {
                        'STT_PRERECORDED_MODEL': {
                            'secret': 'STT_PRERECORDED_MODEL',
                            'version': 'latest',
                        },
                        'DEEPGRAM_API_KEY': {'secret': 'DEEPGRAM_API_KEY', 'version': 'latest'},
                        'MODULATE_API_KEY': {'secret': 'MODULATE_API_KEY', 'version': 'latest'},
                    },
                }
                for service in ('backend', 'backend-sync', 'backend-integration')
            }
        },
    }
    del env_config['cloud_run']['services']['backend']['env']['HOSTED_PARAKEET_API_URL']

    errors = validator._validate_prerecorded_stt_contract('dev', env_config)
    matching = [
        error
        for error in errors
        if error.scope == 'dev/cloud_run/backend' and 'HOSTED_PARAKEET_API_URL' in error.message
    ]

    assert matching == [
        validator.ValidationError(
            'dev/cloud_run/backend',
            'required Cloud Run service is missing non-empty HOSTED_PARAKEET_API_URL',
        )
    ]
    assert len(errors) == 1


def test_cloud_run_state_reports_missing_gateway_url(tmp_path):
    validator = load_validator()
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        with_cloud_run_oauth_secrets(
            '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    },
    "backend-sync": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    },
    "backend-integration": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    }
  }
}
''',
        ),
        encoding='utf-8',
    )

    errors = validator.validate_runtime_env(env='dev', cloud_run_state_path=state_path)

    assert [error.message for error in errors] == ['missing env OMI_LLM_GATEWAY_URL']
    assert errors[0].scope == 'cloud_run/backend'


def test_cloud_run_workflow_reports_missing_gateway_url(tmp_path):
    validator = load_validator()
    values_file = tmp_path / 'backend_listen.yaml'
    write_yaml(
        values_file,
        {
            'env': [
                {'name': 'OMI_LLM_GATEWAY_URL', 'value': 'http://gateway.local'},
            ]
        },
    )
    workflow_file = tmp_path / 'deploy.yml'
    write_yaml(
        workflow_file,
        {
            'env': {'SERVICE': 'backend'},
            'jobs': {
                'deploy': {
                    'steps': [
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'service': '${{ env.SERVICE }}',
                                'env_vars': 'GOOGLE_CLOUD_PROJECT=${{ vars.RUNTIME_GCP_PROJECT_ID }}\n',
                            },
                        },
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'job': 'memory-maintenance-job',
                                'env_vars': (
                                    'MEMORY_MODE=off\n'
                                    'MEMORY_ENABLED_USERS=\n'
                                    'MEMORY_V3_GET_ENABLED=false\n'
                                    'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=false\n'
                                    'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=false\n'
                                    'MEMORY_CANONICAL_CONSOLIDATION_ENABLED=true\n'
                                ),
                                'secrets': (
                                    'SERVICE_ACCOUNT_JSON=SERVICE_ACCOUNT_JSON:latest\n'
                                    'ENCRYPTION_SECRET=ENCRYPTION_SECRET:latest\n'
                                    'OPENAI_API_KEY=OPENAI_API_KEY:latest\n'
                                    'PINECONE_API_KEY=PINECONE_API_KEY:latest\n'
                                    'TYPESENSE_HOST=TYPESENSE_HOST:latest\n'
                                    'TYPESENSE_API_KEY=TYPESENSE_API_KEY:latest\n'
                                ),
                            },
                        },
                    ]
                }
            },
        },
    )
    manifest_path = tmp_path / 'runtime_env.yaml'
    write_yaml(
        manifest_path,
        {
            'schema_version': 1,
            'environments': {
                'dev': {
                    'gcp_project': 'based-hardware-dev',
                    'runtime_gcp_project': 'based-hardware',
                    'region': 'us-central1',
                    'gke': {
                        'backend-listen': {
                            'values_file': str(values_file),
                            'env': {
                                'OMI_LLM_GATEWAY_URL': {
                                    'value': 'http://gateway.local',
                                },
                            },
                        }
                    },
                    'cloud_run': {
                        'workflow_files': [str(workflow_file)],
                        'services': {
                            'backend': {
                                'env': {
                                    'GOOGLE_CLOUD_PROJECT': {'value': 'based-hardware'},
                                    'OMI_LLM_GATEWAY_URL': {'value': 'http://172.16.63.232'},
                                },
                                'secrets': {},
                            }
                        },
                        'jobs': {
                            'memory-maintenance-job': memory_maintenance_job_block(),
                        },
                    },
                }
            },
        },
    )

    errors = validate_cloud_run_workflows_only(validator, env='dev', manifest_path=manifest_path)

    assert any(error.message == 'missing env OMI_LLM_GATEWAY_URL' for error in errors)
    assert any(error.scope == 'cloud_run_workflow/backend' for error in errors)


def test_cloud_run_workflow_validation_uses_custom_manifest_for_runtime_env_outputs(tmp_path):
    validator = load_validator()
    values_file = tmp_path / 'backend_listen.yaml'
    write_yaml(
        values_file,
        {
            'env': [
                {'name': 'OMI_LLM_GATEWAY_URL', 'value': 'http://gateway.local'},
            ]
        },
    )
    workflow_file = tmp_path / 'deploy.yml'
    write_yaml(
        workflow_file,
        {
            'env': {'SERVICE': 'backend'},
            'jobs': {
                'deploy': {
                    'steps': [
                        {
                            'id': 'runtime-env',
                            'run': 'python3 backend/scripts/render_backend_runtime_env.py --env dev',
                        },
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'service': '${{ env.SERVICE }}',
                                'flags': '${{ steps.runtime-env.outputs.cloud_run_flags }}',
                                'env_vars': '${{ steps.runtime-env.outputs.backend_env_vars }}',
                                'secrets': '${{ steps.runtime-env.outputs.backend_secrets }}',
                            },
                        },
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'job': 'memory-maintenance-job',
                                'env_vars': '${{ steps.runtime-env.outputs.memory_maintenance_job_env_vars }}',
                                'secrets': '${{ steps.runtime-env.outputs.memory_maintenance_job_secrets }}',
                            },
                        },
                    ]
                }
            },
        },
    )
    manifest_path = tmp_path / 'runtime_env.yaml'
    write_yaml(
        manifest_path,
        {
            'schema_version': 1,
            'environments': {
                'dev': {
                    'gcp_project': 'based-hardware-dev',
                    'runtime_gcp_project': 'based-hardware',
                    'region': 'us-central1',
                    'gke': {
                        'backend-listen': {
                            'values_file': str(values_file),
                            'env': {
                                'OMI_LLM_GATEWAY_URL': {
                                    'value': 'http://gateway.local',
                                },
                            },
                        }
                    },
                    'cloud_run': {
                        'workflow_files': [str(workflow_file)],
                        'network': {
                            'flags': {
                                '--network': 'custom-network',
                                '--subnet': 'custom-subnet',
                                '--vpc-egress': 'private-ranges-only',
                            }
                        },
                        'services': {
                            'backend': {
                                'env': {
                                    'GOOGLE_CLOUD_PROJECT': {'value': 'based-hardware'},
                                    'OMI_ENV_STAGE': {'value': 'dev'},
                                    'OMI_LLM_GATEWAY_URL': {'value': 'http://custom-manifest-gateway'},
                                    'OMI_LLM_GATEWAY_FEATURE_MODE': {'value': 'gateway'},
                                    'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION': {'value': 'true'},
                                    'OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED': {'value': 'false'},
                                    'OMI_LLM_GATEWAY_DEV_SHADOW_ALL_SAMPLE_RATE': {'value': '1.0'},
                                    'HOSTED_PARAKEET_API_URL': {'value': 'http://parakeet.omiapi.com'},
                                    'CUSTOM_MANIFEST_ONLY_MARKER': {'value': 'present'},
                                },
                                'secrets': {
                                    **STANDARD_CLOUD_RUN_SECRETS,
                                    'STT_PRERECORDED_MODEL': {
                                        'secret': 'STT_PRERECORDED_MODEL',
                                        'version': 'latest',
                                    },
                                    'DEEPGRAM_API_KEY': {
                                        'secret': 'DEEPGRAM_API_KEY',
                                        'version': 'latest',
                                    },
                                    'MODULATE_API_KEY': {
                                        'secret': 'MODULATE_API_KEY',
                                        'version': 'latest',
                                    },
                                },
                            }
                        },
                        'jobs': {
                            'memory-maintenance-job': memory_maintenance_job_block(),
                        },
                    },
                }
            },
        },
    )

    errors = validate_cloud_run_workflows_only(validator, env='dev', manifest_path=manifest_path)

    assert errors == []

    validator = load_validator()
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        with_cloud_run_oauth_secrets(
            '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    },
    "backend-sync": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    },
    "backend-integration": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    }
  }
}
''',
        ),
        encoding='utf-8',
    )

    errors = validator.validate_runtime_env(env='dev', cloud_run_state_path=state_path)

    assert errors == []


def test_cloud_run_state_rejects_old_secret_versions(tmp_path):
    validator = load_validator()
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        with_cloud_run_oauth_secrets(
            '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON", "key": "1"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET", "key": "latest"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "key": "latest"}}}
      ]
    },
    "backend-sync": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON", "key": "latest"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET", "key": "latest"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "key": "latest"}}}
      ]
    },
    "backend-integration": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "MEMORY_TYPESENSE_COLLECTION", "value": "canonical_memory_atoms"},
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON", "key": "latest"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET", "key": "latest"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "key": "latest"}}}
      ]
    }
  }
}
''',
        ),
        encoding='utf-8',
    )

    errors = validator.validate_runtime_env(env='dev', cloud_run_state_path=state_path)

    assert len(errors) == 1
    assert errors[0].scope == 'cloud_run/backend'
    assert errors[0].message == (
        "secret binding SERVICE_ACCOUNT_JSON mismatch: "
        "expected {'secret': 'SERVICE_ACCOUNT_JSON', 'version': 'latest'}"
    )


def test_provisional_prod_endpoint_requires_presence_but_not_exact_value(tmp_path):
    validator = load_validator()
    values_file = tmp_path / 'prod_backend_listen.yaml'
    write_yaml(
        values_file,
        {
            'env': [
                {
                    'name': 'OMI_LLM_GATEWAY_URL',
                    'value': 'http://prod-omi-llm-gateway.prod-omi-backend.svc.cluster.local:8080',
                },
                {
                    'name': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'prod-omi-backend-secrets',
                            'key': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
                        }
                    },
                },
            ]
        },
    )
    manifest_path = tmp_path / 'runtime_env.yaml'
    write_yaml(
        manifest_path,
        {
            'schema_version': 1,
            'environments': {
                'prod': {
                    'gcp_project': 'based-hardware',
                    'region': 'us-central1',
                    'gke': {
                        'backend-listen': {
                            'values_file': str(values_file),
                            'env': {
                                'OMI_LLM_GATEWAY_URL': {
                                    'value': 'http://prod-omi-llm-gateway.prod-omi-backend.svc.cluster.local:8080'
                                },
                                'OMI_LLM_GATEWAY_SERVICE_TOKEN': {
                                    'secret': {
                                        'name': 'prod-omi-backend-secrets',
                                        'key': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
                                    }
                                },
                            },
                        }
                    },
                    'cloud_run': {
                        'services': {
                            'backend': {
                                'env': {
                                    'OMI_LLM_GATEWAY_URL': {
                                        'value': 'TBD_STABLE_PRIVATE_ENDPOINT',
                                        'provisional': True,
                                    },
                                    'HOSTED_PARAKEET_API_URL': {'value': 'http://parakeet.omi.me'},
                                },
                                'secrets': {
                                    'OMI_LLM_GATEWAY_SERVICE_TOKEN': {
                                        'secret': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
                                        'version': 'latest',
                                    },
                                    'STT_PRERECORDED_MODEL': {
                                        'secret': 'STT_PRERECORDED_MODEL',
                                        'version': 'latest',
                                    },
                                    'DEEPGRAM_API_KEY': {'secret': 'DEEPGRAM_API_KEY', 'version': 'latest'},
                                    'MODULATE_API_KEY': {'secret': 'MODULATE_API_KEY', 'version': 'latest'},
                                },
                            }
                        },
                        'jobs': {
                            'memory-maintenance-job': memory_maintenance_job_block(),
                        },
                    },
                }
            },
        },
    )
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        '''
{
  "services": {
    "backend": {
        "env": [
          {"name": "OMI_LLM_GATEWAY_URL", "value": "http://stable-private-endpoint"},
          {"name": "HOSTED_PARAKEET_API_URL", "value": "http://parakeet.omi.me"},
          {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}},
          {"name": "STT_PRERECORDED_MODEL", "valueFrom": {"secretKeyRef": {"name": "STT_PRERECORDED_MODEL"}}},
          {"name": "DEEPGRAM_API_KEY", "valueFrom": {"secretKeyRef": {"name": "DEEPGRAM_API_KEY"}}},
          {"name": "MODULATE_API_KEY", "valueFrom": {"secretKeyRef": {"name": "MODULATE_API_KEY"}}}
      ]
    }
  }
}
''',
        encoding='utf-8',
    )

    manifest = validator._load_yaml(manifest_path)
    errors = validator._validate_cloud_run(
        validator._get_env_config(manifest, 'prod'),
        validator._load_json(state_path),
        strict_provisional=False,
    )

    assert errors == []


def test_provisional_cloud_run_env_missing_is_allowed():
    validator = load_validator()
    errors = validator._validate_env_entries(
        scope='cloud_run/backend',
        expected={
            'OMI_LLM_GATEWAY_URL': {
                'env_var': 'OMI_LLM_GATEWAY_URL',
                'provisional': True,
            },
            'MEMORY_MODE': {'value': 'canonical'},
        },
        actual={'MEMORY_MODE': {'name': 'MEMORY_MODE', 'value': 'canonical'}},
        strict_provisional=False,
    )

    assert errors == []


def test_empty_literal_env_matches_cloud_run_entry_without_value():
    validator = load_validator()
    errors = validator._validate_env_entries(
        scope='cloud_run/backend',
        expected={'MEMORY_ENABLED_USERS': {'value': ''}},
        actual={'MEMORY_ENABLED_USERS': {'name': 'MEMORY_ENABLED_USERS'}},
        strict_provisional=False,
    )

    assert errors == []


def test_non_empty_literal_env_still_rejects_cloud_run_entry_without_value():
    validator = load_validator()
    errors = validator._validate_env_entries(
        scope='cloud_run/backend',
        expected={'MEMORY_MODE': {'value': 'off'}},
        actual={'MEMORY_MODE': {'name': 'MEMORY_MODE'}},
        strict_provisional=False,
    )

    assert len(errors) == 1
    assert errors[0].message == "env MEMORY_MODE value mismatch: expected 'off'"


def test_backend_listen_chart_only_workflow_preserves_runtime_project():
    workflow_path = ROOT.parent / '.github/workflows/gcp_backend_listen_helm.yml'
    workflow_text = workflow_path.read_text(encoding='utf-8')

    assert workflow_text.count('--set runtimeGcpProjectId=${{ vars.RUNTIME_GCP_PROJECT_ID }}') == 2


def test_repo_rendered_cloud_run_matches_manifest():
    validator = load_validator()

    assert validator.validate_runtime_env(env='dev', check_rendered_cloud_run=True) == []
    assert validator.validate_runtime_env(env='prod', check_rendered_cloud_run=True) == []


def test_parakeet_selected_without_endpoint_is_rejected_for_all_cloud_run_validation_modes(tmp_path):
    validator = load_validator()
    manifest = copy.deepcopy(validator._load_yaml(ROOT / 'deploy/runtime_env.yaml'))
    services = manifest['environments']['dev']['cloud_run']['services']
    required_dev_services = {'backend', 'backend-sync', 'backend-integration'}
    affected_services: list[str] = []
    for service_name, service in services.items():
        env = service.setdefault('env', {})
        secrets = service.get('secrets') or {}
        has_prerecorded_binding = (
            'HOSTED_PARAKEET_API_URL' in env or 'STT_PRERECORDED_MODEL' in env or 'STT_PRERECORDED_MODEL' in secrets
        )
        if not has_prerecorded_binding:
            continue
        affected_services.append(service_name)
        env.pop('HOSTED_PARAKEET_API_URL', None)

    manifest_path = tmp_path / 'runtime_env.yaml'
    write_yaml(manifest_path, manifest)

    errors = validator.validate_runtime_env(env='dev', manifest_path=manifest_path, check_rendered_cloud_run=True)

    missing_endpoint_messages = {
        'required Cloud Run service is missing non-empty HOSTED_PARAKEET_API_URL',
        'STT_PRERECORDED_MODEL requires non-empty HOSTED_PARAKEET_API_URL',
    }
    assert {(error.scope, error.message) for error in errors if error.message in missing_endpoint_messages} == {
        (
            f'dev/cloud_run/{service_name}',
            (
                'required Cloud Run service is missing non-empty HOSTED_PARAKEET_API_URL'
                if service_name in required_dev_services
                else 'STT_PRERECORDED_MODEL requires non-empty HOSTED_PARAKEET_API_URL'
            ),
        )
        for service_name in affected_services
    }


def test_prod_cloud_run_secret_bindings_exclude_stale_optional_secrets():
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    prod_services = manifest['environments']['prod']['cloud_run']['services']
    stale_secrets = {'SERVICE_ACCOUNT_JSON', 'POSTHOG_PROJECT_API_KEY'}

    for service_name, service_config in prod_services.items():
        secret_names = set((service_config.get('secrets') or {}).keys())
        assert stale_secrets.isdisjoint(secret_names), f'{service_name} still binds stale secrets'


def test_memory_maintenance_job_contract_passes_for_repo_manifest():
    validator = load_validator()
    assert validator.validate_runtime_env(env='dev') == []
    assert validator.validate_runtime_env(env='prod') == []


def test_memory_maintenance_job_contract_rejects_missing_dev_capacity_flag():
    validator = load_validator()
    job = memory_maintenance_job_block()
    job['flags'] = {
        '--task-timeout': '3600s',
        '--cpu': '2',
        '--memory': '2Gi',
    }
    del job['flags']['--memory']

    errors = validator._validate_memory_maintenance_job_contract(
        'dev',
        {'cloud_run': {'jobs': {'memory-maintenance-job': job}}},
    )

    assert (
        validator.ValidationError(
            'dev/cloud_run/jobs/memory-maintenance-job',
            'missing required dev Cloud Run flag --memory',
        )
        in errors
    )


def test_memory_maintenance_job_contract_rejects_wrong_dev_capacity_value(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    job = manifest['environments']['dev']['cloud_run']['jobs']['memory-maintenance-job']
    job['flags']['--cpu'] = '1'
    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)

    errors = validator.validate_runtime_env(env='dev', manifest_path=path)

    assert (
        validator.ValidationError(
            'dev/cloud_run/jobs/memory-maintenance-job',
            "dev Cloud Run flag --cpu must be '2'",
        )
        in errors
    )


def test_memory_maintenance_job_contract_rejects_notifications_job_maintenance_config(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    notifications_job = manifest['environments']['dev']['cloud_run']['jobs']['notifications-job']
    forbidden_env = {
        'MEMORY_MODE',
        'MEMORY_ENABLED_USERS',
        'MEMORY_V3_GET_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'MEMORY_TYPESENSE_COLLECTION',
        'TYPESENSE_HOST',
        'TYPESENSE_HOST_PORT',
        'TYPESENSE_API_KEY',
    }
    forbidden_secrets = {'TYPESENSE_HOST', 'TYPESENSE_API_KEY'}
    notifications_job['env'].update({name: {'value': 'true', 'category': 'memory_rollout'} for name in forbidden_env})
    notifications_job['secrets'].update({name: {'secret': name, 'version': 'latest'} for name in forbidden_secrets})

    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='dev', manifest_path=path)

    actual = {(error.scope, error.message) for error in errors}
    expected = {
        ('dev/cloud_run/jobs/notifications-job', f'env {name} belongs only on memory-maintenance-job')
        for name in forbidden_env
    }
    expected.update(
        {
            ('dev/cloud_run/jobs/notifications-job', f'secret {name} belongs only on memory-maintenance-job')
            for name in forbidden_secrets
        }
    )
    assert expected <= actual


def test_memory_maintenance_job_contract_rejects_read_mode_without_job_cron(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    job = manifest['environments']['prod']['cloud_run']['jobs']['memory-maintenance-job']
    # Simulate forgetting to enable the job while flipping a request-path surface to read.
    manifest['environments']['prod']['cloud_run']['services']['backend']['env']['MEMORY_MODE'] = {
        'value': 'read',
        'category': 'memory_rollout',
    }
    manifest['environments']['prod']['cloud_run']['services']['backend']['env']['MEMORY_ENABLED_USERS'] = {
        'value': 'canary-uid',
        'category': 'memory_rollout',
    }
    job['env']['MEMORY_MODE'] = {'value': 'off', 'category': 'memory_rollout'}
    job['env']['MEMORY_CANONICAL_PROMOTION_CRON_ENABLED'] = {'value': 'false', 'category': 'memory_rollout'}

    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='prod', manifest_path=path)
    messages = [error.message for error in errors]
    assert any('requires memory-maintenance-job' in message for message in messages)


def test_memory_maintenance_job_contract_rejects_missing_job(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    del manifest['environments']['prod']['cloud_run']['jobs']['memory-maintenance-job']
    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='prod', manifest_path=path)
    assert any('missing cloud_run.jobs.memory-maintenance-job' in error.message for error in errors)


def test_memory_maintenance_job_contract_rejects_request_path_cron(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    backend_env = manifest['environments']['dev']['cloud_run']['services']['backend']['env']
    backend_env['MEMORY_CANONICAL_PROMOTION_CRON_ENABLED'] = {'value': 'true', 'category': 'memory_rollout'}
    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='dev', manifest_path=path)
    assert any('request-path surfaces' in error.message for error in errors)


def test_memory_maintenance_job_contract_rejects_empty_surface_allowlist(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    backend_env = manifest['environments']['dev']['cloud_run']['services']['backend']['env']
    backend_env['MEMORY_ENABLED_USERS'] = {'value': '', 'category': 'memory_rollout'}
    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='dev', manifest_path=path)
    assert any('must match memory-maintenance-job allowlist' in error.message for error in errors)


def test_memory_maintenance_job_contract_rejects_fast_track_mismatch(tmp_path):
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    job = manifest['environments']['dev']['cloud_run']['jobs']['memory-maintenance-job']
    job['env']['MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED'] = {
        'value': 'false',
        'category': 'memory_rollout',
    }
    path = tmp_path / 'runtime_env.yaml'
    write_yaml(path, manifest)
    errors = validator.validate_runtime_env(env='dev', manifest_path=path)
    assert any('FAST_TRACK_ENABLED' in error.message for error in errors)


def test_memory_maintenance_auto_dev_workflow_is_listed_and_targets_job():
    workflow = ROOT.parent / '.github/workflows/gcp_memory_maintenance_job_auto_dev.yml'
    text = workflow.read_text(encoding='utf-8')
    assert 'SERVICE: memory-maintenance-job' in text
    assert 'branches: [ "main" ]' in text
    assert "backend/**" in text
    assert 'Dockerfile.memory_maintenance_job' in text
    assert "id-token: 'write'" not in text
    assert (
        'flags: ${{ steps.runtime-env.outputs.cloud_run_flags }} '
        '${{ steps.runtime-env.outputs.memory_maintenance_job_flags }}'
    ) in text
    manifest = yaml.safe_load((ROOT / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))
    assert (
        '.github/workflows/gcp_memory_maintenance_job_auto_dev.yml'
        in manifest['environments']['dev']['cloud_run']['workflow_files']
    )


def test_sync_backfill_co_deploy_is_required_per_workflow(tmp_path):
    validator = load_validator()
    values_file = tmp_path / 'backend_listen.yaml'
    write_yaml(values_file, {'env': [{'name': 'OMI_LLM_GATEWAY_URL', 'value': 'http://gateway.local'}]})
    incomplete = tmp_path / 'incomplete.yml'
    write_yaml(
        incomplete,
        {
            'env': {'SERVICE': 'backend'},
            'jobs': {
                'deploy': {
                    'steps': [
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'service': '${{ env.SERVICE }}-sync',
                                'env_vars': 'SYNC_BACKFILL_ENABLED=true\n',
                            },
                        }
                    ]
                }
            },
        },
    )
    complete = tmp_path / 'complete.yml'
    write_yaml(
        complete,
        {
            'env': {'SERVICE': 'backend'},
            'jobs': {
                'deploy': {
                    'steps': [
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'service': '${{ env.SERVICE }}-sync',
                                'env_vars': 'SYNC_BACKFILL_ENABLED=true\n',
                            },
                        },
                        {
                            'uses': 'google-github-actions/deploy-cloudrun@v2',
                            'with': {
                                'service': '${{ env.SERVICE }}-sync-backfill',
                                'env_vars': 'SYNC_BACKFILL_ENABLED=true\n',
                            },
                        },
                    ]
                }
            },
        },
    )
    manifest_path = tmp_path / 'runtime_env.yaml'
    write_yaml(
        manifest_path,
        {
            'schema_version': 1,
            'environments': {
                'dev': {
                    'gcp_project': 'based-hardware-dev',
                    'runtime_gcp_project': 'based-hardware',
                    'region': 'us-central1',
                    'gke': {
                        'backend-listen': {
                            'values_file': str(values_file),
                            'env': {'OMI_LLM_GATEWAY_URL': {'value': 'http://gateway.local'}},
                        }
                    },
                    'cloud_run': {
                        'workflow_files': [str(incomplete), str(complete)],
                        'services': {
                            'backend-sync': {'env': {}, 'secrets': {}},
                            'backend-sync-backfill': {'env': {}, 'secrets': {}},
                        },
                        'jobs': {},
                    },
                }
            },
        },
    )

    errors = validate_cloud_run_workflows_only(validator, env='dev', manifest_path=manifest_path)

    assert any(
        error.message == 'deploys backend-sync without backend-sync-backfill' and str(incomplete) in error.scope
        for error in errors
    )
    assert not any(
        str(complete) in error.scope and 'without backend-sync-backfill' in error.message for error in errors
    )


_ILB_ENV_VARS = ['HOSTED_PARAKEET_API_URL', 'HOSTED_TRANSLATION_API_URL']


@pytest.mark.parametrize('env_name', ['dev', 'prod'])
def test_repo_ilb_endpoints_use_http_scheme(env_name):
    """ILB endpoints are HTTP-only (no TLS) — https:// causes timeouts."""
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)
    env_config = validator._get_env_config(manifest, env_name)

    violations = []

    def _check_service(surface, svc_name, svc_cfg):
        env_vars = svc_cfg.get('env', {})
        for var_name in _ILB_ENV_VARS:
            if var_name not in env_vars:
                continue
            value = env_vars[var_name]
            url = value.get('value', '') if isinstance(value, dict) else value
            if url.startswith('https://'):
                violations.append(f'{env_name}/{surface}/{svc_name}: {var_name}={url}')

    # cloud_run: nested under 'services' key
    cloud_run_cfg = env_config.get('cloud_run', {})
    for svc_name, svc_cfg in cloud_run_cfg.get('services', {}).items():
        _check_service('cloud_run', svc_name, svc_cfg)

    # gke: service entries are direct children (not under 'services')
    gke_cfg = env_config.get('gke', {})
    for svc_name, svc_cfg in gke_cfg.items():
        if isinstance(svc_cfg, dict) and 'env' in svc_cfg:
            _check_service('gke', svc_name, svc_cfg)

    assert violations == [], f'ILB endpoints must use http:// (no TLS): {violations}'

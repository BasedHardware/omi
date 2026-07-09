from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/validate-backend-runtime-env.py'


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
        {"name": "OMI_ENV_STAGE", "value": "dev"},
        {"name": "OMI_LLM_GATEWAY_FEATURE_MODE", "value": "gateway"},
        {"name": "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION", "value": "true"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE", "value": "1.0"},
        {"name": "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED", "value": "false"},
        {"name": "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_SAMPLE_RATE", "value": "1.0"},
        {"name": "POSTHOG_HOST", "value": "https://app.posthog.com"},
        {"name": "GOOGLE_CLIENT_ID", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_ID", "key": "latest"}}},
        {"name": "GOOGLE_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_SECRET", "key": "latest"}}},
        {"name": "POSTHOG_PROJECT_API_KEY", "valueFrom": {"secretKeyRef": {"name": "POSTHOG_PROJECT_API_KEY", "key": "latest"}}},
        {"name": "MEMORY_MODE", "value": "read"},
        {"name": "MEMORY_ENABLED_USERS", "value": "vi7SA9ckQCe4ccobWNxlbdcNdC23"},
        {"name": "MEMORY_V3_GET_ENABLED", "value": "true"},
        {"name": "MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "value": "true"},
        {"name": "MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED", "value": "true"},'''
    return payload.replace(
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},',
        '        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},\n' + memory_env,
    )


GOOGLE_OAUTH_SECRETS = '''\
        {"name": "GOOGLE_CLIENT_ID", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_ID"}}},
        {"name": "GOOGLE_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "GOOGLE_CLIENT_SECRET"}}},'''


def with_cloud_run_oauth_secrets(payload: str) -> str:
    payload = with_memory_env(payload)
    return re.sub(
        r'^(\s*\{"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN".*\}\s*\})\s*,?\s*$',
        r'\1,\n' + GOOGLE_OAUTH_SECRETS.rstrip(','),
        payload,
        flags=re.MULTILINE,
    )


STANDARD_CLOUD_RUN_SECRETS = {
    'GOOGLE_CLIENT_ID': {'secret': 'GOOGLE_CLIENT_ID', 'version': 'latest'},
    'GOOGLE_CLIENT_SECRET': {'secret': 'GOOGLE_CLIENT_SECRET', 'version': 'latest'},
}


def test_repo_gke_values_match_manifest():
    validator = load_validator()

    errors = validator.validate_runtime_env(env='dev')

    assert errors == []


def test_repo_cloud_run_workflows_match_manifest():
    validator = load_validator()

    errors = validator.validate_runtime_env(env='dev', check_workflows=True)

    assert errors == []


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
                        }
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
                    },
                }
            },
        },
    )

    errors = validator.validate_runtime_env(env='dev', manifest_path=manifest_path, check_workflows=True)

    assert [error.message for error in errors] == ['missing env OMI_LLM_GATEWAY_URL']
    assert errors[0].scope == 'cloud_run_workflow/backend'


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
                                    'CUSTOM_MANIFEST_ONLY_MARKER': {'value': 'present'},
                                },
                                'secrets': STANDARD_CLOUD_RUN_SECRETS,
                            }
                        },
                    },
                }
            },
        },
    )

    errors = validator.validate_runtime_env(env='dev', manifest_path=manifest_path, check_workflows=True)

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
                                    }
                                },
                                'secrets': {
                                    'OMI_LLM_GATEWAY_SERVICE_TOKEN': {
                                        'secret': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
                                        'version': 'latest',
                                    }
                                },
                            }
                        }
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
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    }
  }
}
''',
        encoding='utf-8',
    )

    errors = validator.validate_runtime_env(
        env='prod',
        manifest_path=manifest_path,
        cloud_run_state_path=state_path,
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


def test_prod_cloud_run_secret_bindings_exclude_stale_optional_secrets():
    validator = load_validator()
    manifest = validator._load_yaml(ROOT / 'deploy/runtime_env.yaml')
    prod_services = manifest['environments']['prod']['cloud_run']['services']
    stale_secrets = {'SERVICE_ACCOUNT_JSON', 'POSTHOG_PROJECT_API_KEY'}

    for service_name, service_config in prod_services.items():
        secret_names = set((service_config.get('secrets') or {}).keys())
        assert stale_secrets.isdisjoint(secret_names), f'{service_name} still binds stale secrets'

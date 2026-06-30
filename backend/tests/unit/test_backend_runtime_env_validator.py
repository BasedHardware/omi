from __future__ import annotations

import importlib.util
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
        '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
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
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    }
  }
}
''',
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


def test_cloud_run_state_accepts_secret_bindings(tmp_path):
    validator = load_validator()
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
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
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN"}}}
      ]
    }
  }
}
''',
        encoding='utf-8',
    )

    errors = validator.validate_runtime_env(env='dev', cloud_run_state_path=state_path)

    assert errors == []


def test_cloud_run_state_rejects_old_secret_versions(tmp_path):
    validator = load_validator()
    state_path = tmp_path / 'cloud_run_state.json'
    state_path.write_text(
        '''
{
  "services": {
    "backend": {
      "flags": {"--network": "omi-dev-vpc-1", "--subnet": "omi-us-central1-dev-vpc-1-subnet-1", "--vpc-egress": "private-ranges-only"},
      "env": [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"},
        {"name": "OMI_LLM_GATEWAY_URL", "value": "http://172.16.63.232"},
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
        {"name": "SERVICE_ACCOUNT_JSON", "valueFrom": {"secretKeyRef": {"name": "SERVICE_ACCOUNT_JSON", "key": "latest"}}},
        {"name": "ENCRYPTION_SECRET", "valueFrom": {"secretKeyRef": {"name": "ENCRYPTION_SECRET", "key": "latest"}}},
        {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "valueFrom": {"secretKeyRef": {"name": "OMI_LLM_GATEWAY_SERVICE_TOKEN", "key": "latest"}}}
      ]
    }
  }
}
''',
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


def test_backend_listen_chart_only_workflow_preserves_runtime_project():
    workflow_path = ROOT.parent / '.github/workflows/gcp_backend_listen_helm.yml'
    workflow_text = workflow_path.read_text(encoding='utf-8')

    assert workflow_text.count('--set runtimeGcpProjectId=${{ vars.RUNTIME_GCP_PROJECT_ID }}') == 2

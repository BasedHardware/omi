from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(relative_path: str) -> dict[str, Any]:
    with (BACKEND_ROOT / relative_path).open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def _env_map(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry['name']: entry for entry in values['env']}


def _secret_keys(values: dict[str, Any]) -> set[str]:
    return {entry['secretKey'] for entry in values['externalSecret']['secretKeys']}


def test_llm_gateway_anthropic_secret_and_authenticated_readiness_probe_contract():
    for environment in ('dev', 'prod'):
        gateway = _load_yaml(f'charts/llm-gateway/{environment}_omi_llm_gateway_values.yaml')
        secrets = _load_yaml(f'charts/backend-secrets/{environment}_omi_backend_secrets_values.yaml')
        env = _env_map(gateway)

        assert env['ANTHROPIC_API_KEY']['valueFrom']['secretKeyRef'] == {
            'name': f'{environment}-omi-backend-secrets',
            'key': 'ANTHROPIC_API_KEY',
        }
        assert 'ANTHROPIC_API_KEY' in _secret_keys(secrets)
        for provider_secret in ('OPENROUTER_API_KEY',):
            assert env[provider_secret]['valueFrom']['secretKeyRef'] == {
                'name': f'{environment}-omi-backend-secrets',
                'key': provider_secret,
            }
            assert provider_secret in _secret_keys(secrets)
        assert 'GEMINI_API_KEY' not in env
        assert env['GOOGLE_CLOUD_PROJECT']['value'] == (
            'based-hardware-dev' if environment == 'dev' else 'based-hardware'
        )
        assert env['GCP_LOCATION']['value'] == 'us-central1'
        assert env['LLM_GATEWAY_ACCOUNTING_ENABLED']['value'] == 'true'
        assert env['LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS']['value'] == '1'
        assert env['LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES']['value'] == '1000'
        assert 'OMI_LLM_GATEWAY_SERVICE_TOKEN' in _secret_keys(secrets)
        assert 'PERPLEXITY_API_KEY' not in env
        probe_command = gateway['readinessProbe']['exec']['command'][-1]
        assert '/ready' in probe_command
        assert '${OMI_LLM_GATEWAY_SERVICE_TOKEN}' in probe_command
        assert 'X-Omi-Service-Caller: backend' in probe_command


def test_prod_gateway_wiring_is_off_until_verified_promotion():
    manifest = _load_yaml('deploy/runtime_env.yaml')
    prod = manifest['environments']['prod']
    gke_env = prod['gke']['backend-listen']['env']
    assert (
        gke_env['OMI_LLM_GATEWAY_URL']['value'] == 'http://prod-omi-llm-gateway.prod-omi-backend.svc.cluster.local:8080'
    )
    assert gke_env['OMI_LLM_GATEWAY_FEATURE_MODE']['value'] == 'off'
    assert gke_env['OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE']['value'] == 'true'
    assert gke_env['OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION']['value'] == 'true'
    assert gke_env['USE_VERTEX_AI']['value'] == 'true'
    assert gke_env['GCP_LOCATION']['value'] == 'us-central1'
    assert gke_env['GOOGLE_CLOUD_PROJECT']['value'] == 'based-hardware'

    for service in ('backend', 'backend-sync', 'backend-integration'):
        service_config = prod['cloud_run']['services'][service]
        assert service_config['env']['OMI_LLM_GATEWAY_URL'] == {
            'env_var': 'OMI_LLM_GATEWAY_URL',
            'default': 'http://127.0.0.1:9',
            'category': 'service_discovery',
        }
        assert service_config['env']['OMI_LLM_GATEWAY_FEATURE_MODE']['value'] == 'off'
        assert service_config['env']['OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE']['value'] == 'true'
        assert service_config['env']['OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION']['value'] == 'true'
        assert service_config['env']['USE_VERTEX_AI']['value'] == 'true'
        assert service_config['env']['GCP_LOCATION']['value'] == 'us-central1'
        assert service_config['env']['GOOGLE_CLOUD_PROJECT']['value'] == 'based-hardware'
        assert service_config['secrets']['OMI_LLM_GATEWAY_SERVICE_TOKEN'] == {
            'secret': 'OMI_LLM_GATEWAY_SERVICE_TOKEN',
            'version': 'latest',
        }

    gateway = _load_yaml('charts/llm-gateway/prod_omi_llm_gateway_values.yaml')
    assert gateway['service']['backendConfig'] == 'prod-llm-gateway-backend-config'
    assert gateway['ingress']['enabled'] is True
    assert gateway['ingress']['annotations']['kubernetes.io/ingress.regional-static-ip-name'] == (
        'prod-omi-self-hosted-llm-ip-address'
    )
    assert prod['llm_gateway'] == {
        'namespace': 'prod-omi-backend',
        'release_name': 'prod-omi-llm-gateway',
        'ingress_name': 'prod-omi-llm-gateway',
        'static_address_name': 'prod-omi-self-hosted-llm-ip-address',
    }


def test_gateway_runtime_static_address_matches_helm_ingress_declaration():
    manifest = _load_yaml('deploy/runtime_env.yaml')

    for environment in ('dev', 'prod'):
        gateway = _load_yaml(f'charts/llm-gateway/{environment}_omi_llm_gateway_values.yaml')
        assert (
            manifest['environments'][environment]['llm_gateway']['static_address_name']
            == gateway['ingress']['annotations']['kubernetes.io/ingress.regional-static-ip-name']
        )


def test_gateway_deploy_workflow_and_helper_allow_explicit_prod_launches():
    helper = (BACKEND_ROOT / 'scripts/deploy-llm-gateway.sh').read_text(encoding='utf-8')
    workflow = (BACKEND_ROOT.parent / '.github/workflows/gcp_llm_gateway.yml').read_text(encoding='utf-8')

    assert '"$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod"' in helper
    assert 'github.event.inputs.environment }}" != "prod"' in workflow
    assert 'Verify production gateway service token' in workflow
    assert 'LLM_GATEWAY_GSA is required for Vertex Workload Identity' in helper
    assert 'serviceAccount.annotations.iam\\\\.gke\\\\.io/gcp-service-account=${LLM_GATEWAY_GSA}' in helper
    assert 'LLM_GATEWAY_GSA: ${{ vars.LLM_GATEWAY_GSA }}' in workflow
    assert 'Verify LLM Gateway serving data plane' in workflow
    assert 'Probe LLM Gateway from the Cloud Run VPC' in workflow
    assert 'verify-llm-gateway-serving.py' in workflow
    assert 'probe-llm-gateway-from-cloud-run.sh' in workflow


def test_backend_deploy_requires_serving_and_cloud_run_vpc_gates_before_gateway_promotion():
    workflow = (BACKEND_ROOT.parent / '.github/workflows/gcp_backend.yml').read_text(encoding='utf-8')
    auto_dev = (BACKEND_ROOT.parent / '.github/workflows/gcp_backend_auto_dev.yml').read_text(encoding='utf-8')

    assert 'Determine whether this deploy requests gateway-first serving' in workflow
    assert 'Verify LLM gateway control plane before promotion' in workflow
    assert 'Probe LLM gateway from the Cloud Run VPC before promotion' in workflow
    assert "steps.gateway-intent.outputs.enabled == 'true'" in workflow
    assert (
        '--listener-values="backend/charts/backend-listen/${{ vars.ENV }}_omi_backend_listen_values.yaml"' in workflow
    )
    assert "steps.gateway-serving.outputs.gateway_url || 'http://127.0.0.1:9'" in workflow
    assert 'Verify LLM gateway control plane before promotion' in auto_dev
    assert 'Probe LLM gateway from the Cloud Run VPC before promotion' in auto_dev
    assert 'OMI_LLM_GATEWAY_URL: ${{ steps.gateway-serving.outputs.gateway_url }}' in auto_dev


def test_gateway_vpc_probe_workflows_explicitly_use_bash():
    for workflow_name in ('gcp_backend_auto_dev.yml', 'gcp_backend.yml', 'gcp_llm_gateway.yml'):
        workflow = (BACKEND_ROOT.parent / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        assert 'bash backend/scripts/probe-llm-gateway-from-cloud-run.sh' in workflow


def test_monitoring_scrapes_llm_gateway_with_shared_metrics_secret_contract():
    for environment in ('dev', 'prod'):
        monitoring = _load_yaml(f'charts/monitoring/kube-prometheus-stack/{environment}_omi_monitoring_values.yaml')
        jobs = {job['job_name']: job for job in monitoring['prometheus']['prometheusSpec']['additionalScrapeConfigs']}

        gateway_job = jobs['llm-gateway-metrics']
        assert gateway_job['metrics_path'] == '/metrics'
        assert gateway_job['authorization']['credentials_file'] == '/etc/prometheus/secrets/metrics-scrape-token/token'
        name_filter = next(
            config
            for config in gateway_job['relabel_configs']
            if config.get('source_labels') == ['__meta_kubernetes_pod_label_app_kubernetes_io_name']
        )
        assert name_filter['regex'] == 'llm-gateway'


def test_gateway_env_validator_requires_vertex_runtime_configuration_not_gemini_api_key(tmp_path):
    backend_values = tmp_path / 'backend.yaml'
    gateway_values = tmp_path / 'gateway.yaml'
    backend_values.write_text('env: []\n', encoding='utf-8')
    gateway_values.write_text(
        'env:\n'
        '  - name: OMI_LLM_GATEWAY_SERVICE_TOKEN\n'
        '    value: token\n'
        '  - name: OPENAI_API_KEY\n'
        '    value: openai\n'
        '  - name: ANTHROPIC_API_KEY\n'
        '    value: anthropic\n'
        '  - name: OPENROUTER_API_KEY\n'
        '    value: openrouter\n'
        '  - name: METRICS_SECRET\n'
        '    value: metrics\n',
        encoding='utf-8',
    )

    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND_ROOT / 'scripts/validate-llm-gateway-env.py'),
            str(backend_values),
            str(gateway_values),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert 'gateway has no GOOGLE_CLOUD_PROJECT env' in result.stdout
    assert 'gateway has no GCP_LOCATION env' in result.stdout
    assert 'GEMINI_API_KEY' not in result.stdout
    assert 'gateway must enable LLM_GATEWAY_ACCOUNTING_ENABLED=true' in result.stdout
    assert 'gateway has no LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS env' in result.stdout
    assert 'gateway has no LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES env' in result.stdout

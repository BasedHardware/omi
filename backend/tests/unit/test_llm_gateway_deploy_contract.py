from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any, cast

import yaml

from testing.shell import bash_command, bash_path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
DEPLOY_BACKEND_STACK_ACTION = REPOSITORY_ROOT / '.github/actions/deploy-backend-stack/action.yml'
_GITHUB_SCRIPTS = REPOSITORY_ROOT / '.github' / 'scripts'
if str(_GITHUB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GITHUB_SCRIPTS))
from workflow_composite_contract import backend_deploy_contract_text as _expand_contract  # noqa: E402

GATEWAY_DEPLOY_WORKFLOWS = (
    'gcp_llm_gateway.yml',
    'gcp_backend_auto_dev.yml',
    'gcp_backend_pusher.yml',
)
VPC_PROBE_WORKFLOWS = (
    'gcp_backend_auto_dev.yml',
    'gcp_backend.yml',
    'gcp_llm_gateway.yml',
    'gcp_backend_pusher.yml',
)
VPC_PROBE_WORKFLOW_DEPLOY_PROFILES = {
    'gcp_backend_auto_dev.yml': 'auto-dev',
    'gcp_backend.yml': 'manual',
}


def backend_deploy_contract_text(workflow_name: str) -> str:
    workflow = (REPOSITORY_ROOT / '.github' / 'workflows' / workflow_name).read_text(encoding='utf-8')
    return _expand_contract(workflow, REPOSITORY_ROOT, Path('.github/actions/deploy-backend-stack/action.yml'))


def _load_yaml(relative_path: str) -> dict[str, Any]:
    with (BACKEND_ROOT / relative_path).open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def _env_map(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry['name']: entry for entry in values['env']}


def _load_workflow(name: str) -> dict[str, Any]:
    with (REPOSITORY_ROOT / '.github' / 'workflows' / name).open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def _deploy_steps(workflow: dict[str, Any], workflow_name: str) -> list[dict[str, Any]]:
    steps = list(workflow['jobs']['deploy']['steps'])
    if any('./.github/actions/deploy-backend-stack' in str(step.get('uses', '')) for step in steps):
        action = yaml.safe_load(DEPLOY_BACKEND_STACK_ACTION.read_text(encoding='utf-8'))
        assert isinstance(action, dict)
        composite_steps = action['runs']['steps']
        assert isinstance(composite_steps, list)
        return [*steps, *composite_steps]
    return steps


def _workflow_step(workflow: dict[str, Any], name: str, *, workflow_name: str) -> dict[str, Any]:
    steps = _deploy_steps(workflow, workflow_name)
    return next(step for step in steps if step.get('name') == name)


def _workflow_step_with_run(workflow: dict[str, Any], needle: str, *, workflow_name: str) -> dict[str, Any]:
    steps = _deploy_steps(workflow, workflow_name)
    return next(step for step in steps if needle in str(step.get('run', '')))


def _render_probe_workflow_run(run: str, *, deploy_profile: str | None = None) -> str:
    replacements = {
        '${{ vars.GCP_PROJECT_ID }}': 'test-project',
        '${{ inputs.project_id }}': 'test-project',
        '${{ inputs.region }}': 'us-central1',
        '${{ inputs.service }}': 'backend',
        '${{ env.REGION }}': 'us-central1',
        '${{ env.SERVICE }}': 'llm-gateway',
        '${{ steps.image-tag.outputs.short_sha }}': 'abc1234',
        '${{ steps.gateway-serving.outputs.gateway_url }}': 'http://10.0.0.5',
        '${{ steps.combined-gateway-serving.outputs.gateway_url || steps.gateway-serving.outputs.gateway_url }}': 'http://10.0.0.5',
        '${{ vars.CLOUD_RUN_VPC_NETWORK }}': 'test-network',
        '${{ vars.CLOUD_RUN_VPC_SUBNET }}': 'test-subnet',
        '${{ env.CLOUD_RUN_VPC_NETWORK }}': 'test-network',
        '${{ env.CLOUD_RUN_VPC_SUBNET }}': 'test-subnet',
    }
    if deploy_profile is not None:
        replacements['${{ inputs.deploy_profile }}'] = deploy_profile
    for expression, value in replacements.items():
        run = run.replace(expression, value)
    return run


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
        for provider_secret in ('OPENROUTER_API_KEY', 'PERPLEXITY_API_KEY'):
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
        probe_command = gateway['readinessProbe']['exec']['command'][-1]
        assert '/ready' in probe_command
        assert '${OMI_LLM_GATEWAY_SERVICE_TOKEN}' in probe_command
        assert 'X-Omi-Service-Caller: backend' in probe_command

    deployment = (BACKEND_ROOT / 'charts/llm-gateway/templates/deployment.yaml').read_text(encoding='utf-8')
    assert 'name: OMI_LLM_GATEWAY_BUILD_IDENTITY' in deployment
    assert 'value: {{ required "image.tag is required" .Values.image.tag | quote }}' in deployment


def test_gateway_ingress_timeout_can_carry_the_flex_route_deadline():
    backend_config = (BACKEND_ROOT / 'charts/llm-gateway/templates/backendconfig.yaml').read_text(encoding='utf-8')

    assert '  timeoutSec: 960\n' in backend_config
    assert '    timeoutSec: 5\n' in backend_config


def test_prod_gateway_wiring_promotes_cloud_run_only_after_verified_endpoint_injection():
    manifest = _load_yaml('deploy/runtime_env.yaml')
    prod = manifest['environments']['prod']
    gke_env = prod['gke']['backend-listen']['env']
    assert (
        gke_env['OMI_LLM_GATEWAY_URL']['value'] == 'http://prod-omi-llm-gateway.prod-omi-backend.svc.cluster.local:8080'
    )
    assert gke_env['OMI_LLM_GATEWAY_FEATURE_MODE']['value'] == 'gateway'
    assert gke_env['OMI_LLM_CHAT_AGENT_ROUTE']['value'] == 'gateway'
    assert gke_env['OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE']['value'] == 'true'
    assert gke_env['OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION']['value'] == 'false'
    assert gke_env['USE_VERTEX_AI']['value'] == 'true'
    assert gke_env['GCP_LOCATION']['value'] == 'us-central1'
    assert gke_env['GOOGLE_CLOUD_PROJECT']['value'] == 'based-hardware'

    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        service_config = prod['cloud_run']['services'][service]
        assert service_config['env']['OMI_LLM_GATEWAY_URL'] == {
            'env_var': 'OMI_LLM_GATEWAY_URL',
            'default': 'http://127.0.0.1:9',
            'category': 'service_discovery',
        }
        assert service_config['env']['OMI_LLM_GATEWAY_FEATURE_MODE']['value'] == 'gateway'
        assert service_config['env']['OMI_LLM_CHAT_AGENT_ROUTE']['value'] == 'gateway'
        assert service_config['env']['OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE']['value'] == 'true'
        assert service_config['env']['OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION']['value'] == 'false'
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
    assert 'workflow_dispatch:' in workflow
    assert 'push:' not in workflow
    assert 'workflow_run:' not in workflow
    assert 'schedule:' not in workflow
    assert '--update-traffic' not in workflow
    assert 'gcloud run services update-traffic' not in workflow


def test_gateway_auto_deploy_is_folded_into_the_admitted_backend_lifecycle():
    """Static tripwire for FC-deploy-concurrency: one automatic backend-stack writer only."""
    workflows = REPOSITORY_ROOT / '.github/workflows'
    auto_dev_path = workflows / 'gcp_backend_auto_dev.yml'
    workflow = backend_deploy_contract_text('gcp_backend_auto_dev.yml')
    trigger = workflow.split('\njobs:', 1)[0]

    assert not (workflows / 'gcp_llm_gateway_auto_dev.yml').exists()
    assert 'workflow_run:' in trigger
    assert '\n  push:' not in trigger
    assert 'workflows: ["Release Eligibility"]' in trigger
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "github.event.workflow_run.run_attempt == 1" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert 'github.event.workflow_run.head_repository.full_name == github.repository' in workflow
    assert '${{ needs.firestore_readiness.outputs.admitted_sha }}' in workflow
    assert 'gcp_llm_gateway' in workflow

    automatic_backend_stack_writers = []
    for path in workflows.glob('*.yml'):
        text = path.read_text(encoding='utf-8')
        workflow_trigger = text.split('\njobs:', 1)[0]
        if 'group: deploy-backend-stack-development' in workflow_trigger and (
            'workflow_run:' in workflow_trigger or '\n  push:' in workflow_trigger
        ):
            automatic_backend_stack_writers.append(path.name)
    assert automatic_backend_stack_writers == ['gcp_backend_auto_dev.yml']

    build = workflow.index('- name: Build, smoke, and push combined LLM Gateway image')
    deploy = workflow.index('- name: Deploy LLM Gateway with backend stack')
    serving = workflow.index('- name: Verify combined LLM gateway serving data plane')
    vpc_probe = workflow.index('- name: Probe LLM gateway from the Cloud Run VPC before promotion')
    smoke = workflow.index('- name: Smoke LLM Gateway')
    caller_render = workflow.index('- name: Render backend runtime env')
    assert build < deploy < serving < smoke < vpc_probe < caller_render
    gateway_image = 'gcr.io/${{ inputs.project_id }}/llm-gateway:${{ steps.image-tag.outputs.short_sha }}'
    assert f'gateway_image="{gateway_image}"' in workflow
    assert f'--image "{gateway_image}"' in workflow
    assert 'runtime_image_contracts.py" smoke' in workflow
    assert (
        'IMAGE_TAG="${{ steps.image-tag.outputs.short_sha }}" "$DEPLOY_CONTROL_SCRIPTS/deploy-llm-gateway.sh"'
        in workflow
    )
    assert (
        'OMI_LLM_GATEWAY_URL: ${{ steps.combined-gateway-serving.outputs.gateway_url || steps.gateway-serving.outputs.gateway_url || \'http://127.0.0.1:9\' }}'
        in workflow
    )
    assert '--lane omi:auto:public-shared-conversation-chat' in workflow
    assert '--check-metrics' in workflow


def test_backend_deploy_requires_serving_and_cloud_run_vpc_gates_before_gateway_promotion():
    workflow = backend_deploy_contract_text('gcp_backend.yml')
    auto_dev = backend_deploy_contract_text('gcp_backend_auto_dev.yml')

    assert 'Determine whether this deploy requests gateway-first serving' in workflow
    assert 'Verify LLM gateway control plane before promotion' in workflow
    assert 'Probe LLM gateway from the Cloud Run VPC before promotion' in workflow
    assert "steps.gateway-intent.outputs.enabled == 'true'" in workflow
    assert (
        '--listener-values="backend/charts/backend-listen/${{ inputs.runtime_env }}_omi_backend_listen_values.yaml"'
        in workflow
    )
    intent_step = workflow[
        workflow.index('- name: Determine whether this deploy requests gateway-first serving') : workflow.index(
            '- name: Get GKE credentials for gateway serving gate'
        )
    ]
    assert "github.event.inputs.deploy_targets == 'all'" not in intent_step
    assert 'Reject an inert gateway endpoint when source-controlled gateway mode is requested' in workflow
    assert 'Gateway mode requires a verified non-sentinel endpoint.' in workflow
    assert (
        'steps.combined-gateway-serving.outputs.gateway_url || steps.gateway-serving.outputs.gateway_url || \'http://127.0.0.1:9\''
        in workflow
    )
    assert 'Build, smoke, and push combined LLM Gateway image' in auto_dev
    assert 'Deploy LLM Gateway with backend stack' in auto_dev
    assert 'Verify combined LLM gateway serving data plane' in auto_dev
    assert 'Probe LLM gateway from the Cloud Run VPC before promotion' in auto_dev
    assert 'Smoke LLM Gateway' in auto_dev
    assert '--lane omi:auto:public-shared-conversation-chat' in workflow
    assert '--lane omi:auto:public-shared-conversation-chat' in auto_dev


def test_backend_can_compose_dev_gateway_with_immutable_backend_image_but_prod_stays_separate():
    workflow = backend_deploy_contract_text('gcp_backend.yml')
    standalone = (BACKEND_ROOT.parent / '.github/workflows/gcp_llm_gateway.yml').read_text(encoding='utf-8')

    assert 'deploy_gateway:' in workflow
    assert "default: false\n        type: boolean" in workflow
    assert (
        'environment=prod, deploy_gateway=true is unsupported; use the standalone manual LLM gateway workflow.'
        in workflow
    )
    assert 'deploy_gateway=true requires deploy_targets=all.' in workflow
    gateway_publish = workflow.index('- name: Build, smoke, and push combined LLM Gateway image')
    gateway_deploy = workflow.index('- name: Deploy LLM Gateway with backend stack')
    assert gateway_publish < gateway_deploy
    combined_publish_step = workflow[gateway_publish:gateway_deploy]
    assert (
        'gateway_image="gcr.io/${{ inputs.project_id }}/llm-gateway:${{ steps.image-tag.outputs.short_sha }}"'
        in combined_publish_step
    )
    assert 'runtime_image_contracts.py" smoke' in combined_publish_step
    assert 'docker push "$gateway_image"' in combined_publish_step
    assert 'Deploy LLM Gateway with backend stack' in workflow
    assert (
        'IMAGE_TAG="${{ steps.image-tag.outputs.short_sha }}" "$DEPLOY_CONTROL_SCRIPTS/deploy-llm-gateway.sh"'
        in workflow
    )
    assert 'deploy-backend-stack-${{ github.event.inputs.environment }}' in workflow
    assert 'deploy-backend-stack-${{ github.event.inputs.environment }}' in standalone
    assert 'IMAGE_TAG=$(git rev-parse --short=7 "$CHECKED_OUT_SHA")' in standalone


def test_gateway_deploy_workflows_bind_identity_and_gate_serving_static_contract():
    """Static guard: each deploy-llm-gateway caller must supply its script inputs and serving gates."""
    serving_step_names = {
        'gcp_backend_auto_dev.yml': 'Verify combined LLM gateway serving data plane',
        'gcp_llm_gateway.yml': 'Verify LLM Gateway serving data plane',
        'gcp_backend_pusher.yml': 'Verify LLM Gateway serving data plane',
    }
    probe_step_names = {
        'gcp_backend_auto_dev.yml': 'Probe LLM gateway from the Cloud Run VPC before promotion',
        'gcp_llm_gateway.yml': 'Probe LLM Gateway from the Cloud Run VPC',
        'gcp_backend_pusher.yml': 'Probe LLM Gateway from the Cloud Run VPC',
    }
    for workflow_name in GATEWAY_DEPLOY_WORKFLOWS:
        workflow = _load_workflow(workflow_name)
        deploy = _workflow_step_with_run(workflow, 'deploy-llm-gateway.sh', workflow_name=workflow_name)
        expected_gsa = (
            '${{ env.LLM_GATEWAY_GSA }}'
            if workflow_name == 'gcp_backend_auto_dev.yml'
            else '${{ vars.LLM_GATEWAY_GSA }}'
        )
        assert deploy['env']['LLM_GATEWAY_GSA'] == expected_gsa
        assert any(
            'test -n "$LLM_GATEWAY_GSA"' in str(step.get('run', '')) for step in _deploy_steps(workflow, workflow_name)
        )
        assert _workflow_step(workflow, serving_step_names[workflow_name], workflow_name=workflow_name)
        assert _workflow_step(workflow, probe_step_names[workflow_name], workflow_name=workflow_name)


def test_gateway_vpc_probe_workflows_execute_the_production_parser(tmp_path):
    """Exercise each rendered workflow caller through the real probe parser with fake gcloud."""
    calls = tmp_path / 'gcloud-calls.txt'
    fake_gcloud = tmp_path / 'gcloud'
    fake_gcloud.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_GCLOUD_CALLS"\n', encoding='utf-8')
    fake_gcloud.chmod(0o755)

    for workflow_name in VPC_PROBE_WORKFLOWS:
        workflow = _load_workflow(workflow_name)
        step = _workflow_step_with_run(workflow, 'probe-llm-gateway-from-cloud-run.sh', workflow_name=workflow_name)
        environment = {
            **os.environ,
            'FAKE_GCLOUD_CALLS': bash_path(calls, cwd=REPOSITORY_ROOT),
            'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_RUN_ID': '42',
            'GITHUB_SHA': 'abcdef0123456789',
            'DEPLOY_CONTROL_SCRIPTS': bash_path(BACKEND_ROOT / 'scripts', cwd=REPOSITORY_ROOT),
            'OMI_TEST_FAKE_BIN': bash_path(tmp_path, cwd=REPOSITORY_ROOT),
        }
        run = (
            f'export PATH="$OMI_TEST_FAKE_BIN:$PATH"\n'
            f'export IMAGE_TAG=abc1234\n'
            f'{_render_probe_workflow_run(str(step["run"]), deploy_profile=VPC_PROBE_WORKFLOW_DEPLOY_PROFILES.get(workflow_name))}'
        )

        result = subprocess.run(
            bash_command('-c', run, cwd=REPOSITORY_ROOT),
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )

        assert result.returncode == 0, f'{workflow_name}: {result.stderr}'

    recorded_calls = calls.read_text(encoding='utf-8').splitlines()
    assert any(call.startswith('run jobs deploy llm-gateway-vpc-probe-42-1 ') for call in recorded_calls)
    assert any(call.startswith('run jobs execute llm-gateway-vpc-probe-42-1 ') for call in recorded_calls)
    assert any(call.startswith('run jobs delete llm-gateway-vpc-probe-42-1 ') for call in recorded_calls)

    # gcloud rejects `--args` lists that repeat an element ("<value>" cannot be
    # specified multiple times), which is how a second probe lane broke every
    # backend deploy at the VPC probe step.
    for call in recorded_calls:
        if not call.startswith('run jobs deploy '):
            continue
        smoke_args = next(
            (token[len('--args=') :] for token in call.split(' ') if token.startswith('--args=')),
            None,
        )
        assert smoke_args is not None, call
        elements = smoke_args.split(',')
        assert len(elements) == len(set(elements)), f'duplicate --args element: {smoke_args}'


def test_gateway_vpc_probe_rejects_equals_style_arguments():
    result = subprocess.run(
        bash_command(
            str(BACKEND_ROOT / 'scripts' / 'probe-llm-gateway-from-cloud-run.sh'),
            '--project=test-project',
            cwd=REPOSITORY_ROOT,
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert 'unknown argument: --project=test-project' in result.stderr


def test_auto_dev_revision_fence_targets_the_deployment_project_static_contract():
    """Static guard: every final revision read uses the same explicit project as promotion."""
    workflow = _load_workflow('gcp_backend_auto_dev.yml')
    fence = _workflow_step(
        workflow, 'Verify validated revisions are still current', workflow_name='gcp_backend_auto_dev.yml'
    )
    promotion = _workflow_step(
        workflow, 'Shift Cloud Run traffic to validated revisions', workflow_name='gcp_backend_auto_dev.yml'
    )
    assert str(fence['run']).count('--region=${{ inputs.region }}') == 4
    assert str(promotion['run']).count('--project=${{ inputs.project_id }}') == 4


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

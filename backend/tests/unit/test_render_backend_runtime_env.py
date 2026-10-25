"""Renderer for backend Cloud Run runtime env."""

import json
import os
import shutil
import subprocess
import sys

import yaml
import runpy
from copy import deepcopy
from pathlib import Path

import pytest
from datetime import datetime, timezone
from config.plan_catalog import (
    LADDER_V1_PRICE_BINDINGS,
    RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
    resolve_subscription_entitlements,
)

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render_backend_runtime_env.py'
_MODULE = runpy.run_path(str(_SCRIPT), run_name='render_backend_runtime_env')
_MANIFEST = _MODULE['_load_yaml'](_MODULE['DEFAULT_MANIFEST'])


@pytest.fixture(autouse=True)
def _reuse_parsed_repo_manifest(monkeypatch, tmp_path):
    # runpy's returned mapping is distinct from the function's globals.
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: _MANIFEST)
    output_path = tmp_path / 'github-output'
    output_path.touch()
    monkeypatch.setenv('GITHUB_OUTPUT', str(output_path))
    # Full-state renderer tests need deploy-time values for every declared job.
    for env_config in _MANIFEST['environments'].values():
        for job in (env_config.get('cloud_run', {}).get('jobs') or {}).values():
            for raw_entry in (job.get('env') or {}).values():
                if isinstance(raw_entry, dict) and isinstance(raw_entry.get('env_var'), str):
                    monkeypatch.setenv(raw_entry['env_var'], str(raw_entry.get('default', 'rendered-value')))


def _read_workflow_outputs() -> str:
    return Path(os.environ['GITHUB_OUTPUT']).read_text(encoding='utf-8')


def test_workflow_outputs_are_not_written_to_stdout(capsys):
    _MODULE['_emit_output']('private_value', 'not-for-logs')

    assert capsys.readouterr().out == ''
    assert 'private_value<<' in _read_workflow_outputs()
    assert 'not-for-logs' in _read_workflow_outputs()


def _job_env_block(out: str, job_prefix: str) -> str:
    start = out.index(f'\n{job_prefix}_env_vars<<') + 1
    end = out.index(f'\n{job_prefix}_secrets<<', start) + 1
    return out[start:end]


def _job_secret_lines(out: str, job_prefix: str) -> set[str]:
    marker = f'__BACKEND_RUNTIME_ENV_{job_prefix}_secrets__'
    start = out.index(f'{job_prefix}_secrets<<{marker}')
    start = out.index('\n', start) + 1
    end = out.index(marker, start)
    return set(out[start:end].splitlines())


def test_required_env_var_missing_raises(monkeypatch):
    monkeypatch.delenv('SOME_REQUIRED_URL', raising=False)
    with pytest.raises(ValueError, match='requires'):
        _MODULE['_render_env_vars']({'REQUIRED': {'env_var': 'SOME_REQUIRED_URL'}})


def test_provisional_env_var_missing_is_omitted(monkeypatch):
    monkeypatch.delenv('OMI_LLM_GATEWAY_URL', raising=False)
    rendered = _MODULE['_render_env_vars'](
        {
            'OMI_LLM_GATEWAY_URL': {'env_var': 'OMI_LLM_GATEWAY_URL', 'provisional': True},
            'MEMORY_MODE': {'value': 'canonical'},
        }
    )
    assert rendered == 'MEMORY_MODE=canonical'


def test_provisional_env_var_present_is_rendered(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://10.0.0.1')
    rendered = _MODULE['_render_env_vars'](
        {'OMI_LLM_GATEWAY_URL': {'env_var': 'OMI_LLM_GATEWAY_URL', 'provisional': True}}
    )
    assert rendered == 'OMI_LLM_GATEWAY_URL=http://10.0.0.1'


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('modulate-velma-2,parakeet', r'modulate-velma-2\,parakeet'),
        (r'C:\models', r'C:\\models'),
        ('first\nsecond', 'first\\\nsecond'),
        ('first\rsecond', 'first\\\rsecond'),
        ('first\u2028second', 'first\\\u2028second'),
        ('first\u2029second', 'first\\\u2029second'),
    ],
)
def test_render_env_vars_escapes_deploy_cloudrun_separators(value, expected):
    rendered = _MODULE['_render_env_vars']({'VALUE': {'value': value}})

    assert rendered == f'VALUE={expected}'


def test_state_output_preserves_yaml_boolean_like_strings(tmp_path, monkeypatch):
    env_config = {
        'cloud_run': {
            'network': {'flags': {'--vpc-egress': 'private-ranges-only'}},
            'services': {
                'backend': {
                    'env': {
                        'FEATURE_OFF': {'value': 'off'},
                        'FEATURE_ON': {'value': 'on'},
                        'FEATURE_YES': {'value': 'yes'},
                        'FEATURE_NO': {'value': 'no'},
                    },
                    'secrets': {},
                }
            },
        }
    }
    state_path = tmp_path / 'runtime-env-state.json'
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: {'environments': {'dev': env_config}})
    monkeypatch.setattr(
        'sys.argv',
        ['render_backend_runtime_env.py', '--env', 'dev', '--state-output', str(state_path)],
    )

    assert _MODULE['main']() == 0

    state = json.loads(state_path.read_text(encoding='utf-8'))
    rendered_env = {entry['name']: entry['value'] for entry in state['services']['backend']['env']}

    assert rendered_env == {
        'FEATURE_OFF': 'off',
        'FEATURE_ON': 'on',
        'FEATURE_YES': 'yes',
        'FEATURE_NO': 'no',
    }
    assert all(isinstance(value, str) for value in rendered_env.values())
    output = _read_workflow_outputs()
    assert 'FEATURE_OFF=off' in output
    assert 'FEATURE_ON=on' in output


def test_network_flags_still_required(monkeypatch):
    monkeypatch.delenv('CLOUD_RUN_VPC_NETWORK', raising=False)
    with pytest.raises(ValueError, match='requires'):
        _MODULE['_render_flags']({'--network': {'env_var': 'CLOUD_RUN_VPC_NETWORK'}})


def test_selected_job_renders_only_shared_network_and_named_job_outputs(monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-dev-subnet-1')
    monkeypatch.setattr(
        'sys.argv',
        ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'memory-maintenance-job'],
    )

    assert _MODULE['main']() == 0

    output = _read_workflow_outputs()
    assert 'cloud_run_flags<<' in output
    assert 'memory_maintenance_job_flags<<' in output
    assert 'memory_maintenance_job_env_vars<<' in output
    assert 'backend_env_vars<<' not in output
    assert 'notifications_job_env_vars<<' not in output


def test_selected_job_rejects_unknown_name_without_emitting_partial_output(monkeypatch):
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'unknown-job'])

    with pytest.raises(ValueError, match='unknown Cloud Run job'):
        _MODULE['main']()

    assert _read_workflow_outputs() == ''


def test_render_dev_emits_memory_maintenance_job_outputs():
    jobs = _MANIFEST['environments']['dev']['cloud_run']['jobs']
    memory_job = jobs['memory-maintenance-job']
    memory_env = _MODULE['_render_env_vars'](memory_job['env'])
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED=true' in memory_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_FLEX' not in memory_env
    assert 'MEMORY_CANONICAL_CONSOLIDATION_ENABLED' not in memory_env
    assert 'OMI_BACKGROUND_FLEX_CAPABLE=true' in memory_env
    assert 'MEMORY_ENABLED_USERS' not in memory_env
    assert 'MEMORY_ENABLED=on' in memory_env
    assert 'MEMORY_MODE=' not in memory_env
    assert 'MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED' not in memory_env
    assert 'TYPESENSE_HOST_PORT=443' in memory_env

    rendered_flags = _MODULE['_render_flags'](memory_job['flags'])
    assert '--task-timeout=3600s' in rendered_flags
    assert '--cpu=2' in rendered_flags
    assert '--memory=2Gi' in rendered_flags
    assert (
        '--remove-env-vars=MEMORY_ENABLED_USERS,'
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED,'
        'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS,'
        'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED'
    ) in rendered_flags
    memory_secrets = _MODULE['_render_secrets'](memory_job['secrets'])
    assert 'OPENAI_API_KEY=OPENAI_API_KEY:latest' in memory_secrets
    assert 'PINECONE_API_KEY=PINECONE_API_KEY:latest' in memory_secrets
    assert 'TYPESENSE_API_KEY=TYPESENSE_API_KEY:latest' in memory_secrets
    assert 'POSTHOG_PROJECT_API_KEY=POSTHOG_PROJECT_API_KEY:latest' in memory_secrets


def test_render_dev_emits_x_connector_sync_job_outputs(monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-dev-subnet-1')
    monkeypatch.setenv('X_OAUTH_CLIENT_ID', 'x-client-id')
    monkeypatch.setenv('X_OAUTH_REDIRECT_URI', 'https://api.example/v1/x/callback')
    monkeypatch.setenv('RAPID_API_HOST', 'twitter-api.example')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'x-connector-sync-job'])

    assert _MODULE['main']() == 0
    output = _read_workflow_outputs()
    assert 'X_OAUTH_CLIENT_ID=x-client-id' in output
    assert 'X_OAUTH_REDIRECT_URI=https://api.example/v1/x/callback' in output
    assert 'RAPID_API_HOST=twitter-api.example' in output
    assert 'X_OAUTH_CLIENT_SECRET=X_OAUTH_CLIENT_SECRET:latest' in output
    assert 'RAPID_API_KEY=RAPID_API_KEY:latest' in output
    assert '--service-account=dev-backend-runtime@based-hardware-dev.iam.gserviceaccount.com' in output
    assert 'notifications_job_env_vars<<' not in output


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_x_connector_sync_job_pins_its_task_timeout(env):
    """The job must pin a task timeout rather than inherit Cloud Run's 600s default.

    Every other Cloud Run job in this manifest pins one. An unpinned job deploys at the
    platform default, and #12530 is what that costs: the notifications job was SIGKILLed
    mid-batch at 600s, users past the kill point were never reached on any run, and the
    pipeline looked healthy throughout. X sync walks a registry at ~1.5s per user plus
    fetch and extraction, so it has the same shape of exposure.

    Pinned equal to memory-maintenance-job, the job this one was cloned from.
    """
    jobs = _MANIFEST['environments'][env]['cloud_run']['jobs']
    assert jobs['x-connector-sync-job']['flags']['--task-timeout'] == '3600s'


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_every_cloud_run_job_pins_a_task_timeout(env):
    """No job may rely on the platform default.

    Asserting only the new job would let the next one repeat the omission — this PR's own
    job was added without a timeout precisely because nothing required one.
    """
    jobs = _MANIFEST['environments'][env]['cloud_run']['jobs']
    unpinned = sorted(name for name, spec in jobs.items() if not (spec.get('flags') or {}).get('--task-timeout'))
    assert unpinned == [], f'Cloud Run jobs without an explicit --task-timeout: {unpinned}'


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_retired_daily_sweep_runtime_is_absent(env):
    jobs = _MANIFEST['environments'][env]['cloud_run']['jobs']
    maintenance = jobs['memory-maintenance-job']
    retired_names = {
        'MEMORY_DAILY_MEMORY_SWEEP_ENABLED',
        'MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH',
        'MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED',
        'MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME',
        'MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES',
        'MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD',
        'MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED',
        'MEMORY_DAILY_MEMORY_SWEEP_COHORT_NAME',
        'MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG',
        'MEMORY_DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_SECONDS',
        'MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED',
        'MEMORY_DAILY_MEMORY_SWEEP_STAGGER_SECONDS',
        'POSTHOG_HOST',
    }
    assert retired_names.isdisjoint(maintenance.get('env', {}))
    assert 'daily-memory-sweep-job' not in jobs


def test_memory_maintenance_entrypoint_does_not_invoke_daily_sweep_job():
    entrypoint = (_SCRIPT.parents[1] / 'modal' / 'memory_maintenance_job.py').read_text(encoding='utf-8')
    dockerfile = (_SCRIPT.parents[1] / 'modal' / 'Dockerfile.memory_maintenance_job').read_text(encoding='utf-8')
    assert 'daily_memory_sweep' not in entrypoint
    assert 'daily_memory_sweep_job.py' not in dockerfile
    assert 'memory_maintenance_job.py' in dockerfile


def _contains_uid_outside_approved_allowlists(node, uid: str) -> bool:
    approved_allowlists = {'AUDIO_ARCHIVE_UID_ALLOWLIST'}
    if isinstance(node, dict):
        for key, value in node.items():
            if key in approved_allowlists:
                continue
            if _contains_uid_outside_approved_allowlists(value, uid):
                return True
        return False
    if isinstance(node, list):
        return any(_contains_uid_outside_approved_allowlists(item, uid) for item in node)
    return node == uid


def test_dev_runtime_manifest_contains_no_removed_first_user_or_capture_admission():
    # Product/runtime surfaces must contain no first-user or capture admission
    # lists. Only explicitly reviewed operational allowlists remain approved.
    assert not _contains_uid_outside_approved_allowlists(
        _MANIFEST['environments']['dev'],
        'vi7SA9ckQCe4ccobWNxlbdcNdC23',
    )

    cloud_run = _MANIFEST['environments']['dev']['cloud_run']
    services = cloud_run['services']
    for service in services.values():
        env = service.get('env', {})
        if 'OMI_PARITY_PACK_CAPTURE' in env:
            assert env['OMI_PARITY_PACK_CAPTURE']['value'] == '0'
            assert env['OMI_PARITY_PACK_ALLOWED_PRINCIPALS']['value'] == ''

    notifications_job = cloud_run['jobs']['notifications-job']
    notifications_env = notifications_job['env']
    forbidden_notifications_vars = {
        'MEMORY_ENABLED',
        'MEMORY_MODE',
        'MEMORY_ENABLED_USERS',
        'MEMORY_V3_GET_ENABLED',
        'MEMORY_CANONICAL_MAINTENANCE_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'MEMORY_TYPESENSE_COLLECTION',
        'TYPESENSE_HOST',
        'TYPESENSE_HOST_PORT',
        'TYPESENSE_API_KEY',
        'X_OAUTH_CLIENT_ID',
        'X_OAUTH_REDIRECT_URI',
        'RAPID_API_HOST',
    }
    assert forbidden_notifications_vars.isdisjoint(notifications_env)
    assert notifications_env['PINECONE_INDEX_NAME']['value'] == 'memories-backend-dev'
    assert notifications_env['OMI_BACKGROUND_FLEX_CAPABLE']['value'] == 'true'
    assert notifications_env['OMI_LLM_GATEWAY_URL']['env_var'] == 'OMI_LLM_GATEWAY_URL'
    assert notifications_env['OMI_CUSTOMER_DATA_PROJECT']['value'] == 'based-hardware'
    assert set(notifications_job['secrets']) == {
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
        'OMI_LLM_GATEWAY_SERVICE_TOKEN',
    }

    x_sync_job = cloud_run['jobs']['x-connector-sync-job']
    x_sync_env = x_sync_job['env']
    assert x_sync_env['PINECONE_INDEX_NAME']['value'] == 'memories-backend-dev'
    assert x_sync_env['OMI_BACKGROUND_FLEX_CAPABLE']['value'] == 'true'
    assert x_sync_env['OMI_LLM_GATEWAY_URL']['env_var'] == 'OMI_LLM_GATEWAY_URL'
    assert set(x_sync_job['secrets']) >= {
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
        'OMI_LLM_GATEWAY_SERVICE_TOKEN',
        'X_OAUTH_CLIENT_SECRET',
        'RAPID_API_KEY',
    }
    assert 'SERVICE_ACCOUNT_JSON' not in x_sync_job['secrets']
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in x_sync_job['secrets']
    assert x_sync_job['flags']['--service-account'] == (
        'dev-backend-runtime@based-hardware-dev.iam.gserviceaccount.com'
    )
    assert notifications_job['flags']['--memory'] == '2Gi'
    assert notifications_job['flags']['--task-timeout'] == '3600s'


def test_x_connector_deploy_uses_verified_gateway_endpoint_and_vpc_flags():
    workflow = (_SCRIPT.parents[2] / '.github/workflows/gcp_x_connector_sync_job.yml').read_text(encoding='utf-8')

    assert 'Verify LLM Gateway serving data plane' in workflow
    assert 'OMI_LLM_GATEWAY_URL: ${{ steps.gateway-serving.outputs.gateway_url }}' in workflow
    assert '${{ steps.runtime-env.outputs.cloud_run_flags }}' in workflow
    assert '--lane omi:auto:x-memory-extraction-flex' in workflow


def test_render_prod_emits_memory_maintenance_job_cron_on(monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'fake-google-client-id')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_ID', 'fake-claude-client-id')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_NAME', 'Claude')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_REDIRECT_URIS', 'https://claude.example/callback')
    monkeypatch.setenv(
        'ACCOUNT_DELETION_HANDLER_URL', 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run'
    )
    monkeypatch.setenv(
        'LISTEN_FINALIZATION_TASKS_HANDLER_URL',
        'https://backend-sync.example.com/v1/conversation-finalization-jobs/run',
    )
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', 'invoker@project.iam.gserviceaccount.com')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://backend-sync.example.com/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@project.iam.gserviceaccount.com')
    monkeypatch.setenv('X_OAUTH_CLIENT_ID', 'fake-x-client-id')
    monkeypatch.setenv('X_OAUTH_REDIRECT_URI', 'https://api.example/v1/x/callback')
    monkeypatch.setenv('RAPID_API_HOST', 'twitter-api.example')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    rc = _MODULE['main']()
    assert rc == 0
    out = _read_workflow_outputs()
    job_env = _job_env_block(out, 'memory_maintenance_job')
    # Prod GO 2026-08-15: the maintenance job follows the request-path product
    # flag. ST→LT cron is job-hosted on both env overlays with Flex.
    assert 'MEMORY_ENABLED=on' in job_env
    assert 'MEMORY_MODE=' not in job_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED=true' in job_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_FLEX' not in job_env
    assert 'OMI_BACKGROUND_FLEX_CAPABLE=true' in job_env
    assert 'MEMORY_ENABLED_USERS' not in job_env
    prod_memory_job = _MANIFEST['environments']['prod']['cloud_run']['jobs']['memory-maintenance-job']
    assert '--task-timeout=3600s' in _MODULE['_render_flags'](prod_memory_job['flags'])

    assert 'DESKTOP_PREVIEW_PUBLISH_KEY=DESKTOP_PREVIEW_PUBLISH_KEY:latest' in _job_secret_lines(out, 'backend')
    assert 'GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY:latest' in _job_secret_lines(out, 'backend_sync')

    notifications_env = _job_env_block(out, 'notifications_job')
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED' not in notifications_env


def test_render_prod_gateway_callers_inject_verified_endpoint(monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'fake-google-client-id')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_ID', 'fake-claude-client-id')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_NAME', 'Claude')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_REDIRECT_URIS', 'https://claude.example/callback')
    monkeypatch.setenv(
        'ACCOUNT_DELETION_HANDLER_URL', 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run'
    )
    monkeypatch.setenv(
        'LISTEN_FINALIZATION_TASKS_HANDLER_URL',
        'https://backend-sync.example.com/v1/conversation-finalization-jobs/run',
    )
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', 'invoker@project.iam.gserviceaccount.com')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://backend-sync.example.com/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@project.iam.gserviceaccount.com')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://172.16.160.108')
    monkeypatch.setenv('X_OAUTH_CLIENT_ID', 'fake-x-client-id')
    monkeypatch.setenv('X_OAUTH_REDIRECT_URI', 'https://api.example/v1/x/callback')
    monkeypatch.setenv('RAPID_API_HOST', 'twitter-api.example')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])

    assert _MODULE['main']() == 0
    output = _read_workflow_outputs()

    for service in ('backend', 'backend_sync', 'backend_sync_backfill', 'backend_integration'):
        service_env = _job_env_block(output, service)
        assert 'OMI_LLM_GATEWAY_FEATURE_MODE=gateway' in service_env
        assert 'OMI_LLM_CHAT_AGENT_ROUTE=gateway' in service_env
        assert 'OMI_LLM_GATEWAY_URL=http://172.16.160.108' in service_env
        assert 'OMI_LLM_GATEWAY_URL=http://127.0.0.1:9' not in service_env


def test_render_prod_requires_vpc_env_vars_before_job_outputs(monkeypatch):
    """Prod network flags are env_var-backed; missing VPC vars abort render before job outputs.

    gcp_memory_maintenance_job.yml must pass CLOUD_RUN_VPC_* like gcp_backend.yml, or prod
    workflow_dispatch fails before memory-maintenance-job env/secrets are emitted.
    """
    monkeypatch.delenv('CLOUD_RUN_VPC_NETWORK', raising=False)
    monkeypatch.delenv('CLOUD_RUN_VPC_SUBNET', raising=False)
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    with pytest.raises(ValueError, match='CLOUD_RUN_VPC'):
        _MODULE['main']()


def test_notifications_job_workflow_passes_vpc_vars_and_checkout_sha():
    workflow = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_notifications_job.yml'
    text = workflow.read_text(encoding='utf-8')
    assert 'CLOUD_RUN_VPC_NETWORK: ${{ vars.CLOUD_RUN_VPC_NETWORK }}' in text
    assert 'CLOUD_RUN_VPC_SUBNET: ${{ vars.CLOUD_RUN_VPC_SUBNET }}' in text
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text
    assert 'render_backend_runtime_env.py --env ${{ vars.ENV }} --job notifications-job' in text
    assert '${{ steps.runtime-env.outputs.notifications_job_flags }}' in text
    assert 'env_vars_update_strategy: overwrite' not in text
    assert 'secrets_update_strategy: overwrite' not in text
    assert (
        '--remove-env-vars=MEMORY_MODE,MEMORY_ENABLED_USERS,MEMORY_V3_GET_ENABLED,'
        'MEMORY_CANONICAL_MAINTENANCE_ENABLED,'
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED,MEMORY_CANONICAL_PROMOTION_CRON_ENABLED,'
        'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS,MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED,'
        'MEMORY_TYPESENSE_COLLECTION,TYPESENSE_HOST,'
        'TYPESENSE_HOST_PORT,TYPESENSE_API_KEY'
    ) in text


def test_memory_maintenance_job_workflow_passes_vpc_vars_and_checkout_sha():
    workflow = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_memory_maintenance_job.yml'
    text = workflow.read_text(encoding='utf-8')
    assert 'SERVICE: memory-maintenance-job' in text
    assert 'Dockerfile.memory_maintenance_job' in text
    assert 'memory_maintenance_job_env_vars' in text
    assert 'memory_maintenance_job_secrets' in text
    assert 'CLOUD_RUN_VPC_NETWORK: ${{ vars.CLOUD_RUN_VPC_NETWORK }}' in text
    assert 'CLOUD_RUN_VPC_SUBNET: ${{ vars.CLOUD_RUN_VPC_SUBNET }}' in text
    assert (
        'flags: ${{ steps.runtime-env.outputs.cloud_run_flags }} '
        '${{ steps.runtime-env.outputs.memory_maintenance_job_flags }}'
    ) in text
    # Prod deploys through GitHub WIF (credential-hygiene WS-C), which needs the
    # OIDC token; development keeps its JSON lane.
    assert "id-token: 'write'" in text
    assert 'omi-gha-deploy-prod/providers/github' in text
    assert "if: github.event.inputs.environment == 'prod'" in text
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text
    assert 'render_backend_runtime_env.py --env ${{ vars.ENV }} --job memory-maintenance-job' in text
    prod_memory_job = _MANIFEST['environments']['prod']['cloud_run']['jobs']['memory-maintenance-job']
    prod_job_flags = _MODULE['_render_flags'](prod_memory_job['flags'])
    assert 'MEMORY_ENABLED_USERS' in prod_job_flags
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED' in prod_job_flags
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS' in prod_job_flags
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED' in prod_job_flags
    assert 'Measure runner disk cleanup' in text
    assert 'Duration: $((SECONDS - started_at))s' in text


def test_auto_dev_memory_maintenance_workflow_selects_only_its_job():
    workflow = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_memory_maintenance_job_auto_dev.yml'

    assert 'render_backend_runtime_env.py --env dev --job memory-maintenance-job' in workflow.read_text(
        encoding='utf-8'
    )
    text = workflow.read_text(encoding='utf-8')
    assert 'Measure runner disk cleanup' in text
    assert 'Duration: $((SECONDS - started_at))s' in text


def test_backend_service_deploys_remove_retired_canonical_memory_env_vars():
    from scripts.runtime_env_memory_contract import RETIRED_CANONICAL_MEMORY_ENV

    retired = ','.join(
        name
        for name in (
            'MEMORY_ENABLED_USERS',
            'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
            'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS',
            'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
        )
        if name in RETIRED_CANONICAL_MEMORY_ENV
    )
    assert set(retired.split(',')) == set(RETIRED_CANONICAL_MEMORY_ENV)
    workflow_root = Path(__file__).resolve().parents[3] / '.github/workflows'
    deploy_action = Path(__file__).resolve().parents[3] / '.github/actions/deploy-backend-stack/action.yml'
    deploy_action_text = deploy_action.read_text(encoding='utf-8')
    for workflow_name in ('gcp_backend.yml', 'gcp_backend_auto_dev.yml'):
        text = (workflow_root / workflow_name).read_text(encoding='utf-8')
        if './.github/actions/deploy-backend-stack' in text:
            text += '\n' + deploy_action_text
        assert text.count(f'--remove-env-vars={retired}') == 1
        assert text.count(f'--remove-env-vars=HOSTED_PUSHER_API_URL,{retired}') == 2

    action = Path(__file__).resolve().parents[3] / '.github/actions/sync-backfill-lifecycle/action.yml'
    action_text = action.read_text(encoding='utf-8')
    assert f'REMOVE_ENV_VARS: HOSTED_PUSHER_API_URL,{retired}' in action_text
    assert f'--remove-env-vars=HOSTED_PUSHER_API_URL,{retired}' in action_text

    # The memory-maintenance-job is also a Cloud Run deploy that merges env
    # vars across revisions. Its rendered --remove-env-vars must strip the
    # same retired set so the stale binding does not survive the universal-
    # memory change (see #11447, #11472).
    manifest = _MANIFEST['environments']
    for env in ('dev', 'prod'):
        job = manifest[env]['cloud_run']['jobs']['memory-maintenance-job']
        job_flags = _MODULE['_render_flags'](job['flags'])
        assert f'--remove-env-vars={retired}' in job_flags, f'memory-maintenance-job for {env} must strip {retired}'


def _deploy_backend_stack_step_flags(step_id: str) -> str:
    action = Path(__file__).resolve().parents[3] / '.github/actions/deploy-backend-stack/action.yml'
    text = action.read_text(encoding='utf-8')
    marker = f'id: {step_id}\n'
    start = text.index(marker)
    flags_key = text.index('flags: >-', start)
    env_key = text.index('env_vars:', flags_key)
    return text[flags_key:env_key]


def test_backend_integration_deploy_pins_mcp_serving_capacity():
    # Live prod backend-integration was maxScale=25, minScale=1, concurrency=300
    # on 1 CPU. ChatGPT openai-mcp POSTs then 503 with "no available instance"
    # because I/O-bound MCP work does not trip CPU scale-out. Pin scale-out
    # here only; do not copy onto backend.
    # backend-sync DOES carry --cpu=2 (#21668): its 6-8Gi memory requires >=2
    # CPU on Cloud Run, and 1-CPU deploys of 8Gi are rejected outright.
    # 2026-10-24 costcut mirror: backend now pins its OWN live shape (prod-scoped
    # 8Gi/2 CPU/20/3/100) instead of inheriting it revision-to-revision; --cpu=2
    # is legitimate there for the same #21668 pairing, but every
    # integration-specific flag below still must not leak onto it.
    integration_flags = _deploy_backend_stack_step_flags('deploy-backend-integration')
    backend_flags = _deploy_backend_stack_step_flags('deploy-backend')
    sync_flags = _deploy_backend_stack_step_flags('deploy-backend-sync')
    # 2026-10-24 right-sizing: prod integration stays warm; the dev project idles at 0.
    integration_min = "--min-instances=${{ inputs.runtime_env == 'prod' && '3' || '0' }}"
    for flag in (
        '--memory=2Gi',
        '--concurrency=40',
        integration_min,
        '--max-instances=50',
        '--no-cpu-throttling',
    ):
        assert flag in integration_flags, flag
        assert flag not in backend_flags, flag
        # backend-sync owns its own scale-out cap (see test_sync_two_lane.py);
        # its value may legitimately equal integration's, so only the other
        # integration-specific flags must stay off it.
        if not flag.startswith('--max-instances='):
            assert flag not in sync_flags, flag
    assert '--cpu=2' in integration_flags
    assert '--cpu=2' in sync_flags
    # Backend's own prod shape (dev branch empty: dev keeps inheriting).
    assert (
        "${{ inputs.runtime_env == 'prod' && '--cpu=2 --memory=8Gi --concurrency=20"
        " --min-instances=3 --max-instances=100' || '' }}"
    ) in backend_flags


VERTEX_PT_CONTRACT = 'Company-paid Gemini text and vision generation may use only the active model'


@pytest.mark.parametrize(
    ('env', 'project', 'gemini_secret'),
    [
        ('dev', 'based-hardware-dev', 'GEMINI_API_KEY'),
        ('prod', 'based-hardware', 'DESKTOP_GEMINI_API_KEY'),
    ],
)
def test_desktop_backend_compose_pins_vertex_pt(env, project, gemini_secret):
    desktop = _MANIFEST['environments'][env]['desktop_backend']
    rendered = _MODULE['_render_env_vars'](desktop['env'])
    assert 'USE_VERTEX_AI=true' in rendered, VERTEX_PT_CONTRACT
    assert f'GOOGLE_CLOUD_PROJECT={project}' in rendered, VERTEX_PT_CONTRACT
    assert 'GCP_LOCATION=us-central1' in rendered, VERTEX_PT_CONTRACT
    assert 'PROMETHEUS_SIDECAR_PORT=9090' in rendered
    expected_secrets = (
        f'GEMINI_API_KEY={gemini_secret}:latest\n'
        'METRICS_SECRET=METRICS_SECRET:latest\n'
        'POSTHOG_PROJECT_API_KEY=POSTHOG_PROJECT_API_KEY:latest'
    )
    assert _MODULE['_render_secrets'](desktop['secrets']) == expected_secrets
    docs = Path(__file__).resolve().parents[2] / 'docs' / 'vertex-pt-flash.md'
    assert VERTEX_PT_CONTRACT in docs.read_text(encoding='utf-8')


def test_state_output_carries_cloud_run_jobs(tmp_path, monkeypatch):
    env_config = {
        'cloud_run': {
            'network': {'flags': {'--vpc-egress': 'private-ranges-only'}},
            'services': {'backend': {'env': {'OMI_ENV_STAGE': {'value': 'dev'}}, 'secrets': {}}},
            'jobs': {
                'notifications-job': {
                    'flags': {'--task-timeout': '3600s'},
                    'env': {'OMI_ENV_STAGE': {'value': 'dev'}},
                    'secrets': {'OPENAI_API_KEY': {'secret': 'OPENAI_API_KEY', 'version': 'latest'}},
                }
            },
        }
    }
    state_path = tmp_path / 'runtime-env-state.json'
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: {'environments': {'dev': env_config}})
    monkeypatch.setattr(
        'sys.argv',
        ['render_backend_runtime_env.py', '--env', 'dev', '--state-output', str(state_path)],
    )

    assert _MODULE['main']() == 0

    state = json.loads(state_path.read_text(encoding='utf-8'))

    assert state['jobs'] == {
        'notifications-job': {
            'env': [
                {'name': 'OMI_ENV_STAGE', 'value': 'dev'},
                {
                    'name': 'OPENAI_API_KEY',
                    'valueFrom': {'secretKeyRef': {'name': 'OPENAI_API_KEY', 'key': 'latest'}},
                },
            ],
            'flags': {'--task-timeout': '3600s'},
        }
    }


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_state_output_covers_every_declared_job(env, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-subnet-1')
    env_config = _MANIFEST['environments'][env]
    cloud_run = env_config['cloud_run']

    # Services need the deploy workflow's environment; the job contract does not.
    state = _MODULE['_render_cloud_run_state']({'cloud_run': {**cloud_run, 'services': {}}})

    assert set(state['jobs']) == set(cloud_run['jobs'])


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DESKTOP_WORKFLOWS = {
    'dev': _REPO_ROOT / '.github/workflows/desktop_backend_auto_dev.yml',
    'prod': _REPO_ROOT / '.github/workflows/desktop_backend_prod.yml',
}


@pytest.mark.parametrize('env_name', ('dev', 'prod'))
def test_desktop_state_output_is_shaped_for_the_sidecar_guard(env_name, tmp_path):
    """attach_cloud_run_gmp_sidecar.py reads state['services'][service]['env']."""
    out = tmp_path / 'state.json'
    env_config = _MODULE['_as_config_dict'](_MANIFEST['environments'][env_name])
    state = _MODULE['_render_desktop_backend_state'](env_config)
    out.write_text(json.dumps(state), encoding='utf-8')

    entries = state['services']['desktop-backend']['env']
    assert entries, 'an empty expectation would make the sidecar guard a no-op'
    for entry in entries:
        assert isinstance(entry['name'], str) and isinstance(entry['value'], str)

    # Round-trip through the consumer so the two stay compatible by construction.
    attach = runpy.run_path(
        str(_REPO_ROOT / 'backend/scripts/attach_cloud_run_gmp_sidecar.py'),
        run_name='attach_cloud_run_gmp_sidecar',
    )
    expected = attach['_expected_literal_env'](out, service_name='desktop-backend')
    assert expected == {entry['name']: entry['value'] for entry in entries}


@pytest.mark.parametrize('env_name', ('dev', 'prod'))
def test_desktop_manifest_env_matches_what_the_workflow_deploys(env_name):
    """The guard is only meaningful while both sources agree.

    desktop-backend still sets most of its env inline in its deploy workflow, so
    the manifest owns a subset. If a manifest value drifts from the deployed one,
    the sidecar attach fails the deploy rather than the value silently differing —
    catch that here instead, at review time.
    """
    env_config = _MODULE['_as_config_dict'](_MANIFEST['environments'][env_name])
    state = _MODULE['_render_desktop_backend_state'](env_config)
    workflow = _DESKTOP_WORKFLOWS[env_name].read_text(encoding='utf-8')

    literal_project = {'dev': 'based-hardware-dev', 'prod': 'based-hardware'}[env_name]
    for entry in state['services']['desktop-backend']['env']:
        name, value = entry['name'], entry['value']
        if name in {row['env_var'] for row in LADDER_V1_PRICE_BINDINGS.values()}:
            assert '${{ steps.desktop-expected-env.outputs.ladder_price_env_vars }}' in workflow
            assert f'{name}: ${{{{ vars.{name} }}}}' in workflow
            continue
        if name in _MODULE['FIRESTORE_READ_RUNTIME_ENV_NAMES']:
            assert '${{ steps.desktop-expected-env.outputs.firestore_read_env_vars }}' in workflow
            continue
        if value == literal_project:
            # Supplied to the workflow as ${{ vars.GCP_PROJECT_ID }}.
            assert f'{name}=${{{{ vars.GCP_PROJECT_ID }}}}' in workflow, name
            continue
        assert f'{name}={value}' in workflow, f'{env_name}: {name}={value} is not what the workflow deploys'


def test_desktop_lever_output_tracks_manifest_value_and_escapes_deploy_delimiters(monkeypatch, tmp_path, capsys):
    env_config = deepcopy(_MANIFEST['environments']['dev'])
    env_config['desktop_backend']['env']['FIRESTORE_READ_LEVERS']['value'] = '{"queue_age":true,"subscription":true}'
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: {'environments': {'dev': env_config}})
    state = tmp_path / 'state.json'
    monkeypatch.setattr('sys.argv', [str(_SCRIPT), '--env', 'dev', '--desktop-state-output', str(state)])

    assert _MODULE['main']() == 0

    output = _read_workflow_outputs()
    assert 'FIRESTORE_READ_LEVERS={"queue_age":true\\,"subscription":true}\n' in output
    assert output.endswith('__BACKEND_RUNTIME_ENV_firestore_read_env_vars__\n')


def test_staged_desktop_production_controls_render_without_runtime_checkout(tmp_path):
    """Exercise the workflow's actual local staging commands and import closure."""
    repo = _SCRIPT.parents[2]
    workflow = yaml.safe_load((repo / '.github/workflows/desktop_backend_prod.yml').read_text())
    staging = next(
        step
        for job in workflow['jobs'].values()
        for step in job.get('steps', [])
        if step.get('name') == 'Stage immutable desktop backend controls'
    )
    source = tmp_path / '.workflow-source'
    # Copy only the paths that the staging commands name. Never copy credentials
    # or the working checkout; the shell operates solely inside this temp tree.
    for line in staging['run'].splitlines():
        if line.strip().startswith('cp .workflow-source/'):
            relative = line.strip().split()[1].removeprefix('.workflow-source/')
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / relative, target)
    runner_temp = tmp_path / 'runner'
    runner_temp.mkdir()
    environment = {**os.environ, 'RUNNER_TEMP': str(runner_temp), 'GITHUB_ENV': str(tmp_path / 'github-env')}
    subprocess.run(['bash', '-c', staging['run']], cwd=tmp_path, env=environment, check=True)
    controls = runner_temp / 'desktop-backend-deploy-controls'
    state = tmp_path / 'state.json'
    renderer_output = tmp_path / 'renderer-github-output'
    result = subprocess.run(
        [
            sys.executable,
            '-I',
            str(controls / 'backend/scripts/render_backend_runtime_env.py'),
            '--env',
            'prod',
            '--desktop-state-output',
            str(state),
        ],
        cwd=tmp_path,
        env={**os.environ, 'GITHUB_OUTPUT': str(renderer_output)},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ''
    workflow_outputs = renderer_output.read_text(encoding='utf-8')
    assert (
        'firestore_read_env_vars<<__BACKEND_RUNTIME_ENV_firestore_read_env_vars__\nFIRESTORE_READ_LEVERS={"action_items_page":100\\,"backfill_task_reads":100\\,"batch_privacy_memoize":5\\,"candidates_page":100\\,"canonical_statuses_dedupe":100\\,"deletion_marker_cache":100\\,"historical_scan_memo":100\\,"ledger_purge_coalesce":100\\,"mcp_conversation_cards_cache":100\\,"memory_list_index_window":25\\,"people_scan_dedupe":0\\,"queue_age_sample_budget":0\\,"request_read_dedupe":100\\,"serving_config_cache":100\\,"singleton_loops":100\\,"subscription_cache":100\\,"usage_month_cache":100}\n'
        in workflow_outputs
    )
    assert workflow_outputs.endswith('__BACKEND_RUNTIME_ENV_firestore_read_env_vars__\n')
    entries = json.loads(state.read_text())['services']['desktop-backend']['env']
    assert {'name': 'CLIENT_SUMMARIES_AT_CAP_ENABLED', 'value': 'true'} in entries


def test_phase_a_keeps_cloud_run_credentials_and_isolates_gke_v2_redis():
    prod = _MANIFEST['environments']['prod']
    gke = [prod['llm_gateway'], prod['gke']['backend-listen'], prod['gke']['pusher']]
    run = list(prod['cloud_run']['services'].values())
    for host in gke + run + [prod['desktop_backend']]:
        assert host['env']['MENTOR_PIPELINE']['value'] == 'cohort'
        assert not any(k.startswith('COMMITMENT_FOLLOWUP_TASKS_') for k in host['env'])
    for host in gke:
        assert host['env']['PROACTIVITY_REDIS_PORT']['value'] == '13151'
    for host in gke:
        assert host['env']['PROACTIVITY_REDIS_HOST']['config_map'] == {
            'name': 'prod-omi-backend-config',
            'key': 'REDIS_DB_HOST',
        }
        assert host['env']['PROACTIVITY_REDIS_PASSWORD']['secret'] == {
            'name': 'prod-omi-backend-secrets',
            'key': 'REDIS_DB_PASSWORD',
        }
    for host in run + [prod['desktop_backend']]:
        for block in ('env', 'secrets'):
            assert not any(key.startswith('PROACTIVITY_REDIS_') for key in host[block])
    for host in run:
        assert 'POSTHOG_PROJECT_API_KEY' not in host['secrets']
        assert 'POSTHOG_API_KEY' not in host['secrets']
    # Desktop's existing normal Redis mounts remain owned by its workflow,
    # rather than introducing extra refs in the manifest's rendered subset.
    desktop = prod['desktop_backend']
    for key in ('HOST', 'PORT', 'PASSWORD'):
        assert f'REDIS_DB_{key}' not in desktop['env']
        assert f'REDIS_DB_{key}' not in desktop['secrets']
    # Gateway reservation state shares the same Redis binding as backend-listen.
    chart = yaml.safe_load((_REPO_ROOT / 'backend/charts/llm-gateway/prod_omi_llm_gateway_values.yaml').read_text())
    env = {row['name']: row for row in chart['env']}
    assert env['REDIS_DB_HOST']['valueFrom']['configMapKeyRef'] == {
        'name': 'prod-omi-backend-config',
        'key': 'REDIS_DB_HOST',
    }
    assert env['REDIS_DB_PORT']['value'] == '13151'
    assert env['REDIS_DB_PASSWORD']['valueFrom']['secretKeyRef'] == {
        'name': 'prod-omi-backend-secrets',
        'key': 'REDIS_DB_PASSWORD',
    }


def test_prod_cloud_run_secret_refs_match_approved_bindings():
    # Base mounts, prod-only dream salt and backend-only messaging provider credentials.
    # Preserve resource, env alias and version: aliases can introduce startup dependencies.
    common = {'GOOGLE_CLIENT_SECRET', 'ENCRYPTION_SECRET', 'MODULATE_API_KEY', 'OMI_LLM_GATEWAY_SERVICE_TOKEN'}
    baseline = {
        'backend': common
        | {
            'METRICS_SECRET',
            'LIFECYCLE_EMAIL_SIGNING_SECRET',
            'MEMORY_V3_CURSOR_SECRET',
            'DESKTOP_PREVIEW_PUBLISH_KEY',
            'BETA_PROMOTION_TOKEN',
            'MCP_OAUTH_CLIENTS_JSON',
            'SCREEN_FRAME_SIGNING_SECRET',
            'DREAM_AGENT_FEEDBACK_SALT',
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_WEBHOOK_SECRET',
            'LINQ_API_KEY',
            'LINQ_WEBHOOK_SECRET',
        },
        'backend-sync': common
        | {'GOOGLE_MAPS_API_KEY', 'DREAM_AGENT_FEEDBACK_SALT', 'TYPESENSE_HOST', 'TYPESENSE_API_KEY'},
        'backend-sync-backfill': common,
        'backend-integration': common | {'POSTHOG_EVENTS_API_KEY'},
    }
    prod = _MANIFEST['environments']['prod']
    for service, names in baseline.items():
        refs = _MODULE['_render_secret_entries'](prod['cloud_run']['services'][service]['secrets'])
        assert {
            (entry['name'], entry['valueFrom']['secretKeyRef']['name'], entry['valueFrom']['secretKeyRef']['key'])
            for entry in refs
        } == {(name, name, 'latest') for name in names}, service
    backend_env = prod['cloud_run']['services']['backend']['env']
    token = backend_env['PROACTIVITY_V2_POSTHOG_TOKEN']['value']
    assert token.startswith('phc_')
    assert backend_env['POSTHOG_BILLING_API_KEY'] == {'value': token, 'category': 'telemetry'}
    assert backend_env['POSTHOG_HOST'] == {'value': 'https://us.posthog.com', 'category': 'telemetry'}
    assert _MODULE['_render_env_entries']({'POSTHOG_BILLING_API_KEY': backend_env['POSTHOG_BILLING_API_KEY']}) == [
        {'name': 'POSTHOG_BILLING_API_KEY', 'value': token}
    ]
    for service_name, service in prod['cloud_run']['services'].items():
        if service_name == 'backend':
            continue
        assert 'POSTHOG_BILLING_API_KEY' not in service.get('env', {})
        assert 'POSTHOG_BILLING_API_KEY' not in service.get('secrets', {})
    desktop = _MODULE['_render_secret_entries'](prod['desktop_backend']['secrets'])
    assert {
        (entry['name'], entry['valueFrom']['secretKeyRef']['name'], entry['valueFrom']['secretKeyRef']['key'])
        for entry in desktop
    } == {
        ('GEMINI_API_KEY', 'DESKTOP_GEMINI_API_KEY', 'latest'),
        ('METRICS_SECRET', 'METRICS_SECRET', 'latest'),
        ('POSTHOG_PROJECT_API_KEY', 'POSTHOG_PROJECT_API_KEY', 'latest'),
    }


def test_integration_enrichment_renderer_targets_fresh_sync_handler(monkeypatch):
    handler = 'https://fresh.invalid/v2/sync-jobs/run'
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', handler)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    entries = _MANIFEST['environments']['prod']['cloud_run']['services']['backend-integration']['env']
    selected = {
        name: entries[name]
        for name in (
            'SYNC_TASKS_QUEUE',
            'SYNC_TASKS_HANDLER_URL',
            'SYNC_TASKS_OIDC_AUDIENCE',
            'SYNC_TASKS_INVOKER_SA',
        )
    }
    rendered = _MODULE['_render_env_vars'](selected)
    assert 'SYNC_TASKS_QUEUE=sync-jobs' in rendered
    assert f'SYNC_TASKS_HANDLER_URL={handler}' in rendered
    assert f'SYNC_TASKS_OIDC_AUDIENCE={handler}' in rendered
    assert 'SYNC_TASKS_INVOKER_SA=invoker@example.invalid' in rendered


@pytest.mark.parametrize('env_name', ['dev', 'prod'])
@pytest.mark.parametrize('bound', [False, True])
def test_rendered_price_bindings_preserve_versioned_screen_capability(monkeypatch, tmp_path, capsys, env_name, bound):
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', 'fixture-subscription-reader')
    bindings = list(LADDER_V1_PRICE_BINDINGS.values())
    for index, row in enumerate(bindings):
        if bound:
            monkeypatch.setenv(row['env_var'], f'price_render_fixture_{index}')
        else:
            monkeypatch.delenv(row['env_var'], raising=False)
    state_path = tmp_path / 'desktop-state.json'
    monkeypatch.setattr('sys.argv', [str(_SCRIPT), '--env', env_name, '--desktop-state-output', str(state_path)])
    assert _MODULE['main']() == 0
    output = _read_workflow_outputs()
    marker = '__BACKEND_RUNTIME_ENV_ladder_price_env_vars__'
    deployed = dict(line.split('=', 1) for line in output.split(marker)[1].strip().splitlines() if line)
    expected_state = {
        entry['name']: entry['value']
        for entry in json.loads(state_path.read_text())['services']['desktop-backend']['env']
    }
    backend_entries = _MANIFEST['environments'][env_name]['cloud_run']['services']['backend']['env']
    backend_workflow = (
        _REPO_ROOT / '.github/workflows' / ('gcp_backend_auto_dev.yml' if env_name == 'dev' else 'gcp_backend.yml')
    )
    workflow_text = backend_workflow.read_text()
    # Environment-scoped price refs must be read after the deployment job selects its environment.
    workflow = yaml.safe_load(workflow_text)
    deploy_job = workflow['jobs']['deploy']
    assert deploy_job.get('environment')
    deploy_steps = [
        step for step in deploy_job['steps'] if step.get('uses') == './.github/actions/deploy-backend-stack'
    ]
    assert len(deploy_steps) == 1
    for index, row in enumerate(bindings):
        key = row['env_var']
        expected = f'price_render_fixture_{index}' if bound else ''
        if bound:
            assert deployed[key] == expected_state[key] == expected
            assert _MODULE['_render_env_vars']({key: backend_entries[key]}) == f'{key}={expected}'
        else:
            assert key not in deployed and key not in expected_state
            assert _MODULE['_render_env_vars']({key: backend_entries[key]}) == ''
        assert f'{key}: ${{{{ vars.{key} }}}}' in workflow_text
        assert key not in workflow.get('env', {})
        assert deploy_steps[0]['env'][key] == '${{ vars.' + key + ' }}'
        if bound:
            subscription = {
                'plan': row['plan_id'],
                'current_price_id': expected,
                'current_period_end': datetime.now(timezone.utc).timestamp() + 3600,
            }
            assert resolve_subscription_entitlements(subscription, deployed)['capabilities'][
                'cloud_screen_vectors'
            ] is (row['plan_id'] != 'plus')
    assert set(deployed) == ({row['env_var'] for row in bindings} if bound else set())
    for price, plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items():
        subscription = {
            'plan': plan.value,
            'current_price_id': price,
            'current_period_end': datetime.now(timezone.utc).timestamp() + 3600,
        }
        assert resolve_subscription_entitlements(subscription, deployed)['capabilities']['cloud_screen_vectors'] is True


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('reference', [None, 'fixture-reader', 'projects/fixture-project/secrets/fixture-reader'])
def test_desktop_mixed_prices_require_only_optional_restricted_read_reference(
    monkeypatch, tmp_path, capsys, environment, reference
):
    for binding in LADDER_V1_PRICE_BINDINGS.values():
        monkeypatch.delenv(binding['env_var'], raising=False)
    if reference is None:
        monkeypatch.delenv('SCREEN_VECTOR_STRIPE_READ_SECRET', raising=False)
    else:
        monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', reference)
    # Explicitly supplied references are mounted even when incoming prices are
    # omitted: the effective service can retain previously configured prices.
    config = _MANIFEST['environments'][environment]
    optional = _MODULE['_render_desktop_backend_state'](config)['services']['desktop-backend']['secrets']
    assert bool(optional) is (reference is not None)
    monkeypatch.setenv('LADDER_V1_PLUS_MONTH_PRICE_ID', 'price_future_fixture')
    path = tmp_path / 'state.json'
    monkeypatch.setattr('sys.argv', [str(_SCRIPT), '--env', environment, '--desktop-state-output', str(path)])
    if reference is None:
        with pytest.raises(ValueError, match='require SCREEN_VECTOR_STRIPE_READ_SECRET'):
            _MODULE['main']()
        assert not path.exists() and capsys.readouterr().out == ''
    else:
        assert _MODULE['main']() == 0
        state = json.loads(path.read_text())['services']['desktop-backend']
        assert state['secrets'] == [
            {
                'name': 'SCREEN_VECTOR_STRIPE_API_KEY',
                'valueFrom': {'secretKeyRef': {'name': reference, 'key': 'latest'}},
            }
        ]
        output = _read_workflow_outputs()
        assert reference not in output
        assert 'screen_vector_stripe_secret' not in output
        assert '\nSTRIPE_API_KEY=' not in output
        assert all(entry['name'] != 'SCREEN_VECTOR_STRIPE_READ_SECRET' for entry in state['env'])
    workflow = yaml.safe_load(_DESKTOP_WORKFLOWS[environment].read_text())
    render = next(
        (job, step)
        for job in workflow['jobs'].values()
        for step in job.get('steps', [])
        if step.get('id') == 'desktop-expected-env'
    )
    assert render[0].get('environment')
    assert (
        render[1]['env']['SCREEN_VECTOR_STRIPE_READ_SECRET'] == '${{ vars.DESKTOP_SCREEN_VECTOR_STRIPE_READ_SECRET }}'
    )
    assert 'SCREEN_VECTOR_STRIPE_READ_SECRET' not in workflow.get('env', {})
    deploy = next(
        step
        for job in workflow['jobs'].values()
        for step in job.get('steps', [])
        if step.get('id') == 'deploy-candidate'
    )
    steps = render[0]['steps']
    assert steps.index(render[1]) < steps.index(deploy)
    assert not render[1].get('continue-on-error')
    assert not deploy.get('if')  # Default success() keeps invalid metadata from reaching deployment.
    assert (
        "${{ vars.DESKTOP_SCREEN_VECTOR_STRIPE_READ_SECRET && "
        "format('SCREEN_VECTOR_STRIPE_API_KEY={0}:latest', vars.DESKTOP_SCREEN_VECTOR_STRIPE_READ_SECRET) || '' }}"
    ) in deploy['with']['secrets']
    assert '\nSTRIPE_API_KEY=' not in deploy['with']['secrets']


@pytest.mark.parametrize(
    'reference',
    [
        'bad:latest',
        'a,b=payload',
        'bad\nSTRIPE_API_KEY=payload',
        '../bad',
        'projects/a/secrets/name/versions/1',
        'sk_live_fixture',
        'rk_live_fixture',
    ],
)
def test_dynamic_secret_reference_rejects_injection_and_credential_payload_shapes(monkeypatch, reference):
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', reference)
    with pytest.raises(ValueError, match='invalid resource reference') as error:
        _MODULE['_render_secret_entries'](
            {
                'SCREEN_VECTOR_STRIPE_API_KEY': {
                    'env_var': 'SCREEN_VECTOR_STRIPE_READ_SECRET',
                    'default': '',
                    'version': 'latest',
                }
            }
        )
    assert reference not in str(error.value)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_cloud_run_omitted_price_updates_preserve_existing_identity(monkeypatch, environment):
    keys = [row['env_var'] for row in LADDER_V1_PRICE_BINDINGS.values()]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv('SCREEN_VECTOR_STRIPE_READ_SECRET', raising=False)
    config = _MANIFEST['environments'][environment]
    # Pin the actual owning deployment actions' merge contract rather than
    # modeling an update independently of the checked-in caller.
    desktop_workflow = yaml.safe_load(_DESKTOP_WORKFLOWS[environment].read_text())
    stack = yaml.safe_load((_REPO_ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    deploys = [step for step in stack['runs']['steps'] if step.get('id') == 'deploy-backend']
    deploys += [
        step
        for job in desktop_workflow['jobs'].values()
        for step in job.get('steps', [])
        if step.get('id') == 'deploy-candidate'
    ]
    assert len(deploys) == 2
    for deploy in deploys:
        assert deploy['uses'] == 'google-github-actions/deploy-cloudrun@v3'
        assert deploy['with'].get('env_vars_update_strategy', 'merge') == 'merge'
        assert all(key not in deploy['with'].get('flags', '') for key in keys)
    from scripts.attach_cloud_run_gmp_sidecar import _validate_expected_literal_env

    prior = {key: f'price_existing_fixture_{index}' for index, key in enumerate(keys)}
    for entries in [config['cloud_run']['services']['backend']['env'], config['desktop_backend']['env']]:
        price_entries = {key: entries[key] for key in keys}
        updates = _MODULE['_render_env_vars'](price_entries)
        expected = _MODULE['_render_env_entries'](price_entries)
        assert updates == '' and expected == []
        # deploy-cloudrun merges only supplied env assignments; omitted names
        # remain operator-owned, including when sidecar guard rewrites the export.
        effective = dict(prior)
        effective.update(dict(line.split('=', 1) for line in updates.splitlines()))
        assert effective == prior
        exported = {
            'spec': {
                'template': {
                    'spec': {
                        'containers': [
                            {
                                'name': 'ingress',
                                'env': [{'name': key, 'value': value} for key, value in effective.items()],
                            }
                        ]
                    }
                }
            }
        }
        _validate_expected_literal_env(exported, expected={}, ingress_container_name='ingress', phase='before')
        assert {e['name']: e['value'] for e in exported['spec']['template']['spec']['containers'][0]['env']} == prior
        monkeypatch.setenv(keys[0], 'price_explicit_fixture')
        updates = _MODULE['_render_env_vars'](price_entries)
        effective.update(dict(line.split('=', 1) for line in updates.splitlines()))
        assert effective == dict(prior, **{keys[0]: 'price_explicit_fixture'})
        assert _MODULE['_render_env_entries'](price_entries) == [{'name': keys[0], 'value': 'price_explicit_fixture'}]
        monkeypatch.delenv(keys[0])


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_desktop_operator_price_realm_is_explicit_and_separate_from_main(monkeypatch, environment):
    workflow = yaml.safe_load(_DESKTOP_WORKFLOWS[environment].read_text())
    render_job, render = next(
        (job, step)
        for job in workflow['jobs'].values()
        for step in job.get('steps', [])
        if step.get('id') == 'desktop-expected-env'
    )
    assert render_job.get('environment')
    config = _MANIFEST['environments'][environment]
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', 'fixture-desktop-customer-reader')
    main = {}
    desktop = {}
    for index, binding in enumerate(LADDER_V1_PRICE_BINDINGS.values()):
        key = binding['env_var']
        assert render['env'][key] == '${{ vars.DESKTOP_' + key + ' }}'
        assert key not in workflow.get('env', {})
        assert '${{ vars.' + key + ' }}' not in _DESKTOP_WORKFLOWS[environment].read_text()
        main[key] = f'price_main_plane_{index}'
        desktop[key] = f'price_desktop_customer_plane_{index}'
        monkeypatch.setenv(key, main[key])
    main_env = {
        e['name']: e['value']
        for e in _MODULE['_render_env_entries'](
            {key: config['cloud_run']['services']['backend']['env'][key] for key in main}
        )
    }
    for key, value in desktop.items():
        monkeypatch.setenv(key, value)
    desktop_env = {
        e['name']: e['value']
        for e in _MODULE['_render_desktop_backend_state'](config)['services']['desktop-backend']['env']
        if e['name'] in desktop
    }
    assert main_env == main and desktop_env == desktop
    for index, binding in enumerate(LADDER_V1_PRICE_BINDINGS.values()):
        for values, price in [(main_env, main[binding['env_var']]), (desktop_env, desktop[binding['env_var']])]:
            subscription = {
                'plan': binding['plan_id'],
                'current_price_id': price,
                'current_period_end': datetime.now(timezone.utc).timestamp() + 3600,
            }
            assert resolve_subscription_entitlements(subscription, values)['capabilities']['cloud_screen_vectors'] is (
                binding['plan_id'] != 'plus'
            )


@pytest.mark.parametrize('descriptor', ['literal', 'dynamic'])
@pytest.mark.parametrize(
    'candidate',
    [
        'sk_live_fixture_not_real',
        'rk_live_fixture_not_real',
        'bad\nSTRIPE_API_KEY=fixture',
        'bad:latest',
        '../fixture',
        '{"private_key":"fixture"}',
    ],
)
def test_invalid_resource_never_reaches_cli_state_or_workflow_output(
    monkeypatch, tmp_path, capsys, descriptor, candidate
):
    config = deepcopy(_MANIFEST['environments']['dev'])
    entry = (
        {'secret': candidate}
        if descriptor == 'literal'
        else {'env_var': 'SCREEN_VECTOR_STRIPE_READ_SECRET', 'default': ''}
    )
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', candidate)
    config['desktop_backend']['secrets']['SCREEN_VECTOR_STRIPE_API_KEY'] = entry
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: {'environments': {'dev': config}})
    output_path = Path(os.environ['GITHUB_OUTPUT'])
    output_path.write_text('existing_output=retained\n')
    state_path = tmp_path / 'state.json'
    monkeypatch.setattr('sys.argv', [str(_SCRIPT), '--env', 'dev', '--desktop-state-output', str(state_path)])
    with pytest.raises(ValueError, match='invalid resource reference') as error:
        _MODULE['main']()
    assert candidate not in str(error.value)
    assert not state_path.exists()
    assert output_path.read_text() == 'existing_output=retained\n'
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('descriptor', ['literal', 'dynamic'])
@pytest.mark.parametrize('resource_name', ['fixture-reader', 'projects/fixture-project/secrets/fixture-reader'])
def test_cli_emits_only_resource_metadata_never_runtime_credential_value(
    monkeypatch, tmp_path, capsys, descriptor, resource_name
):
    config = deepcopy(_MANIFEST['environments']['dev'])
    entry = (
        {'secret': resource_name}
        if descriptor == 'literal'
        else {'env_var': 'SCREEN_VECTOR_STRIPE_READ_SECRET', 'default': ''}
    )
    config['desktop_backend']['secrets']['SCREEN_VECTOR_STRIPE_API_KEY'] = entry
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: {'environments': {'dev': config}})
    fixture_credential = 'sk_live_fixture_not_real'
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_API_KEY', fixture_credential)
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', resource_name)
    state_path = tmp_path / 'state.json'
    monkeypatch.setattr('sys.argv', [str(_SCRIPT), '--env', 'dev', '--desktop-state-output', str(state_path)])
    assert _MODULE['main']() == 0
    state = json.loads(state_path.read_text())['services']['desktop-backend']
    assert state['secrets'] == [
        {
            'name': 'SCREEN_VECTOR_STRIPE_API_KEY',
            'valueFrom': {'secretKeyRef': {'name': resource_name, 'key': 'latest'}},
        }
    ]
    output = _read_workflow_outputs()
    assert resource_name not in output
    assert 'screen_vector_stripe_secret' not in output
    assert fixture_credential not in output + state_path.read_text()
    assert capsys.readouterr() == ('', '')


# Ops keys the lead re-set by hand after every Cloud Run train until the prod overlay carried them.
_TRAIN_DRIFT_KEYS = {
    'backend': ('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED',),
    'backend-sync': ('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'SUMMARY_DEBT_REPAIR_ENABLED'),
    'backend-sync-backfill': ('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED',),
    'backend-integration': ('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED'),
}


def _set_workflow_bound_env(monkeypatch, env_config):
    for workload in (
        *(env_config['cloud_run'].get('services') or {}).values(),
        *(env_config['cloud_run'].get('jobs') or {}).values(),
    ):
        for raw_entry in (workload.get('env') or {}).values():
            if isinstance(raw_entry, dict) and isinstance(raw_entry.get('env_var'), str):
                monkeypatch.setenv(raw_entry['env_var'], str(raw_entry.get('default') or 'rendered-value'))


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_every_manifest_env_key_renders_for_every_cloud_run_workload(env, monkeypatch):
    env_config = _MANIFEST['environments'][env]
    _set_workflow_bound_env(monkeypatch, env_config)
    for kind in ('services', 'jobs'):
        for name, config in (env_config['cloud_run'].get(kind) or {}).items():
            rendered = _MODULE['_render_env_vars'](config.get('env', {}))
            if kind == 'services':
                removed = _MODULE['_action_removed_env_names'](name) | set(config.get('forbidden_env', []))
            else:
                removed = _MODULE['_job_removed_env_names'](config)
            _MODULE['assert_manifest_env_renders'](f'{kind} {name}', config, rendered, removed)
            assert len(_MODULE['_parse_deploy_cloud_run_env_vars'](rendered)) == len(config.get('env', {}))


def test_train_drift_keys_render_on_their_prod_services(monkeypatch):
    env_config = _MANIFEST['environments']['prod']
    _set_workflow_bound_env(monkeypatch, env_config)
    for service, keys in _TRAIN_DRIFT_KEYS.items():
        services = env_config['cloud_run']['services']
        names = {
            name
            for name, _ in _MODULE['_parse_deploy_cloud_run_env_vars'](
                _MODULE['_render_env_vars'](services[service]['env'])
            )
        }
        assert set(keys) <= names, service


def test_render_assertion_round_trips_deploy_cloudrun_escapes():
    config = {
        'env': {
            'LIST': {'value': 'modulate-velma-2,parakeet'},
            'PATH_LIKE': {'value': r'C:\models'},
            'MULTILINE': {'value': 'first\nsecond'},
            'EMPTY': {'value': ''},
        }
    }
    rendered = _MODULE['_render_env_vars'](config['env'])
    assert _MODULE['_parse_deploy_cloud_run_env_vars'](rendered) == [
        ('LIST', 'modulate-velma-2,parakeet'),
        ('PATH_LIKE', r'C:\models'),
        ('MULTILINE', 'first\nsecond'),
        ('EMPTY', ''),
    ]
    _MODULE['assert_manifest_env_renders']('service fixture', config, rendered, set())


def test_render_assertion_fails_when_a_manifest_key_does_not_land():
    config = {'env': {'KEEP': {'value': 'true'}, 'OPS_KEY': {'value': 'true'}}}
    with pytest.raises(ValueError, match='missing from the rendered env: OPS_KEY'):
        _MODULE['assert_manifest_env_renders']('service fixture', config, 'KEEP=true', set())
    with pytest.raises(ValueError, match='rendered value differs from the manifest: OPS_KEY'):
        _MODULE['assert_manifest_env_renders']('service fixture', config, 'KEEP=true\nOPS_KEY=false', set())
    with pytest.raises(ValueError, match='rendered more than once: KEEP'):
        _MODULE['assert_manifest_env_renders']('service fixture', config, 'KEEP=true\nOPS_KEY=true\nKEEP=true', set())
    with pytest.raises(ValueError, match='not in the manifest: STRAY'):
        _MODULE['assert_manifest_env_renders']('service fixture', config, 'KEEP=true\nOPS_KEY=true\nSTRAY=1', set())


def test_render_assertion_fails_when_the_deploy_also_removes_a_manifest_key():
    retired = _MODULE['RETIRED_ENV_NAMES'][0]
    config = {'env': {retired: {'value': 'true'}}}
    rendered = _MODULE['_render_env_vars'](config['env'])
    with pytest.raises(ValueError, match=f'also removed by the deploy: {retired}'):
        _MODULE['assert_manifest_env_renders'](
            'service backend', config, rendered, _MODULE['_action_removed_env_names']('backend')
        )


def test_job_removal_set_includes_its_rendered_remove_env_vars_flag():
    job = {
        'flags': {'--remove-env-vars': 'HOSTED_PUSHER_API_URL,MEMORY_MODE', '--task-timeout': '900s'},
        'forbidden_env': ['OLD_KEY'],
        'env': {'MEMORY_MODE': {'value': 'off'}},
    }
    assert _MODULE['_job_removed_env_names'](job) == {'HOSTED_PUSHER_API_URL', 'MEMORY_MODE', 'OLD_KEY'}
    with pytest.raises(ValueError, match='also removed by the deploy: MEMORY_MODE'):
        _MODULE['assert_manifest_env_renders'](
            'job fixture', job, _MODULE['_render_env_vars'](job['env']), _MODULE['_job_removed_env_names'](job)
        )


def test_render_assertion_allows_the_documented_provisional_omission(monkeypatch):
    monkeypatch.delenv('OMI_LLM_GATEWAY_URL', raising=False)
    config = {'env': {'OMI_LLM_GATEWAY_URL': {'env_var': 'OMI_LLM_GATEWAY_URL', 'provisional': True}}}
    _MODULE['assert_manifest_env_renders']('service fixture', config, _MODULE['_render_env_vars'](config['env']), set())


def test_full_render_refuses_to_emit_when_a_service_key_would_be_removed(monkeypatch):
    manifest = deepcopy(_MANIFEST)
    backend = manifest['environments']['prod']['cloud_run']['services']['backend']
    backend['env'][_MODULE['RETIRED_ENV_NAMES'][0]] = {'value': 'true'}
    monkeypatch.setitem(_MODULE['main'].__globals__, '_load_yaml', lambda _path: manifest)
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    _set_workflow_bound_env(monkeypatch, manifest['environments']['prod'])
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    with pytest.raises(ValueError, match='Cloud Run service backend env does not render every manifest key'):
        _MODULE['main']()
    assert _read_workflow_outputs() == ''

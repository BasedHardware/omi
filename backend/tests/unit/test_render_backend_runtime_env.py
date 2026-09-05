"""Renderer for backend Cloud Run runtime env."""

import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render_backend_runtime_env.py'
_MODULE = runpy.run_path(str(_SCRIPT), run_name='render_backend_runtime_env')
_MANIFEST = _MODULE['_load_yaml'](_MODULE['DEFAULT_MANIFEST'])


@pytest.fixture(autouse=True)
def _reuse_parsed_repo_manifest(monkeypatch):
    monkeypatch.setitem(_MODULE, '_load_yaml', lambda _path: _MANIFEST)
    # Full-state renderer tests need deploy-time values for every declared job.
    for env_config in _MANIFEST['environments'].values():
        for job in (env_config.get('cloud_run', {}).get('jobs') or {}).values():
            for raw_entry in (job.get('env') or {}).values():
                if isinstance(raw_entry, dict) and isinstance(raw_entry.get('env_var'), str):
                    monkeypatch.setenv(raw_entry['env_var'], str(raw_entry.get('default', 'rendered-value')))


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


def test_state_output_preserves_yaml_boolean_like_strings(tmp_path, capsys, monkeypatch):
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
    output = capsys.readouterr().out
    assert 'FEATURE_OFF=off' in output
    assert 'FEATURE_ON=on' in output


def test_network_flags_still_required(monkeypatch):
    monkeypatch.delenv('CLOUD_RUN_VPC_NETWORK', raising=False)
    with pytest.raises(ValueError, match='requires'):
        _MODULE['_render_flags']({'--network': {'env_var': 'CLOUD_RUN_VPC_NETWORK'}})


def test_selected_job_renders_only_shared_network_and_named_job_outputs(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-dev-subnet-1')
    monkeypatch.setattr(
        'sys.argv',
        ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'memory-maintenance-job'],
    )

    assert _MODULE['main']() == 0

    output = capsys.readouterr().out
    assert 'cloud_run_flags<<' in output
    assert 'memory_maintenance_job_flags<<' in output
    assert 'memory_maintenance_job_env_vars<<' in output
    assert 'backend_env_vars<<' not in output
    assert 'notifications_job_env_vars<<' not in output


def test_selected_job_rejects_unknown_name_without_emitting_partial_output(capsys, monkeypatch):
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'unknown-job'])

    with pytest.raises(ValueError, match='unknown Cloud Run job'):
        _MODULE['main']()

    assert capsys.readouterr().out == ''


def test_render_dev_emits_memory_maintenance_job_outputs():
    jobs = _MANIFEST['environments']['dev']['cloud_run']['jobs']
    memory_job = jobs['memory-maintenance-job']
    memory_env = _MODULE['_render_env_vars'](memory_job['env'])
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED=true' in memory_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_FLEX=true' in memory_env
    assert 'MEMORY_CANONICAL_CONSOLIDATION_ENABLED=true' in memory_env
    assert 'OMI_BACKGROUND_FLEX_CAPABLE=true' in memory_env
    assert 'MEMORY_ENABLED_USERS' not in memory_env
    assert 'MEMORY_ENABLED=on' in memory_env
    assert 'MEMORY_MODE=' not in memory_env
    assert 'MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED=false' in memory_env
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


def test_render_dev_emits_x_connector_sync_job_outputs(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-dev-subnet-1')
    monkeypatch.setenv('X_OAUTH_CLIENT_ID', 'x-client-id')
    monkeypatch.setenv('X_OAUTH_REDIRECT_URI', 'https://api.example/v1/x/callback')
    monkeypatch.setenv('RAPID_API_HOST', 'twitter-api.example')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'x-connector-sync-job'])

    assert _MODULE['main']() == 0
    output = capsys.readouterr().out
    assert 'X_OAUTH_CLIENT_ID=x-client-id' in output
    assert 'X_OAUTH_REDIRECT_URI=https://api.example/v1/x/callback' in output
    assert 'RAPID_API_HOST=twitter-api.example' in output
    assert 'X_OAUTH_CLIENT_SECRET=X_OAUTH_CLIENT_SECRET:latest' in output
    assert 'RAPID_API_KEY=RAPID_API_KEY:latest' in output
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
def test_memory_maintenance_runtime_has_no_daily_sweep_or_posthog_bindings(env):
    jobs = _MANIFEST['environments'][env]['cloud_run']['jobs']
    maintenance = jobs['memory-maintenance-job']
    daily = jobs['daily-memory-sweep-job']
    daily_names = {
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
        'POSTHOG_HOST',
    }
    assert daily_names.isdisjoint(maintenance.get('env', {}))
    assert maintenance.get('secrets', {}).get('POSTHOG_PROJECT_API_KEY') == {
        'secret': 'POSTHOG_PROJECT_API_KEY',
        'version': 'latest',
    }
    assert {
        'MEMORY_DAILY_MEMORY_SWEEP_ENABLED',
        'MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED',
    } <= set(daily.get('env', {}))
    assert 'POSTHOG_PROJECT_API_KEY' in daily.get('secrets', {})


def test_memory_maintenance_entrypoint_does_not_invoke_daily_sweep_job():
    entrypoint = (_SCRIPT.parents[1] / 'modal' / 'memory_maintenance_job.py').read_text(encoding='utf-8')
    dockerfile = (_SCRIPT.parents[1] / 'modal' / 'Dockerfile.memory_maintenance_job').read_text(encoding='utf-8')
    assert 'daily_memory_sweep' not in entrypoint
    assert 'daily_memory_sweep_job.py' not in dockerfile
    assert 'memory_maintenance_job.py' in dockerfile


def test_dev_runtime_manifest_contains_no_removed_first_user_or_capture_admission():
    dev = deepcopy(_MANIFEST['environments']['dev'])
    # The dev-only ledger drain has an explicit operational fence for the two
    # owner test accounts. Product/runtime surfaces must still contain no
    # first-user or capture admission lists.
    dev['cloud_run']['jobs'].pop('knowledge-ledger-drain-job', None)
    serialized = json.dumps(dev, sort_keys=True)
    assert 'vi7SA9ckQCe4ccobWNxlbdcNdC23' not in serialized

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
        'PINECONE_INDEX_NAME',
        'OMI_BACKGROUND_FLEX_CAPABLE',
        'OMI_LLM_GATEWAY_URL',
        'X_OAUTH_CLIENT_ID',
        'X_OAUTH_REDIRECT_URI',
        'RAPID_API_HOST',
    }
    assert forbidden_notifications_vars.isdisjoint(notifications_env)
    assert set(notifications_job['secrets']) == {
        'SERVICE_ACCOUNT_JSON',
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
    }

    x_sync_job = cloud_run['jobs']['x-connector-sync-job']
    x_sync_env = x_sync_job['env']
    assert x_sync_env['PINECONE_INDEX_NAME']['value'] == 'memories-backend-dev'
    assert x_sync_env['OMI_BACKGROUND_FLEX_CAPABLE']['value'] == 'true'
    assert x_sync_env['OMI_LLM_GATEWAY_URL']['env_var'] == 'OMI_LLM_GATEWAY_URL'
    assert set(x_sync_job['secrets']) >= {
        'SERVICE_ACCOUNT_JSON',
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
        'OMI_LLM_GATEWAY_SERVICE_TOKEN',
        'X_OAUTH_CLIENT_SECRET',
        'RAPID_API_KEY',
    }


def test_x_connector_deploy_uses_verified_gateway_endpoint_and_vpc_flags():
    workflow = (_SCRIPT.parents[2] / '.github/workflows/gcp_x_connector_sync_job.yml').read_text(encoding='utf-8')

    assert 'Verify LLM Gateway serving data plane' in workflow
    assert 'OMI_LLM_GATEWAY_URL: ${{ steps.gateway-serving.outputs.gateway_url }}' in workflow
    assert '${{ steps.runtime-env.outputs.cloud_run_flags }}' in workflow
    assert '--lane omi:auto:x-memory-extraction-flex' in workflow


def test_render_prod_emits_memory_maintenance_job_cron_on(capsys, monkeypatch):
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
    out = capsys.readouterr().out
    job_env = _job_env_block(out, 'memory_maintenance_job')
    # Prod GO 2026-08-15: the maintenance job follows the request-path product
    # flag. ST→LT cron is job-hosted on both env overlays with Flex.
    assert 'MEMORY_ENABLED=on' in job_env
    assert 'MEMORY_MODE=' not in job_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED=true' in job_env
    assert 'MEMORY_CANONICAL_MAINTENANCE_FLEX=true' in job_env
    assert 'OMI_BACKGROUND_FLEX_CAPABLE=true' in job_env
    assert 'MEMORY_ENABLED_USERS' not in job_env
    prod_memory_job = _MANIFEST['environments']['prod']['cloud_run']['jobs']['memory-maintenance-job']
    assert '--task-timeout=3600s' in _MODULE['_render_flags'](prod_memory_job['flags'])

    assert 'DESKTOP_PREVIEW_PUBLISH_KEY=DESKTOP_PREVIEW_PUBLISH_KEY:latest' in _job_secret_lines(out, 'backend')
    assert 'GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY:latest' in _job_secret_lines(out, 'backend_sync')

    notifications_env = _job_env_block(out, 'notifications_job')
    assert 'MEMORY_CANONICAL_MAINTENANCE_ENABLED' not in notifications_env


def test_render_prod_gateway_callers_inject_verified_endpoint(capsys, monkeypatch):
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
    output = capsys.readouterr().out

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
    assert "id-token: 'write'" not in text
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
    # here only; do not copy onto backend / backend-sync.
    integration_flags = _deploy_backend_stack_step_flags('deploy-backend-integration')
    backend_flags = _deploy_backend_stack_step_flags('deploy-backend')
    sync_flags = _deploy_backend_stack_step_flags('deploy-backend-sync')
    for flag in (
        '--cpu=2',
        '--memory=2Gi',
        '--concurrency=40',
        '--min-instances=3',
        '--max-instances=50',
        '--no-cpu-throttling',
    ):
        assert flag in integration_flags, flag
        assert flag not in backend_flags, flag
        assert flag not in sync_flags, flag


VERTEX_PT_CONTRACT = 'Vertex PT: 5 GSU gemini-2.5-flash us-central1, expires ~2027-05-28'


@pytest.mark.parametrize(
    ('env', 'project'),
    [
        ('dev', 'based-hardware-dev'),
        ('prod', 'based-hardware'),
    ],
)
def test_desktop_backend_compose_pins_vertex_pt(env, project):
    desktop = _MANIFEST['environments'][env]['desktop_backend']
    rendered = _MODULE['_render_env_vars'](desktop['env'])
    assert 'USE_VERTEX_AI=true' in rendered, VERTEX_PT_CONTRACT
    assert f'GOOGLE_CLOUD_PROJECT={project}' in rendered, VERTEX_PT_CONTRACT
    assert 'GCP_LOCATION=us-central1' in rendered, VERTEX_PT_CONTRACT
    assert 'PROMETHEUS_SIDECAR_PORT=9090' in rendered
    assert _MODULE['_render_secrets'](desktop['secrets']) == (
        'METRICS_SECRET=METRICS_SECRET:latest\nPOSTHOG_PROJECT_API_KEY=POSTHOG_PROJECT_API_KEY:latest'
    )
    docs = Path(__file__).resolve().parents[2] / 'docs' / 'vertex-pt-flash.md'
    assert VERTEX_PT_CONTRACT.split(',')[0] in docs.read_text(encoding='utf-8')


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
        if value == literal_project:
            # Supplied to the workflow as ${{ vars.GCP_PROJECT_ID }}.
            assert f'{name}=${{{{ vars.GCP_PROJECT_ID }}}}' in workflow, name
            continue
        assert f'{name}={value}' in workflow, f'{env_name}: {name}={value} is not what the workflow deploys'

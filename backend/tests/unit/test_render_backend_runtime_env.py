"""Renderer for backend Cloud Run runtime env."""

import json
import runpy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render_backend_runtime_env.py'
_MODULE = runpy.run_path(str(_SCRIPT), run_name='render_backend_runtime_env')
_MANIFEST = _MODULE['_load_yaml'](_MODULE['DEFAULT_MANIFEST'])


@pytest.fixture(autouse=True)
def _reuse_parsed_repo_manifest(monkeypatch):
    monkeypatch.setitem(_MODULE, '_load_yaml', lambda _path: _MANIFEST)


def _job_env_block(out: str, job_prefix: str) -> str:
    start = out.index(f'{job_prefix}_env_vars<<')
    end = out.index(f'{job_prefix}_secrets<<')
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


def test_dev_runtime_manifest_contains_no_removed_first_user_or_capture_admission():
    serialized = json.dumps(_MANIFEST['environments']['dev'], sort_keys=True)
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
    }
    assert forbidden_notifications_vars.isdisjoint(notifications_env)
    assert notifications_env['PINECONE_INDEX_NAME']['value'] == 'memories-backend-dev'
    assert notifications_env['OMI_BACKGROUND_FLEX_CAPABLE']['value'] == 'true'
    assert notifications_env['OMI_LLM_GATEWAY_URL']['env_var'] == 'OMI_LLM_GATEWAY_URL'
    assert set(notifications_job['secrets']) == {
        'SERVICE_ACCOUNT_JSON',
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
        'OMI_LLM_GATEWAY_SERVICE_TOKEN',
    }


def test_notifications_deploy_uses_verified_gateway_endpoint_and_vpc_flags():
    workflow = (_SCRIPT.parents[2] / '.github/workflows/gcp_notifications_job.yml').read_text(encoding='utf-8')

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
    docs = Path(__file__).resolve().parents[2] / 'docs' / 'vertex-pt-flash.md'
    assert VERTEX_PT_CONTRACT.split(',')[0] in docs.read_text(encoding='utf-8')

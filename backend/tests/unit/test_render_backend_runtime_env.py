"""Renderer for backend Cloud Run runtime env."""

import runpy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render_backend_runtime_env.py'
_MODULE = runpy.run_path(str(_SCRIPT), run_name='render_backend_runtime_env')


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


def _write_job_scope_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / 'runtime_env.yaml'
    manifest.write_text(
        '''\
environments:
  dev:
    cloud_run:
      network:
        flags:
          --network:
            value: test-network
      services:
        backend:
          env:
            GOOGLE_CLIENT_ID:
              env_var: GOOGLE_CLIENT_ID
          secrets: {}
      jobs:
        memory-maintenance-job:
          env:
            JOB_MODE:
              value: maintenance
          secrets: {}
        notifications-job:
          env: {}
          secrets: {}
''',
        encoding='utf-8',
    )
    return manifest


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


def test_network_flags_still_required(monkeypatch):
    monkeypatch.delenv('CLOUD_RUN_VPC_NETWORK', raising=False)
    with pytest.raises(ValueError, match='requires'):
        _MODULE['_render_flags']({'--network': {'env_var': 'CLOUD_RUN_VPC_NETWORK'}})


def test_selected_job_ignores_unrelated_service_env(capsys, monkeypatch, tmp_path):
    manifest = _write_job_scope_manifest(tmp_path)
    monkeypatch.delenv('GOOGLE_CLIENT_ID', raising=False)
    monkeypatch.setattr(
        'sys.argv',
        [
            'render_backend_runtime_env.py',
            '--env',
            'dev',
            '--job',
            'memory-maintenance-job',
            '--manifest',
            str(manifest),
        ],
    )

    assert _MODULE['main']() == 0
    out = capsys.readouterr().out
    assert 'cloud_run_flags<<' in out
    assert 'memory_maintenance_job_env_vars<<' in out
    assert 'backend_env_vars<<' not in out
    assert 'notifications_job_env_vars<<' not in out


def test_unknown_selected_job_fails_before_outputs(capsys, monkeypatch, tmp_path):
    manifest = _write_job_scope_manifest(tmp_path)
    monkeypatch.setattr(
        'sys.argv',
        ['render_backend_runtime_env.py', '--env', 'dev', '--job', 'missing-job', '--manifest', str(manifest)],
    )

    with pytest.raises(ValueError, match='Cloud Run job missing-job is not defined for dev'):
        _MODULE['main']()
    assert capsys.readouterr().out == ''


def test_render_dev_emits_memory_maintenance_job_outputs(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-us-central1-dev-vpc-1-subnet-1')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'fake-google-client-id')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_ID', 'fake-claude-client-id')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_NAME', 'Claude')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_REDIRECT_URIS', 'https://claude.example/callback')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://172.16.63.232')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev'])
    rc = _MODULE['main']()
    assert rc == 0
    out = capsys.readouterr().out

    memory_env = _job_env_block(out, 'memory_maintenance_job')
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true' in memory_env
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=true' in memory_env
    assert 'MEMORY_CANONICAL_CONSOLIDATION_ENABLED=true' in memory_env
    assert 'MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23' in memory_env
    assert 'MEMORY_MODE=read' in memory_env
    assert 'TYPESENSE_HOST_PORT=443' in memory_env

    flags_marker = '__BACKEND_RUNTIME_ENV_memory_maintenance_job_flags__'
    flags_start = out.index(f'memory_maintenance_job_flags<<{flags_marker}')
    flags_body_start = out.index('\n', flags_start) + 1
    flags_body_end = out.index(flags_marker, flags_body_start)
    assert out[flags_body_start:flags_body_end].strip() == '--task-timeout=3600s --cpu=2 --memory=2Gi'

    assert 'memory_maintenance_job_secrets<<' in out
    assert 'OPENAI_API_KEY=OPENAI_API_KEY:latest' in out
    assert 'PINECONE_API_KEY=PINECONE_API_KEY:latest' in out
    assert 'TYPESENSE_API_KEY=TYPESENSE_API_KEY:latest' in out

    notifications_env = _job_env_block(out, 'notifications_job')
    forbidden_notifications_vars = {
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
    assert all(f'{name}=' not in notifications_env for name in forbidden_notifications_vars)
    assert 'PINECONE_INDEX_NAME=memories-backend-dev' in notifications_env
    assert _job_secret_lines(out, 'notifications_job') == {
        'SERVICE_ACCOUNT_JSON=SERVICE_ACCOUNT_JSON:latest',
        'ENCRYPTION_SECRET=ENCRYPTION_SECRET:latest',
        'OPENAI_API_KEY=OPENAI_API_KEY:latest',
        'PINECONE_API_KEY=PINECONE_API_KEY:latest',
    }
    secret_names_marker = '__BACKEND_RUNTIME_ENV_notifications_job_secret_names__'
    names_start = out.index(f'notifications_job_secret_names<<{secret_names_marker}')
    names_body_start = out.index('\n', names_start) + 1
    names_body_end = out.index(secret_names_marker, names_body_start)
    assert set(out[names_body_start:names_body_end].strip().split(',')) == {
        'SERVICE_ACCOUNT_JSON',
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
    }


def test_render_prod_keeps_memory_maintenance_job_promotion_off(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'fake-google-client-id')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_ID', 'fake-claude-client-id')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_CLIENT_NAME', 'Claude')
    monkeypatch.setenv('MCP_OAUTH_CLAUDE_REDIRECT_URIS', 'https://claude.example/callback')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    rc = _MODULE['main']()
    assert rc == 0
    out = capsys.readouterr().out
    job_env = _job_env_block(out, 'memory_maintenance_job')
    assert 'MEMORY_MODE=off' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=false' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=false' in job_env
    assert 'MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23' not in job_env

    assert 'DESKTOP_PREVIEW_PUBLISH_KEY=DESKTOP_PREVIEW_PUBLISH_KEY:latest' in _job_secret_lines(out, 'backend')

    notifications_env = _job_env_block(out, 'notifications_job')
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED' not in notifications_env


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
    assert 'render_backend_runtime_env.py --env ${{ vars.ENV }} --job notifications-job' in text
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text
    assert 'env_vars_update_strategy: overwrite' not in text
    assert 'secrets_update_strategy: overwrite' not in text
    assert (
        '--remove-env-vars=MEMORY_MODE,MEMORY_ENABLED_USERS,MEMORY_V3_GET_ENABLED,'
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED,MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED,'
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED,MEMORY_TYPESENSE_COLLECTION,TYPESENSE_HOST,'
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
    assert 'render_backend_runtime_env.py --env ${{ vars.ENV }} --job memory-maintenance-job' in text
    assert (
        'flags: ${{ steps.runtime-env.outputs.cloud_run_flags }} '
        '${{ steps.runtime-env.outputs.memory_maintenance_job_flags }}'
    ) in text
    assert "id-token: 'write'" not in text
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text

    auto_dev_workflow = (
        Path(__file__).resolve().parents[3] / '.github/workflows/gcp_memory_maintenance_job_auto_dev.yml'
    )
    auto_dev_text = auto_dev_workflow.read_text(encoding='utf-8')
    assert 'render_backend_runtime_env.py --env dev --job memory-maintenance-job' in auto_dev_text

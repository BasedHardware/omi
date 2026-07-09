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


def test_render_dev_emits_memory_maintenance_job_outputs(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-us-central1-dev-vpc-1-subnet-1')
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

    assert 'memory_maintenance_job_secrets<<' in out
    assert 'OPENAI_API_KEY=OPENAI_API_KEY:latest' in out
    assert 'PINECONE_API_KEY=PINECONE_API_KEY:latest' in out
    assert 'TYPESENSE_API_KEY=TYPESENSE_API_KEY:latest' in out

    notifications_env = _job_env_block(out, 'notifications_job')
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED' not in notifications_env
    assert 'MEMORY_MODE' not in notifications_env
    assert 'PINECONE_INDEX_NAME=memories-backend-dev' in notifications_env
    assert 'PINECONE_API_KEY=PINECONE_API_KEY:latest' in out


def test_render_prod_keeps_memory_maintenance_job_promotion_off(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    rc = _MODULE['main']()
    assert rc == 0
    out = capsys.readouterr().out
    job_env = _job_env_block(out, 'memory_maintenance_job')
    assert 'MEMORY_MODE=off' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=false' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=false' in job_env
    assert 'MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23' not in job_env

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
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text


def test_memory_maintenance_job_workflow_passes_vpc_vars_and_checkout_sha():
    workflow = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_memory_maintenance_job.yml'
    text = workflow.read_text(encoding='utf-8')
    assert 'SERVICE: memory-maintenance-job' in text
    assert 'Dockerfile.memory_maintenance_job' in text
    assert 'memory_maintenance_job_env_vars' in text
    assert 'memory_maintenance_job_secrets' in text
    assert 'CLOUD_RUN_VPC_NETWORK: ${{ vars.CLOUD_RUN_VPC_NETWORK }}' in text
    assert 'CLOUD_RUN_VPC_SUBNET: ${{ vars.CLOUD_RUN_VPC_SUBNET }}' in text
    assert 'flags: ${{ steps.runtime-env.outputs.cloud_run_flags }}' in text
    assert "id-token: 'write'" not in text
    assert 'git rev-parse --short=7 HEAD' in text
    assert 'short_sha=${GITHUB_SHA::7}' not in text

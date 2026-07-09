"""Renderer for backend Cloud Run runtime env."""

import runpy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render_backend_runtime_env.py'
_MODULE = runpy.run_path(str(_SCRIPT), run_name='render_backend_runtime_env')


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


def test_render_dev_emits_notifications_job_outputs(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-dev-vpc-1')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-us-central1-dev-vpc-1-subnet-1')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://172.16.63.232')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'dev'])
    rc = _MODULE['main']()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'notifications_job_env_vars<<' in out
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true' in out
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=true' in out
    assert 'MEMORY_CANONICAL_CONSOLIDATION_ENABLED=true' in out
    assert 'MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23' in out
    assert 'notifications_job_secrets<<' in out
    assert 'OPENAI_API_KEY=OPENAI_API_KEY:latest' in out
    assert 'PINECONE_API_KEY=PINECONE_API_KEY:latest' in out
    assert 'TYPESENSE_API_KEY=TYPESENSE_API_KEY:latest' in out


def test_render_prod_keeps_notifications_job_promotion_off(capsys, monkeypatch):
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'omi-prod-vpc')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'omi-prod-subnet')
    monkeypatch.setattr('sys.argv', ['render_backend_runtime_env.py', '--env', 'prod'])
    rc = _MODULE['main']()
    assert rc == 0
    out = capsys.readouterr().out
    # Isolate the notifications-job env block
    start = out.index('notifications_job_env_vars<<')
    end = out.index('notifications_job_secrets<<')
    job_env = out[start:end]
    assert 'MEMORY_MODE=off' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=false' in job_env
    assert 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=false' in job_env
    assert 'MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23' not in job_env

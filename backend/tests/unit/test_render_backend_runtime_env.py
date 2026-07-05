"""Renderer for backend Cloud Run runtime env."""

import runpy
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'render-backend-runtime-env.py'
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

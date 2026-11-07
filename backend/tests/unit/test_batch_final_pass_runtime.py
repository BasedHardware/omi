"""Every production final-pass host must have an effective rollback binding."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.runtime_env_capability_contracts import (
    BATCH_FINAL_PASS_FLAG as FLAG,
    BATCH_FINAL_PASS_HOSTS as HOSTS,
    validate_batch_final_pass_hosts,
)
from scripts.runtime_env_validation import manifest as validator
from tests.unit.test_backend_runtime_env_validator import render_cloud_run_state

ROOT = Path(__file__).resolve().parents[3]
HOSTED_URL = 'HOSTED_DIARIZATION_API_URL'


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(yaml, 'safe_load', lambda stream: yaml.load(stream, Loader=yaml.CSafeLoader))
    return yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())['environments']['prod']


def test_all_production_pass_hosts_have_explicit_consistent_switch(config, monkeypatch):
    assert len(HOSTS) == 6
    assert validate_batch_final_pass_hosts('prod', config) == []
    assert not [error for error in validator._validate_gke(config, strict_provisional=False) if FLAG in error.message]
    state = render_cloud_run_state(config, monkeypatch)
    for platform, name in HOSTS:
        if platform == 'cloud_run':
            env = {entry['name']: entry.get('value') for entry in state['services'][name]['env']}
            assert env[FLAG] == 'true'


@pytest.mark.parametrize('platform,name', HOSTS)
def test_missing_flag_cannot_make_runtime_disappear_from_admission(config, platform, name):
    hosts = config['gke'] if platform == 'gke' else config['cloud_run']['services']
    del hosts[name]['env'][FLAG]
    assert validate_batch_final_pass_hosts('prod', config)


def test_full_rollback_is_valid_but_partial_rollback_is_rejected(config):
    config['gke']['config_map']['entries'][FLAG]['value'] = 'false'
    assert validate_batch_final_pass_hosts('prod', config)
    for platform, name in HOSTS:
        if platform == 'cloud_run':
            config['cloud_run']['services'][name]['env'][FLAG]['value'] = 'false'
    assert validate_batch_final_pass_hosts('prod', config) == []


@pytest.mark.parametrize('value', ['', 'flase', True, None])
def test_rollback_literal_is_unambiguous(config, value):
    config['gke']['config_map']['entries'][FLAG]['value'] = value
    assert validate_batch_final_pass_hosts('prod', config)


@pytest.mark.parametrize('host', ['pusher', 'backend-listen'])
def test_literal_chart_override_cannot_defeat_shared_configmap(config, monkeypatch, host):
    load = validator._load_yaml
    values_file = config['gke'][host]['values_file']

    def wrong(path):
        data = deepcopy(load(path))
        if str(path).endswith(values_file):
            data['env'] = [e for e in data['env'] if e['name'] != FLAG] + [{'name': FLAG, 'value': 'true'}]
        return data

    monkeypatch.setattr(validator, '_load_yaml', wrong)
    assert any(FLAG in error.message for error in validator._validate_gke(config, strict_provisional=False))


def test_host_without_diarizer_url_can_be_switched_off_alone(config):
    # backend-integration has no HOSTED_DIARIZATION_API_URL: its pass can only fall back.
    assert HOSTED_URL not in config['cloud_run']['services']['backend-integration']['env']
    config['cloud_run']['services']['backend-integration']['env'][FLAG]['value'] = 'false'
    assert validate_batch_final_pass_hosts('prod', config) == []


def test_host_with_diarizer_url_cannot_be_switched_off_alone(config):
    assert HOSTED_URL in config['cloud_run']['services']['backend']['env']
    config['cloud_run']['services']['backend']['env'][FLAG]['value'] = 'false'
    errors = validate_batch_final_pass_hosts('prod', config)
    assert any('cloud_run/backend' == error.scope and FLAG in error.message for error in errors)


def test_shared_configmap_off_is_rejected_while_pusher_has_the_diarizer_url(config):
    config['gke']['config_map']['entries'][FLAG]['value'] = 'false'
    errors = validate_batch_final_pass_hosts('prod', config)
    assert any(error.scope == 'gke/pusher' for error in errors)

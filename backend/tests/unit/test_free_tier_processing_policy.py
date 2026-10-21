"""At-cap summaries ship on and no longer consult basic-plan/cohort policy."""

import pytest
from utils.free_tier_processing_policy import client_summaries_at_cap_enabled


@pytest.mark.parametrize('value,expected', [(None, True), ('true', True), ('false', False), ('0', True), ('', True)])
def test_summary_kill_switch_is_default_on(monkeypatch, value, expected):
    monkeypatch.delenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', raising=False)
    if value is not None:
        monkeypatch.setenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', value)
    assert client_summaries_at_cap_enabled() is expected


@pytest.mark.parametrize('value', ['true', 'false', 'pct:0', 'invalid'])
def test_retired_environment_cannot_control_summary_acceptance(monkeypatch, value):
    monkeypatch.delenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', raising=False)
    for key in (
        'FREE_TIER_LOCAL_PROCESSING',
        'FREE_TIER_LOCAL_PROCESSING_COHORT',
        'BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED',
        'BASIC_PLAN_GATE_PROXY_EMBED_ENABLED',
    ):
        monkeypatch.setenv(key, value)
    assert client_summaries_at_cap_enabled()


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_summary_acceptance_is_default_on_on_every_finalization_host(environment):
    from pathlib import Path
    import yaml

    manifest = yaml.load(
        (Path(__file__).resolve().parents[2] / 'deploy/runtime_env.yaml').read_text(),
        Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader),
    )
    config = manifest['environments'][environment]
    hosts = [
        config['gke']['backend-listen'],
        config['gke']['pusher'],
        *config['cloud_run']['services'].values(),
        config['desktop_backend'],
    ]
    for host in hosts:
        assert host['env']['CLIENT_SUMMARIES_AT_CAP_ENABLED']['value'] == 'true'
        assert 'FREE_TIER_EMERGENCY_STOP' not in host['env']

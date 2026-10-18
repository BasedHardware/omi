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

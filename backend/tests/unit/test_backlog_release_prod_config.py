"""The composed prod manifest opens the backlog authority only where the runbook allows it.

A malformed value would make the heartbeat authority stop fail-closed at deploy time, so the
gate would silently never open; pin the prod values through the real parser instead.
"""

import os
from pathlib import Path

import pytest
import yaml

from config.batch_pipeline_backlog_release import PREFIX, WriterConfig
from config.process_role import ProcessRoleConfigError, startup_process_role
from scripts.cloud_run_scope import PROJECTION_PUMP

ROOT = Path(__file__).resolve().parents[3]
LEGACY = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'
# One-way owner_key() digests of the support owners held on the provider backlog: four approved
# 2026-11-18, three more approved 2026-11-20 (never raw identifiers).
APPROVED_OWNER_KEYS = frozenset(
    {
        '70a8958da857b008477b9ab8ba52205bf5d4f7f61b4ed18d1e48b70344a3e80d',
        'c68953b9fdbdcd5528b856fd4d50097e14c6b5eb4f48968115783ade222e59b1',
        'cbf55865bc7f785d18a634a4615a21f052bbea40f4b9d5e726dec3dcbae40c26',
        'f5d5e95afa2e18b4073f43099f4499f99326a2d3f2c50219dfa26013060cb177',
        '30a9aadced4e2bc0aec94b34ebd9c4563f37e64b84399557fd24a0377dd8e223',
        'aac672257a5b347976517c0d65483bc11538a6c75cf3d16523cf6a4f884bf5e1',
        'cc49ba0944135998f50e3a8c1655ff8ce39ed6e6177e0fa2d9a5b7a83af99d87',
    }
)


def _manifest():
    return yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)


def _value(entry):
    return str(entry['value'] if isinstance(entry, dict) else entry)


def _walk_env_keys(node, found):
    if isinstance(node, dict):
        for key, child in node.items():
            # Cloud Run maps keys by name; Helm values list {name, value} rows.
            name = child if key == 'name' else key
            if isinstance(name, str) and (name.startswith(PREFIX) or name == LEGACY):
                found.add(name)
            _walk_env_keys(child, found)
    elif isinstance(node, list):
        for child in node:
            _walk_env_keys(child, found)


def test_prod_backend_integration_parses_as_the_approved_allowlist_authority(monkeypatch):
    env = _manifest()['environments']['prod']['cloud_run']['services']['backend-integration']['env']
    keys = {key: _value(entry) for key, entry in env.items() if key.startswith(PREFIX)}
    for key in list(os.environ):
        if key.startswith(PREFIX):
            monkeypatch.delenv(key)
    for key, value in keys.items():
        monkeypatch.setenv(key, value)

    config = WriterConfig.from_env()

    assert config.enabled is True
    assert config.state == 'open'
    assert config.rate_per_hour == 60
    assert config.reach_seconds == 0
    assert config.mode == 'allowlist_only'
    assert set(config.owner_keys) == APPROVED_OWNER_KEYS
    assert len(config.owner_keys) == len(APPROVED_OWNER_KEYS)
    assert LEGACY not in env


def test_no_other_prod_host_or_chart_sets_backlog_authority_keys():
    prod = _manifest()['environments']['prod']
    integration = prod['cloud_run']['services']['backend-integration']
    found = set()
    _walk_env_keys({k: v for k, v in prod.items() if k != 'cloud_run'}, found)
    _walk_env_keys(prod['cloud_run'].get('jobs', {}), found)
    services = prod['cloud_run']['services']
    for name, service in services.items():
        if service is not integration and name != PROJECTION_PUMP:
            _walk_env_keys(service, found)
    assert not found, sorted(found)
    # The projection pump derives backend-integration's env verbatim, so it carries these keys,
    # but it can never run the writer: the heartbeat runs only in the serving loop, and the
    # pump process role refuses BATCH_PIPELINE_SERVING_ENABLED=true at startup.
    pump = services[PROJECTION_PUMP]['env']
    assert _value(pump['OMI_PROCESS_ROLE']) == 'projection_pump'
    assert _value(pump['BATCH_PIPELINE_SERVING_ENABLED']) == 'false'
    with pytest.raises(ProcessRoleConfigError):
        startup_process_role({'OMI_PROCESS_ROLE': 'projection_pump', 'BATCH_PIPELINE_SERVING_ENABLED': 'true'})
    for chart in (ROOT / 'backend/charts').glob('*/prod_*_values.yaml'):
        chart_keys = set()
        _walk_env_keys(yaml.load(chart.read_text(), Loader=yaml.CSafeLoader), chart_keys)
        assert not chart_keys, (chart.name, sorted(chart_keys))

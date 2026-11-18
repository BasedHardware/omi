"""The composed prod manifest opens the backlog authority only where the runbook allows it.

A malformed value would make the heartbeat authority stop fail-closed at deploy time, so the
gate would silently never open; pin the prod values through the real parser instead.
"""

import os
from pathlib import Path

import yaml

from config.batch_pipeline_backlog_release import PREFIX, WriterConfig

ROOT = Path(__file__).resolve().parents[3]
LEGACY = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'


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
    assert len(config.owner_keys) == 4
    assert LEGACY not in env


def test_no_other_prod_role_enables_the_writer_or_the_legacy_release():
    services = _manifest()['environments']['prod']['cloud_run']['services']
    for name, service in services.items():
        if name == 'backend-integration':
            continue
        found = set()
        _walk_env_keys(service, found)
        assert not found, (name, sorted(found))
    for chart in (ROOT / 'backend/charts').glob('*/prod_*_values.yaml'):
        found = set()
        _walk_env_keys(yaml.load(chart.read_text(), Loader=yaml.CSafeLoader), found)
        assert 'BATCH_PIPELINE_BACKLOG_RELEASE_WRITER' not in found, chart
        assert LEGACY not in found, chart

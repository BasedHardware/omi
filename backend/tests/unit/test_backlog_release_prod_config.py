"""Production ships with the backlog heartbeat disabled and its gate closed."""

import os
from pathlib import Path

import yaml

from config.batch_pipeline_backlog_release import PREFIX, WriterConfig

ROOT = Path(__file__).resolve().parents[3]
LEGACY = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'


def _manifest():
    return yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)


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


def test_prod_manifest_leaves_backlog_release_settings_unset(monkeypatch):
    prod = _manifest()['environments']['prod']
    found = set()
    _walk_env_keys(prod, found)
    assert not found, sorted(found)

    for key in list(os.environ):
        if key.startswith(PREFIX):
            monkeypatch.delenv(key)
    config = WriterConfig.from_env()
    assert config.enabled is False
    assert config.state == 'closed'
    assert config.rate_per_hour == 0
    assert not config.owner_keys


def test_prod_charts_leave_backlog_release_settings_unset():
    for chart in (ROOT / 'backend/charts').glob('*/prod_*_values.yaml'):
        chart_keys = set()
        _walk_env_keys(yaml.load(chart.read_text(), Loader=yaml.CSafeLoader), chart_keys)
        assert not chart_keys, (chart.name, sorted(chart_keys))

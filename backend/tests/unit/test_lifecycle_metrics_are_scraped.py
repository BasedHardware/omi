"""Lifecycle ledger and hold metrics must survive the sync services' GMP keep rule.

Seal and summary ledger writes run on backend-sync and backend-integration. Their
families were dropped by the collector's ``__name__`` keep rule, so a failing
ledger writer could not be seen (FC-metric-dropped-by-scrape-allowlist). Names are
derived from the producer registrations so a rename fails here.
"""

import re
from pathlib import Path

import yaml
from prometheus_client import REGISTRY

import database.pipeline_ledger  # noqa: F401  Registers the ledger collectors.
from utils.sync import processing_hold

SYNC_PROFILE = Path(__file__).resolve().parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml'
PREFIXES = ('omi_pipeline_ledger_', 'omi_sync_content_arrival_gap_seconds', 'omi_sync_processing_hold')


def _kept(name, relabels):
    labels = {'__name__': name, 'component': ''}
    for rule in relabels:
        matched = re.fullmatch(rule['regex'], ';'.join(labels.get(key, '') for key in rule['sourceLabels']))
        if (rule['action'] == 'keep' and not matched) or (rule['action'] == 'drop' and matched):
            return False
    return True


def _samples():
    processing_hold._outcomes()
    processing_hold._arrival_gap()
    names = set()
    for metric in REGISTRY.collect():
        if metric.type == 'counter':
            names.add(metric.name + '_total')
        elif metric.type == 'histogram':
            names.update(metric.name + suffix for suffix in ('_bucket', '_count', '_sum'))
        else:
            names.add(metric.name)
    return {name for name in names if name.startswith(PREFIXES)}


def test_lifecycle_families_are_registered_and_kept():
    samples = _samples()
    for name in (
        'omi_pipeline_ledger_write_total',
        'omi_pipeline_ledger_write_failures_total',
        'omi_pipeline_ledger_transition_total',
        'omi_pipeline_ledger_stage_seconds_bucket',
        'omi_sync_content_arrival_gap_seconds_bucket',
        'omi_sync_processing_hold_total',
    ):
        assert name in samples, name
    relabels = yaml.safe_load(SYNC_PROFILE.read_text(encoding='utf-8'))['spec']['endpoints'][0]['metricRelabeling']
    missing = sorted(name for name in samples if not _kept(name, relabels))
    assert not missing, f'sync GMP keep rule drops {missing}'

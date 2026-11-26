"""The v3 audio purge counter must survive the backend-sync GMP keep rule.

Path E audio purges (``omi_conversations_v3_audio_purges_total{outcome}``) run on
backend-sync as well as backend. The sync sidecar keeps an explicit allow-list
instead of ``omi_.*``, so a counter missing from it reads as "no series" on Sync,
which is indistinguishable from a purge path that never ran
(FC-metric-dropped-by-scrape-allowlist).
"""

import re
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]
METRIC = 'omi_conversations_v3_audio_purges_total'


def _keep_regexes(node):
    if isinstance(node, dict):
        if node.get('action') == 'keep' and isinstance(node.get('regex'), str):
            yield node['regex']
        for value in node.values():
            yield from _keep_regexes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keep_regexes(value)


def _name_keep_regexes(path):
    docs = list(yaml.safe_load_all(path.read_text()))
    return [regex for doc in docs for regex in _keep_regexes(doc) if 'omi_' in regex]


def test_purge_counter_is_registered_with_the_expected_name():
    source = (BACKEND / 'utils/conversations/v3/metrics.py').read_text()
    assert f"'{METRIC}'" in source


def test_sync_sidecar_keeps_the_purge_counter():
    regexes = _name_keep_regexes(BACKEND / 'deploy/cloud_run_gmp_sync.yaml')
    assert regexes, 'sync sidecar has no metric-name keep rule'
    # Prometheus relabel regexes are fully anchored.
    assert any(re.fullmatch(regex, METRIC) for regex in regexes)


def test_backend_sidecar_keeps_the_purge_counter():
    regexes = _name_keep_regexes(BACKEND / 'deploy/cloud_run_gmp_sidecar.yaml')
    assert any(re.fullmatch(regex, METRIC) for regex in regexes)

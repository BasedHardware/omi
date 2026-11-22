"""Quiet-check counters must survive both Cloud Run GMP keep rules.

The arm counter is born in listen/pusher and in the finalization route; the
empty-exit counter is born only in the finalization route, which runs on
backend-sync. Neither name carries the ``omi_`` prefix, so the shared and sync
sidecar keep rules dropped them with no error and the quiet-exit rollout read
"no data" (FC-metric-dropped-by-scrape-allowlist).
"""

import re
from pathlib import Path

import pytest
import yaml
from prometheus_client import REGISTRY

from database import conversation_quiet_checks as checks  # noqa: F401  (registers the counters)

BACKEND = Path(__file__).resolve().parents[2]
PROFILES = ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml')
QUIET_CHECK_FAMILIES = {'listen_quiet_check_arm_total', 'listen_quiet_check_empty_exit_total'}


def _keep_regex(profile):
    config = yaml.safe_load((BACKEND / 'deploy' / profile).read_text(encoding='utf-8'))
    relabels = config['spec']['endpoints'][0]['metricRelabeling']
    keep = [rule for rule in relabels if rule['action'] == 'keep']
    assert len(keep) == 1, profile
    return keep[0]['regex']


def test_quiet_check_counters_are_registered():
    # prometheus_client strips the _total suffix from a Counter family name.
    emitted = {metric.name for metric in REGISTRY.collect()}
    assert {'listen_quiet_check_arm', 'listen_quiet_check_empty_exit'} <= emitted


@pytest.mark.parametrize('profile', PROFILES)
def test_quiet_check_counters_match_the_sidecar_keep_rule(profile):
    keep = _keep_regex(profile)
    for name in sorted(QUIET_CHECK_FAMILIES):
        assert re.fullmatch(keep, name), (profile, name, keep)

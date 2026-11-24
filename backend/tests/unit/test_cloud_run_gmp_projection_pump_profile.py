"""SCA-3120: the projection pump's scrape profile keeps the pump and ramp families with
revision identity, and the shared profiles stay unchanged."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'
PUMP = yaml.safe_load((DEPLOY / 'cloud_run_gmp_projection_pump.yaml').read_text())
SYNC = yaml.safe_load((DEPLOY / 'cloud_run_gmp_sync.yaml').read_text())
SOURCE = Path(__file__).resolve().parents[2] / 'utils/batch_pipeline'
PUMP_FAMILIES = (
    'omi_batch_projection_pump_last_success_seconds',
    'omi_batch_projection_pump_last_tick_seconds',
    'omi_batch_pipeline_projection_followup_outcomes_total',
)


def _keep(profile):
    rules = profile['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    return re.compile(rule['regex'])


def test_families_are_the_names_the_pump_emits():
    emitted = (SOURCE / 'metrics.py').read_text() + (SOURCE / 'projection_followup.py').read_text()
    for name in PUMP_FAMILIES:
        assert f"'{name}'" in emitted, name


@pytest.mark.parametrize('name', PUMP_FAMILIES)
def test_pump_keep_list_scrapes_each_pump_family(name):
    assert _keep(PUMP).fullmatch(name)


# Families the ramp gates and readbacks query on the pump. The profile is NOT pinned to the
# sync profile byte for byte: that made every lane editing the sync keep-list fail here.
RAMP_FAMILIES = (
    'omi_firestore_billed_reads_by_origin_total',
    'omi_firestore_billed_reads_by_caller_total',
    'omi_fsr_leader_lease_total',
    'omi_batch_leader_lease_total',
    'omi_executor_task_active',
    'omi_batch_projection_claim_busy_backoffs_total',
)


@pytest.mark.parametrize('name', RAMP_FAMILIES)
def test_pump_keep_list_scrapes_each_ramp_family(name):
    assert _keep(PUMP).fullmatch(name)


def test_pump_profile_carries_revision_identity_and_the_shared_scrape_shape():
    assert PUMP['spec']['targetLabels']['metadata'] == ['service', 'revision']
    assert 'revision' not in SYNC['spec']['targetLabels']['metadata']
    assert PUMP['metadata'] == SYNC['metadata']
    without_rules = lambda doc: {**doc['spec']['endpoints'][0], 'metricRelabeling': None}
    assert without_rules(PUMP) == without_rules(SYNC)
    assert {k: v for k, v in PUMP['spec'].items() if k not in ('endpoints', 'targetLabels')} == {
        k: v for k, v in SYNC['spec'].items() if k not in ('endpoints', 'targetLabels')
    }


def test_sync_profile_does_not_scrape_the_pump_gauges():
    for name in PUMP_FAMILIES[:2]:
        assert not _keep(SYNC).fullmatch(name)
